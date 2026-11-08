"""Host dependency helpers (libx264 / ffmpeg warnings for AppImage)."""

from __future__ import annotations

from meridian.host_deps import (
    ffmpeg_media_backend_likely,
    ffmpeg_missing_message,
    host_ffmpeg_available,
    should_warn_missing_ffmpeg,
    should_warn_missing_libx264,
)
from meridian.host_deps import libx264_missing_message


def test_libx264_message_mentions_install() -> None:
    msg = libx264_missing_message()
    assert "libx264" in msg
    assert "pacman" in msg


def test_ffmpeg_message_mentions_install() -> None:
    msg = ffmpeg_missing_message()
    assert "ffmpeg" in msg.lower()
    assert "pacman" in msg


def test_should_warn_respects_gstreamer(monkeypatch) -> None:
    monkeypatch.setenv("QT_MEDIA_BACKEND", "gstreamer")
    monkeypatch.delenv("APPIMAGE", raising=False)
    # Even if x264 is missing, gstreamer backend should not warn.
    monkeypatch.setattr("meridian.host_deps.host_libx264_available", lambda: False)
    assert should_warn_missing_libx264() is False


def test_should_warn_when_ffmpeg_and_missing(monkeypatch) -> None:
    monkeypatch.setenv("QT_MEDIA_BACKEND", "ffmpeg")
    monkeypatch.setattr("meridian.host_deps.host_libx264_available", lambda: False)
    assert should_warn_missing_libx264() is True
    monkeypatch.setattr("meridian.host_deps.host_libx264_available", lambda: True)
    assert should_warn_missing_libx264() is False


def test_ffmpeg_backend_appimage_default(monkeypatch) -> None:
    monkeypatch.delenv("QT_MEDIA_BACKEND", raising=False)
    monkeypatch.setenv("APPIMAGE", "/tmp/Meridian.AppImage")
    assert ffmpeg_media_backend_likely() is True


def test_should_warn_missing_ffmpeg_cli(monkeypatch) -> None:
    monkeypatch.setattr("meridian.host_deps.shutil.which", lambda _n: None)
    assert host_ffmpeg_available() is False
    assert should_warn_missing_ffmpeg() is True
    monkeypatch.setattr("meridian.host_deps.shutil.which", lambda _n: "/usr/bin/ffmpeg")
    assert host_ffmpeg_available() is True
    assert should_warn_missing_ffmpeg() is False


def test_packaging_builds_aubio_without_distro_ffmpeg() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    recipe = (root / "packaging" / "build-appimage-ubuntu2404.sh").read_text(encoding="utf-8")
    audit = (root / "packaging" / "build-appimage.sh").read_text(encoding="utf-8")
    assert "libavcodec*" in recipe
    assert "'fftw3f'" in recipe
    assert "libaubio-dev" not in recipe
    assert "libx264" in audit
    assert "aubio still linked to distro ffmpeg" in audit
