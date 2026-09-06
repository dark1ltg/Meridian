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
    finally:
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
    finally:
        lib.close()


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
    assert LIVE_STARS_ZOOM == 2.4
    assert HIT_RADIUS_SKY >= 10
    assert HIT_RADIUS_SKY_GRAB < HIT_RADIUS_SKY
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
    check_analyze_failed_marks_done(tmp_dir / "fail.sqlite")
    check_mood_map_helpers()
