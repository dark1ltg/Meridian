# Documentation

Extra guides for how Meridian listens to your files and puts them on the mood map.

The [main README](../README.md) is the short “what is this / how do I run it” page.  
Release history is in [CHANGELOG.md](../CHANGELOG.md).

## System requirements (release AppImage)

| | |
|---|---|
| **Baseline OS** | Ubuntu 24.04 LTS (x86_64), or equivalent |
| **glibc** | **2.38+** required (Ubuntu 24.04 has **2.39**) |
| **Host tools** | `ffmpeg` for mood analysis; `x264` / `libx264` for H.264 via Qt’s FFmpeg plugin |

Older glibc (e.g. AlmaLinux 9 / 2.34) will not run the release AppImage. AlmaLinux 10 (glibc 2.39) matches the baseline. Build with `packaging/build-appimage-ubuntu2404.sh` for that target.

| Guide | In plain words |
|---|---|
| [How Meridian listens](audio-analysis-pipeline.md) | How it takes a short listen of each song |
| [How stars get placed](placement-pipeline.md) | How that listen (plus tags) becomes a spot on the map |

Screenshots for the README are in [`screenshots/`](screenshots/).
