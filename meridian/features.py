from __future__ import annotations

import re
import shutil
import subprocess
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
}

WORD_VALENCE = {
    "sad": -0.28,
    "blue": -0.18,
    "dark": -0.22,
    "night": -0.10,
    "rain": -0.12,
    "lonely": -0.24,
    "grief": -0.30,
    "love": 0.22,
    "sun": 0.18,
    "happy": 0.26,
    "joy": 0.24,
    "light": 0.12,
    "dream": 0.08,
    "hope": 0.16,
    "war": -0.16,
    "rage": -0.12,
    "party": 0.20,
    "chill": 0.04,
}

WORD_ENERGY = {
    "slow": -0.22,
    "chill": -0.18,
    "sleep": -0.28,
    "ambient": -0.20,
    "ballad": -0.16,
    "fast": 0.22,
    "run": 0.18,
    "fire": 0.16,
    "rage": 0.24,
    "war": 0.18,
    "club": 0.22,
    "banger": 0.26,
    "live": 0.12,
    "acoustic": -0.14,
}


def _text(tag) -> str:
    if tag is None:
        return ""
    if isinstance(tag, list):
        return str(tag[0]) if tag else ""
    return str(tag)


def read_tags(path: str) -> dict:
    info = {
        "title": Path(path).stem,
        "artist": "",
        "album": "",
        "genre": "",
        "year": None,
        "bpm": None,
        "duration_ms": 0,
    }
    try:
        audio = MutagenFile(path, easy=True)
    except (ID3NoHeaderError, Exception):
        return info
    if audio is None:
        return info
    info["title"] = _text(audio.get("title")) or info["title"]
    info["artist"] = _text(audio.get("artist"))
    info["album"] = _text(audio.get("album"))
    info["genre"] = _text(audio.get("genre"))
    date = _text(audio.get("date") or audio.get("year"))
    if date:
        match = re.search(r"(\d{4})", date)
        if match:
            info["year"] = int(match.group(1))
    bpm = _text(audio.get("bpm"))
    if bpm:
        try:
            info["bpm"] = float(str(bpm).split()[0])
        except ValueError:
            pass
    length = getattr(audio.info, "length", None)
    if length:
        info["duration_ms"] = int(length * 1000)
    return info


def _keyword_shift(text: str) -> tuple[float, float]:
    blob = text.lower()
    dv = de = 0.0
    for word, delta in WORD_VALENCE.items():
        if word in blob:
            dv += delta
    for word, delta in WORD_ENERGY.items():
        if word in blob:
            de += delta
    return dv, de


def genre_seed(genre: str, title: str, artist: str) -> tuple[float, float]:
    g = (genre or "").lower()
    valence, energy = 0.5, 0.48
    for key, pair in GENRE_MOOD.items():
        if key in g:
            valence, energy = pair
            break
    dv, de = _keyword_shift(f"{title} {artist} {genre}")
    return (
        float(np.clip(valence + dv, 0.03, 0.97)),
        float(np.clip(energy + de, 0.03, 0.97)),
    )


def _decode_pcm(path: str) -> np.ndarray | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-ss",
        "12",
        "-t",
        "28",
        "-i",
        path,
        "-ac",
        "1",
        "-ar",
        "11025",
        "-f",
        "f32le",
        "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False, timeout=20)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    pcm = np.frombuffer(proc.stdout, dtype=np.float32)
    if pcm.size < 2048:
        return None
    return pcm


def _aubio_rhythm(pcm: np.ndarray, samplerate: int = 11025) -> tuple[float | None, float]:
    """Return (bpm_or_None, kinetic_from_onsets in 0..1). Soft-fails if aubio is missing."""
    try:
        import aubio
    except ImportError:
        return None, 0.5

    win_s = 512
    hop_s = 256
    if pcm.size < hop_s * 4:
        return None, 0.5

    mono = np.ascontiguousarray(pcm, dtype=np.float32)
    tempo_o = aubio.tempo("default", win_s, hop_s, samplerate)
    onset_o = aubio.onset("default", win_s, hop_s, samplerate)
    onsets = 0
    for i in range(0, mono.size - hop_s + 1, hop_s):
        frame = mono[i : i + hop_s]
        if onset_o(frame):
            onsets += 1
        tempo_o(frame)

    duration_s = max(mono.size / float(samplerate), 1e-3)
    onset_rate = onsets / duration_s  # onsets per second
    # ~0.5/s calm → ~4/s very kinetic
    kinetic = float(np.clip((onset_rate - 0.35) / 3.4, 0.05, 0.95))

    bpm = float(tempo_o.get_bpm())
    if not np.isfinite(bpm) or bpm < 40.0 or bpm > 220.0:
        bpm_out: float | None = None
    else:
        bpm_out = bpm
    return bpm_out, kinetic


def analyze_audio(path: str, genre: str, title: str, artist: str, bpm: float | None) -> tuple[float, float, float | None]:
    valence, energy = genre_seed(genre, title, artist)
    detected_bpm: float | None = None
    pcm = _decode_pcm(path)
    if pcm is not None:
        rms = float(np.sqrt(np.mean(np.square(pcm))))
        energy_from_rms = float(np.clip(np.log10(rms * 40 + 1e-6) / 1.6 + 0.55, 0.04, 0.96))
        zcr = float(np.mean(np.abs(np.diff(np.sign(pcm)))) / 2)
        kinetic_zcr = float(np.clip(zcr * 3.2, 0.05, 0.95))
        window = np.hanning(min(4096, pcm.size))
        spec = np.abs(np.fft.rfft(pcm[: window.size] * window))
        freqs = np.fft.rfftfreq(window.size, 1 / 11025)
        denom = float(spec.sum()) + 1e-9
        centroid = float((freqs * spec).sum() / denom)
        bright = float(np.clip(centroid / 4200, 0.05, 0.95))

        detected_bpm, kinetic_onset = _aubio_rhythm(pcm)
        kinetic = float(np.clip(0.45 * kinetic_zcr + 0.55 * kinetic_onset, 0.05, 0.95))

        energy = float(np.clip(0.40 * energy + 0.28 * energy_from_rms + 0.32 * kinetic, 0.03, 0.97))
        valence = float(np.clip(0.55 * valence + 0.45 * bright, 0.03, 0.97))

    out_bpm = bpm if bpm else detected_bpm
    if out_bpm:
        energy = float(np.clip(0.7 * energy + 0.3 * np.clip((out_bpm - 70) / 110, 0, 1), 0.03, 0.97))
    return valence, energy, out_bpm
