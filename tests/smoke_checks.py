"""Shared smoke checks used by pytest and scripts/smoke_test.py."""

from __future__ import annotations

from pathlib import Path

from meridian import __version__
from meridian.features import analyze_audio, mood_confidence
from meridian.library import Library


def check_version() -> None:
    parts = __version__.split(".")
    assert len(parts) >= 2, f"unexpected version: {__version__!r}"
    assert all(p.isdigit() for p in parts[:3] if p), f"unexpected version: {__version__!r}"


def check_confidence() -> None:
    c, note = mood_confidence(tag_key="metal", pcm_ok=True, bpm_ok=True)
    assert "tag:metal" in note and "PCM" in note and c > 0.7

    c2, n2 = mood_confidence(tag_key="metal", pcm_ok=True, bpm_conflict=True)
    assert "BPM conflict" in n2 and c2 < c

    c3, n3 = mood_confidence(pcm_ok=True, pcm_unstable=True)
    c4, _ = mood_confidence(pcm_ok=True, pcm_unstable=False)
    assert "PCM weak" in n3 and c3 < c4

    result = analyze_audio("/nonexistent/x.flac", "metal", "t", "a", 140.0)
    assert result.confidence_note and result.confidence >= 0


def _seed_library(lib: Library, n: int = 16) -> None:
    for i in range(n):
        lib.upsert_track(
            {
                "path": f"/m/{i}.mp3",
                "title": f"t{i}",
                "artist": "Band",
                "albumartist": "Band",
                "album": "LP",
                "genre": "Metal",
                "duration_ms": 1,
                "year": None,
                "bpm": 120,
                "valence": 0.2 + i * 0.04,
                "energy": 0.3 + (i % 5) * 0.1,
                "mood_confidence": 0.85 if i < 12 else 0.25,
                "confidence_note": "seed",
                "low_trust": 0 if i < 12 else 1,
                "added_at": 0,
                "mtime": 0,
                "analyzed": 1,
            }
        )


def check_library_moods(db_path: Path) -> None:
    lib = Library(db_path)
    try:
        _seed_library(lib)
        lib.set_mood(1, 0.99, 0.99, pinned=True)
        pin_v = lib.get(1).valence
        assert lib.get(1).pinned and lib.get(1).mood_confidence == 1.0

        # Rescan-style upsert must not strip pin confidence.
        lib.upsert_track(
            {
                "path": "/m/0.mp3",
                "title": "t0",
                "artist": "Band",
                "albumartist": "Band",
                "album": "LP",
                "genre": "Metal",
                "duration_ms": 1,
                "year": None,
                "bpm": 120,
                "valence": 0.1,
                "energy": 0.1,
                "mood_confidence": 0.2,
                "confidence_note": "pre-analyze",
                "low_trust": 1,
                "added_at": 999,
                "mtime": 1,
                "analyzed": 0,
            }
        )
        pinned = lib.get(1)
        assert abs(pinned.valence - pin_v) < 1e-9
        assert pinned.mood_confidence == 1.0
        assert pinned.confidence_note == "pinned"
        assert pinned.analyzed

        n_smooth = lib.smooth_album_moods()
        assert n_smooth >= 0
        assert any("album smooth" in (t.confidence_note or "") for t in lib.all_tracks())

        n_sc = lib.rescale_moods_by_percentile(min_group=8)
        assert abs(lib.get(1).valence - pin_v) < 1e-9, "pin moved by rescale"
        assert n_sc > 0
        assert any(
            "relative rescale" in (t.confidence_note or "")
            for t in lib.all_tracks()
            if not t.pinned
        )

        tid = next(t.id for t in lib.all_tracks() if not t.pinned)
        before = lib.get(tid).mood_confidence
        lib.nudge_mood_from_listen(tid, lens_x=0.9, lens_y=0.9, skipped=False)
        after = lib.get(tid)
        assert after.mood_confidence >= before - 1e-9
        assert "listen finish" in (after.confidence_note or "")

        lib.nudge_mood_from_listen(tid, lens_x=0.1, lens_y=0.1, skipped=True)
        assert "listen skip" in (lib.get(tid).confidence_note or "")

        assert lib.nudge_mood_from_listen(1, lens_x=0.1, lens_y=0.1, skipped=False) is False
        assert abs(lib.get(1).valence - pin_v) < 1e-9

        lib.set_analyzed_mood(
            1, 0.11, 0.22, 90.0, confidence=0.2, low_trust=True, confidence_note="overwrite?"
        )
        t1 = lib.get(1)
        assert abs(t1.valence - pin_v) < 1e-9 and t1.pinned and t1.mood_confidence == 1.0
        assert t1.bpm == 120.0  # pinned BPM must not be overwritten
    finally:
        lib.close()


