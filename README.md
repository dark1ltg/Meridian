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

Richer acoustic placement from the same decode budget, desktop install, and a reliability pass (AppImage refreshed 2026-09-07):

- Multi-band energy, spectral flux, RMS dynamics, and onset consistency/burstiness
- Soft genre+BPM keeps tagged tempo inside the soft energy clamp
- Quiet hiss stays near-neutral on Glow; bass darkness counted once; brightness stays on Shadow↔Glow
- Relative spectral flux separates steady vs busy material without saturating
- Safer scan (no empty/partial wipe; out-of-root symlinks ignored; failed scan stays failed)
- Honest crossfade play/skip credits; tiny libraries don’t loop the just-finished track
- Lens drag and pin update the map without rebuilding the context queue mid-listen
- AppImage `--install` / `--uninstall`; sticky host `libx264` tip when H.264 may fail

Earlier notes: [1.3.4](https://github.com/dark1ltg/Meridian/releases/tag/v1.3.4) · [CHANGELOG](CHANGELOG.md)

## Why Meridian

Most players ask *what album next*. Meridian asks *where do you want to be*.

- **Shadow → Glow** / **Still → Kinetic** — emotional color and energy on one map  
- A **lens** you drag and resize (scroll) chooses the neighborhood the queue pulls from — modes can tighten or widen that radius  
- **Pinch** / **Ctrl+scroll** zooms into a cluster; drag empty space to pan; double-click empty to return to the full sky  
- Large libraries stay fluid — overview is one cached starfield (OpenGL when available)  
- Stars you move stay **pinned**; analysis, album/artist smoothing, and listen nudges leave pins alone  
- **Search** by title, artist, album, or path — pick a hit to snap the lens and play  
- While something is already playing, advances **crossfade** (about 3s, shorter on short tracks)

Under the hood: tags + a short mid-track waveform (`ffmpeg`) + optional **aubio** tempo/onset cues. Stars show **confidence** and a short evidence note on hover. After analyze, moods get a light **library/genre percentile** rescale so neighbors rank relative to *your* collection.

## How listening works

### Mood map
Click a star to snap the lens; **drag a star to pin** its mood (pin refreshes the map without wiping the context queue). Scroll resizes the lens (queue neighborhood). Pinch / Ctrl+scroll zooms — chrome fades, nearby tracks pick up glow and names. Drag empty space to pan. Double-click empty space for the full sky; double-click a tight star core to play.

From the full sky: **click** snaps the lens; **drag on the star** pins (empty space still pans). Zooming in loads interactive stars in the viewport. Dragging a star that disappears mid-refresh no longer crashes the map.

### Listen matrix

Nearby tracks are sorted into four buckets by how close they are to the lens (and a bit of love/play history):

| | Closer to the lens | Farther out |
|---|---|---|
| **More important** | **NOW** — play this | **DEEP** — keep close |
| **Less important** | **FILL** — background pulse | **SHELF** — park it |

Importance leans on mood fit, loves, and play history (skips lower importance). Urgency is mostly lens distance, clock band, mode energy bias, and tracks you pull in by hand. Matrix pulls play once, then drop.

### Context queue
The queue replenishes from the lens, clock, and matrix when it runs dry. **Play** / Space with nothing loaded starts the queue from the top. Moving the lens (or pinning a star) updates ranking without rebuilding the queue mid-listen. When the queue refills, the track that just finished is kept out so tiny libraries don’t hard-cut restart the same song.

| Mode | Intent |
|---|---|
| **Focus** | Steady mid-energy, fewer surprises (tighter lens) |
| **Wander** | Follow the lens; let the map wander (wider lens) |
| **Charge** | High kinetic bias |
| **Dim** | Low light, low pulse — night gravity |

Clock bands (**Dawn / Day / Dusk / Night**) nudge the target without replacing the lens.

Finishes and skips can gently nudge **unpinned** moods toward the current lens; pins stay put. After analyze, album/artist neighbors also get a light mood smooth before the library percentile pass.

### Search
Header search or **Ctrl+F**. Results as you type; choosing one snaps the lens and starts playback.

### Crossfade
When you are already playing, queue advances, skips, and manual jumps crossfade (default ~3s; shorter when the track is short). The first start of a track is a clean cut — no toggle. Play counts land after a hard cut or when a fade settles; Next/Prev during a fade credit the outgoing track. Short tracks that end during a fade still advance afterward.

## Get Meridian

### AppImage (recommended)

**Latest:** [Meridian 1.3.5](https://github.com/dark1ltg/Meridian/releases/tag/v1.3.5) — `Meridian-x86_64.AppImage` from [Releases](https://github.com/dark1ltg/Meridian/releases/latest).

```bash
chmod +x Meridian-x86_64.AppImage
./Meridian-x86_64.AppImage --install    # menu entry + icons under ~/.local/share
./Meridian-x86_64.AppImage              # or launch from your app menu
```

`--uninstall` removes the menu entry and icons. AppImageLauncher / appimaged also work if you prefer those.

Install host **`ffmpeg`** for mood analysis. For H.264 playback through Qt’s FFmpeg plugin, also install the system **`x264` / `libx264`** package (Meridian does not ship libx264). If that library is missing, Meridian warns at startup and keeps a sticky tip in the status line so scan/analyze messages don’t bury it. Playback uses Qt Multimedia. The mood map prefers desktop OpenGL and falls back to software if needed.

### Run from source

Needs system PySide6 (Qt 6) plus a venv for analysis libraries:

```bash
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install mutagen numpy aubio
bash scripts/run.sh
```

`aubio` needs the native library (e.g. Arch/CachyOS: `sudo pacman -S aubio`). Without it, Meridian still runs; tempo/onset features are skipped.

**Add library folder** imports folders. `~/Music` is scanned on first launch if it exists. **Rescan** refreshes tags and re-analyzes every track in your library folders. Scans never wipe the library on empty or half-readable folders; only fully walked roots prune missing files. Symlinks that point outside a library root are ignored.

### Tests

```bash
.venv/bin/python -m pip install -r requirements-dev.txt   # pytest (dev only)
bash scripts/run_tests.sh -v
bash scripts/smoke_test.sh
```

### Build the AppImage yourself

```bash
bash packaging/build-appimage.sh
./dist/Meridian-$(uname -m).AppImage --install   # optional
```

## Shortcuts

| Key | Action |
|---|---|
| Space / Play | Play / pause — or start the context queue if nothing is loaded |
| Ctrl+F | Focus search (title, artist, album, path) |
| Ctrl+Left / Ctrl+Right | Previous / next |
| Double-click star, matrix row, or queue row | Play |
| Pinch / Ctrl+scroll on map | Zoom night sky ↔ cluster |
| Scroll on map | Resize lens |
| Double-click empty map | Reset to full sky |
| Double-click star (tight core) | Play that track |
| Heart (transport) | Mark a track important |

## License

Meridian is free software under the **GNU General Public License v3.0**.  
See [LICENSE](LICENSE) / [COPYING](COPYING).

Release history: [CHANGELOG.md](CHANGELOG.md) · [GitHub Releases](https://github.com/dark1ltg/Meridian/releases/latest)

Third-party components: [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).  
Ubuntu fonts ship under the Ubuntu Font Licence 1.0 in `resources/fonts/`.  
AppImage builds include these under `usr/share/doc/meridian/` with [SOURCE_OFFER.txt](SOURCE_OFFER.txt).
