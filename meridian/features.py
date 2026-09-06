from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
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
    # Aliases → same coordinates as a nearby canonical genre (longest match wins).
    "alt rock": (0.50, 0.64),
    "alternative rock": (0.50, 0.64),
    "alt-rock": (0.50, 0.64),
    "alternative": (0.52, 0.56),
    "indie rock": (0.52, 0.58),
    "indie-rock": (0.52, 0.58),
    "indie pop": (0.62, 0.52),
    "indie-pop": (0.62, 0.52),
    "post-rock": (0.44, 0.42),
    "post rock": (0.44, 0.42),
    "postrock": (0.44, 0.42),
    "emo": (0.38, 0.58),
    "shoegaze": (0.40, 0.48),
    "grunge": (0.34, 0.70),
    "hard rock": (0.42, 0.80),
    "hard-rock": (0.42, 0.80),
    "progressive rock": (0.48, 0.62),
    "prog": (0.48, 0.62),
    "prog-rock": (0.48, 0.62),
    "prog rock": (0.48, 0.62),
    "death metal": (0.22, 0.92),
    "black metal": (0.20, 0.90),
    "heavy metal": (0.30, 0.88),
    "metalcore": (0.30, 0.90),
    "hardcore": (0.32, 0.88),
    "drum and bass": (0.48, 0.88),
    "dnb": (0.48, 0.88),
    "jungle": (0.46, 0.86),
    "dubstep": (0.40, 0.84),
    "trap": (0.50, 0.76),
    "synthwave": (0.58, 0.60),
    "synth-wave": (0.58, 0.60),
    "synthpop": (0.66, 0.62),
    "electro": (0.58, 0.76),
    "trance": (0.60, 0.82),
    "dub": (0.52, 0.40),
    "dancehall": (0.62, 0.70),
    "reggaeton": (0.64, 0.72),
    "funk": (0.68, 0.66),
    "disco": (0.74, 0.70),
    "gospel": (0.70, 0.50),
    "rnb": (0.60, 0.48),
    "rhythm and blues": (0.60, 0.48),
    "hip-hop": (0.52, 0.62),
    "hiphop": (0.52, 0.62),
    "k-pop": (0.74, 0.68),
    "kpop": (0.74, 0.68),
    "j-pop": (0.72, 0.60),
    "anime": (0.62, 0.58),
    "video game": (0.52, 0.46),
    "game": (0.52, 0.46),
    "score": (0.50, 0.40),
    "ost": (0.50, 0.40),
    "acoustic": (0.54, 0.30),
    "singer-songwriter": (0.52, 0.32),
    "americana": (0.56, 0.40),
    "bluegrass": (0.58, 0.48),
    "new age": (0.50, 0.20),
    "downtempo": (0.48, 0.28),
    "chillout": (0.56, 0.26),
    "idm": (0.44, 0.58),
    "industrial": (0.28, 0.82),
    "gothic": (0.30, 0.55),
    "goth": (0.30, 0.55),
    "ska": (0.66, 0.68),
    "latin": (0.66, 0.58),
    "afrobeats": (0.68, 0.72),
    "afrobeat": (0.68, 0.72),
}

# Lowercase alias table once (match path always lowercases haystacks).
GENRE_MOOD = {k.lower(): v for k, v in GENRE_MOOD.items()}

# Collision tokens (blue/black/light/sun) intentionally omitted.
WORD_VALENCE = {
    "sad": -0.28,
    "dark": -0.22,
    "night": -0.10,
    "rain": -0.12,
    "lonely": -0.24,
    "grief": -0.30,
    "love": 0.22,
    "happy": 0.26,
    "joy": 0.24,
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
    # "live" omitted — too many calm live albums got a false kinetic bump.
    "acoustic": -0.14,
    "lofi": -0.18,
    "lo-fi": -0.18,
}

PCM_MAX_SHIFT = 0.12
# Tiny residual when genre+BPM are already strong — spreads neighbors without leaving the cluster.
SOFT_PCM_MAX_SHIFT = 0.06
KEYWORD_SHIFT_CAP = 0.18
REPLAYGAIN_ENERGY_CAP = 0.06
DEFAULT_VALENCE = 0.5
DEFAULT_ENERGY = 0.48
# Dump / raw formats often have empty or junk tags — favor PCM more.
WEAK_TAG_EXTS = {".wav", ".aiff", ".aif"}
# Graduated confidence bands (UI + low_trust compat).
CONFIDENCE_LOW = 0.45
CONFIDENCE_HIGH = 0.75

