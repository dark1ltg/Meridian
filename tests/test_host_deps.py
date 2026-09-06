"""Host dependency helpers (libx264 warning for AppImage playback)."""

from __future__ import annotations

from meridian.host_deps import (
    ffmpeg_media_backend_likely,
    host_libx264_available,
    libx264_missing_message,
    should_warn_missing_libx264,
)


def test_libx264_message_mentions_install() -> None:
    msg = libx264_missing_message()
    assert "libx264" in msg
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
