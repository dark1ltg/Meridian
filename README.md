# Meridian

[![Release](https://img.shields.io/github/v/release/dark1ltg/Meridian?label=release&color=e8b86d)](https://github.com/dark1ltg/Meridian/releases/latest)

**Your library is a night sky. Navigate by feel.**

Meridian is a local, offline Linux music player. Every track becomes a star on a mood map — **Shadow → Glow**, **Still → Kinetic**. Aim a lens where you want to be, and a context queue builds from that neighborhood. No accounts. No streaming. Your files stay on your disk.

![Meridian overview](docs/screenshots/01-overview.png)

<p align="center">
  <img src="docs/screenshots/02-mood-map.png" alt="Mood map with selection lens" width="48%" />
  &nbsp;
  <img src="docs/screenshots/03-matrix-queue.png" alt="Listen matrix and context queue" width="48%" />
</p>

## Features

- **Mood map** — browse by atmosphere instead of folders; drag the lens, scroll to resize, pinch to zoom
- **Listen matrix** — nearby tracks sorted into NOW / DEEP / FILL / SHELF
- **Context queue** — replenishes from the lens, time of day, and listening mode (Focus, Wander, Charge, Dim)
- **Local analysis** — tags plus a short mid-track waveform (`ffmpeg`); optional **aubio** for tempo/onset cues
- **Pins & search** — drag a star to lock its mood; search by title, artist, album, or path
- **Crossfade** — smooth advances while something is already playing

## Get Meridian

### AppImage (recommended)

Download **`Meridian-x86_64.AppImage`** from the [latest release](https://github.com/dark1ltg/Meridian/releases/latest).

```bash
chmod +x Meridian-x86_64.AppImage
./Meridian-x86_64.AppImage --install    # menu entry + icons under ~/.local/share
./Meridian-x86_64.AppImage              # or launch from your app menu
```

`--uninstall` removes the menu entry and icons.

Install host **`ffmpeg`** for mood analysis. For H.264 through Qt’s FFmpeg plugin, also install system **`x264` / `libx264`** (not bundled). Meridian warns if that library is missing.

### Run from source

Needs system PySide6 (Qt 6) plus a venv for analysis libraries:

```bash
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install mutagen numpy aubio
bash scripts/run.sh
```

`aubio` needs the native library (e.g. Arch/CachyOS: `sudo pacman -S aubio`). Without it, Meridian still runs; tempo/onset cues are skipped.

**Add library folder** imports music. `~/Music` is scanned on first launch if it exists. **Rescan** refreshes tags and re-analyzes every track.

### Build the AppImage

```bash
bash packaging/build-appimage.sh
./dist/Meridian-$(uname -m).AppImage --install   # optional
```

## Quick use

| Action | How |
|---|---|
| Aim the queue | Drag the lens on the mood map |
| Resize neighborhood | Scroll on the map |
| Zoom / pan | Pinch or Ctrl+scroll; drag empty space |
| Pin a mood | Drag a star |
| Play | Double-click a star, matrix row, or queue row; Space plays/pauses |
| Search | Ctrl+F |

Release history: [CHANGELOG.md](CHANGELOG.md) · [GitHub Releases](https://github.com/dark1ltg/Meridian/releases)

## Documentation

How Meridian works under the hood (plain language):

- [How Meridian listens](docs/audio-analysis-pipeline.md) — the short listen of each track  
- [How stars get placed](docs/placement-pipeline.md) — sticker + listen → mood map  
- [Docs index](docs/README.md)

## License

Meridian is free software under the **GNU General Public License v3.0**.  
See [LICENSE](LICENSE) / [COPYING](COPYING).

Third-party components: [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).  
Ubuntu fonts ship under the Ubuntu Font Licence 1.0 in `resources/fonts/`.  
AppImage builds include notices under `usr/share/doc/meridian/` with [SOURCE_OFFER.txt](SOURCE_OFFER.txt).