def check_empty_scan_does_not_wipe(db_path: Path) -> None:
    from meridian.scanner import ScanWorker

    lib = Library(db_path)
    try:
        _seed_library(lib, n=4)
        assert len(lib.all_tracks()) == 4
        lib.add_folder("/nonexistent/meridian-empty-scan-guard")
        worker = ScanWorker(lib, force=False)
        added = worker._scan()
        assert added == 0
        assert len(lib.all_tracks()) == 4, "empty/missing folders must not wipe library"

        # Existing but empty folder must also keep prior rows (no delete_missing wipe).
        empty = db_path.parent / "empty-music-root"
        empty.mkdir(parents=True, exist_ok=True)
        lib.add_folder(str(empty))
        added = ScanWorker(lib, force=False)._scan()
        assert added == 0
        assert len(lib.all_tracks()) == 4, "empty existing folder must not wipe library"
    finally:
        lib.close()


def check_partial_and_symlink_scan(tmp_dir: Path) -> None:
    from meridian.scanner import ScanWorker

    db_path = tmp_dir / "partial.sqlite"
    music = tmp_dir / "music"
    visible = music / "ok"
    blocked = music / "blocked"
    visible.mkdir(parents=True)
    blocked.mkdir(parents=True)
    (visible / "keep.mp3").write_bytes(b"ID3")
    (blocked / "hidden.mp3").write_bytes(b"ID3")

    outside = tmp_dir / "outside"
    outside.mkdir()
    (outside / "leak.mp3").write_bytes(b"ID3")
    leak_link = visible / "leak-link.mp3"
    leak_link.symlink_to(outside / "leak.mp3")

    lib = Library(db_path)
    try:
        # Seed a track under the blocked subtree so a partial walk must not delete it.
        lib.upsert_track(
            {
                "path": str(blocked / "hidden.mp3"),
                "title": "hidden",
                "artist": "Band",
                "albumartist": "Band",
                "album": "LP",
                "genre": "Metal",
                "duration_ms": 1,
                "year": None,
                "bpm": 120,
                "valence": 0.5,
                "energy": 0.5,
                "mood_confidence": 0.5,
                "confidence_note": "seed",
                "low_trust": 0,
                "added_at": 0,
                "mtime": 0,
                "analyzed": 1,
            }
        )
        lib.add_folder(str(music))
        blocked.chmod(0o000)
        try:
            ScanWorker(lib, force=False)._scan()
        finally:
            blocked.chmod(0o755)
        paths = {t.path for t in lib.all_tracks()}
        assert str(blocked / "hidden.mp3") in paths, "partial/unreadable tree must not prune"
        assert str(leak_link) not in paths, "out-of-root file symlink must be ignored"
        # only_under: tracks outside pruned roots stay
        other = tmp_dir / "other-lib" / "song.mp3"
        other.parent.mkdir(parents=True)
        other.write_bytes(b"ID3")
        lib.upsert_track(
            {
                "path": str(other),
                "title": "other",
                "artist": "Band",
                "albumartist": "Band",
                "album": "LP",
                "genre": "Metal",
                "duration_ms": 1,
                "year": None,
                "bpm": 120,
                "valence": 0.5,
                "energy": 0.5,
                "mood_confidence": 0.5,
                "confidence_note": "seed",
                "low_trust": 0,
                "added_at": 0,
                "mtime": 0,
                "analyzed": 1,
            }
        )
        lib.delete_missing([str(visible / "keep.mp3")], only_under=[music.resolve()])
        paths = {t.path for t in lib.all_tracks()}
        assert str(other) in paths, "delete_missing must not touch paths outside only_under"
    finally:
        try:
            blocked.chmod(0o755)
        except OSError:
            pass
        lib.close()


def check_analyze_failed_marks_done(db_path: Path) -> None:
    lib = Library(db_path)
    try:
        _seed_library(lib, n=2)
        tid = lib.all_tracks()[0].id
        lib.conn.execute("UPDATE tracks SET analyzed = 0 WHERE id = ?", (tid,))
        lib.conn.commit()
        lib.mark_analyze_failed(tid)
        t = lib.get(tid)
        assert t is not None and t.analyzed
        assert "analyze failed" in (t.confidence_note or "")
        assert tid not in lib.unanalyzed_ids()

        # Even if the DB row is forced back to pending, process denylist blocks the poison loop.
        lib.conn.execute("UPDATE tracks SET analyzed = 0 WHERE id = ?", (tid,))
        lib.conn.commit()
        assert tid not in lib.unanalyzed_ids()

        # Proper upsert reset (scan re-queue) clears the sticky denylist entry.
        row = lib.get(tid)
        lib.upsert_track(
            {
                "path": row.path,
                "title": row.title,
                "artist": row.artist,
                "albumartist": row.albumartist,
                "album": row.album,
                "genre": row.genre,
                "duration_ms": row.duration_ms,
                "year": row.year,
                "bpm": row.bpm,
                "valence": row.valence,
                "energy": row.energy,
                "mood_confidence": row.mood_confidence,
                "confidence_note": row.confidence_note or "",
                "low_trust": int(row.low_trust),
                "analyzed": 0,
                "mtime": row.mtime,
                "added_at": row.added_at,
            }
        )
        assert tid not in lib._analyze_denylist
        assert tid in lib.unanalyzed_ids()
    finally:
        lib.close()