# Test hook: increments whenever ffmpeg decode is attempted.
_decode_pcm_calls = 0


@dataclass(frozen=True, slots=True)
class MoodSeed:
    valence: float
    energy: float
    tag_key: str | None = None
    path_key: str | None = None
    keyword_hit: bool = False

    @property
    def clamp_match(self) -> bool:
        """Tag or path genre hit — used to limit PCM drag."""
        return self.tag_key is not None or self.path_key is not None


@dataclass(frozen=True, slots=True)
class MoodResult:
    valence: float
    energy: float
    bpm: float | None
    confidence: float
    low_trust: bool
    confidence_note: str = ""

def _text(tag) -> str:
    if tag is None:
        return ""
    if isinstance(tag, (list, tuple)):
        return str(tag[0]) if tag else ""
    return str(tag)


def _text_join(tag) -> str:
    """Join multi-value tags (genre) so every entry reaches genre matching."""
    if tag is None:
        return ""
    if isinstance(tag, (list, tuple)):
        return " ".join(str(part) for part in tag if part is not None and str(part).strip())
    return str(tag)


def _parse_gain_db(raw: str, *, r128: bool = False) -> float | None:
    """Parse ReplayGain / R128 style strings into dB (negative = louder master)."""
    if not raw:
        return None
    text = str(raw).strip()
    # Opus/R128 gain is Q7.8 integer (divide by 256). Never treat bare ints as ReplayGain dB.
    if re.fullmatch(r"[+-]?\d+", text):
        try:
            q = int(text)
        except ValueError:
            return None
        if r128:
            return float(q) / 256.0
        return None
    match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*dB?", text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        val = float(match.group(1))
    except ValueError:
        return None
    # Explicit R128 with a unit still sometimes stored as Q7.8-sized ints.
    if r128 and abs(val) > 64 and "db" not in text.lower():
        return val / 256.0
    return val


def _read_replaygain_db(audio) -> float | None:
    """Prefer track gain; fall back to album / R128. Free loudness prior when present."""
    easy_rg = ("replaygain_track_gain", "replaygain_album_gain")
    easy_r128 = ("r128_track_gain", "r128_album_gain")
    for key in easy_rg:
        parsed = _parse_gain_db(_text(audio.get(key)), r128=False)
        if parsed is not None:
            return parsed
    for key in easy_r128:
        parsed = _parse_gain_db(_text(audio.get(key)), r128=True)
        if parsed is not None:
            return parsed
    try:
        raw = getattr(audio, "tags", None)
        if raw is None:
            return None
        for key in ("REPLAYGAIN_TRACK_GAIN", "REPLAYGAIN_ALBUM_GAIN"):
            if key in raw:
                parsed = _parse_gain_db(_text_join(raw.get(key)), r128=False)
                if parsed is not None:
                    return parsed
        for key in ("R128_TRACK_GAIN", "R128_ALBUM_GAIN"):
            if key in raw:
                parsed = _parse_gain_db(_text_join(raw.get(key)), r128=True)
                if parsed is not None:
                    return parsed
        # ID3 TXXX frames
        for frame in raw.getall("TXXX") if hasattr(raw, "getall") else []:
            desc = str(getattr(frame, "desc", "") or "").lower()
            text = _text_join(frame.text if hasattr(frame, "text") else frame)
            if "replaygain_track_gain" in desc or "replaygain_album_gain" in desc:
                parsed = _parse_gain_db(text, r128=False)
                if parsed is not None:
                    return parsed
        for frame in raw.getall("TXXX") if hasattr(raw, "getall") else []:
            desc = str(getattr(frame, "desc", "") or "").lower()
            text = _text_join(frame.text if hasattr(frame, "text") else frame)
            if desc in {"r128_track_gain", "r128_album_gain"} or "r128_track_gain" in desc or "r128_album_gain" in desc:
                parsed = _parse_gain_db(text, r128=True)
                if parsed is not None:
                    return parsed
    except Exception:
        return None
    return None


