# Changelog

All notable Meridian releases are listed here. Download AppImages from [Releases](https://github.com/dark1ltg/Meridian/releases).

## [1.3.5](https://github.com/dark1ltg/Meridian/releases/tag/v1.3.5) — 2026-09-06 (AppImage refreshed 2026-09-08)

Richer acoustic mood cues from the existing PCM decode budget, smarter local recommendations, more honest initial placement (soft-PCM and conflict handling), desktop integration, and reliability passes for scan, matrix/context queue, crossfade accounting, quit/analyze teardown, mood map, and BPM/signal trust.

### Acoustic profile
- Multi-band frequency energy and spectral flux from the current FFT/PCM path
- RMS dynamics (mean, variation, peak, range, trend, consistency) and onset density/burstiness/consistency
- Nonlinear brightness mapping; confidence reflects spectral/rhythm stability
- Local-window aggregation inside the decode; map remains Shadow↔Glow / Still↔Kinetic
- Longer tracks use two ~14s windows (early + mid) within the same ~28s mono @ 11025 Hz budget; short tracks keep a single window
- Disagree-aware dual-window merge: strong intro/drop mismatch keeps the stabler window instead of a false middle
- Richer 2D blend from band/mid balance, flux, and energy trend; tonal vs noisy weighting (flatness pulls Glow down)
- Energy uses RMS consistency and peak; burstiness textures Kinetic only when onset structure is trustworthy
- Evidence-gated soft-PCM: stable waveform that clearly disagrees with a genre+BPM seed may move farther (Glow freer than Kinetic)
- Tag vs path genre conflict reduces metadata authority; freed weight goes to PCM only in proportion to PCM trust (not maxed)
- Structure-aware soft/genre clamps: steady rhythm + genre disagreement trusts PCM more; unstable material hugs the seed
- When tag and detected BPM conflict, energy nudge trusts detected if rhythm is steady, otherwise the tag
- Persists onset consistency, spectral flux, and brightness for Focus ranking and album spread (no re-decode)
- After album smooth, within-album acoustic spread unsticks clones using those cues (pins untouched)
- Expanded local genre seeds (phonk, hyperpop, drill, vaporwave, amapiano, city pop, and related aliases)
- Pins, metadata, and total decode budget unchanged

### Recommendations (local)
- Skip pressure (recent skips) widens the lens neighborhood, softens NOW stickiness, and steals queue slots into FILL
- Context queue soft-caps artist/album repeats (2) while alternatives exist, then relaxes to fill gaps
- Gap-fill protects the matrix mix: NOW/DEEP/FILL first (diversity on, then off); SHELF only after, with a small cap
- Mode-aware matrix mix: Focus steadier NOW/DEEP; Charge more NOW; Dim more DEEP; Wander balanced
- Finish vs skip history weights importance more strongly; listen nudges on unpinned stars are slightly stronger
- Focus mode lightly prefers tracks with steady persisted onset consistency

### Acoustic reliability
- Spurious aubio BPM on silence / near-zero onsets is rejected (needs real onset evidence)
- Tag BPM `0` / NaN is ignored — no soft-PCM shortcut, false BPM conflict, or confidence “BPM” claim
- Prefer a real tag BPM; otherwise use detected BPM (never treat `0` as present)
- Non-finite PCM (Inf/NaN) fails the signal check; mood values are sanitized before write
- Pinned tracks keep BPM through analyze (same protection as valence/energy)
- Upsert that resets `analyzed=0` clears the in-process analyze denylist so Rescan can retry

### Placement fixes
- Soft genre+BPM: tagged BPM no longer undoes the soft PCM energy envelope
- Quiet near-floor hiss no longer maps as Glow; bass darkness counted once via band glow
- Brightness contributes to Shadow↔Glow only (not Still↔Kinetic)
- Relative spectral flux with log mapping — steady / evolving / noisy stay distinct

### Library scan safety
- Empty or missing folders no longer wipe the library (`delete_missing` only after a successful walk finds audio)
- Multi-root scans: an empty sibling root (unmounted drive, empty mount) no longer prunes that root’s DB tracks just because another root still has audio
- Sparse/wrong mounts: a root is not pruned when this walk finds less than half the tracks the DB already knows under it
- Partial / unreadable trees are not pruned — only fully walked roots are eligible for cleanup
- File symlinks that resolve outside a library root are ignored; symlink directories are not descended into
- Failed scans no longer look like success (UI does not start analyze on failure)

### Queue & playback reliability
- Playback errors (corrupt/unsupported media) auto-skip and advance like missing files instead of stalling
- Outgoing-deck errors during a crossfade no longer skip the incoming track
- Corrupt/unsupported files are denylisted for the session (cleared on rescan) so they do not re-enter the context queue
- Hard-cut play credit is undone if media errors before ~500ms of progress
- Crossfade auto-advance ignores provisional short durations and never arms in the first 10s (VBR false ends)
- Spurious EndOfMedia at the start of a longer incoming track no longer ejects it when the fade settles
- Quit/rescan disconnects worker UI slots, kills in-flight ffmpeg, and keeps timed-out threads alive until they exit (no UAF)
- Context queue gap-fill no longer raids SHELF while NOW/DEEP/FILL still have unused tracks (anti-repeat yields first)
- Lens drag and star pin refresh the map **without** rebuilding the context queue mid-listen
- Scan / rescan / analyze refresh the matrix and map without replacing the live context queue
- Map star play syncs `queue_index` (or inserts like a matrix pull) so Next/Prev stay aligned
- Search snaps the lens and refreshes the Eisenhower matrix before pulling the hit
- Plan refresh and replenish both skip missing files; rebuilds keep ephemeral “play once” rows still in order
- Listen-nudge plan refreshes deferred under the play lock are flushed after unlock
- Tiny libraries no longer hard-cut restart the track that just finished (hard-exclude on replenish)
- Short tracks that end during a crossfade still advance when the fade settles
- Empty replenish after nearly-finished no longer leaves playback permanently stuck
- When the playing track is absent from a rebuilt queue, Next lands on the first row (not the second)
- Play credit is deferred until a hard cut or a settled fade; aborting a fade commits the armed incoming play
- Next during a natural end-of-track fade finish-nudges the outgoing track (never skip-credits it), then leaves the incoming under the 8s rule
- Map / matrix / search jumps use the same 8s skip-vs-finish rule as Next (not always “finished”)
- Prev during crossfade restores the outgoing track without double `play_count` or spurious finish on the next song
- Pause / seek / stop mid end-of-track fade still finish-nudges the outgoing track and commits the incoming play
- Failed analyze is denylisted in-process (with DB retries) so a poison file cannot loop the worker

### Mood map interaction
- Lens sits under live stars so tracks inside the lens stay clickable and draggable
- Starfield rebakes only when the bake fingerprint changes (fewer hitches on large libraries)
- Sky press candidates survive mid-press refreshes; core-star pin no longer pans the viewport first
- Zoomed-in clicks materialize the nearest baked star; title double-click plays the track
- Deferred lens snap so double-click empty can reset without first snapping the lens
- In-progress pins stay visible during pinch/zoom; star grid updates while dragging

### Desktop / AppImage
- Freedesktop `.desktop`, hicolor icons (16–512 + SVG), AppStream metainfo
- `Meridian-*.AppImage --install` / `--uninstall` registers a normal menu entry under `~/.local/share`
- AppImage does not ship `libx264` (GPL-2.0-only); host `x264`/`libx264` is used for H.264 via Qt’s FFmpeg plugin
- Sticky startup / status tip when host `libx264` is missing under the FFmpeg media backend
- Safer quit: longer waits for scan/analyze; do not `deleteLater` live threads; do not close SQLite under workers that outlive the wait
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
