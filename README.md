# Meridian

Local, offline Linux music player built with Qt 6 (PySide6). Your library is a **mood map**. The queue is a **context-aware Eisenhower matrix**, not a folder list.

## Ideas

**Mood map** — tracks sit on a 2D field: *shadow → glow* (valence) and *still → kinetic* (energy). Drag the dashed **lens** to say where you want to be. Scroll to resize it (smaller lens = tighter matrix/queue neighborhood). Drag a star to pin a track’s mood forever.

**Eisenhower listen matrix**

| | Urgent (fits *now*) | Not urgent |
|---|---|---|
| **Important** | **NOW** — play this | **DEEP** — keep close |
| **Not important** | **FILL** — background pulse | **SHELF** — park it |

Importance comes from mood fit, loves, and play history. Urgency comes from the lens, time of day, session skips, and tracks you pulled in by hand.

**Context-aware queue** — rebuilt from the lens, clock band (Dawn / Day / Dusk / Night), and mode:

- **Focus** — tighter mid-energy
- **Wander** — follow the map
- **Charge** — kinetic bias
- **Dim** — night gravity

Everything stays on disk. No accounts, no streaming.

## Run from source

Needs system PySide6 (Qt 6) plus a venv for mutagen/numpy/aubio:

```bash
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install mutagen numpy aubio
bash scripts/run.sh
```

`aubio` needs the native library available (e.g. Arch/CachyOS: `sudo pacman -S aubio`). Mood analysis still works without it, but tempo/onset features are skipped.

Add folders with **Add library folder**. `~/Music` is scanned on first launch if it exists.

## AppImage

```bash
bash packaging/build-appimage.sh
```

Output: `dist/Meridian-$(uname -m).AppImage`

Needs `ffmpeg` on PATH for mood analysis (waveform energy / brightness). Playback uses Qt Multimedia. AppImage builds also bundle **aubio** for tempo/onset when the venv has it installed.

## Shortcuts

- Space — play / pause
- Ctrl+Left / Ctrl+Right — previous / next
- Double-click a star, matrix row, or queue row to play
- Heart on the transport to mark a track important

## License

Meridian is free software licensed under the **GNU General Public License v3.0**.
See [LICENSE](LICENSE) / [COPYING](COPYING).

Redistributed components are listed in [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).
Ubuntu fonts ship under the Ubuntu Font Licence 1.0 in `resources/fonts/`.
AppImage builds install these texts under `usr/share/doc/meridian/` together with
[SOURCE_OFFER.txt](SOURCE_OFFER.txt) (GPLv3 corresponding-source offer).