def read_tags(path: str) -> dict:
    info = {
        "title": Path(path).stem,
        "artist": "",
        "album": "",
        "albumartist": "",
        "composer": "",
        "genre": "",
        "year": None,
        "bpm": None,
        "duration_ms": 0,
        "replaygain_db": None,
        "extra_text": "",
    }
    try:
        audio = MutagenFile(path, easy=True)
    except (ID3NoHeaderError, Exception):
        info["extra_text"] = _filename_mood_text(path)
        return info
    if audio is None:
        info["extra_text"] = _filename_mood_text(path)
        return info
    info["title"] = _text(audio.get("title")) or info["title"]
    info["artist"] = _text(audio.get("artist"))
    info["album"] = _text(audio.get("album"))
    info["albumartist"] = _text(
        audio.get("albumartist") or audio.get("album artist") or audio.get("performer")
    )
    info["composer"] = _text(audio.get("composer"))
    info["genre"] = _text_join(audio.get("genre"))
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
    info["replaygain_db"] = _read_replaygain_db(audio)

    extras: list[str] = []
    for key in ("comment", "grouping", "mood", "description", "lyrics"):
        val = _text_join(audio.get(key))
        if val:
            extras.append(val)
    # Non-easy ID3 mood / grouping frames when present.
    try:
        raw = getattr(audio, "tags", None)
        if raw is not None:
            for frame_id in ("TMOO", "GRP1", "TIT1"):
                if frame_id in raw:
                    extras.append(_text_join(raw.get(frame_id)))
            if not info["composer"] and "TCOM" in raw:
                info["composer"] = _text_join(raw.get("TCOM"))
            if not info["albumartist"] and "TPE2" in raw:
                info["albumartist"] = _text_join(raw.get("TPE2"))
    except Exception:
        pass
    extras.append(_filename_mood_text(path))
    info["extra_text"] = " ".join(x for x in extras if x).strip()
    return info


def _weak_tag_ext(path: str | None) -> bool:
    if not path:
        return False
    return Path(path).suffix.lower() in WEAK_TAG_EXTS


def _replaygain_energy_prior(gain_db: float | None) -> float:
    """Negative track gain ⇒ louder master ⇒ slight kinetic nudge."""
    if gain_db is None or not np.isfinite(float(gain_db)):
        return 0.0
    return float(np.clip(-float(gain_db) * 0.007, -REPLAYGAIN_ENERGY_CAP, REPLAYGAIN_ENERGY_CAP))


def _credit_text(albumartist: str = "", composer: str = "") -> str:
    """Composer / album artist — often cleaner than track artist (classical, VA, OST)."""
    parts: list[str] = []
    aa = (albumartist or "").strip()
    if aa and aa.lower() not in {"various artists", "various", "va", "unknown"}:
        parts.append(aa)
    comp = (composer or "").strip()
    if comp:
        parts.append(comp)
    return " ".join(parts)

def _filename_mood_text(path: str | None) -> str:
    if not path:
        return ""
    stem = Path(path).stem
    stem = re.sub(r"^\d{1,3}[\s.\-_]+", "", stem)
    stem = stem.replace("_", " ").replace(".", " ")
    return stem.strip()


def _year_prior(year: int | None) -> tuple[float, float]:
    """Older releases → slightly calmer/darker; recent → slight glow/kinetic."""
    if year is None or year < 1920 or year > 2035:
        return 0.0, 0.0
    # 0 = 1960-era, 1 = 2020-era
    t = float(np.clip((year - 1960) / 60.0, 0.0, 1.0))
    dv = (t - 0.5) * 0.06
    de = (t - 0.5) * 0.08
    return float(dv), float(de)


