from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import exp, hypot

from meridian.context import Context, LENS_RADIUS_MIN, Mode, band_bias, mode_bias
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

# Soft caps while building a queue so lens loyalty does not become one-artist loops.
_MAX_ARTIST_IN_QUEUE = 2
_MAX_ALBUM_IN_QUEUE = 2


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


def _artist_key(track: Track) -> str:
    raw = (track.albumartist or track.artist or "").strip().lower()
    return raw


def _album_key(track: Track) -> str:
    album = (track.album or "").strip().lower()
    if not album:
        return ""
    artist = _artist_key(track)
    return f"{artist}|{album}" if artist else album


def mix_counts(ctx: Context) -> tuple[int, int, int, int, int]:
    """Return (explicit, now, deep, fill, shelf) take sizes for the context queue.

    Modes reshape the Eisenhower mix; skip pressure steals a little from NOW into FILL
    so a skip streak explores the lens neighborhood instead of doubling down.
    """
    if ctx.mode == Mode.FOCUS:
        explicit, now, deep, fill, shelf = 3, 8, 6, 3, 1
    elif ctx.mode == Mode.CHARGE:
        explicit, now, deep, fill, shelf = 3, 9, 3, 4, 2
    elif ctx.mode == Mode.DIM:
        explicit, now, deep, fill, shelf = 2, 5, 7, 3, 3
    else:  # WANDER
        explicit, now, deep, fill, shelf = 3, 7, 5, 4, 2

    pressure = _clip01(ctx.skip_pressure)
    steal = int(round(2.0 * pressure))
    if steal:
        now = max(3, now - steal)
        fill = fill + steal
    return explicit, now, deep, fill, shelf


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
    pressure = _clip01(ctx.skip_pressure)
    # Skip streak slightly widens the neighborhood so FILL can surface alternatives.
    radius = max(LENS_RADIUS_MIN, ctx.lens_radius * (1.0 + 0.22 * pressure))

    ranked: list[RankedTrack] = []
    distances: list[float] = []
    for track in tracks:
        dist = hypot(track.valence - target_x, track.energy - target_y)
        fit = _gauss(dist, radius)
        plays = int(track.play_count or 0)
        skips = int(track.skip_count or 0)
        total = max(1, plays + skips)
        skip_ratio = skips / total
        importance = 0.28 * fit
        if track.loved:
            importance += 0.42
        importance += 0.22 * min(plays, 10) / 10
        if track.pinned:
            importance += 0.08
        # Finishes vs skips: net listen quality after a few observations.
        if plays + skips >= 3:
            finish_ratio = plays / total
            importance += 0.14 * (finish_ratio - 0.5)
        # Focus prefers steady rhythm when we have a persisted onset cue.
        if ctx.mode == Mode.FOCUS and track.onset_consistency is not None:
            oc = float(track.onset_consistency)
            if oc > 0.70:
                importance += 0.06
            elif oc < 0.35:
                importance -= 0.04
        importance = min(1.0, max(0.0, importance)) * (1.0 - 0.45 * skip_ratio)
        # High skip pressure softens NOW stickiness (favor exploring the ring).
        urgency = fit * (1.0 - 0.18 * pressure)
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

    nearby_scale = 2.4 + 0.7 * pressure
    nearby_idx = [i for i, dist in enumerate(distances) if dist <= radius * nearby_scale]
    if len(nearby_idx) < 6:
        nearby_idx = sorted(range(len(distances)), key=distances.__getitem__)[: min(16, len(distances))]
    nearby_idx.sort(key=lambda i: distances[i])

    n = len(nearby_idx)
    if n == 1:
        n_now, n_deep = 1, 0
    elif n == 2:
        n_now, n_deep = 1, 1
    else:
        # Under skip pressure, shrink the NOW core and grow the FILL ring.
        now_frac = 0.38 - 0.10 * pressure
        deep_frac = 0.34
        n_now = max(1, round(n * now_frac))
        n_deep = max(1, round(n * deep_frac))
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
    hard_exclude_ids: set[int] | None = None,
) -> QueuePlan:
    """Build a context queue from lens fit, time-of-day, and the four matrix lists."""
    explicit_set = set(explicit_ids)
    skip = set(exclude_ids or ())
    hard_exclude = set(hard_exclude_ids or ())
    skip |= hard_exclude
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
    artist_n: dict[str, int] = {}
    album_n: dict[str, int] = {}
    n_explicit, n_now, n_deep, n_fill, n_shelf = mix_counts(ctx)

    def take(items: list[RankedTrack], n: int, *, allow_recent: bool, diversity: bool) -> None:
        grabbed = 0
        for item in items:
            if grabbed >= n:
                break
            tid = item.track.id
            if tid in used:
                continue
            # Recently played are soft-skipped first; hard-excluded ids stay out even
            # when allow_recent fills gaps (tiny libraries must not loop the same song).
            if tid in hard_exclude:
                continue
            if not allow_recent and tid in skip:
                continue
            artist = _artist_key(item.track)
            album = _album_key(item.track)
            if diversity:
                if artist and artist_n.get(artist, 0) >= _MAX_ARTIST_IN_QUEUE:
                    continue
                if album and album_n.get(album, 0) >= _MAX_ALBUM_IN_QUEUE:
                    continue
            order.append(tid)
            used.add(tid)
            if artist:
                artist_n[artist] = artist_n.get(artist, 0) + 1
            if album:
                album_n[album] = album_n.get(album, 0) + 1
            grabbed += 1

    # Mix from all four playlists; mode + skip pressure set the ratios.
    take(
        [r for r in ranked if r.track.id in explicit_set],
        min(n_explicit, len(explicit_set)),
        allow_recent=True,
        diversity=False,
    )
    take(buckets[Quadrant.NOW], n_now, allow_recent=False, diversity=True)
    take(buckets[Quadrant.DEEP], n_deep, allow_recent=False, diversity=True)
    take(buckets[Quadrant.FILL], n_fill, allow_recent=False, diversity=True)
    take(buckets[Quadrant.SHELF], n_shelf, allow_recent=False, diversity=True)
    if len(order) < length:
        # Gap fill: still prefer diversity, then relax.
        take(buckets[Quadrant.NOW], length - len(order), allow_recent=True, diversity=True)
        take(buckets[Quadrant.DEEP], length - len(order), allow_recent=True, diversity=True)
        take(buckets[Quadrant.FILL], length - len(order), allow_recent=True, diversity=True)
        take(buckets[Quadrant.SHELF], length - len(order), allow_recent=True, diversity=True)
    if len(order) < length:
        take(ranked, length - len(order), allow_recent=True, diversity=False)
    return QueuePlan(ranked=ranked, order=order[:length], by_quadrant=buckets)
