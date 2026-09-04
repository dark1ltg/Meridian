from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import exp, hypot

from meridian.context import Context, LENS_RADIUS_MIN, band_bias, mode_bias
from meridian.library import Track


class Quadrant(str, Enum):
    NOW = "now"  # important + urgent
    DEEP = "deep"  # important + not urgent
    FILL = "fill"  # not important + urgent
    SHELF = "shelf"  # neither


QUADRANT_TITLE = {
    Quadrant.NOW: "NOW",
    Quadrant.DEEP: "DEEP",
    Quadrant.FILL: "FILL",
    Quadrant.SHELF: "SHELF",
}

QUADRANT_SUB = {
    Quadrant.NOW: "Important · Urgent — play this",
    Quadrant.DEEP: "Important · Later — keep close",
    Quadrant.FILL: "Urgent · Light — background pulse",
    Quadrant.SHELF: "Neither — park it",
}


@dataclass(slots=True)
class RankedTrack:
    track: Track
    fit: float
    importance: float
    urgency: float
    quadrant: Quadrant


@dataclass
class QueuePlan:
    ranked: list[RankedTrack]
    order: list[int] = field(default_factory=list)
    by_quadrant: dict[Quadrant, list[RankedTrack]] = field(default_factory=dict)


def _gauss(distance: float, radius: float) -> float:
    sigma = max(LENS_RADIUS_MIN * 0.85, radius * 0.72)
    return exp(-(distance * distance) / (2 * sigma * sigma))


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def classify(tracks: list[Track], ctx: Context, explicit_ids: set[int]) -> list[RankedTrack]:
    """Map tracks onto the Eisenhower grid from the mood-lens neighborhood.

    Importance and urgency used to be the same `fit` number, so anything
    important was also urgent and DEEP (important, not urgent) stayed empty.
    Urgency is closeness to the lens. Importance is catalog weight plus being
    in the wider neighborhood. Nearby tracks are split into inner NOW, ring
    DEEP, and outer FILL so moving the lens always refills DEEP.
    """
    bx, by = band_bias(ctx.band)
    mv, me, _ = mode_bias(ctx.mode)
    # Tiny clock/mode nudge; the lens the user dragged is the real target.
    target_x = _clip01(0.88 * ctx.lens_x + 0.12 * (bx + mv))
    target_y = _clip01(0.88 * ctx.lens_y + 0.12 * (by + me))
    radius = max(LENS_RADIUS_MIN, ctx.lens_radius)

    ranked: list[RankedTrack] = []
    distances: list[float] = []
    for track in tracks:
        dist = hypot(track.valence - target_x, track.energy - target_y)
        fit = _gauss(dist, radius)
        skip_ratio = track.skip_count / max(1, track.play_count + track.skip_count)
        importance = 0.28 * fit
        if track.loved:
            importance += 0.42
        importance += 0.22 * min(track.play_count, 10) / 10
        if track.pinned:
            importance += 0.08
        importance = min(1.0, importance) * (1.0 - 0.35 * skip_ratio)
        urgency = fit
        if track.id in explicit_ids:
            urgency = min(1.0, urgency + 0.45)
        if ctx.mode.value == "charge" and track.energy > 0.62:
            urgency = min(1.0, urgency + 0.08)
        if ctx.mode.value == "dim" and track.energy < 0.4:
            urgency = min(1.0, urgency + 0.08)
        ranked.append(
            RankedTrack(
                track=track,
                fit=fit,
                importance=importance,
                urgency=urgency,
                quadrant=Quadrant.SHELF,
            )
        )
        distances.append(dist)

    nearby_idx = [i for i, dist in enumerate(distances) if dist <= radius * 2.4]
    if len(nearby_idx) < 6:
        nearby_idx = sorted(range(len(distances)), key=distances.__getitem__)[: min(16, len(distances))]
    nearby_idx.sort(key=lambda i: distances[i])

    n = len(nearby_idx)
    if n == 1:
        n_now, n_deep = 1, 0
    elif n == 2:
        n_now, n_deep = 1, 1
    else:
        n_now = max(1, round(n * 0.38))
        n_deep = max(1, round(n * 0.34))
        if n_now + n_deep >= n:
            n_deep = max(1, n - n_now - 1) if n >= 3 else n - n_now

    for order, i in enumerate(nearby_idx):
        item = ranked[i]
        if item.track.id in explicit_ids:
            item.quadrant = Quadrant.NOW
            continue
        if order < n_now:
            item.quadrant = Quadrant.NOW
        elif order < n_now + n_deep:
            item.quadrant = Quadrant.DEEP
        else:
            item.quadrant = Quadrant.FILL

    # Loved / often-played tracks just outside NOW still belong in DEEP, not SHELF.
    for i, item in enumerate(ranked):
        if item.quadrant != Quadrant.SHELF:
            continue
        if item.importance >= 0.42 and distances[i] <= radius * 3.2:
            item.quadrant = Quadrant.DEEP

    ranked.sort(key=lambda r: (r.fit * 0.7 + r.importance * 0.3), reverse=True)
    return ranked


def build_plan(
    tracks: list[Track],
    ctx: Context,
    explicit_ids: list[int],
    length: int = 18,
    exclude_ids: set[int] | None = None,
) -> QueuePlan:
    """Build a context queue from lens fit, time-of-day, and the four matrix lists."""
    explicit_set = set(explicit_ids)
    skip = set(exclude_ids or ())
    ranked = classify(tracks, ctx, explicit_set)
    buckets: dict[Quadrant, list[RankedTrack]] = {q: [] for q in Quadrant}
    for item in ranked:
        buckets[item.quadrant].append(item)
    for bucket in buckets.values():
        bucket.sort(
            key=lambda r: (
                -(r.fit * 0.7 + r.importance * 0.3),
                r.track.last_played or 0.0,
            )
        )
    order: list[int] = []
    used: set[int] = set()

    def take(items: list[RankedTrack], n: int, *, allow_recent: bool) -> None:
        grabbed = 0
        for item in items:
            if grabbed >= n:
                break
            tid = item.track.id
            if tid in used:
                continue
            if not allow_recent and tid in skip:
                continue
            order.append(tid)
            used.add(tid)
            grabbed += 1

    # Mix from all four playlists; NOW leads, then DEEP / FILL, a little SHELF.
    take([r for r in ranked if r.track.id in explicit_set], min(3, len(explicit_set)), allow_recent=True)
    take(buckets[Quadrant.NOW], 7, allow_recent=False)
    take(buckets[Quadrant.DEEP], 5, allow_recent=False)
    take(buckets[Quadrant.FILL], 4, allow_recent=False)
    take(buckets[Quadrant.SHELF], 2, allow_recent=False)
    if len(order) < length:
        take(buckets[Quadrant.NOW], length - len(order), allow_recent=True)
        take(buckets[Quadrant.DEEP], length - len(order), allow_recent=True)
        take(buckets[Quadrant.FILL], length - len(order), allow_recent=True)
        take(buckets[Quadrant.SHELF], length - len(order), allow_recent=True)
    if len(order) < length:
        take(ranked, length - len(order), allow_recent=True)
    return QueuePlan(ranked=ranked, order=order[:length], by_quadrant=buckets)
