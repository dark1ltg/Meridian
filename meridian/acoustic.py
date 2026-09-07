"""Expanded acoustic profile from the existing PCM decode budget (no extra FFmpeg beyond ~28s).

Items 2–11: multi-band energy, spectral flux, RMS dynamics, onset stats,
brightness normalization, confidence, local-window aggregation — still projecting
onto Shadow↔Glow / Still↔Kinetic only. Dual mid-track windows (two ~14s seeks)
are orchestrated in features when duration allows; this module profiles one buffer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SAMPLERATE = 11025


@dataclass
class AcousticProfile:
    valence: float
    energy: float
    bpm: float | None
    unstable: bool
    brightness: float
    flux: float
    band_energy: dict[str, float] = field(default_factory=dict)
    energy_mean: float = 0.5
    energy_std: float = 0.0
    energy_peak: float = 0.5
    energy_range: float = 0.0
    energy_trend: float = 0.0
    onset_rate: float = 0.0
    onset_burstiness: float = 0.0
    onset_consistency: float = 0.5
    variation: float = 0.0
    window_count: int = 0
    pcm_samples: int = 0


def trim_silence(pcm: np.ndarray, floor: float = 0.012) -> np.ndarray:
    if pcm.size < 4096:
        return pcm
    abs_p = np.abs(pcm)
    peak = float(np.max(abs_p) + 1e-12)
    thr = max(floor * peak, 1e-4)
    idx = np.where(abs_p >= thr)[0]
    if idx.size < 2048:
        return pcm
    return pcm[int(idx[0]) : int(idx[-1]) + 1]


def spectral_bands(spec: np.ndarray, freqs: np.ndarray) -> dict[str, float]:
    """Broad band energy shares from an existing magnitude spectrum."""
    denom = float(spec.sum()) + 1e-12
    nyq = float(freqs[-1]) if freqs.size else 5500.0
    edges = (
        ("bass", 20.0, 250.0),
        ("low_mid", 250.0, 500.0),
        ("mid", 500.0, 2000.0),
        ("high_mid", 2000.0, min(4000.0, nyq)),
        ("high", min(4000.0, nyq), nyq + 1.0),
    )
    out: dict[str, float] = {}
    for name, lo, hi in edges:
        if hi <= lo:
            out[name] = 0.0
            continue
        mask = (freqs >= lo) & (freqs < hi)
        out[name] = float(np.clip(spec[mask].sum() / denom, 0.0, 1.0))
    return out


def normalize_brightness(centroid_hz: float) -> float:
    """Bounded nonlinear map — less brittle than centroid/4200 alone."""
    c = max(0.0, float(centroid_hz))
    mapped = np.log1p(c / 700.0) / np.log1p(4500.0 / 700.0)
    return float(np.clip(mapped, 0.05, 0.95))


def spectral_slice(
    pcm: np.ndarray, start: int, n: int, samplerate: int = SAMPLERATE
) -> tuple[float, float, float, dict[str, float], float]:
    """bright, bass_share, flatness, bands, centroid_hz for one window."""
    end = min(start + n, pcm.size)
    if end - start < n // 2:
        start = max(0, pcm.size - n)
        end = pcm.size
    frame = pcm[start:end]
    if frame.size < 64:
        empty = {k: 0.2 for k in ("bass", "low_mid", "mid", "high_mid", "high")}
        return 0.5, 0.35, 0.3, empty, 1500.0
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
    bright = normalize_brightness(centroid)
    bass = float(np.clip(spec[freqs < 250.0].sum() / denom, 0.0, 1.0))
    power = np.square(spec)
    flatness = float(np.exp(np.mean(np.log(power))) / (float(np.mean(power)) + 1e-12))
    flatness = float(np.clip(flatness, 0.0, 1.0))
    bands = spectral_bands(spec, freqs)
    return bright, bass, flatness, bands, centroid


def spectral_flux(pcm: np.ndarray, samplerate: int = SAMPLERATE) -> float:
    """Mean positive spectral flux over hops, normalized by prior frame energy.

    Relative flux keeps steady tones low and avoids absolute-sum saturation on
    loud or broadband material (chirp/noise no longer both pin near 0.95).
    """
    win_s = 512
    hop_s = 256
    if pcm.size < win_s * 2:
        return 0.35
    mono = np.ascontiguousarray(pcm, dtype=np.float32)
    window = np.hanning(win_s).astype(np.float32)
    prev: np.ndarray | None = None
    fluxes: list[float] = []
    for i in range(0, mono.size - win_s + 1, hop_s):
        frame = mono[i : i + win_s] * window
        spec = np.abs(np.fft.rfft(frame))
        if prev is not None:
            diff = spec - prev
            pos = float(np.sum(diff[diff > 0.0]))
            denom = float(np.sum(prev)) + 1e-12
            fluxes.append(pos / denom)
        prev = spec
    if not fluxes:
        return 0.35
    raw = float(np.mean(fluxes))
    # raw ~0 for steady tones, ~0.1 musical change, ~0.3 broadband noise
    mapped = np.log1p(raw * 10.0) / np.log1p(10.0 * 0.55)
    return float(np.clip(mapped, 0.05, 0.95))


def energy_stats(pcm: np.ndarray) -> dict[str, float]:
    """RMS-derived dynamics from existing PCM (no extra decode)."""
    mono = np.ascontiguousarray(pcm, dtype=np.float32)
    if mono.size < 512:
        return {
            "mean": 0.4,
            "std": 0.0,
            "peak": 0.4,
            "range": 0.0,
            "trend": 0.0,
            "consistency": 0.5,
        }
    hop = max(256, int(SAMPLERATE * 0.2))
    win = hop * 2
    vals: list[float] = []
    for i in range(0, mono.size - win + 1, hop):
        chunk = mono[i : i + win]
        vals.append(float(np.sqrt(np.mean(np.square(chunk)) + 1e-12)))
    if not vals:
        vals = [float(np.sqrt(np.mean(np.square(mono)) + 1e-12))]
    arr = np.asarray(vals, dtype=np.float64)
    mean = float(np.mean(arr))
    std = float(np.std(arr))
    peak = float(np.max(arr))
    lo = float(np.min(arr))
    rng = float(peak - lo)
    consistency = float(np.clip(1.0 - (std / (mean + 1e-6)), 0.0, 1.0))
    mid = len(arr) // 2
    trend = 0.0
    if mid > 0:
        trend = float(
            np.clip(
                (float(np.mean(arr[mid:])) - float(np.mean(arr[:mid]))) / (mean + 1e-6),
                -1.0,
                1.0,
            )
        )
    mean_n = float(np.clip(np.log10(mean * 40 + 1e-6) / 1.6 + 0.55, 0.04, 0.96))
    peak_n = float(np.clip(np.log10(peak * 40 + 1e-6) / 1.6 + 0.55, 0.04, 0.96))
    return {
        "mean": mean_n,
        "std": float(np.clip(std / (mean + 1e-6), 0.0, 1.5)),
        "peak": peak_n,
        "range": float(np.clip(rng / (mean + 1e-6), 0.0, 2.0)),
        "trend": trend,
        "consistency": consistency,
    }


def onset_stats(pcm: np.ndarray, samplerate: int = SAMPLERATE) -> tuple[float | None, dict[str, float]]:
    """aubio onset/tempo pass — keep timing stats from the existing hop walk."""
    try:
        import aubio
    except ImportError:
        return None, {
            "kinetic": 0.5,
            "rate": 0.0,
            "burstiness": 0.0,
            "consistency": 0.5,
            "density": 0.0,
        }

    win_s = 512
    hop_s = 256
    if pcm.size < hop_s * 4:
        return None, {
            "kinetic": 0.5,
            "rate": 0.0,
            "burstiness": 0.0,
            "consistency": 0.5,
            "density": 0.0,
        }

    mono = np.ascontiguousarray(pcm, dtype=np.float32)
    tempo_o = aubio.tempo("default", win_s, hop_s, samplerate)
    onset_o = aubio.onset("default", win_s, hop_s, samplerate)
    onset_times: list[float] = []
    for i in range(0, mono.size - hop_s + 1, hop_s):
        frame = mono[i : i + hop_s]
        if onset_o(frame):
            onset_times.append(i / float(samplerate))
        tempo_o(frame)

    duration_s = max(mono.size / float(samplerate), 1e-3)
    rate = len(onset_times) / duration_s
    kinetic = float(np.clip((rate - 0.35) / 3.4, 0.05, 0.95))

    burstiness = 0.0
    consistency = 0.5
    if len(onset_times) >= 3:
        intervals = np.diff(np.asarray(onset_times, dtype=np.float64))
        intervals = intervals[intervals > 1e-4]
        if intervals.size >= 2:
            mu = float(np.mean(intervals))
            sig = float(np.std(intervals))
            burstiness = float(np.clip(sig / (mu + 1e-6), 0.0, 2.0) / 2.0)
            consistency = float(np.clip(1.0 - burstiness, 0.0, 1.0))

    density = 0.0
    if onset_times:
        bins = max(1, int(np.ceil(duration_s)))
        counts = np.zeros(bins, dtype=np.float64)
        for t in onset_times:
            counts[min(bins - 1, int(t))] += 1.0
        density = float(np.clip(np.mean(counts) / 4.0, 0.0, 1.0))

    bpm = float(tempo_o.get_bpm())
    bpm_out: float | None
    # Require real onset evidence — aubio often invents ~60–90 BPM on silence.
    if (
        len(onset_times) < 3
        or rate < 0.25
        or not np.isfinite(bpm)
        or bpm < 40.0
        or bpm > 220.0
    ):
        bpm_out = None
    else:
        bpm_out = bpm

    return bpm_out, {
        "kinetic": kinetic,
        "rate": float(rate),
        "burstiness": float(np.clip(burstiness, 0.0, 1.0)),
        "consistency": consistency,
        "density": density,
    }


def _mean_bands(band_list: list[dict[str, float]]) -> dict[str, float]:
    if not band_list:
        return {k: 0.2 for k in ("bass", "low_mid", "mid", "high_mid", "high")}
    keys = band_list[0].keys()
    return {k: float(np.mean([b[k] for b in band_list])) for k in keys}


def aggregate_window_metrics(
    bright: list[float],
    bass: list[float],
    flat: list[float],
    bands: list[dict[str, float]],
) -> tuple[dict[str, float], dict[str, float]]:
    """Robust overall + variation across local windows inside one decode."""
    if not bright:
        empty_bands = {k: 0.2 for k in ("bass", "low_mid", "mid", "high_mid", "high")}
        return (
            {
                "bright": 0.5,
                "bass": 0.35,
                "flat": 0.3,
                "bright_std": 0.0,
                "bass_std": 0.0,
                "variation": 0.0,
                "unstable": 0.0,
            },
            empty_bands,
        )
    b = np.asarray(bright, dtype=np.float64)
    ba = np.asarray(bass, dtype=np.float64)
    fl = np.asarray(flat, dtype=np.float64)
    bright_m = float(np.median(b))
    bass_m = float(np.median(ba))
    flat_m = float(np.median(fl))
    bright_std = float(np.std(b))
    bass_std = float(np.std(ba))
    variation = float(np.clip(0.55 * bright_std + 0.45 * bass_std, 0.0, 1.0))
    unstable = 1.0 if (bright_std > 0.22 or bass_std > 0.24 or abs(float(b[0] - b[-1])) > 0.28) else 0.0
    return (
        {
            "bright": bright_m,
            "bass": bass_m,
            "flat": flat_m,
            "bright_std": bright_std,
            "bass_std": bass_std,
            "variation": variation,
            "unstable": unstable,
        },
        _mean_bands(bands),
    )


def local_analysis_windows(pcm_size: int, n: int) -> list[int]:
    """Several FFT starts along the already-decoded buffer (not track timeline %)."""
    max_start = max(0, int(pcm_size) - n)
    if max_start <= 0:
        return [0]
    fracs = (0.08, 0.28, 0.50, 0.72, 0.90)
    starts = sorted({int(frac * max_start) for frac in fracs})
    return starts if starts else [0]


def build_profile(pcm: np.ndarray, samplerate: int = SAMPLERATE) -> AcousticProfile:
    """Expanded acoustic profile → still projects to valence/energy only."""
    pcm = trim_silence(np.ascontiguousarray(pcm, dtype=np.float32))
    n = min(4096, int(pcm.size))
    brights: list[float] = []
    basses: list[float] = []
    flats: list[float] = []
    band_list: list[dict[str, float]] = []
    for start in local_analysis_windows(pcm.size, n):
        bright, bass, flat, bands, _c = spectral_slice(pcm, start, n, samplerate)
        brights.append(bright)
        basses.append(bass)
        flats.append(flat)
        band_list.append(bands)

    agg, bands_m = aggregate_window_metrics(brights, basses, flats, band_list)
    bright = float(agg["bright"])
    flatness = float(agg["flat"])
    variation = float(agg["variation"])
    unstable = bool(agg["unstable"] > 0.5)

    flux = spectral_flux(pcm, samplerate)
    est = energy_stats(pcm)
    detected_bpm, ostats = onset_stats(pcm, samplerate)

    zcr = float(np.mean(np.abs(np.diff(np.sign(pcm)))) / 2) if pcm.size > 2 else 0.0
    kinetic_zcr = float(np.clip(zcr * 3.2, 0.05, 0.95))

    peak = float(np.max(np.abs(pcm)) + 1e-12) if pcm.size else 1e-12
    rms = float(np.sqrt(np.mean(np.square(pcm))) + 1e-12) if pcm.size else 1e-12
    crest = peak / rms
    crest_n = float(np.clip((np.log10(crest) - 0.25) / 1.15, 0.05, 0.95))

    # Quiet / near-floor material: broadband hiss looks "bright" but shouldn't Glow.
    # audibility→0 collapses brightness and band_glow toward neutral.
    audibility = float(np.clip(rms / 0.045, 0.0, 1.0))
    bright_v = 0.50 + (bright - 0.50) * audibility

    warm = float(bands_m.get("bass", 0.2) + bands_m.get("low_mid", 0.2))
    present = float(bands_m.get("high_mid", 0.2) + bands_m.get("high", 0.2))
    mid = float(bands_m.get("mid", 0.2))
    band_glow = float(np.clip(0.5 + 0.55 * (present - warm), 0.05, 0.95))
    band_glow_v = 0.50 + (band_glow - 0.50) * audibility

    # Tonal vs noisy: high flatness (noise-like) pulls Glow down; clear tones keep Glow.
    tonal = float(np.clip(1.0 - 0.85 * flatness, 0.05, 0.95))
    noise_pull = float(np.clip((flatness - 0.35) / 0.45, 0.0, 1.0))
    # band_glow already encodes bass/low-mid darkness — do not also use (1-bass).
    valence = float(
        np.clip(
            0.40 * bright_v
            + 0.28 * band_glow_v
            + 0.24 * tonal
            + 0.08 * float(np.clip(0.5 + 0.4 * (mid - warm), 0.05, 0.95))
            - 0.06 * noise_pull * audibility,
            0.03,
            0.97,
        )
    )

    kinetic = float(
        np.clip(
            0.26 * kinetic_zcr
            + 0.32 * float(ostats["kinetic"])
            + 0.22 * flux
            + 0.12 * float(np.clip(ostats["density"] + 0.35 * ostats["burstiness"], 0.05, 0.95))
            + 0.08 * float(np.clip(est["std"], 0.0, 1.0)),
            0.05,
            0.95,
        )
    )
    # Brightness belongs on Shadow↔Glow only — keep energy Still↔Kinetic.
    # Use flux + energy_trend a bit more so evolving tracks feel more kinetic.
    energy = float(
        np.clip(
            0.28 * float(est["mean"])
            + 0.34 * kinetic
            + 0.16 * crest_n
            + 0.12 * float(np.clip(est["range"] / 2.0, 0.0, 1.0))
            + 0.10 * float(np.clip(0.5 + 0.35 * est["trend"], 0.05, 0.95)),
            0.03,
            0.97,
        )
    )

    # np.clip does not scrub NaN — never leak non-finite moods.
    if not np.isfinite(valence):
        valence = 0.5
    if not np.isfinite(energy):
        energy = 0.5
    valence = float(np.clip(valence, 0.03, 0.97))
    energy = float(np.clip(energy, 0.03, 0.97))

    return AcousticProfile(
        valence=valence,
        energy=energy,
        bpm=detected_bpm,
        unstable=unstable or variation > 0.35,
        brightness=bright,
        flux=flux,
        band_energy={k: float(v) for k, v in bands_m.items()},
        energy_mean=float(est["mean"]),
        energy_std=float(est["std"]),
        energy_peak=float(est["peak"]),
        energy_range=float(est["range"]),
        energy_trend=float(est["trend"]),
        onset_rate=float(ostats["rate"]),
        onset_burstiness=float(ostats["burstiness"]),
        onset_consistency=float(ostats["consistency"]),
        variation=variation,
        window_count=len(brights),
        pcm_samples=int(pcm.size),
    )


def confidence_from_evidence(
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
    genre_conflict: bool = False,
) -> tuple[float, str]:
    """Graduated confidence: consistent evidence up, conflict/unstable down."""
    score = 0.0
    reasons: list[str] = []
    if tag_key:
        score += 0.40 if pcm_ok else 0.30
        reasons.append(f"tag:{tag_key}")
    if path_key:
        if tag_key:
            if genre_conflict:
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
            score += 0.50
            reasons.append("PCM only")
        if variation > 0.28:
            score -= float(np.clip((variation - 0.28) * 0.35, 0.0, 0.12))
            reasons.append("unstable spectrum")
        elif variation < 0.10 and not pcm_unstable:
            score += 0.03
            reasons.append("stable spectrum")
        if onset_consistency is not None:
            if onset_consistency > 0.7:
                score += 0.03
            elif onset_consistency < 0.35:
                score -= 0.03
                reasons.append("uneven rhythm")
        if flux is not None and flux > 0.85:
            score -= 0.02
    if bpm_conflict:
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
