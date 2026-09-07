from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QThread

from meridian.features import (
    AUDIO_EXTS,
    analyze_audio,
    confidence_low_trust,
    genre_seed,
    mood_confidence,
    read_tags,
)
from meridian.library import Library


def _resolve(path: Path) -> Path | None:
    try:
        return path.resolve()
    except OSError:
        return None


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class ScanWorker(QObject):
    progress = Signal(str)
    finished = Signal(int)
    failed = Signal(str)

    def __init__(self, library: Library, *, force: bool = False) -> None:
        super().__init__()
        self.library = library
        self.force = force
        self._abort = False

    def abort(self) -> None:
        self._abort = True

    def run(self) -> None:
        try:
            count = self._scan()
            self.finished.emit(count)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            # Always close the finished channel so the UI can quit the QThread.
            # Negative count = failure (UI must not treat this as a successful scan).
            self.finished.emit(-1)

    def _scan(self) -> int:
        folders = self.library.folders()
        found: list[str] = []
        prune_roots: list[Path] = []
        added = 0
        now = time.time()
        for folder in folders:
            if self._abort:
                break
            root = Path(folder)
            if not root.is_dir():
                continue
            root_resolved = _resolve(root)
            if root_resolved is None:
                continue
            root_found: list[str] = []
            walk_ok = True

            def on_walk_error(_err: OSError) -> None:
                nonlocal walk_ok
                walk_ok = False

            for dirpath, dirnames, filenames in os.walk(
                root,
                onerror=on_walk_error,
                followlinks=False,
            ):
                if self._abort:
                    return added
                # Do not descend into hidden or symlink directories.
                keep_dirs: list[str] = []
                for name in dirnames:
                    if name.startswith("."):
                        continue
                    child = Path(dirpath) / name
                    if child.is_symlink():
                        continue
                    keep_dirs.append(name)
                dirnames[:] = keep_dirs
                for name in filenames:
                    path = Path(dirpath) / name
                    if path.suffix.lower() not in AUDIO_EXTS:
                        continue
                    # Skip file symlinks that escape the library root.
                    if path.is_symlink():
                        resolved = _resolve(path)
                        if resolved is None or not _is_under(resolved, root_resolved):
                            continue
                    path_str = str(path)
                    root_found.append(path_str)
                    try:
                        st = os.stat(path_str)
                    except OSError:
                        continue
                    mtime = self.library.existing_mtime(path_str)
                    if (
                        not self.force
                        and mtime is not None
                        and abs(mtime - st.st_mtime) < 0.5
                    ):
                        continue
                    self.progress.emit(name)
                    tags = read_tags(path_str)
                    seed = genre_seed(
                        tags["genre"],
                        tags["title"],
                        tags["artist"],
                        path=path_str,
                        year=tags.get("year"),
                        extra_text=tags.get("extra_text") or "",
                        albumartist=tags.get("albumartist") or "",
                        composer=tags.get("composer") or "",
                        replaygain_db=tags.get("replaygain_db"),
                    )
                    # Provisional score (no PCM yet) — same weights as analyze, pcm_ok=False.
                    bpm = tags.get("bpm")
                    conf, note = mood_confidence(
                        tag_key=seed.tag_key,
                        path_key=seed.path_key,
                        pcm_ok=False,
                        bpm_ok=bpm is not None,
                        replaygain=tags.get("replaygain_db") is not None,
                        keyword_hit=seed.keyword_hit,
                        weak_tags=path.suffix.lower() in {".wav", ".aiff", ".aif"},
                    )
                    self.library.upsert_track(
                        {
                            "path": path_str,
                            "title": tags["title"],
                            "artist": tags["artist"],
                            "album": tags["album"],
                            "albumartist": tags.get("albumartist") or "",
                            "genre": tags["genre"],
                            "duration_ms": tags["duration_ms"],
                            "year": tags["year"],
                            "bpm": tags["bpm"],
                            "valence": seed.valence,
                            "energy": seed.energy,
                            "mood_confidence": conf,
                            "confidence_note": note or "pre-analyze",
                            "low_trust": int(confidence_low_trust(conf)),
                            "added_at": now,
                            "mtime": st.st_mtime,
                            "analyzed": 0,
                        }
                    )
                    added += 1
            found.extend(root_found)
            # Only prune under roots we fully walked without errors.
            if walk_ok and not self._abort:
                prune_roots.append(root_resolved)
        # Never wipe when nothing was kept, walk aborted, or a root was incomplete.
        if found and prune_roots and not self._abort:
            self.library.delete_missing(found, only_under=prune_roots)
        return added


class AnalyzeWorker(QObject):
    progress = Signal(str, int, int)
    finished = Signal()

    def __init__(self, library: Library) -> None:
        super().__init__()
        self.library = library
        self._abort = False

    def abort(self) -> None:
        self._abort = True

    def run(self) -> None:
        try:
            ids = self.library.unanalyzed_ids()
            total = len(ids)
            for index, track_id in enumerate(ids, start=1):
                if self._abort:
                    break
                track = self.library.get(track_id)
                if not track:
                    continue
                self.progress.emit(track.short_title, index, total)
                try:
                    tags = read_tags(track.path)
                    result = analyze_audio(
                        track.path,
                        track.genre or tags.get("genre") or "",
                        track.title,
                        track.artist,
                        track.bpm if track.bpm is not None else tags.get("bpm"),
                        year=track.year if track.year is not None else tags.get("year"),
                        extra_text=tags.get("extra_text") or "",
                        albumartist=track.albumartist or tags.get("albumartist") or "",
                        composer=tags.get("composer") or "",
                        replaygain_db=tags.get("replaygain_db"),
                        duration_ms=track.duration_ms or int(tags.get("duration_ms") or 0),
                    )
                    if self._abort:
                        break
                    self.library.set_analyzed_mood(
                        track.id,
                        result.valence,
                        result.energy,
                        result.bpm,
                        confidence=result.confidence,
                        low_trust=result.low_trust,
                        confidence_note=result.confidence_note,
                    )
                except Exception:
                    # Always denylist in-process; DB mark may fail under lock contention.
                    self.library.mark_analyze_failed(track.id)
                    continue
            if not self._abort:
                self.library.smooth_album_moods()
                self.library.smooth_artist_moods()
                self.library.rescale_moods_by_percentile()
        finally:
            self.finished.emit()


def start_worker(worker: QObject, fn_name: str = "run") -> QThread:
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(getattr(worker, fn_name))
    thread.start()
    return thread
