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
            self.finished.emit(0)

    def _scan(self) -> int:
        folders = self.library.folders()
        found: list[str] = []
        added = 0
        now = time.time()
        walked_ok = False
        for folder in folders:
            root = Path(folder)
            if not root.is_dir():
                continue
            walked_ok = True
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                if self._abort:
                    return added
                for name in filenames:
                    path = str(Path(dirpath) / name)
                    if Path(name).suffix.lower() not in AUDIO_EXTS:
                        continue
                    found.append(path)
                    try:
                        st = os.stat(path)
                    except OSError:
                        continue
                    mtime = self.library.existing_mtime(path)
                    if (
                        not self.force
                        and mtime is not None
                        and abs(mtime - st.st_mtime) < 0.5
                    ):
                        continue
                    self.progress.emit(name)
                    tags = read_tags(path)
                    seed = genre_seed(
                        tags["genre"],
                        tags["title"],
                        tags["artist"],
                        path=path,
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
                        weak_tags=Path(path).suffix.lower() in {".wav", ".aiff", ".aif"},
                    )
                    self.library.upsert_track(
                        {
                            "path": path,
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
        # Never wipe the library when nothing was discovered (moved/empty folders).
        # Still prune when we successfully walked at least one folder (even if empty).
        if walked_ok and not self._abort:
            self.library.delete_missing(found)
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
                    # Poison the row so auto-restart cannot loop forever on a bad file.
                    try:
                        self.library.mark_analyze_failed(track.id)
                    except Exception:
                        pass
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
