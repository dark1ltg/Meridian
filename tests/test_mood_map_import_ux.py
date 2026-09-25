"""Tests for scan-time seed scatter, density bake, and sticky job status."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def test_genre_seed_path_jitter_distinct_coords() -> None:
    """Same genre + distinct paths must not collapse to identical seed coords."""
    from meridian.features import genre_seed

    genre = "Soundtrack"
    title = "Theme"
    artist = "Composer"
    a = genre_seed(genre, title, artist, path="/music/OCR/game_a/track_01.mp3")
    b = genre_seed(genre, title, artist, path="/music/OCR/game_b/track_02.mp3")
    c = genre_seed(genre, title, artist, path="/music/OCR/game_c/track_03.mp3")
    coords = {(round(s.valence, 5), round(s.energy, 5)) for s in (a, b, c)}
    assert len(coords) == 3
    # Stable across calls for the same path.
    a2 = genre_seed(genre, title, artist, path="/music/OCR/game_a/track_01.mp3")
    assert abs(a.valence - a2.valence) < 1e-12
    assert abs(a.energy - a2.energy) < 1e-12
    # Stay inside a genre neighborhood (not flung across the whole map).
    for s in (a, b, c):
        assert abs(s.valence - a.valence) < 0.15
        assert abs(s.energy - a.energy) < 0.15


def test_scan_upsert_applies_seed_jitter(tmp_path: Path) -> None:
    """Scan upserts must persist non-identical coords for shared-genre files."""
    from meridian.library import Library
    from meridian.scanner import ScanWorker

    root = tmp_path / "ost"
    root.mkdir()
    for i in range(8):
        (root / f"track_{i:02d}.mp3").write_bytes(b"ID3")

    db = tmp_path / "lib.sqlite"
    lib = Library(db)
    try:
        lib.add_folder(str(root))
        # Force tag-less genre via empty files; path keywords still seed soundtrack/ost.
        added = ScanWorker(lib, force=True)._scan()
        assert added == 8
        tracks = lib.all_tracks()
        assert len(tracks) == 8
        coords = {(round(t.valence, 5), round(t.energy, 5)) for t in tracks}
        assert len(coords) >= 6, f"expected scatter, got {coords}"
    finally:
        lib.close()


def test_mood_map_plots_full_ranked_set_and_density_bake() -> None:
    """Large identical-mood ranked set still plots fully; bake keeps readable radius."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    from meridian.queue_engine import Quadrant
    from meridian.ui.mood_map import MoodMap

    m = MoodMap()
    ranked = []
    for i in range(3000):
        track = SimpleNamespace(
            id=i + 1,
            valence=0.52,
            energy=0.46,
            label=f"T{i}",
            loved=False,
            pinned=False,
            mood_confidence=0.35,
            confidence_note="pre-analyze",
        )
        ranked.append(
            SimpleNamespace(
                track=track,
                quadrant=Quadrant.SHELF,
                fit=1.0,
                importance=1.0,
            )
        )
    m.set_tracks(ranked, None)
    assert len(m._ranked) == 3000
    assert len(m._positions) == 3000
    # Density underlay + floor radius: bake must produce a non-null field pixmap.
    pix = m._field.pixmap()
    assert not pix.isNull()
    assert pix.width() > 0 and pix.height() > 0


def test_scan_progress_includes_folder_and_scanning_verb(tmp_path: Path) -> None:
    """Regression for L1: progress must include Scanning + folder, not Found {basename}."""
    from meridian.library import Library
    from meridian.scanner import ScanWorker

    root = tmp_path / "MusicLib"
    root.mkdir()
    (root / "song.mp3").write_bytes(b"ID3")
    messages: list[str] = []
    lib = Library(tmp_path / "scan-progress.sqlite")
    try:
        lib.add_folder(str(root))
        worker = ScanWorker(lib, force=True)
        worker.progress.connect(messages.append)
        assert worker._scan() == 1
    finally:
        lib.close()
    assert messages, "scan must emit progress"
    assert any("Scanning" in m and "MusicLib" in m for m in messages)
    assert not any(m.startswith("Found ") for m in messages)


def test_sticky_job_status_survives_hover() -> None:
    """Hover / ephemeral _set_status must not clear an active job line."""
    from PySide6.QtWidgets import QApplication, QLabel

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    from meridian.ui.main_window import MainWindow

    w = MainWindow.__new__(MainWindow)
    w._host_codec_sticky = False
    w._job_status = None
    w.status_label = QLabel()
    # Bind real methods.
    w._paint_status = MainWindow._paint_status.__get__(w, MainWindow)
    w._set_job_status = MainWindow._set_job_status.__get__(w, MainWindow)
    w._clear_job_status = MainWindow._clear_job_status.__get__(w, MainWindow)
    w._set_status = MainWindow._set_status.__get__(w, MainWindow)

    w._set_job_status("Scanning Music: a.mp3 · indexed 3")
    assert "Scanning" in w.status_label.text()
    w._set_status("Archangel — Paladin's Quest OC ReMix")
    assert "Scanning" in w.status_label.text()
    assert "Archangel" not in w.status_label.text()
    w._clear_job_status()
    w._set_status("Archangel — Paladin's Quest OC ReMix")
    assert "Archangel" in w.status_label.text()


def test_plan_ranked_matches_playable_after_scan(tmp_path: Path) -> None:
    """After a mock scan, classify/build_plan ranked length equals playable count."""
    from meridian.context import LENS_RADIUS_DEFAULT, Mode, make_context
    from meridian.library import Library
    from meridian.queue_engine import build_plan
    from meridian.scanner import ScanWorker

    root = tmp_path / "mix"
    root.mkdir()
    for i in range(12):
        (root / f"song_{i:02d}.flac").write_bytes(b"fLaC")

    db = tmp_path / "plan.sqlite"
    lib = Library(db)
    try:
        lib.add_folder(str(root))
        assert ScanWorker(lib, force=True)._scan() == 12
        tracks = lib.all_tracks()
        ctx = make_context(Mode.WANDER, 0.5, 0.5, LENS_RADIUS_DEFAULT, 0.0)
        plan = build_plan(tracks, ctx, [])
        assert len(plan.ranked) == len(tracks) == 12
    finally:
        lib.close()
