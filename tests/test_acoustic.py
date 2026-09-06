"""Tests for acoustic profile helpers (items 2–11; no distributed decode)."""

from __future__ import annotations

import numpy as np

from meridian.acoustic import (
    SAMPLERATE,
    aggregate_window_metrics,
    build_profile,
    confidence_from_evidence,
    energy_stats,
    local_analysis_windows,
    normalize_brightness,
    onset_stats,
    spectral_flux,
    spectral_slice,
)
from meridian.features import mood_confidence


def test_local_windows_inside_buffer() -> None:
    starts = local_analysis_windows(SAMPLERATE * 20, 4096)
    assert len(starts) >= 2
    assert starts[0] >= 0
    assert starts[-1] <= SAMPLERATE * 20 - 4096


def test_spectral_bands_flux_energy() -> None:
    sr = SAMPLERATE
    t = np.arange(sr * 3, dtype=np.float32) / sr
    steady = (0.4 * np.sin(2 * np.pi * 110 * t)).astype(np.float32)
    bright, bass, flat, bands, _c = spectral_slice(steady, 0, 4096, sr)
    assert set(bands) >= {"bass", "low_mid", "mid", "high_mid", "high"}
    assert bass >= 0.15
    flux_steady = spectral_flux(steady, sr)
    assert 0.05 <= flux_steady <= 0.25
    rng = np.random.default_rng(0)
    noisy = rng.standard_normal(sr * 3).astype(np.float32) * 0.25
    flux_noisy = spectral_flux(noisy, sr)
    assert flux_noisy > flux_steady + 0.15
    assert flux_noisy < 0.95
    chirp = (0.4 * np.sin(2 * np.pi * (110 + 400 * t / t[-1]) * t)).astype(np.float32)
    flux_chirp = spectral_flux(chirp, sr)
    assert flux_steady < flux_chirp < flux_noisy
    est = energy_stats(steady)
    assert 0.0 <= est["mean"] <= 1.0
    ramp = (steady * np.linspace(0.15, 1.0, steady.size)).astype(np.float32)
    assert energy_stats(ramp)["trend"] > 0.0


def test_quiet_noise_not_glowing() -> None:
    sr = SAMPLERATE
    rng = np.random.default_rng(1)
    quiet = (rng.standard_normal(sr * 3) * 0.002).astype(np.float32)
    loud_bright = (0.35 * np.sin(2 * np.pi * 3200 * np.arange(sr * 3) / sr)).astype(np.float32)
    pq = build_profile(quiet)
    pb = build_profile(loud_bright)
    assert pq.valence < 0.55
    assert pb.valence > pq.valence + 0.08


def test_bass_not_double_counted() -> None:
    sr = SAMPLERATE
    t = np.arange(sr * 4, dtype=np.float32) / sr
    bass_heavy = (0.45 * np.sin(2 * np.pi * 80 * t)).astype(np.float32)
    mid = (0.45 * np.sin(2 * np.pi * 900 * t)).astype(np.float32)
    pb = build_profile(bass_heavy)
    pm = build_profile(mid)
    assert pb.valence < pm.valence
    assert pb.band_energy["bass"] > pm.band_energy["bass"]


def test_brightness_not_in_energy_axis() -> None:
    sr = SAMPLERATE
    t = np.arange(sr * 4, dtype=np.float32) / sr
    dark = (0.35 * np.sin(2 * np.pi * 120 * t)).astype(np.float32)
    bright = (0.35 * np.sin(2 * np.pi * 2800 * t)).astype(np.float32)
    pd = build_profile(dark)
    pb = build_profile(bright)
    assert abs(pb.energy - pd.energy) < 0.12
    assert pb.valence > pd.valence + 0.05


def test_brightness_and_aggregate() -> None:
    assert normalize_brightness(3000.0) > normalize_brightness(400.0)
    bands = [{"bass": 0.3, "low_mid": 0.2, "mid": 0.2, "high_mid": 0.15, "high": 0.15}] * 4
    agg_s, _ = aggregate_window_metrics([0.5, 0.51, 0.49, 0.5], [0.3, 0.31, 0.29, 0.3], [0.2] * 4, bands)
    agg_c, _ = aggregate_window_metrics([0.15, 0.35, 0.7, 0.85], [0.6, 0.45, 0.2, 0.15], [0.2] * 4, bands)
    assert agg_s["variation"] < agg_c["variation"]
    assert 0.05 <= agg_c["bright"] <= 0.95


def test_build_profile_bounded() -> None:
    sr = SAMPLERATE
    t = np.arange(sr * 4, dtype=np.float32) / sr
    pcm = (0.35 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    profile = build_profile(pcm)
    assert 0.03 <= profile.valence <= 0.97
    assert 0.03 <= profile.energy <= 0.97
    assert 0.05 <= profile.flux <= 0.95
    assert profile.window_count >= 2
    _bpm, ostats = onset_stats(pcm)
    assert "burstiness" in ostats and "consistency" in ostats


def test_soft_pcm_bpm_stays_clamped() -> None:
    """Tagged BPM must not pull energy outside the soft PCM envelope."""
    from unittest.mock import patch

    from meridian.features import SOFT_PCM_MAX_SHIFT, analyze_audio, genre_seed

    sr = SAMPLERATE
    t = np.arange(sr * 3, dtype=np.float32) / sr
    pcm = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    seed = genre_seed("metal", "x", "y", path="/tmp/x.flac")
    assert seed.clamp_match
    with patch("meridian.features._decode_pcm_with_fallback", return_value=(pcm, False)):
        result = analyze_audio("/tmp/x.flac", "metal", "x", "y", 180.0)
    assert abs(result.energy - seed.energy) <= SOFT_PCM_MAX_SHIFT + 1e-9


def test_confidence_consistency() -> None:
    strong, _ = confidence_from_evidence(
        tag_key="metal",
        pcm_ok=True,
        bpm_ok=True,
        variation=0.05,
        onset_consistency=0.85,
    )
    weak, note_w = confidence_from_evidence(pcm_ok=True, pcm_unstable=True, variation=0.45)
    conflict, note_c = confidence_from_evidence(tag_key="metal", pcm_ok=True, bpm_conflict=True, variation=0.4)
    assert strong > weak
    assert strong > conflict
    assert "PCM weak" in note_w or "unstable" in note_w
    assert "BPM conflict" in note_c
    c, note = mood_confidence(tag_key="metal", pcm_ok=True, bpm_ok=True)
    assert c > 0.7 and "tag:metal" in note