def _keyword_shift(text: str, skip_words: set[str] | None = None) -> tuple[float, float]:
    """Apply title/artist mood words; skip tokens already used as genre seeds."""
    blob = text.lower()
    skip = {w.lower() for w in (skip_words or ()) if w}
    expanded = set(skip)
    for w in list(skip):
        expanded.add(w.replace("-", " "))
        expanded.add(w.replace(" ", "-"))
        expanded.add(w.replace(" ", ""))
    skip = expanded
    dv = de = 0.0
    for word, delta in WORD_VALENCE.items():
        if word in skip:
            continue
        if re.search(rf"\b{re.escape(word)}\b", blob, flags=re.IGNORECASE):
            dv += delta
    for word, delta in WORD_ENERGY.items():
        if word in skip:
            continue
        if re.search(rf"\b{re.escape(word)}\b", blob, flags=re.IGNORECASE):
            de += delta
    dv = float(np.clip(dv, -KEYWORD_SHIFT_CAP, KEYWORD_SHIFT_CAP))
    de = float(np.clip(de, -KEYWORD_SHIFT_CAP, KEYWORD_SHIFT_CAP))
    return dv, de


def _match_genre_keys(haystack: str) -> list[str]:
    """All matching GENRE_MOOD keys, longest first (most specific).

    Keys must match as whole tokens (word boundaries) so short aliases like
    ost/prog/game/house do not fire inside host/program/gameplay/warehouse.
    """
    g = (haystack or "").lower()
    if not g.strip():
        return []
    hits: list[str] = []
    for key in GENRE_MOOD:
        # (?<![a-z0-9])…(?![a-z0-9]) ≈ word boundary for genre tokens incl. &/-.
        pattern = rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])"
        if re.search(pattern, g, flags=re.IGNORECASE):
            hits.append(key)
    hits.sort(key=len, reverse=True)
    # Drop shorter keys fully contained in a longer hit ("rock" under "indie rock").
    filtered: list[str] = []
    for key in hits:
        if any(key != other and key in other for other in filtered):
            continue
        filtered.append(key)
    return filtered


def _match_genre_key(haystack: str) -> str | None:
    keys = _match_genre_keys(haystack)
    return keys[0] if keys else None


def _blend_genre_pairs(keys: list[str]) -> tuple[float, float] | None:
    """Weight longest key 0.7 and next 0.3 when multiple genres match."""
    if not keys:
        return None
    if len(keys) == 1:
        return GENRE_MOOD[keys[0]]
    v0, e0 = GENRE_MOOD[keys[0]]
    v1, e1 = GENRE_MOOD[keys[1]]
    return (0.70 * v0 + 0.30 * v1, 0.70 * e0 + 0.30 * e1)


def _best_genre_keys_from_parts(parts: list[str]) -> list[str]:
    best: list[str] = []
    best_len = -1
    for part in parts:
        part_l = (part or "").lower().strip()
        if not part_l or part_l in {".", "/"}:
            continue
        stem = Path(part_l).stem if "." in part_l else part_l
        stem = stem.replace("_", " ")
        for candidate in (part_l.replace("_", " "), stem):
            keys = _match_genre_keys(candidate)
            if keys and len(keys[0]) > best_len:
                best = keys
                best_len = len(keys[0])
    return best


def _path_genre_keys(path: str | None) -> list[str]:
    """Genre from path — prefer folder taxonomy over the filename stem (#2 / #6)."""
    if not path:
        return []
    p = Path(path)
    parts = list(p.parts)
    if not parts:
        return []
    dir_parts = parts[:-1]
    file_stem = p.stem.replace("_", " ").replace(".", " ")
    dir_keys = _best_genre_keys_from_parts(dir_parts)
    if dir_keys:
        return dir_keys
    return _match_genre_keys(file_stem)


def _path_genre_key(path: str | None) -> str | None:
    keys = _path_genre_keys(path)
    return keys[0] if keys else None


