"""Placement-honesty package — dialogue drop, blend floor, pitch Glow, slope,
pulse Kinetic gate, keyword undo, sub-bass Shadow vote."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np

from meridian.acoustic import (
    SAMPLERATE,
    AcousticProfile,
    build_profile,
    is_dialogue_frame,
    spectral_bands,
    spectral_slice_ex,
    spectral_slope_clarity,
    tonal_onset_score,
)


def _tone(hz: float, seconds: float = 3.0, amp: float = 0.4) -> np.ndarray:
    t = np.arange(int(SAMPLERATE * seconds), dtype=np.float32) / SAMPLERATE
    return (amp * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def _prof(**kwargs) -> AcousticProfile:
    base = dict(
        valence=0.5,
        energy=0.5,
        bpm=120.0,
        unstable=False,
        brightness=0.5,
        flux=0.4,
        onset_rate=1.0,
        onset_consistency=0.8,
        onset_burstiness=0.2,
        variation=0.1,
        energy_mean=0.55,
        tonal=0.7,
        spectral_slope=0.6,
        sub_bass=0.05,
        window_count=3,
        pcm_samples=1000,
    )
    base.update(kwargs)
    return AcousticProfile(**base)


def test_dialogue_frame_keeps_sung_and_drops_speechy() -> None:
    # Tonal / harmonic → never dialogue (sung bias).
    assert not is_dialogue_frame(
        tonal=0.70,
        flatness=0.25,
        zcr=0.12,
        bands={"mid": 0.45, "high_mid": 0.2, "bass": 0.1, "low_mid": 0.1, "high": 0.1},
    )
    # Mid-heavy, flat, speechy ZCR, low tonal → dialogue.
    assert is_dialogue_frame(
        tonal=0.35,
        flatness=0.55,
        zcr=0.18,
        bands={"mid": 0.40, "high_mid": 0.22, "bass": 0.08, "low_mid": 0.10, "high": 0.12},
    )
    # Unsure mid case → keep (bias toward music).
    assert not is_dialogue_frame(
        tonal=0.50,
        flatness=0.40,
        zcr=0.10,
        bands={"mid": 0.30, "high_mid": 0.20, "bass": 0.25, "low_mid": 0.15, "high": 0.10},
    )


def test_sub_bass_band_and_shadow_vote() -> None:
    sr = SAMPLERATE
    # Pure ~50 Hz tone should show sub-bass share and land darker than a bright mid.
    sub = _tone(50.0, seconds=4.0, amp=0.45)
    mid = _tone(1200.0, seconds=4.0, amp=0.45)
    # Mix a bright lead over heavy sub — must not land fully Glow.
    mixed = (0.55 * sub + 0.35 * _tone(2800.0, seconds=4.0, amp=1.0)).astype(np.float32)
    ps = build_profile(sub)
    pm = build_profile(mid)
    px = build_profile(mixed)
    assert ps.sub_bass > pm.sub_bass + 0.05
    assert "sub_bass" in ps.band_energy
    assert ps.valence < pm.valence
    # Bright lead + heavy sub stays below a clean bright mid.
    assert px.valence < pm.valence + 0.02


def test_pitch_glow_only_when_tonal() -> None:
    # Steady tonal tone: pitch/centroid Glow path active (high tonal).
    tonal_hi = _tone(2200.0, seconds=4.0)
    # Broadband noise: not tonal enough → brightness path, not pitch Glow.
    rng = np.random.default_rng(3)
    noisy = (rng.standard_normal(SAMPLERATE * 4) * 0.28).astype(np.float32)
    pt = build_profile(tonal_hi)
    pn = build_profile(noisy)
    assert pt.tonal >= 0.55
    assert pn.tonal < 0.55
    assert pt.valence > pn.valence + 0.05


def test_spectral_slope_clarity_muffled_vs_clear() -> None:
    n = 4096
    freqs = np.fft.rfftfreq(n, 1.0 / SAMPLERATE)
    # Steep falloff → muffled (low clarity).
    muffled = np.exp(-freqs / 400.0)
    # Flatter → clearer.
    clear = np.exp(-freqs / 2500.0) + 0.15
    assert spectral_slope_clarity(muffled, freqs) < spectral_slope_clarity(clear, freqs)
    bright, bass, flat, bands, _c, slope, zcr = spectral_slice_ex(
        _tone(440.0), 0, 4096, SAMPLERATE
    )
    assert 0.0 <= slope <= 1.0
    assert "sub_bass" in bands
    assert flat >= 0.0
    assert bright > 0.0
    assert zcr >= 0.0


def test_tonal_onset_blend_floor_caps_sting() -> None:
    from meridian.features import (
        SECTION_TONAL_ONSET_CAP,
        SECTION_TONAL_ONSET_FLOOR,
        _reweight_tonal_onset,
    )

    # Flashy sting intro vs solid mid/late body.
    intro = _prof(tonal=0.95, onset_consistency=0.95, onset_rate=3.0, energy=0.9, valence=0.9)
    mid = _prof(tonal=0.55, onset_consistency=0.6, onset_rate=0.8, energy=0.45, valence=0.4)
    late = _prof(tonal=0.50, onset_consistency=0.55, onset_rate=0.7, energy=0.42, valence=0.38)
    base = {"intro": 0.20, "mid": 0.50, "late": 0.30}
    out = _reweight_tonal_onset(base, {"intro": intro, "mid": mid, "late": late})
    assert abs(sum(out.values()) - 1.0) < 1e-6
    assert out["intro"] <= SECTION_TONAL_ONSET_CAP + 1e-9
    assert out["mid"] >= SECTION_TONAL_ONSET_FLOOR - 1e-9
    assert out["late"] >= SECTION_TONAL_ONSET_FLOOR - 1e-9
    # Mid+late still carry meaningful body share.
    assert out["mid"] + out["late"] >= 0.45


def test_pulse_clarity_gates_bpm_kinetic() -> None:
    """Muddy pulse must not get a BPM Kinetic step; clear pulse may."""
    from meridian.features import analyze_audio

    pcm = _tone(220.0, seconds=3.0)
    # Profile with muddy pulse + high tag BPM that would otherwise shove Kinetic.
    muddy = _prof(
        valence=0.45,
        energy=0.40,
        bpm=None,
        onset_consistency=0.25,
        variation=0.12,
        unstable=False,
        tonal=0.6,
        spectral_slope=0.6,
    )
    clear = _prof(
        valence=0.45,
        energy=0.40,
        bpm=160.0,
        onset_consistency=0.88,
        variation=0.08,
        unstable=False,
        tonal=0.6,
        spectral_slope=0.6,
    )

    def _run(profile: AcousticProfile):
        with patch(
            "meridian.features._decode_pcm_with_fallback",
            return_value=(pcm, False, None, None),
        ):
            with patch(
                "meridian.features._pcm_mood_cues",
                return_value=(
                    float(profile.valence),
                    float(profile.energy),
                    profile.bpm,
                    False,
                    profile,
                ),
            ):
                return analyze_audio(
                    "/tmp/honest_pulse.flac",
                    "",
                    "x",
                    "y",
                    170.0,
                )

    muddy_r = _run(muddy)
    clear_r = _run(clear)
    # Muddy pulse: energy stays near PCM/seed; clear pulse may step Kinetic via BPM.
    assert muddy_r.energy < clear_r.energy + 0.02
    assert clear_r.energy > muddy_r.energy + 0.02


def test_keyword_nudge_zeroed_on_pcm_contradiction() -> None:
    from meridian.features import (
        _keyword_contradicted_by_pcm,
        genre_seed,
        analyze_audio,
    )

    seed = genre_seed("", "Happy Party Joy", "Artist", path="/tmp/kw_honest.flac")
    assert seed.keyword_hit
    assert seed.keyword_dv > 0.0 or seed.keyword_de > 0.0

    # Steady dark/calm PCM contradicts happy/party keywords.
    assert _keyword_contradicted_by_pcm(
        keyword_dv=float(seed.keyword_dv),
        keyword_de=float(seed.keyword_de),
        seed_valence=float(seed.valence),
        seed_energy=float(seed.energy),
        pcm_valence=0.22,
        pcm_energy=0.20,
        onset_consistency=0.80,
        unstable=False,
        variation=0.08,
    )
    # Shaky listen must not undo keywords.
    assert not _keyword_contradicted_by_pcm(
        keyword_dv=float(seed.keyword_dv),
        keyword_de=float(seed.keyword_de),
        seed_valence=float(seed.valence),
        seed_energy=float(seed.energy),
        pcm_valence=0.22,
        pcm_energy=0.20,
        onset_consistency=0.30,
        unstable=True,
        variation=0.35,
    )

    dark = _prof(
        valence=0.20,
        energy=0.18,
        bpm=90.0,
        onset_consistency=0.82,
        variation=0.08,
        unstable=False,
        tonal=0.65,
        spectral_slope=0.62,
        brightness=0.30,
    )
    pcm = _tone(110.0, seconds=3.0)
    with patch(
        "meridian.features._decode_pcm_with_fallback",
        return_value=(pcm, False, None, None),
    ):
        with patch(
            "meridian.features._pcm_mood_cues",
            return_value=(0.20, 0.18, 90.0, False, dark),
        ):
            # Untagged so blend trusts PCM heavily; keywords would otherwise Glow/Kinetic.
            result = analyze_audio(
                "/tmp/kw_honest.flac",
                "",
                "Happy Party Joy",
                "Artist",
                None,
            )
    # Genre left alone (none here); keyword Glow must not stick after contradiction.
    assert result.valence < seed.valence - 0.05


def test_slope_muffled_stays_nearer_sticker() -> None:
    from meridian.features import analyze_audio, genre_seed

    seed = genre_seed("ambient", "pad", "x", path="/tmp/slope_muff.flac")
    pcm = _tone(200.0, seconds=3.0)
    muffled = _prof(
        valence=0.85,
        energy=0.70,
        bpm=100.0,
        onset_consistency=0.75,
        variation=0.10,
        unstable=False,
        tonal=0.55,
        spectral_slope=0.20,  # muffled
        brightness=0.70,
        sub_bass=0.05,
    )
    clear_dark = _prof(
        valence=0.25,
        energy=0.40,
        bpm=100.0,
        onset_consistency=0.75,
        variation=0.10,
        unstable=False,
        tonal=0.65,
        spectral_slope=0.75,  # clear
        brightness=0.28,
        sub_bass=0.22,
    )

    def _run(profile: AcousticProfile):
        with patch(
            "meridian.features._decode_pcm_with_fallback",
            return_value=(pcm, False, None, None),
        ):
            with patch(
                "meridian.features._pcm_mood_cues",
                return_value=(
                    float(profile.valence),
                    float(profile.energy),
                    profile.bpm,
                    False,
                    profile,
                ),
            ):
                return analyze_audio(
                    "/tmp/slope_muff.flac",
                    "ambient",
                    "pad",
                    "x",
                    100.0,
                )

    muff_r = _run(muffled)
    clear_r = _run(clear_dark)
    # Muffled Glow PCM stays nearer sticker than a clear dark listen may Shadow-shift.
    muff_move = abs(muff_r.valence - seed.valence)
    clear_move = abs(clear_r.valence - seed.valence)
    assert muff_move <= clear_move + 0.02
    assert clear_r.valence < muff_r.valence


def test_tonal_onset_score_monotonic() -> None:
    weak = _prof(tonal=0.30, onset_consistency=0.2, onset_rate=0.1)
    strong = _prof(tonal=0.85, onset_consistency=0.9, onset_rate=2.5)
    assert tonal_onset_score(strong) > tonal_onset_score(weak) + 0.2


def test_spectral_bands_include_sub_bass() -> None:
    n = 4096
    frame = _tone(55.0)[:n]
    windowed = frame * np.hanning(frame.size)
    spec = np.abs(np.fft.rfft(windowed)) + 1e-12
    freqs = np.fft.rfftfreq(frame.size, 1.0 / SAMPLERATE)
    bands = spectral_bands(spec, freqs)
    assert bands["sub_bass"] > 0.15
