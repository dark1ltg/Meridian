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
    # Container / catalog labels (not acoustic identities) — see CONTAINER_SEED_KEYS.
    "video game": (0.52, 0.46),
    "game": (0.52, 0.46),
    "score": (0.50, 0.40),
    "ost": (0.50, 0.40),
    "vgm": (0.52, 0.46),
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
    # Contemporary / long-tail tags (local seeds only — longest match wins).
    "phonk": (0.36, 0.78),
    "drift phonk": (0.34, 0.80),
    "hyperpop": (0.78, 0.82),
    "digicore": (0.72, 0.76),
    "drill": (0.34, 0.80),
    "uk drill": (0.32, 0.78),
    "jersey club": (0.70, 0.84),
    "baile funk": (0.72, 0.86),
    "funk carioca": (0.72, 0.86),
    "breakcore": (0.42, 0.92),
    "jungle terror": (0.48, 0.88),
    "vaporwave": (0.48, 0.24),
    "future funk": (0.70, 0.58),
    "city pop": (0.72, 0.52),
    "citypop": (0.72, 0.52),
    "pluggnb": (0.56, 0.48),
    "plugg": (0.54, 0.50),
    "rage": (0.44, 0.88),
    "opium": (0.40, 0.82),
    "dream pop": (0.58, 0.36),
    "dreampop": (0.58, 0.36),
    "math rock": (0.50, 0.66),
    "post-punk": (0.36, 0.62),
    "post punk": (0.36, 0.62),
    "garage rock": (0.44, 0.74),
    "psychedelic": (0.48, 0.52),
    "psych": (0.48, 0.52),
    "boom bap": (0.46, 0.58),
    "cloud rap": (0.50, 0.42),
    "detroit techno": (0.38, 0.86),
    "minimal techno": (0.36, 0.78),
    "deep house": (0.62, 0.68),
    "afro house": (0.66, 0.74),
    "amapiano": (0.64, 0.70),
    "kwaito": (0.62, 0.66),
    "soca": (0.74, 0.78),
    "compas": (0.68, 0.60),
    "highlife": (0.70, 0.58),
    "bossa nova": (0.62, 0.32),
    "bossa": (0.62, 0.32),
    "mpb": (0.60, 0.42),
    "cumbia": (0.66, 0.62),
    "tango": (0.44, 0.48),
    "flamenco": (0.52, 0.56),
    "grime": (0.40, 0.82),
    "garage": (0.52, 0.76),
    "uk garage": (0.54, 0.78),
    "2-step": (0.56, 0.74),
    "footwork": (0.48, 0.90),
    "juke": (0.50, 0.88),
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
# Evidence-gated soft widen: steady PCM that clearly disagrees with the seed.
EVIDENCE_SOFT_VALENCE_MAX = 0.12
EVIDENCE_SOFT_ENERGY_MAX = 0.10
KEYWORD_SHIFT_CAP = 0.18
REPLAYGAIN_ENERGY_CAP = 0.06
DEFAULT_VALENCE = 0.5
DEFAULT_ENERGY = 0.48
# Dump / raw formats often have empty or junk tags — favor PCM more.
WEAK_TAG_EXTS = {".wav", ".aiff", ".aif"}
# Contextual catalog labels: useful neighborhood priors, not soft-PCM locks.
CONTAINER_SEED_KEYS = frozenset(
    {
        "soundtrack",
        "ost",
        "score",
        "game",
        "video game",
        "vgm",
    }
)
# Graduated confidence bands (UI + low_trust compat).
CONFIDENCE_LOW = 0.45
CONFIDENCE_HIGH = 0.75

# Test hook: increments whenever ffmpeg decode is attempted.
_decode_pcm_calls = 0
# Cooperative abort for AnalyzeWorker.stop / quit (kills in-flight ffmpeg).
_decode_abort = False
_decode_proc: subprocess.Popen | None = None
_decode_proc_lock = threading.Lock()


def request_decode_abort() -> None:
    """Stop any in-flight ffmpeg decode ASAP (analyze abort / quit)."""
    global _decode_abort, _decode_proc
    _decode_abort = True
    with _decode_proc_lock:
        proc = _decode_proc
    if proc is not None:
        try:
            proc.kill()
        except OSError:
            pass


