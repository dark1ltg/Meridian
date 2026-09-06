# Meridian

[![Release](https://img.shields.io/github/v/release/dark1ltg/Meridian?label=release&color=e8b86d)](https://github.com/dark1ltg/Meridian/releases/latest)
**Current release: [1.3.5](https://github.com/dark1ltg/Meridian/releases/tag/v1.3.5)** (`v1.3.5`) · [Changelog](CHANGELOG.md)

**Your library is a night sky. Navigate by feel.**

Meridian is a local, offline Linux music player that charts every track as a star on a mood map — shadow to glow, still to kinetic. Aim the lens where you want to be. Discover what was already on your disk, by atmosphere instead of folders. No accounts. No streaming.

![Meridian overview](docs/screenshots/01-overview.png)

<p align="center">
  <img src="docs/screenshots/02-mood-map.png" alt="Mood map with selection lens" width="48%" />
  &nbsp;
  <img src="docs/screenshots/03-matrix-queue.png" alt="Listen matrix and context queue" width="48%" />
</p>

## What's new in 1.3.5

Richer acoustic placement from the same decode budget (no extra FFmpeg regions):

- Multi-band energy, spectral flux, RMS dynamics, and onset consistency/burstiness
- Soft genre+BPM paths keep tagged tempo from blowing past the soft energy clamp
- Quieter hiss stays near-neutral on Glow; bass darkness is counted once; brightness stays on Shadow↔Glow
- Relative spectral flux separates steady vs busy material without saturating
- AppImage installs like a normal app: `--install` / `--uninstall` (menu entry + icons)

Full notes: [CHANGELOG](CHANGELOG.md)

## What's new in 1.3.4

Queue and mood-map reliability release. Highlights:

- Queue no longer freezes on missing/deleted files; failed analyzes cannot loop forever
- Crossfade skip credits the track you left, not the one fading in
- Lens ring matches the real selection (including mode radius); trackpad lens scroll works
- Pinning stays stable during refreshes; double-click empty space returns to the full sky

Full notes: [v1.3.4 release](https://github.com/dark1ltg/Meridian/releases/tag/v1.3.4) · [CHANGELOG](CHANGELOG.md)

## Why Meridian

Most players ask *what album next*. Meridian asks *where do you want to be*.

- **Shadow → Glow** — darker to brighter emotional color  
- **Still → Kinetic** — calm to driving energy  
- A **lens** you drag and resize (scroll) chooses the neighborhood the queue pulls from  
- **Pinch** to dive from the full night sky into a local cluster; **Ctrl+scroll** zooms; drag empty space to pan; double-click empty to return to the sky  
- Large libraries stay fluid — the sky is baked into a single starfield texture and composited with OpenGL when available  
- Stars you move stay **pinned** so your sense of a track can override the analysis  
- **Search** by title, artist, or album — pick a hit to snap the lens there and play  
- Playback always **crossfades** (~3s) between tracks — queue advances, skips, matrix pulls, and double-clicks  

Under the hood, Meridian reads tags, samples short waveforms (via `ffmpeg`), and uses **aubio** for tempo and onset cues so placements stay musical without a cloud model. Stars show a **graduated confidence** score (and short evidence notes on hover); after analyze, moods get a light **library/genre percentile** nudge so neighbors rank relative to *your* collection — pins stay put.

## How listening works

### Mood map
Every track is a star on the map. Click a star to snap the lens; **drag a star to pin** its mood. Scroll to tighten or widen the lens (queue neighborhood) — the ring matches the mood-space area the queue uses (modes can scale that radius).

**Pinch** (or Ctrl+scroll) zooms from the full sky into a neighborhood — chrome fades, nearby tracks pick up glow and names, and zoom bias pulls toward clusters under your fingers. Drag empty space to pan. Double-click empty space to show the full map again (double-click a star core to play).

Thousands of tracks stay smooth because the overview is one cached starfield; zooming in loads interactive stars in the viewport. From the full sky: **click** a star to snap the lens; **drag on the star** to pin (empty space still pans).

### Eisenhower listen matrix

| | Fits the lens *now* | Not urgent |
|---|---|---|
| **Important** | **NOW** — play this | **DEEP** — keep close |
| **Not important** | **FILL** — background pulse | **SHELF** — park it |

Importance comes from mood fit, loves, and play history. Urgency comes from the lens, clock band, skips, and tracks you pull in by hand.

### Context queue
The queue replenishes from the lens, clock, and matrix when it runs dry. Hit **Play** (or Space) with nothing loaded and Meridian starts the context queue from the top. Modes shape the gravity:

| Mode | Intent |
|---|---|
| **Focus** | Steady mid-energy, fewer surprises |
| **Wander** | Follow the map |
| **Charge** | High kinetic bias |
| **Dim** | Low light, low pulse — night gravity |

Clock bands (**Dawn / Day / Dusk / Night**) nudge the target without overriding the lens you set.

### Search
Need a known track without hunting the sky? Use the header search (or **Ctrl+F**). Type part of a title, artist, or album — results appear as you type. Choosing one **snaps the lens** to that track’s mood and starts playback, so the map and queue stay oriented around what you just found.

### Crossfade
Natural advances, skips, and manual jumps always crossfade (~3s) between tracks — no toggle. Softens cuts while the queue and lens still decide *what* comes next.

## Get Meridian

### AppImage (recommended)

**Latest:** [Meridian 1.3.5](https://github.com/dark1ltg/Meridian/releases/tag/v1.3.5) — download `Meridian-x86_64.AppImage` from [Releases](https://github.com/dark1ltg/Meridian/releases/latest).

```bash
chmod +x Meridian-x86_64.AppImage
./Meridian-x86_64.AppImage --install    # menu entry + icons under ~/.local/share
./Meridian-x86_64.AppImage              # or launch from your app menu
```

`--uninstall` removes the menu entry and icons. AppImageLauncher / appimaged also work if you prefer those.

Install **`ffmpeg`** on the host for mood analysis. Playback uses Qt Multimedia. The mood map prefers desktop OpenGL (NVIDIA / AMD / Intel) and falls back to software if needed.

### Run from source

Needs system PySide6 (Qt 6) plus a venv for analysis libraries:

```bash
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install mutagen numpy aubio
bash scripts/run.sh
```

`aubio` needs the native library (e.g. Arch/CachyOS: `sudo pacman -S aubio`). Without it, Meridian still runs; tempo/onset features are skipped.

Add folders with **Add library folder**. `~/Music` is scanned on first launch if it exists. **Rescan** force-refreshes tags and re-analyzes every track in your library folders.

### Tests

```bash
.venv/bin/python -m pip install -r requirements-dev.txt   # pytest (dev only)
bash scripts/run_tests.sh -v     # pytest suite
bash scripts/smoke_test.sh       # same checks, no pytest required
```

### Build the AppImage yourself

```bash
bash packaging/build-appimage.sh
```

Output: `dist/Meridian-$(uname -m).AppImage`

Then optionally:

```bash
./dist/Meridian-$(uname -m).AppImage --install
```

## Shortcuts

| Key | Action |
|---|---|
| Space / Play | Play / pause — or start the context queue if nothing is loaded |
| Ctrl+F | Focus search (title, artist, album) |
| Ctrl+Left / Ctrl+Right | Previous / next |
| Double-click star, matrix row, or queue row | Play |
| Pinch / Ctrl+scroll on map | Zoom night sky ↔ cluster |
| Scroll on map | Resize lens |
| Double-click empty map | Reset to full sky |
| Double-click star (or tight sky core) | Play that track |
| Heart (transport) | Mark a track important |

## License

Meridian is free software under the **GNU General Public License v3.0**.  
See [LICENSE](LICENSE) / [COPYING](COPYING).

Release history: [CHANGELOG.md](CHANGELOG.md) · [GitHub Releases](https://github.com/dark1ltg/Meridian/releases/latest)

Third-party components are listed in [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).  
Ubuntu fonts ship under the Ubuntu Font Licence 1.0 in `resources/fonts/`.  
AppImage builds include these texts under `usr/share/doc/meridian/` with [SOURCE_OFFER.txt](SOURCE_OFFER.txt).
