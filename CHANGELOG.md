# Changelog

All notable Meridian releases are listed here. Download AppImages from [Releases](https://github.com/dark1ltg/Meridian/releases).

## [1.3.4](https://github.com/dark1ltg/Meridian/releases/tag/v1.3.4) — 2026-09-06

Bugfix — queue reliability and mood-map correctness.

### Queue & analyze
- Missing / deleted tracks no longer freeze the queue (depth-capped skip; replenish ignores gone files)
- Failed analyze marks poison files done so the worker cannot loop forever
- Analyze abort / restart races guarded with generation + closing flags
- Skip during crossfade credits the outgoing track, not the incoming one

### Mood map
- Pin drag survives mid-drag map refreshes (zoomed and sky hold)
- Lens ring matches mood-space selection (ellipse + mode radius scale)
- Trackpad lens scroll uses `pixelDelta` when `angleDelta` is 0
- Live hit targets sized to the drawn star
- Sticky pan after sky pin/pan cleaned up
- Double-click empty returns to the full sky; play only on a tight star core
- Backdrop chrome no longer leaks if redrawn

## [1.3.3](https://github.com/dark1ltg/Meridian/releases/tag/v1.3.3) — 2026-09-06

Bugfix — library safety, map interaction, scan/analyze reliability.

- Empty / missing folders no longer wipe the library on scan
- Sky pan vs pin: empty-space pans stay pans; drag-to-pin only from a tight press on the star
- Safer quit during analyze
- Pin confidence / notes survive rescan upserts
- Analyze restarts if new unanalyzed tracks appear mid-run
- Listen nudge credits finish after natural crossfade
- Remain time, `added_at`, search disambiguation, and worker `deleteLater` fixes

## [1.3.2](https://github.com/dark1ltg/Meridian/releases/tag/v1.3.2) — 2026-09-06

- Pytest suite and smoke scripts
- AppImage excludes pytest / numpy tests from the bundle

## [1.3.1](https://github.com/dark1ltg/Meridian/releases/tag/v1.3.1) — 2026-09-06

- Sky-mode star drag-to-pin fix

## [1.3.0](https://github.com/dark1ltg/Meridian/releases/tag/v1.3.0) — 2026-09-06

- Confidence polish and library/genre percentile rescale (pins stay put)