def clear_decode_abort() -> None:
    global _decode_abort
    _decode_abort = False


def decode_abort_requested() -> bool:
    return bool(_decode_abort)


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

    @property
    def container_only(self) -> bool:
        """True when every matched key is a catalog/container label (OST/game/…)."""
        keys = {k for k in (self.tag_key, self.path_key) if k}
        return bool(keys) and keys <= CONTAINER_SEED_KEYS


@dataclass(frozen=True, slots=True)
class MoodResult:
    valence: float
    energy: float
    bpm: float | None
    confidence: float
    low_trust: bool
    confidence_note: str = ""
    # Optional acoustic cues persisted for ranking / album spread (no re-decode).
    onset_consistency: float | None = None
    acoustic_flux: float | None = None
    brightness: float | None = None
    pcm_ok: bool = False

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
    """Prefer the deepest path segment that is a genre folder, not the longest key."""
    for part in reversed(parts):
        part_l = (part or "").lower().strip()
        if not part_l or part_l in {".", "/"}:
            continue
        stem = Path(part_l).stem if "." in part_l else part_l
        for candidate in (part_l, stem):
            keys = _path_segment_genre_keys(candidate)
            if keys:
                return keys
    return []


def _path_segment_genre_keys(segment: str) -> list[str]:
    """Genre keys for one folder/file stem — avoid 'rock' in 'rock-drive'."""
    raw = (segment or "").lower().strip()
    if not raw:
        return []
    normalized = re.sub(
        r"[\s_\-]+",
        " ",
        raw.replace(".", " ").replace("&", " and "),
    ).strip()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return []
    # Whole segment is a known genre (e.g. "indie rock", "drum and bass").
    if normalized in GENRE_MOOD:
        return [normalized]
    keys = _match_genre_keys(normalized)
    if not keys:
        return []
    # Residual after removing matched keys must be empty (or harmless stopwords).
    # Reject compound device/volume names like "rock drive" / "jazz usb".
    residual = normalized
    for key in sorted(keys, key=len, reverse=True):
        residual = re.sub(
            rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])",
            " ",
            residual,
            flags=re.IGNORECASE,
        )
    residual = re.sub(r"\s+", " ", residual).strip()
    noise = {"the", "a", "an", "and", "n", "music", "songs", "genre", "mix", "vol", "volume"}
    leftover = [w for w in residual.split() if w and w not in noise]
    if leftover:
        return []
    return keys


def _path_genre_keys(path: str | None) -> list[str]:
    """Genre from path — deepest matching folder, then filename stem."""
    if not path:
        return []
    p = Path(path)
    parts = list(p.parts)
    if not parts:
        return []
    dir_parts = parts[:-1]
    file_stem = p.stem
    dir_keys = _best_genre_keys_from_parts(dir_parts)
    if dir_keys:
        return dir_keys
    return _path_segment_genre_keys(file_stem)


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


def _decode_pcm(path: str, *, start_s: float = 12.0, duration_s: float = 28.0) -> np.ndarray | None:
    global _decode_pcm_calls, _decode_proc
    _decode_pcm_calls += 1
    if _decode_abort:
        return None
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    dur = max(2.0, float(duration_s))
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-ss",
        f"{float(start_s):.3f}",
        "-t",
        f"{dur:.3f}",
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
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError:
        return None
    with _decode_proc_lock:
        _decode_proc = proc
    try:
        if _decode_abort:
            proc.kill()
            proc.wait(timeout=2)
            return None
        stdout, _stderr = proc.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=2)
        except OSError:
            pass
        return None
    except OSError:
        return None
    finally:
        with _decode_proc_lock:
            if _decode_proc is proc:
                _decode_proc = None
    if _decode_abort:
        return None
    if proc.returncode != 0 or not stdout:
        return None
    pcm = np.frombuffer(stdout, dtype=np.float32)
    if pcm.size < 2048:
        return None
    return pcm


def _pcm_signal_ok(pcm: np.ndarray) -> bool:
    """True when the buffer still has usable energy after silence trim."""
    trimmed = _trim_silence(np.ascontiguousarray(pcm, dtype=np.float32))
    if trimmed.size < 4096:
        return False
    if not np.isfinite(trimmed).all():
        return False
    rms = float(np.sqrt(np.mean(np.square(trimmed))) + 1e-12)
    return rms > 1e-4