def genre_seed(
    genre: str,
    title: str,
    artist: str,
    path: str | None = None,
    *,
    year: int | None = None,
    extra_text: str = "",
    albumartist: str = "",
    composer: str = "",
    replaygain_db: float | None = None,
) -> MoodSeed:
    tag_keys = _match_genre_keys(genre or "")
    path_keys = _path_genre_keys(path)
    tag_key = tag_keys[0] if tag_keys else None
    path_key = path_keys[0] if path_keys else None

    tag_pair = _blend_genre_pairs(tag_keys)
    path_pair = _blend_genre_pairs(path_keys)

    if tag_pair and path_pair:
        valence = 0.75 * tag_pair[0] + 0.25 * path_pair[0]
        energy = 0.75 * tag_pair[1] + 0.25 * path_pair[1]
    elif tag_pair:
        valence, energy = tag_pair
    elif path_pair:
        valence, energy = path_pair
    else:
        valence, energy = DEFAULT_VALENCE, DEFAULT_ENERGY

    # Year prior: stronger when genre tags are missing.
    yv, ye = _year_prior(year)
    if tag_key is None:
        valence += yv
        energy += ye
    else:
        valence += 0.35 * yv
        energy += 0.35 * ye

    energy += _replaygain_energy_prior(replaygain_db)

    skip_words = set(tag_keys) | set(path_keys)
    credit = _credit_text(albumartist, composer)
    # Filename is already folded into extra_text by read_tags — only add if missing.
    fn = _filename_mood_text(path)
    blob = f"{title} {artist} {credit} {genre} {extra_text}"
    if fn and fn.lower() not in blob.lower():
        blob = f"{blob} {fn}"
    dv, de = _keyword_shift(blob, skip_words=skip_words)
    return MoodSeed(
        valence=float(np.clip(valence + dv, 0.03, 0.97)),
        energy=float(np.clip(energy + de, 0.03, 0.97)),
        tag_key=tag_key,
        path_key=path_key,
        keyword_hit=bool(abs(dv) > 1e-9 or abs(de) > 1e-9),
    )

def genre_match(genre: str) -> str | None:
    return _match_genre_key(genre or "")


def _stable_jitter(path: str) -> tuple[float, float]:
    """Tiny stable scatter so unknown tracks do not stack on one point.

    Uses blake2b (not Python hash) so positions stay fixed across rescans/processes.
    """
    digest = hashlib.blake2b(path.encode("utf-8", errors="replace"), digest_size=8).digest()
    h_v = int.from_bytes(digest[:4], "little")
    h_e = int.from_bytes(digest[4:], "little")
    valence = DEFAULT_VALENCE + ((h_v % 1000) / 1000.0 - 0.5) * 0.06
    energy = DEFAULT_ENERGY + ((h_e % 1000) / 1000.0 - 0.5) * 0.06
    return (
        float(np.clip(valence, 0.03, 0.97)),
        float(np.clip(energy, 0.03, 0.97)),
    )


def _decode_pcm(path: str, *, start_s: float = 12.0) -> np.ndarray | None:
    global _decode_pcm_calls
    _decode_pcm_calls += 1
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-ss",
        f"{float(start_s):.3f}",
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


def _pcm_signal_ok(pcm: np.ndarray) -> bool:
    """True when the buffer still has usable energy after silence trim."""
    trimmed = _trim_silence(np.ascontiguousarray(pcm, dtype=np.float32))
    if trimmed.size < 4096:
        return False
    rms = float(np.sqrt(np.mean(np.square(trimmed))) + 1e-12)
    return rms > 1e-4


def _decode_pcm_with_fallback(path: str, duration_ms: int = 0) -> tuple[np.ndarray | None, bool]:
    """Decode at +12s; if near-silent, retry mid-track (or earlier for short files).

    Returns (pcm_or_None, used_fallback). used_fallback True when the primary
    +12s window failed signal checks and a later seek was used.
    """
    starts = [12.0]
    dur_s = max(0.0, float(duration_ms) / 1000.0) if duration_ms else 0.0
    if dur_s > 0:
        if dur_s < 40.0:
            starts.append(max(1.0, dur_s * 0.15))
        else:
            starts.append(float(np.clip(dur_s * 0.35, 20.0, max(20.0, dur_s - 30.0))))
    else:
        starts.append(45.0)

    seen: set[float] = set()
    for index, ss in enumerate(starts):
        key = round(float(ss), 2)
        if key in seen:
            continue
        seen.add(key)
        pcm = _decode_pcm(path, start_s=float(ss))
        if pcm is not None and _pcm_signal_ok(pcm):
            return pcm, index > 0
    return None, False


def _genre_pair_conflict(tag_key: str | None, path_key: str | None) -> bool:
    """True when tag and path genre seeds disagree strongly on the map."""
    if not tag_key or not path_key or tag_key == path_key:
        return False
    tv, te = GENRE_MOOD[tag_key]
    pv, pe = GENRE_MOOD[path_key]
    return float(np.hypot(tv - pv, te - pe)) > 0.35