def check_build_plan_hard_exclude() -> None:
    from meridian.context import Mode, make_context
    from meridian.library import Track
    from meridian.queue_engine import build_plan

    def t(i: int) -> Track:
        return Track(
            id=i,
            path=f"/m/{i}.mp3",
            title=f"t{i}",
            artist="Band",
            album="LP",
            albumartist="Band",
            genre="Metal",
            duration_ms=1000,
            year=None,
            bpm=120.0,
            valence=0.5,
            energy=0.5,
            mood_confidence=0.8,
            confidence_note="seed",
            low_trust=False,
            pinned=False,
            loved=False,
            play_count=0,
            skip_count=0,
            last_played=None,
            added_at=0.0,
            mtime=0.0,
            analyzed=True,
        )

    tracks = [t(1), t(2), t(3)]
    ctx = make_context(Mode.WANDER, 0.5, 0.5, 0.25, 0.0)
    plan = build_plan(tracks, ctx, [], exclude_ids={1}, hard_exclude_ids={1})
    assert 1 not in plan.order, "hard_exclude must keep the just-finished track out"
    solo = build_plan([t(1)], ctx, [], hard_exclude_ids={1})
    assert solo.order == [], "single-track hard_exclude must not refill with itself"


def check_mood_map_helpers() -> None:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QPointF

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    from meridian.ui.mood_map import (
        HIT_RADIUS_SKY,
        HIT_RADIUS_SKY_GRAB,
        LIVE_STARS_ZOOM,
        MoodMap,
    )
    from meridian.context import LENS_RADIUS_DEFAULT
    from meridian.queue_engine import Quadrant
    from types import SimpleNamespace

    m = MoodMap()
    assert hasattr(m, "_ensure_interactive_star")
    assert hasattr(m, "_sky_hold_id")
    assert hasattr(m, "_drag_locked_ids")
    assert hasattr(m, "set_radius_scale")
    assert hasattr(m, "_field_signature")
    assert hasattr(m, "_track_star_from_item")
    assert LIVE_STARS_ZOOM == 2.4
    assert HIT_RADIUS_SKY >= 10
    assert HIT_RADIUS_SKY_GRAB < HIT_RADIUS_SKY
    assert m.lens.zValue() < 7, "lens must sit under live stars for hit-testing"
    assert m._ensure_interactive_star(999) is None

    # Lens ellipse matches mood radius on map axes (and mode scale).
    m.set_radius_scale(1.0)
    m.set_lens(0.5, 0.5, LENS_RADIUS_DEFAULT)
    rx = m.lens.rect().width() / 2
    ry = m.lens.rect().height() / 2
    assert abs(rx - LENS_RADIUS_DEFAULT * 720) < 0.5
    assert abs(ry - LENS_RADIUS_DEFAULT * 524) < 0.5
    m.set_radius_scale(0.78)
    assert abs(m.lens.rect().width() / 2 - LENS_RADIUS_DEFAULT * 0.78 * 720) < 0.5

    # Mid-drag set_tracks must not wipe the held star position.
    track = SimpleNamespace(
        id=1,
        valence=0.2,
        energy=0.8,
        label="T",
        loved=False,
        pinned=False,
        mood_confidence=0.9,
        confidence_note="",
    )
    ranked = SimpleNamespace(track=track, quadrant=Quadrant.NOW, fit=1.0, importance=1.0)
    m.set_tracks([ranked], None)
    star = m._ensure_interactive_star(1)
    assert star is not None
    drag = QPointF(600.0, 250.0)
    star.setPos(drag)
    m._positions[1] = QPointF(drag)
    m._sky_hold_id = 1
    m.set_tracks([ranked], None)
    assert abs(m._stars[1].pos().x() - 600.0) < 0.5
    assert abs(m._positions[1].x() - 600.0) < 0.5

    # Sky candidate (press before drag) must also survive set_tracks.
    m._sky_hold_id = None
    m._sky_candidate_id = 1
    star.setPos(QPointF(610.0, 260.0))
    m._positions[1] = QPointF(610.0, 260.0)
    assert 1 in m._drag_locked_ids()
    m.set_tracks([ranked], None)
    assert abs(m._positions[1].x() - 610.0) < 0.5
    m._sky_candidate_id = None

    # Identical set_tracks must not allocate a new starfield pixmap.
    m.set_tracks([ranked], None)  # settle positions from mood coords
    pix0 = m._field.pixmap()
    key0 = pix0.cacheKey()
    m.set_tracks([ranked], None)
    assert m._field.pixmap().cacheKey() == key0

    # Backdrop rebuild must not leak chrome items.
    n0 = len(m._sky_chrome)
    m._draw_backdrop()
    assert len(m._sky_chrome) == n0


def run_all_smoke_checks(tmp_dir: Path) -> None:
    """Run every smoke check (used by scripts/smoke_test.py)."""
    check_version()
    check_confidence()
    check_library_moods(tmp_dir / "smoke.sqlite")
    check_empty_scan_does_not_wipe(tmp_dir / "wipe.sqlite")
    check_partial_and_symlink_scan(tmp_dir / "scan-guards")
    check_analyze_failed_marks_done(tmp_dir / "fail.sqlite")
    check_build_plan_hard_exclude()
    check_mood_map_helpers()