def _coerce_bpm(bpm: float | None) -> float | None:
    """Return a usable BPM, or None for missing / non-finite / non-positive tags."""
    if bpm is None:
        return None
    try:
        value = float(bpm)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(value) or value <= 0.0:
        return None
    return value


def _secondary_seek_s(duration_ms: int) -> float | None:
    """Mid-track seek for dual-window / fallback decode, or None when too short / unknown."""
    dur_s = max(0.0, float(duration_ms) / 1000.0) if duration_ms else 0.0
    if dur_s <= 0:
        # Unknown duration: do not seek far — caller starts at 0.
        return None
    if dur_s < 40.0:
        return max(0.0, dur_s * 0.15)
    return float(np.clip(dur_s * 0.35, 20.0, max(20.0, dur_s - 30.0)))


def _primary_seek_s(duration_ms: int) -> float:
    """Primary window start — 0 for short/unknown so we actually hear the file."""
    dur_s = max(0.0, float(duration_ms) / 1000.0) if duration_ms else 0.0
    if dur_s <= 0 or dur_s < 40.0:
        return 0.0
    return 12.0


def _merge_pcm_profiles(primary, secondary):
    """Combine two window profiles; on strong disagreement prefer the stabler song-like window."""
    from meridian.acoustic import AcousticProfile

    def _stability(p) -> float:
        # Higher is better: consistent onsets, low variation, not marked unstable.
        return (
            float(p.onset_consistency)
            + (0.0 if p.unstable else 0.25)
            + float(np.clip(1.0 - float(p.variation), 0.0, 1.0)) * 0.35
        )

    disagree = float(
        np.hypot(primary.valence - secondary.valence, primary.energy - secondary.energy)
    )
    s1, s2 = _stability(primary), _stability(secondary)
    if s1 >= s2:
        winner, loser = primary, secondary
    else:
        winner, loser = secondary, primary

    if disagree > 0.18:
        # Intro vs drop (etc.): keep the stabler window as the base, but do not discard
        # a musically active disagreeing window — inject contrast (Kinetic freer than Glow).
        loser_more_active = (
            float(loser.flux) > float(winner.flux) + 0.04
            or float(loser.onset_rate) > float(winner.onset_rate) + 0.02
            or float(loser.energy) > float(winner.energy) + 0.06
        )
        inj_e = 0.32 if loser_more_active else 0.18
        inj_v = 0.14 if loser_more_active else 0.08
        valence = float((1.0 - inj_v) * winner.valence + inj_v * loser.valence)
        energy = float((1.0 - inj_e) * winner.energy + inj_e * loser.energy)
        brightness = float((1.0 - inj_v) * winner.brightness + inj_v * loser.brightness)
        flux = float(max(winner.flux, (1.0 - inj_e) * winner.flux + inj_e * loser.flux))
        trend = float((1.0 - inj_e) * winner.energy_trend + inj_e * loser.energy_trend)
        bands = dict(winner.band_energy)
        bpm = winner.bpm if winner.bpm is not None else loser.bpm
        onset_consistency = float(winner.onset_consistency)
        variation = float(
            max(winner.variation, (1.0 - inj_e) * winner.variation + inj_e * loser.variation)
        )
        unstable = bool(winner.unstable)
        ostats_src = winner
        if loser_more_active:
            # Persist the active window's motion cues for Focus / album spread.
            ostats_src = loser if float(loser.onset_rate) >= float(winner.onset_rate) else winner
    else:
        # Mild disagreement: lean toward the stabler window.
        w = 0.62 if s1 != s2 else 0.5
        if winner is secondary:
            w = 1.0 - w
        # w = weight on primary when winner is primary… simplify:
        wp = 0.62 if primary is winner else 0.38
        ws = 1.0 - wp
        valence = float(wp * primary.valence + ws * secondary.valence)
        energy = float(wp * primary.energy + ws * secondary.energy)
        brightness = float(wp * primary.brightness + ws * secondary.brightness)
        flux = float(wp * primary.flux + ws * secondary.flux)
        trend = float(wp * primary.energy_trend + ws * secondary.energy_trend)
        bands = dict(winner.band_energy)
        bpms = [b for b in (primary.bpm, secondary.bpm) if b is not None]
        bpm = float(np.median(bpms)) if bpms else None
        onset_consistency = float(winner.onset_consistency)
        variation = float(wp * primary.variation + ws * secondary.variation)
        unstable = bool(primary.unstable or secondary.unstable)
        ostats_src = winner

    return AcousticProfile(
        valence=float(np.clip(valence, 0.03, 0.97)),
        energy=float(np.clip(energy, 0.03, 0.97)),
        bpm=bpm,
        unstable=unstable,
        brightness=brightness,
        flux=flux,
        band_energy=bands,
        energy_mean=float(np.median([primary.energy_mean, secondary.energy_mean])),
        energy_std=float(np.median([primary.energy_std, secondary.energy_std])),
        energy_peak=float(max(primary.energy_peak, secondary.energy_peak)),
        energy_range=float(np.median([primary.energy_range, secondary.energy_range])),
        energy_trend=trend,
        onset_rate=float(ostats_src.onset_rate),
        onset_burstiness=float(ostats_src.onset_burstiness),
        onset_consistency=onset_consistency,
        variation=variation,
        window_count=int(primary.window_count + secondary.window_count),
        pcm_samples=int(primary.pcm_samples + secondary.pcm_samples),
    )


