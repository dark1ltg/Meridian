# Meridian

[![Release](https://img.shields.io/github/v/release/dark1ltg/Meridian?label=release&color=e8b86d)](https://github.com/dark1ltg/Meridian/releases/latest)
**Current release: [1.2](https://github.com/dark1ltg/Meridian/releases/tag/v1.2.0)** (`v1.2.0`)

**Your library is a night sky. Navigate by feel.**

Meridian is a local, offline Linux music player that charts every track as a star on a mood map — shadow to glow, still to kinetic. Aim the lens where you want to be. Discover what was already on your disk, by atmosphere instead of folders. No accounts. No streaming.

![Meridian overview](docs/screenshots/01-overview.png)

<p align="center">
  <img src="docs/screenshots/02-mood-map.png" alt="Mood map with selection lens" width="48%" />
  &nbsp;
  <img src="docs/screenshots/03-matrix-queue.png" alt="Listen matrix and context queue" width="48%" />
</p>

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

Under the hood, Meridian reads tags, samples short waveforms (via `ffmpeg`), and uses **aubio** for tempo and onset cues so placements stay musical without a cloud model.

## How listening works

### Mood map
Every track is a star on the map. Click a star to snap the lens. Scroll to tighten or widen the lens (queue neighborhood).

**Pinch** (or Ctrl+scroll) zooms from the full sky into a neighborhood — chrome fades, nearby tracks pick up glow and names, and zoom bias pulls toward clusters under your fingers. Drag empty space to pan. Double-click empty space to show the full map again.

Thousands of tracks stay smooth because the overview is one cached starfield; interactive stars appear only once you are zoomed in on a region.

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

**Latest:** [Meridian 1.2](https://github.com/dark1ltg/Meridian/releases/tag/v1.2.0) — download `Meridian-x86_64.AppImage` from [Releases](https://github.com/dark1ltg/Meridian/releases/latest).

```bash
chmod +x Meridian-x86_64.AppImage
./Meridian-x86_64.AppImage
```

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

### Build the AppImage yourself

```bash
bash packaging/build-appimage.sh
```

Output: `dist/Meridian-$(uname -m).AppImage`

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
| Heart (transport) | Mark a track important |

## License

Meridian is free software under the **GNU General Public License v3.0**.  
See [LICENSE](LICENSE) / [COPYING](COPYING).

Third-party components are listed in [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).  
Ubuntu fonts ship under the Ubuntu Font Licence 1.0 in `resources/fonts/`.  
AppImage builds include these texts under `usr/share/doc/meridian/` with [SOURCE_OFFER.txt](SOURCE_OFFER.txt).
