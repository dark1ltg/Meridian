from __future__ import annotations

from pathlib import Path

import pytest

from tests.smoke_checks import (
    check_analyze_failed_marks_done,
    check_confidence,
    check_empty_scan_does_not_wipe,
    check_library_moods,
    check_mood_map_helpers,
    check_version,
)


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "library.sqlite"


def test_version() -> None:
    check_version()


def test_confidence_scoring_and_notes() -> None:
    check_confidence()


def test_smooth_rescale_pin_and_listen_nudge(tmp_db: Path) -> None:
    check_library_moods(tmp_db)


def test_empty_scan_does_not_wipe_library(tmp_path: Path) -> None:
    check_empty_scan_does_not_wipe(tmp_path / "wipe.sqlite")


def test_analyze_failed_marks_done(tmp_path: Path) -> None:
    check_analyze_failed_marks_done(tmp_path / "fail.sqlite")


def test_mood_map_sky_drag_helpers() -> None:
    check_mood_map_helpers()