def _decode_pcm_with_fallback(
    path: str, duration_ms: int = 0
) -> tuple[np.ndarray | None, bool, object | None]:
    """Decode within ~28s total budget; dual 14s windows when the track is long enough.

    Returns (pcm_or_None, used_secondary_seek, merged_profile_or_None).
    When dual windows succeed, pcm is the first window (for callers that need a
    buffer) and merged_profile carries median mood cues from both seeks.
    """
    from meridian.acoustic import build_profile

    dur_s = max(0.0, float(duration_ms) / 1000.0) if duration_ms else 0.0
    primary = _primary_seek_s(duration_ms)
    secondary = _secondary_seek_s(duration_ms)

    # Dual-window path: same total seconds (~28) as a single long window.
    if dur_s >= 55.0 and secondary is not None and abs(secondary - primary) >= 8.0:
        if decode_abort_requested():
            return None, False, None
        pcm_a = _decode_pcm(path, start_s=primary, duration_s=14.0)
        if decode_abort_requested():
            return None, False, None
        pcm_b = _decode_pcm(path, start_s=float(secondary), duration_s=14.0)
        ok_a = pcm_a is not None and _pcm_signal_ok(pcm_a)
        ok_b = pcm_b is not None and _pcm_signal_ok(pcm_b)
        if ok_a and ok_b:
            p1 = build_profile(pcm_a)
            p2 = build_profile(pcm_b)
            return pcm_a, True, _merge_pcm_profiles(p1, p2)
        if ok_a:
            return pcm_a, False, None
        if ok_b:
            return pcm_b, True, None

    # Single 28s window with silence fallback (short tracks / dual failed).
    starts = [primary]
    if secondary is not None:
        starts.append(float(secondary))
    if primary > 0.0:
        starts.append(0.0)

    seen: set[float] = set()
    for index, ss in enumerate(starts):
        if decode_abort_requested():
            return None, False, None
        key = round(float(ss), 2)
        if key in seen:
            continue
        seen.add(key)
        pcm = _decode_pcm(path, start_s=float(ss), duration_s=28.0)
        if pcm is not None and _pcm_signal_ok(pcm):
            return pcm, index > 0, None
    return None, False, None


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
    variation: float = 0.0,
    flux: float | None = None,
    onset_consistency: float | None = None,
) -> tuple[float, str]:
    """Graduated placement confidence in 0..1 plus a short evidence note for tooltips."""
    from meridian.acoustic import confidence_from_evidence

    return confidence_from_evidence(
        tag_key=tag_key,
        path_key=path_key,
        pcm_ok=pcm_ok,
        pcm_fallback=pcm_fallback,
        pcm_unstable=pcm_unstable,
        bpm_ok=bpm_ok,
        bpm_conflict=bpm_conflict,
        replaygain=replaygain,
        keyword_hit=keyword_hit,
        weak_tags=weak_tags,
        jitter=jitter,
        variation=variation,
        flux=flux,
        onset_consistency=onset_consistency,
        genre_conflict=_genre_pair_conflict(tag_key, path_key),
    )


