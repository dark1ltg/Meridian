"""Host library checks for AppImage / Qt Multimedia playback."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys

# Common sonames across distros (Arch/CachyOS currently ships .165).
_LIBX264_CANDIDATES = (
    "x264",
    "libx264.so.165",
    "libx264.so.164",
    "libx264.so.163",
    "libx264.so.161",
    "libx264.so",
)


def host_libx264_available() -> bool:
    """True when the dynamic linker can load a system libx264."""
    seen: set[str] = set()
    names: list[str] = []
    found = ctypes.util.find_library("x264")
    if found:
        names.append(found)
    names.extend(_LIBX264_CANDIDATES)
    for name in names:
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            ctypes.CDLL(name)
            return True
        except OSError:
            continue
    return False


def ffmpeg_media_backend_likely() -> bool:
    """True when Qt is likely to use the FFmpeg multimedia plugin."""
    backend = (os.environ.get("QT_MEDIA_BACKEND") or "").strip().lower()
    if backend == "gstreamer":
        return False
    if backend == "ffmpeg":
        return True
    # AppImage AppRun defaults to ffmpeg; empty often still picks FFmpeg on Linux Qt builds.
    if os.environ.get("APPIMAGE") or getattr(sys, "_MEIPASS", None):
        return True
    return backend == ""


def should_warn_missing_libx264() -> bool:
    return ffmpeg_media_backend_likely() and not host_libx264_available()


def libx264_missing_message() -> str:
    return (
        "Meridian’s playback backend needs the system H.264 library "
        "<b>libx264</b>, which is not bundled (GPL-2 licence).\n\n"
        "It was not found on this computer. Without it, Qt’s FFmpeg "
        "audio backend may fail to start and playback can be broken.\n\n"
        "<b>Install libx264 from your distribution, then restart Meridian.</b>\n\n"
        "Examples:\n"
        "• Arch / CachyOS: <code>sudo pacman -S x264</code>\n"
        "• Fedora: <code>sudo dnf install x264-libs</code>\n"
        "• Debian / Ubuntu: <code>sudo apt install libx264-164</code> "
        "(package name may vary by release)\n"
    )


def libx264_missing_status() -> str:
    return "Playback may fail — install system libx264 (e.g. pacman -S x264), then restart."
