"""Regression tests for bug-hunt scores 8/7/6 (Rescan wipe, matrix pull, zoom, ffmpeg warn)."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MERIDIAN_NO_GL", "1")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from meridian.host_deps import (
    ffmpeg_missing_message,
    ffmpeg_missing_status,
    host_ffmpeg_available,
    should_warn_missing_ffmpeg,
)
from meridian.library import Library
from meridian.ui.main_window import MainWindow
from meridian.ui.mood_map import VIEW_ZOOM_MAX, MoodMap


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_rescan_order_preserves_pcm_coords(tmp_path: Path) -> None:
    lib = Library(tmp_path / "rescan.sqlite")
    try:
        lib.upsert_track(
            {
                "path": "/t/a.mp3",
                "title": "a",
                "artist": "A",
                "album": "L",
                "genre": "Rock",
                "duration_ms": 1,
                "year": None,
                "bpm": None,
                "valence": 0.91,
                "energy": 0.12,
                "mood_confidence": 0.85,
                "confidence_note": "pcm",
                "low_trust": 0,
                "added_at": 0,
                "mtime": 1,
                "analyzed": 1,
            }
        )
        lib.set_analyzed_mood(
            1, 0.91, 0.12, None, confidence=0.85, brightness=0.7, acoustic_flux=0.3
        )
        lib.mark_all_pending_analysis()
        lib.upsert_track(
            {
                "path": "/t/a.mp3",
                "title": "a",
                "artist": "A",
                "album": "L",
                "genre": "Rock",
                "duration_ms": 1,
                "year": None,
                "bpm": None,
                "valence": 0.42,
                "energy": 0.67,
                "mood_confidence": 0.25,
                "confidence_note": "seed",
                "low_trust": 1,
                "added_at": 0,
                "mtime": 2,
                "analyzed": 0,
            }
        )
        t = lib.get(1)
        assert t is not None
        assert abs(t.valence - 0.91) < 1e-9
        assert abs(t.energy - 0.12) < 1e-9
        assert not t.analyzed
    finally:
        lib.close()


def test_pull_and_play_current_track_does_not_strand_queue(qapp) -> None:
    w = MainWindow.__new__(MainWindow)
    w.session_queue = [1, 2, 3, 4]
    w.queue_index = 0
    w.ephemeral = set()
    w.explicit = []
    w.player = MagicMock()
    w.player.current = SimpleNamespace(id=1)
    played: list[int] = []
    w.play_id = lambda tid: played.append(tid)  # type: ignore[method-assign]

    MainWindow._pull_and_play(w, 1)

    assert w.session_queue == [1, 2, 3, 4]
    assert w.queue_index == 0
    assert w.ephemeral == set()
    assert played == [1]


def test_pull_and_play_other_track_still_inserts(qapp) -> None:
    w = MainWindow.__new__(MainWindow)
    w.session_queue = [1, 2, 3]
    w.queue_index = 0
    w.ephemeral = set()
    w.explicit = []
    w.player = MagicMock()
    w.player.current = SimpleNamespace(id=1)
    played: list[int] = []
    w.play_id = lambda tid: played.append(tid)  # type: ignore[method-assign]

    MainWindow._pull_and_play(w, 9)

    assert w.session_queue == [1, 9, 2, 3]
    assert w.queue_index == 1
    assert 9 in w.ephemeral
    assert played == [9]


def test_zoom_past_ceiling_schedules_lod(qapp) -> None:
    m = MoodMap()

    class FakeStar:
        def __init__(self) -> None:
            self._shown = True
            self._press_scene = None

        def show(self) -> None:
            self._shown = True

        def hide(self) -> None:
            self._shown = False

    star = FakeStar()
    m._stars = {1: star}
    m._user_zoom = VIEW_ZOOM_MAX
    m._zoom_target = VIEW_ZOOM_MAX
    m._zoom_active = False
    m._sync_live_stars = lambda force=False: star.show()  # type: ignore[method-assign]
    m._set_zoom_target(VIEW_ZOOM_MAX * 1.06, QPoint(10, 10))
    assert m._zoom_active is True
    assert star._shown is False
    assert m._lod_timer.isActive() is True
    m._flush_zoom_lod()
    assert m._zoom_active is False
    assert star._shown is True


def test_ffmpeg_missing_warning_helpers(monkeypatch) -> None:
    monkeypatch.setattr("meridian.host_deps.shutil.which", lambda _name: None)
    assert host_ffmpeg_available() is False
    assert should_warn_missing_ffmpeg() is True
    assert "ffmpeg" in ffmpeg_missing_message().lower()
    assert "ffmpeg" in ffmpeg_missing_status().lower()

    monkeypatch.setattr("meridian.host_deps.shutil.which", lambda _name: "/usr/bin/ffmpeg")
    assert host_ffmpeg_available() is True
    assert should_warn_missing_ffmpeg() is False