def confidence_low_trust(confidence: float) -> bool:
    """Compat flag: dimmest band / smooth target."""
    return float(confidence) < CONFIDENCE_LOW


def _aubio_rhythm(pcm: np.ndarray, samplerate: int = 11025) -> tuple[float | None, float]:
    """Return (bpm_or_None, kinetic_from_onsets in 0..1). Soft-fails if aubio is missing."""
    from meridian.acoustic import onset_stats

    bpm, stats = onset_stats(pcm, samplerate)
    return bpm, float(stats["kinetic"])


def _bpm_nudge(energy: float, out_bpm: float | None, *, soft: bool = False) -> float:
    if out_bpm is None or not np.isfinite(out_bpm) or out_bpm <= 0.0:
        return energy
    pace = float(np.clip((out_bpm - 70) / 110, 0, 1))
    w = 0.18 if soft else 0.30
    return float(np.clip((1.0 - w) * energy + w * pace, 0.03, 0.97))


def _energy_bpm_for_nudge(
    tag_bpm: float | None,
    detected_bpm: float | None,
    *,
    onset_consistency: float,
    unstable: bool,
) -> float | None:
    """Pick which BPM drives the energy nudge when tag and waveform disagree."""
    if tag_bpm is None:
        return detected_bpm
    if detected_bpm is None:
        return tag_bpm
    if abs(float(tag_bpm) - float(detected_bpm)) <= 18.0:
        return tag_bpm
    # Conflict: steady rhythm → trust detected for pace; messy audio → keep tag.
    if onset_consistency > 0.70 and not unstable:
        return detected_bpm
    return tag_bpm


def _trim_silence(pcm: np.ndarray, floor: float = 0.012) -> np.ndarray:
    """Drop leading/trailing near-silence so RMS/crest aren't skewed."""
    from meridian.acoustic import trim_silence

    return trim_silence(pcm, floor=floor)


def _spectral_slice(
    pcm: np.ndarray, start: int, n: int, samplerate: int
) -> tuple[float, float, float]:
    """Return (bright, bass_share, flatness) for one window."""
    from meridian.acoustic import spectral_slice

    bright, bass, flatness, _bands, _c = spectral_slice(pcm, start, n, samplerate)
    return bright, bass, flatness


