from __future__ import annotations

from pathlib import Path

import pytest

from tests.smoke_checks import (
    check_analyze_failed_marks_done,
    check_build_plan_hard_exclude,
    check_confidence,
    check_empty_scan_does_not_wipe,
    check_library_moods,
    check_mood_map_helpers,
    check_multi_root_empty_does_not_wipe,
    check_partial_and_symlink_scan,
    check_playback_error_auto_skips,
    check_player_ignores_outgoing_errors,
    check_nearly_finished_duration_guards,
    check_incoming_end_ignores_spurious_eom,
    check_decode_abort_helpers,
    check_sparse_mount_does_not_wipe,
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


def test_multi_root_empty_does_not_wipe(tmp_path: Path) -> None:
    check_multi_root_empty_does_not_wipe(tmp_path / "multi-root")


def test_sparse_mount_does_not_wipe(tmp_path: Path) -> None:
    check_sparse_mount_does_not_wipe(tmp_path / "sparse")


def test_playback_error_auto_skips() -> None:
    check_playback_error_auto_skips()


def test_player_ignores_outgoing_errors() -> None:
    check_player_ignores_outgoing_errors()


def test_nearly_finished_duration_guards() -> None:
    check_nearly_finished_duration_guards()


def test_incoming_end_ignores_spurious_eom() -> None:
    check_incoming_end_ignores_spurious_eom()


def test_decode_abort_helpers() -> None:
    check_decode_abort_helpers()


def test_partial_and_symlink_scan(tmp_path: Path) -> None:
    check_partial_and_symlink_scan(tmp_path / "scan-guards")


def test_analyze_failed_marks_done(tmp_path: Path) -> None:
    check_analyze_failed_marks_done(tmp_path / "fail.sqlite")


def test_build_plan_hard_exclude() -> None:
    check_build_plan_hard_exclude()


def test_mood_map_sky_drag_helpers() -> None:
    check_mood_map_helpers()