def mood_confidence(
    *,
    tag_key: str | None = None,
    path_key: str | None = None,
    pcm_ok: bool = False,
    pcm_fallback: bool = False,
    pcm_unstable: bool = False,
    bpm_ok: bool = False,
    bpm_conflict: bool = False,
    replaygain: bool = False,
    keyword_hit: bool = False,
    weak_tags: bool = False,
    jitter: bool = False,
) -> tuple[float, str]:
    """Graduated placement confidence in 0..1 plus a short evidence note for tooltips."""
    score = 0.0
    reasons: list[str] = []
    if tag_key:
        # Seed-only genre is weaker than genre confirmed by PCM.
        score += 0.40 if pcm_ok else 0.30
        reasons.append(f"tag:{tag_key}")
    if path_key:
        if tag_key:
            if _genre_pair_conflict(tag_key, path_key):
                score -= 0.10
                reasons.append("path conflict")
            else:
                score += 0.08
                reasons.append("path agrees")
        else:
            score += 0.12 if pcm_ok else 0.15
            reasons.append(f"path:{path_key}")
    if pcm_ok:
        if pcm_fallback or pcm_unstable:
            score += 0.12
            reasons.append("PCM weak" if pcm_unstable else "PCM fallback")
        elif tag_key or path_key:
            score += 0.30
            reasons.append("PCM")
        else:
            # PCM-only placements are real mid-tier evidence, not "full trust".
            score += 0.50
            reasons.append("PCM only")
    if bpm_conflict:
        # Tag vs detected tempo disagree — flag only, no BPM credit (C3).
        score -= 0.04
        reasons.append("BPM conflict")
    elif bpm_ok:
        score += 0.08
        reasons.append("BPM")
    if replaygain:
        score += 0.04
        reasons.append("ReplayGain")
    if keyword_hit:
        score += 0.03
        reasons.append("keywords")
    if weak_tags:
        score -= 0.08
        reasons.append("weak-tag format")
    if jitter or (not pcm_ok and not tag_key and not path_key):
        score = min(score, 0.20)
        if jitter:
            reasons.append("jitter")
        elif not reasons:
            reasons.append("no evidence")
    score = float(np.clip(score, 0.0, 1.0))
    return score, " · ".join(reasons)


def confidence_low_trust(confidence: float) -> bool:
    """Compat flag: dimmest band / smooth target."""
    return float(confidence) < CONFIDENCE_LOW


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
    onset_rate = onsets / duration_s
    kinetic = float(np.clip((onset_rate - 0.35) / 3.4, 0.05, 0.95))

    bpm = float(tempo_o.get_bpm())
    if not np.isfinite(bpm) or bpm < 40.0 or bpm > 220.0:
        bpm_out: float | None = None
    else:
        bpm_out = bpm
    return bpm_out, kinetic


def _bpm_nudge(energy: float, out_bpm: float | None, *, soft: bool = False) -> float:
    if not out_bpm or not np.isfinite(out_bpm):
        return energy
    pace = float(np.clip((out_bpm - 70) / 110, 0, 1))
    w = 0.18 if soft else 0.30
    return float(np.clip((1.0 - w) * energy + w * pace, 0.03, 0.97))


def _trim_silence(pcm: np.ndarray, floor: float = 0.012) -> np.ndarray:
    """Drop leading/trailing near-silence so RMS/crest aren't skewed."""
    if pcm.size < 4096:
        return pcm
    abs_p = np.abs(pcm)
    peak = float(np.max(abs_p) + 1e-12)
    thr = max(floor * peak, 1e-4)
    idx = np.where(abs_p >= thr)[0]
    if idx.size < 2048:
        return pcm
    return pcm[int(idx[0]) : int(idx[-1]) + 1]


