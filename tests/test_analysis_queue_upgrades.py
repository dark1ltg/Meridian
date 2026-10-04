"""Queue behavior for analysis upgrades 1/4/5 (shape, timbre, steer)."""

from __future__ import annotations

from meridian.context import Mode, make_context
from meridian.library import Track
from meridian.queue_engine import Quadrant, classify


def _track(
    tid: int,
    *,
    valence: float = 0.5,
    energy: float = 0.5,
    shape_note: str | None = None,
    timbre_flag: str | None = None,
    steer_weight: float | None = 0.9,
    pinned: bool = False,
    loved: bool = False,
    confidence_note: str = "pcm",
    low_trust: bool = False,
    mood_confidence: float = 0.8,
) -> Track:
    return Track(
        id=tid,
        path=f"/m/{tid}.mp3",
        title=f"t{tid}",
        artist="Band",
        album="LP",
        albumartist="Band",
        genre="Electronic",
        duration_ms=180_000,
        year=None,
        bpm=120.0,
        valence=valence,
        energy=energy,
        mood_confidence=mood_confidence,
        confidence_note=confidence_note,
        low_trust=low_trust,
        pinned=pinned,
        loved=loved,
        play_count=2,
        skip_count=0,
        last_played=None,
        added_at=0.0,
        mtime=0.0,
        analyzed=True,
        shape_note=shape_note,
        timbre_flag=timbre_flag,
        steer_weight=steer_weight,
    )


def test_dim_avoids_drop_charge_prefers_drop() -> None:
    drop = _track(1, energy=0.7, shape_note="drop", steer_weight=0.95)
    steady = _track(2, energy=0.7, shape_note="steady", steer_weight=0.95)
    ctx_dim = make_context(Mode.DIM, 0.5, 0.7, 0.35, 0.0)
    ctx_charge = make_context(Mode.CHARGE, 0.5, 0.7, 0.35, 0.0)
    dim_ranked = {r.track.id: r for r in classify([drop, steady], ctx_dim, set())}
    charge_ranked = {r.track.id: r for r in classify([drop, steady], ctx_charge, set())}
    assert dim_ranked[1].urgency < dim_ranked[2].urgency
    # Urgency often saturates at 1.0 under Charge energy boost — importance still prefers drop.
    assert charge_ranked[1].importance > charge_ranked[2].importance
    assert charge_ranked[1].urgency >= charge_ranked[2].urgency


def test_steer_keeps_seed_only_out_of_now_unless_pinned() -> None:
    seed = _track(
        1,
        steer_weight=0.05,
        confidence_note="tag:metal · seed only",
        low_trust=True,
        mood_confidence=0.3,
    )
    solid = _track(2, steer_weight=0.95, valence=0.51, energy=0.51)
    # A few more solids so NOW has alternatives.
    others = [_track(i, steer_weight=0.9, valence=0.5 + i * 0.01, energy=0.5) for i in range(3, 10)]
    ctx = make_context(Mode.WANDER, 0.5, 0.5, 0.4, 0.0)
    ranked = classify([seed, solid, *others], ctx, set())
    by_id = {r.track.id: r for r in ranked}
    assert by_id[1].quadrant != Quadrant.NOW
    assert by_id[2].quadrant in (Quadrant.NOW, Quadrant.DEEP, Quadrant.FILL)

    pinned_seed = _track(
        1,
        steer_weight=0.05,
        pinned=True,
        confidence_note="seed only",
        low_trust=True,
        mood_confidence=0.3,
    )
    ranked_p = classify([pinned_seed, solid, *others], ctx, set())
    # Pinned low-steer may still land in NOW when close enough.
    assert any(r.track.id == 1 for r in ranked_p)


def test_focus_prefers_tonal_over_noisy() -> None:
    tonal = _track(1, timbre_flag="tonal", steer_weight=0.9)
    noisy = _track(2, timbre_flag="noisy", energy=0.7, steer_weight=0.9)
    ctx = make_context(Mode.FOCUS, 0.5, 0.5, 0.35, 0.0)
    ranked = {r.track.id: r for r in classify([tonal, noisy], ctx, set())}
    assert ranked[1].importance > ranked[2].importance
