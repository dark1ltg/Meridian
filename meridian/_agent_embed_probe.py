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

# Real file continues — this probe checks whether ~2KB embeds survive MCP.
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

PROBE_OK = True