def _spectral_slice(
    pcm: np.ndarray, start: int, n: int, samplerate: int
) -> tuple[float, float, float]:
    """Return (bright, bass_share, flatness) for one window."""
    end = min(start + n, pcm.size)
    if end - start < n // 2:
        start = max(0, pcm.size - n)
        end = pcm.size
    frame = pcm[start:end]
    if frame.size < 64:
        return 0.5, 0.35, 0.3
    if frame.size < n:
        pad = np.zeros(n, dtype=np.float32)
        pad[: frame.size] = frame
        frame = pad
    else:
        frame = frame[:n]
    windowed = frame * np.hanning(frame.size)
    spec = np.abs(np.fft.rfft(windowed)) + 1e-12
    freqs = np.fft.rfftfreq(frame.size, 1.0 / samplerate)
    denom = float(spec.sum()) + 1e-12
    centroid = float((freqs * spec).sum() / denom)
    bright = float(np.clip(centroid / 4200.0, 0.05, 0.95))
    bass = float(np.clip(spec[freqs < 250.0].sum() / denom, 0.0, 1.0))
    power = np.square(spec)
    flatness = float(np.exp(np.mean(np.log(power))) / (float(np.mean(power)) + 1e-12))
    flatness = float(np.clip(flatness, 0.0, 1.0))
    return bright, bass, flatness


def _pcm_mood_cues(
    pcm: np.ndarray, samplerate: int = 11025
) -> tuple[float, float, float | None, bool]:
    """Derive valence/energy cues from one already-decoded PCM buffer (no extra I/O).

    Returns (valence, energy, bpm, unstable) where unstable means the two FFT
    windows disagree strongly (weaker PCM evidence for confidence).
    """
    pcm = _trim_silence(np.ascontiguousarray(pcm, dtype=np.float32))
    rms = float(np.sqrt(np.mean(np.square(pcm))) + 1e-12)
    energy_from_rms = float(np.clip(np.log10(rms * 40 + 1e-6) / 1.6 + 0.55, 0.04, 0.96))

    zcr = float(np.mean(np.abs(np.diff(np.sign(pcm)))) / 2)
    kinetic_zcr = float(np.clip(zcr * 3.2, 0.05, 0.95))

    n = min(4096, int(pcm.size))
    # Two windows along the same buffer (early + mid) — still one ffmpeg decode.
    max_start = max(0, int(pcm.size) - n)
    i0 = int(0.10 * max_start)
    i1 = int(0.55 * max_start)
    b0, bass0, flat0 = _spectral_slice(pcm, i0, n, samplerate)
    b1, bass1, flat1 = _spectral_slice(pcm, i1, n, samplerate)
    bright = 0.5 * (b0 + b1)
    bass = 0.5 * (bass0 + bass1)
    flatness = 0.5 * (flat0 + flat1)
    unstable = abs(b0 - b1) > 0.28 or abs(bass0 - bass1) > 0.30

    peak = float(np.max(np.abs(pcm)) + 1e-12)
    crest = peak / rms
    crest_n = float(np.clip((np.log10(crest) - 0.25) / 1.15, 0.05, 0.95))

    detected_bpm, kinetic_onset = _aubio_rhythm(pcm, samplerate)
    kinetic = float(np.clip(0.38 * kinetic_zcr + 0.62 * kinetic_onset, 0.05, 0.95))

    # Tuned weights from synthetic bass-vs-noise checks + messy-library bias.
    valence_pcm = float(
        np.clip(
            0.50 * bright
            + 0.28 * (1.0 - bass)
            + 0.22 * (1.0 - 0.85 * flatness),
            0.03,
            0.97,
        )
    )
    energy_pcm = float(
        np.clip(
            0.30 * energy_from_rms
            + 0.36 * kinetic
            + 0.20 * crest_n
            + 0.14 * bright,
            0.03,
            0.97,
        )
    )
    return valence_pcm, energy_pcm, detected_bpm, bool(unstable)