def _pcm_mood_cues(
    pcm: np.ndarray, samplerate: int = 11025
) -> tuple[float, float, float | None, bool, object]:
    """Derive valence/energy cues from one already-decoded PCM buffer (no extra I/O).

    Returns (valence, energy, bpm, unstable, profile). Uses local windows inside
    the existing decode only — no distributed track-wide sampling.
    """
    from meridian.acoustic import build_profile

    profile = build_profile(pcm, samplerate=samplerate)
    return profile.valence, profile.energy, profile.bpm, profile.unstable, profile


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
    tag_bpm = _coerce_bpm(bpm)
    tag_bpm_ok = tag_bpm is not None
    weak_tags = _weak_tag_ext(path)
    # Strong acoustic genre (tag or path) + BPM: tiny PCM residual only.
    # Container labels (OST/game/…) stay clamp neighborhoods but do not soft-lock PCM.
    soft_pcm_only = (
        seed.clamp_match and tag_bpm_ok and not weak_tags and not seed.container_only
    )

    detected_bpm: float | None = None
    pcm_ok = False
    pcm_fallback = False
    pcm_unstable = False
    profile = None
    soft_shift = SOFT_PCM_MAX_SHIFT

    pcm, pcm_fallback, merged_profile = _decode_pcm_with_fallback(path, duration_ms=duration_ms)
    if pcm is not None:
        pcm_ok = True
        if merged_profile is not None:
            profile = merged_profile
            valence_pcm = float(profile.valence)
            energy_pcm = float(profile.energy)
            detected_bpm = profile.bpm
            pcm_unstable = bool(profile.unstable)
        else:
            valence_pcm, energy_pcm, detected_bpm, pcm_unstable, profile = _pcm_mood_cues(pcm)
        detected_bpm = _coerce_bpm(detected_bpm)

        onset_c = float(getattr(profile, "onset_consistency", 0.5) or 0.5) if profile else 0.5
        variation = float(getattr(profile, "variation", 0.0) or 0.0) if profile else 0.0
        unstable = bool(pcm_unstable or variation > 0.28)
        disagree = float(
            np.hypot(valence_pcm - seed.valence, energy_pcm - seed.energy)
        )
        genre_conflict = _genre_pair_conflict(seed.tag_key, seed.path_key)
        # Structure-aware clamps: steady rhythm + genre disagreement → trust PCM more;
        # unstable / uneven onsets → hug the genre seed tighter.
        soft_shift_v = SOFT_PCM_MAX_SHIFT
        soft_shift_e = SOFT_PCM_MAX_SHIFT
        pcm_w_v, pcm_w_e = 0.40, 0.48
        clamp_shift = PCM_MAX_SHIFT
        if onset_c > 0.70 and disagree > 0.12:
            widened = min(0.09, SOFT_PCM_MAX_SHIFT * 1.45)
            soft_shift_v = widened
            soft_shift_e = widened
            pcm_w_v, pcm_w_e = 0.55, 0.62
            clamp_shift = min(0.16, PCM_MAX_SHIFT * 1.25)
        elif unstable or onset_c < 0.35:
            soft_shift_v = SOFT_PCM_MAX_SHIFT * 0.55
            soft_shift_e = SOFT_PCM_MAX_SHIFT * 0.55
            pcm_w_v, pcm_w_e = 0.28, 0.32
            clamp_shift = PCM_MAX_SHIFT * 0.70

        # OST/game/score: keep a seed neighborhood but do not hug it like acoustic genres.
        if seed.container_only:
            pcm_w_v = max(pcm_w_v, 0.68)
            pcm_w_e = max(pcm_w_e, 0.75)
            clamp_shift = max(clamp_shift, 0.20)

        # Evidence-gated soft widen: stable PCM that clearly disagrees with the seed.
        # Glow may move farther than Kinetic (genre+BPM usually encode pace better).
        if (
            soft_pcm_only
            and onset_c > 0.70
            and not unstable
            and variation < 0.22
            and disagree > 0.18
        ):
            soft_shift_v = max(soft_shift_v, EVIDENCE_SOFT_VALENCE_MAX)
            soft_shift_e = max(soft_shift_e, min(EVIDENCE_SOFT_ENERGY_MAX, EVIDENCE_SOFT_VALENCE_MAX))

        # Tag vs path conflict: metadata is unreliable — reduce seed authority.
        # Freed weight goes to PCM only in proportion to how trustworthy PCM is
        # (conflict alone must not crank waveform authority to maximum).
        if genre_conflict and seed.tag_key and seed.path_key:
            tv, te = GENRE_MOOD[seed.tag_key]
            pv, pe = GENRE_MOOD[seed.path_key]
            conflict_d = float(np.hypot(tv - pv, te - pe))
            conflict_amt = float(np.clip((conflict_d - 0.35) / 0.40, 0.0, 1.0))
            if unstable or onset_c < 0.35:
                pcm_claim = 0.20
            elif variation > 0.22 or onset_c < 0.55:
                pcm_claim = 0.50
            else:
                pcm_claim = 0.85
            transfer = conflict_amt * pcm_claim
            # Soft residual: open the envelope a little with freed metadata weight.
            soft_shift_v = min(0.10, soft_shift_v + transfer * 0.045)
            soft_shift_e = min(0.09, soft_shift_e + transfer * 0.035)
            # Clamp blend: move weight from seed → PCM (capped; not untagged-level).
            pcm_w_v = min(0.58, pcm_w_v + transfer * 0.18)
            pcm_w_e = min(0.65, pcm_w_e + transfer * 0.18)
            clamp_shift = min(0.15, clamp_shift + transfer * 0.025)

        soft_shift = soft_shift_e  # post-BPM energy reclamp uses Kinetic envelope

        if weak_tags:
            # Dump formats: distrust tags; lean hard on waveform.
            valence = float(np.clip(0.22 * seed.valence + 0.78 * valence_pcm, 0.03, 0.97))
            energy = float(np.clip(0.18 * seed.energy + 0.82 * energy_pcm, 0.03, 0.97))
        elif soft_pcm_only:
            # Genre+BPM already trusted — residual spreads neighbors (wider when evidence is strong).
            valence = float(
                np.clip(
                    seed.valence
                    + float(np.clip(valence_pcm - seed.valence, -soft_shift_v, soft_shift_v)),
                    0.03,
                    0.97,
                )
            )
            energy = float(
                np.clip(
                    seed.energy
                    + float(np.clip(energy_pcm - seed.energy, -soft_shift_e, soft_shift_e)),
                    0.03,
                    0.97,
                )
            )
        elif seed.clamp_match:
            valence = float(np.clip((1.0 - pcm_w_v) * seed.valence + pcm_w_v * valence_pcm, 0.03, 0.97))
            energy = float(np.clip((1.0 - pcm_w_e) * seed.energy + pcm_w_e * energy_pcm, 0.03, 0.97))
            valence = float(
                np.clip(
                    seed.valence
                    + float(np.clip(valence - seed.valence, -clamp_shift, clamp_shift)),
                    0.03,
                    0.97,
                )
            )
            energy = float(
                np.clip(
                    seed.energy
                    + float(np.clip(energy - seed.energy, -clamp_shift, clamp_shift)),
                    0.03,
                    0.97,
                )
            )
        else:
            # Messy / untagged: trust waveform cues heavily.
            valence = float(np.clip(0.15 * seed.valence + 0.85 * valence_pcm, 0.03, 0.97))
            energy = float(np.clip(0.12 * seed.energy + 0.88 * energy_pcm, 0.03, 0.97))

    # Prefer a real tag BPM for storage; energy nudge may use detected when rhythm is steady.
    out_bpm = tag_bpm if tag_bpm is not None else detected_bpm
    onset_for_bpm = float(getattr(profile, "onset_consistency", 0.5) or 0.5) if profile else 0.5
    nudge_bpm = _energy_bpm_for_nudge(
        tag_bpm,
        detected_bpm,
        onset_consistency=onset_for_bpm,
        unstable=bool(pcm_unstable),
    )
    energy = _bpm_nudge(
        energy,
        nudge_bpm,
        soft=soft_pcm_only or (tag_bpm is None and detected_bpm is not None),
    )
    if soft_pcm_only and pcm_ok:
        energy = float(
            np.clip(
                seed.energy
                + float(
                    np.clip(
                        energy - seed.energy,
                        -soft_shift,
                        soft_shift,
                    )
                ),
                0.03,
                0.97,
            )
        )

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
    if tag_bpm is not None and detected_bpm is not None:
        if abs(float(tag_bpm) - float(detected_bpm)) > 18.0:
            bpm_conflict = True
        else:
            bpm_ok = True
    elif tag_bpm is not None or detected_bpm is not None:
        # Only credit BPM when we have a coerced (finite, positive) value.
        bpm_ok = True

    if not np.isfinite(valence):
        valence = float(seed.valence)
    if not np.isfinite(energy):
        energy = float(seed.energy)
    valence = float(np.clip(valence, 0.03, 0.97))
    energy = float(np.clip(energy, 0.03, 0.97))

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
        variation=float(getattr(profile, "variation", 0.0) or 0.0) if profile else 0.0,
        flux=float(getattr(profile, "flux", 0.0)) if profile else None,
        onset_consistency=float(getattr(profile, "onset_consistency", 0.5)) if profile else None,
    )
    return MoodResult(
        valence=float(valence),
        energy=float(energy),
        bpm=out_bpm,
        confidence=float(confidence),
        low_trust=confidence_low_trust(confidence),
        confidence_note=note,
        onset_consistency=(
            float(getattr(profile, "onset_consistency", 0.5)) if profile else None
        ),
        acoustic_flux=float(getattr(profile, "flux", 0.0)) if profile else None,
        brightness=float(getattr(profile, "brightness", 0.5)) if profile else None,
        pcm_ok=bool(pcm_ok),
    )
