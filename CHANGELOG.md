# Changelog

All notable Meridian releases are listed here. Download AppImages from [Releases](https://github.com/dark1ltg/Meridian/releases).

## [1.3.5](https://github.com/dark1ltg/Meridian/releases/tag/v1.3.5) — 2026-09-06

Richer acoustic mood cues from the existing single PCM decode (items 2–11; no distributed track sampling), placement fixes, and desktop integration.

### Acoustic profile
- Multi-band frequency energy and spectral flux from the current FFT/PCM path
- RMS dynamics (mean, variation, peak, range, trend) and onset density/burstiness/consistency
- Nonlinear brightness mapping; confidence reflects spectral/rhythm stability
- Local-window aggregation inside the decode; map remains Shadow↔Glow / Still↔Kinetic
- Pins, metadata, and decode budget unchanged (still ~one FFmpeg, ~28s mono @ 11025 Hz)

### Placement fixes
- Soft genre+BPM: tagged BPM no longer undoes the soft PCM energy envelope
- Quiet near-floor hiss no longer maps as Glow; bass darkness counted once via band glow
- Brightness contributes to Shadow↔Glow only (not Still↔Kinetic)
- Relative spectral flux with log mapping — steady / evolving / noisy stay distinct

### Desktop / AppImage
- Freedesktop `.desktop`, hicolor icons (16–512 + SVG), AppStream metainfo
- `Meridian-*.AppImage --install` / `--uninstall` registers a normal menu entry under `~/.local/share`
- AppImage does not ship `libx264` (GPL-2.0-only); host `x264`/`libx264` is used for H.264 via Qt’s FFmpeg plugin
- Startup warning when host `libx264` is missing under the FFmpeg media backend
- Licence compliance pack: full LGPL-3/GPL texts for Qt, `BUILD_LIBRARIES.txt` inventory, expanded `SOURCE_OFFER` for bundled GPL libs

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