def analyze_audio(
    path: str,
    genre: str,
    title: str,
    artist: str,
    bpm: float | None,
    *,
    year: int | None = None,
    extra_text: str = "",
    albumartist: str = "",
    composer: str = "",
    replaygain_db: float | None = None,
    duration_ms: int = 0,
) -> MoodResult:
    seed = genre_seed(
        genre,
        title,
        artist,
        path=path,
        year=year,
        extra_text=extra_text,
        albumartist=albumartist,
        composer=composer,
        replaygain_db=replaygain_db,
    )
    valence, energy = seed.valence, seed.energy
    tag_bpm_ok = bpm is not None and np.isfinite(float(bpm))
    weak_tags = _weak_tag_ext(path)
    # Strong genre (tag or path) + BPM: tiny PCM residual only — includes path genre (#3).
    soft_pcm_only = seed.clamp_match and tag_bpm_ok and not weak_tags

    detected_bpm: float | None = None
    pcm_ok = False
    pcm_fallback = False
    pcm_unstable = False

    pcm, pcm_fallback = _decode_pcm_with_fallback(path, duration_ms=duration_ms)
    if pcm is not None:
        pcm_ok = True
        valence_pcm, energy_pcm, detected_bpm, pcm_unstable = _pcm_mood_cues(pcm)

        if weak_tags:
            # Dump formats: distrust tags; lean hard on waveform.
            valence = float(np.clip(0.22 * seed.valence + 0.78 * valence_pcm, 0.03, 0.97))
            energy = float(np.clip(0.18 * seed.energy + 0.82 * energy_pcm, 0.03, 0.97))
        elif soft_pcm_only:
            # Genre+BPM already trusted — soft residual spreads same-genre neighbors.
            valence = float(
                np.clip(
                    seed.valence
                    + float(np.clip(valence_pcm - seed.valence, -SOFT_PCM_MAX_SHIFT, SOFT_PCM_MAX_SHIFT)),
                    0.03,
                    0.97,
                )
            )
            energy = float(
                np.clip(
                    seed.energy
                    + float(np.clip(energy_pcm - seed.energy, -SOFT_PCM_MAX_SHIFT, SOFT_PCM_MAX_SHIFT)),
                    0.03,
                    0.97,
                )
            )
        elif seed.clamp_match:
            valence = float(np.clip(0.60 * seed.valence + 0.40 * valence_pcm, 0.03, 0.97))
            energy = float(np.clip(0.52 * seed.energy + 0.48 * energy_pcm, 0.03, 0.97))
            valence = float(
                np.clip(
                    seed.valence
                    + float(np.clip(valence - seed.valence, -PCM_MAX_SHIFT, PCM_MAX_SHIFT)),
                    0.03,
                    0.97,
                )
            )
            energy = float(
                np.clip(
                    seed.energy
                    + float(np.clip(energy - seed.energy, -PCM_MAX_SHIFT, PCM_MAX_SHIFT)),
                    0.03,
                    0.97,
                )
            )
        else:
            # Messy / untagged: trust waveform cues heavily.
            valence = float(np.clip(0.15 * seed.valence + 0.85 * valence_pcm, 0.03, 0.97))
            energy = float(np.clip(0.12 * seed.energy + 0.88 * energy_pcm, 0.03, 0.97))

    out_bpm = bpm if bpm else detected_bpm
    energy = _bpm_nudge(energy, out_bpm, soft=(bpm is None and detected_bpm is not None))

    used_jitter = False
    if (
        not seed.clamp_match
        and not pcm_ok
        and abs(valence - DEFAULT_VALENCE) < 1e-6
        and abs(energy - DEFAULT_ENERGY) < 1e-6
    ):
        valence, energy = _stable_jitter(path)
        used_jitter = True

    bpm_conflict = False
    bpm_ok = False
    if tag_bpm_ok and detected_bpm is not None and np.isfinite(float(detected_bpm)):
        if abs(float(bpm) - float(detected_bpm)) > 18.0:
            bpm_conflict = True
        else:
            bpm_ok = True
    elif tag_bpm_ok or (detected_bpm is not None and np.isfinite(float(detected_bpm))):
        bpm_ok = True

    confidence, note = mood_confidence(
        tag_key=seed.tag_key,
        path_key=seed.path_key,
        pcm_ok=pcm_ok,
        pcm_fallback=pcm_fallback,
        pcm_unstable=pcm_unstable,
        bpm_ok=bpm_ok,
        bpm_conflict=bpm_conflict,
        replaygain=replaygain_db is not None and np.isfinite(float(replaygain_db)),
        keyword_hit=seed.keyword_hit,
        weak_tags=weak_tags,
        jitter=used_jitter,
    )
    return MoodResult(
        valence=float(valence),
        energy=float(energy),
        bpm=out_bpm,
        confidence=float(confidence),
        low_trust=confidence_low_trust(confidence),
        confidence_note=note,
    )
