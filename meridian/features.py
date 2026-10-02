from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from mutagen import File as MutagenFile
from mutagen.id3 import ID3NoHeaderError

AUDIO_EXTS = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wav", ".aac", ".wma", ".aiff"}

GENRE_MOOD: dict[str, tuple[float, float]] = {
    "ambient": (0.42, 0.18),
    "classical": (0.48, 0.28),
    "jazz": (0.55, 0.38),
    "blues": (0.32, 0.36),
    "soul": (0.58, 0.45),
    "r&b": (0.60, 0.48),
    "hip hop": (0.52, 0.62),
    "rap": (0.48, 0.68),
    "rock": (0.46, 0.72),
    "metal": (0.28, 0.88),
    "punk": (0.34, 0.86),
    "electronic": (0.56, 0.74),
    "edm": (0.62, 0.86),
    "techno": (0.40, 0.84),
    "house": (0.66, 0.78),
    "pop": (0.72, 0.58),
    "indie": (0.54, 0.50),
    "folk": (0.50, 0.34),
    "country": (0.58, 0.44),
    "reggae": (0.64, 0.46),
    "lofi": (0.46, 0.22),
    "lo-fi": (0.46, 0.22),
    "soundtrack": (0.50, 0.40),
    "video game": (0.52, 0.46),
    "game": (0.52, 0.46),
    "score": (0.50, 0.40),
    "ost": (0.50, 0.40),
    "vgm": (0.52, 0.46),
}

GENRE_MOOD = {k.lower(): v for k, v in GENRE_MOOD.items()}

# NOTE: truncated GENRE_MOOD aliases omitted in this emergency restore attempt — DO NOT MERGE
# This is intentionally incomplete; used only to test ~3KB upload ceiling.

def _close_decode_pipes(proc: subprocess.Popen) -> None:
    """Close stdout/stderr PIPEs so timeout/abort cannot leak FDs."""
    for stream in (proc.stdout, proc.stderr):
        if stream is None:
            continue
        try:
            if getattr(stream, "closed", False):
                continue
            stream.close()
        except (OSError, ValueError):
            pass


def _decode_pcm(path: str, *, start_s: float = 12.0, duration_s: float = 28.0):
    global _decode_pcm_calls, _decode_proc
    return None  # incomplete probe

_decode_pcm_calls = 0
_decode_abort = False
_decode_proc = None
_decode_proc_lock = threading.Lock()
