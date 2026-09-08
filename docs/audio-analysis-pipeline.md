# How Meridian listens (audio analysis)

This guide explains, in plain language, how Meridian takes a **short listen** of each track on your disk.  
It does not need the internet. It does not stream music.

For how that listen turns into a star on the map, see [How stars get placed](placement-pipeline.md).

## The big idea

Meridian does **not** listen to the whole song every time.

It takes about **28 seconds** of sound (mono, lower quality on purpose so it’s fast), usually from the **middle** of the track.  
Long songs get **two shorter tastes** (about 14 + 14 seconds) that still add up to the same 28-second budget — not extra work.

From that snippet it guesses:

- **Shadow ↔ Glow** — darker / softer vs brighter / more open  
- **Still ↔ Kinetic** — calm vs moving / punchy  

That’s the “feel” it will use on the mood map.

## Step by step

### 1. Import (scan)

Meridian walks your music folders and reads the **labels** on the files (title, artist, genre, and so on).

- It does **not** do the deep listen yet.  
- It may park a rough guess on the map from the genre/folder name.  
- It marks the track as “still needs a real listen.”

### 2. A guess from the sticker (tags)

Before listening, it looks at:

- Genre tags  
- Folder names (sometimes more honest than the tag)  
- Year, loudness tags if present  
- Mood-ish words in titles  

That gives a starting “neighborhood” — like “this is probably metal-energy” or “probably chill.”

### 3. The short listen (`ffmpeg`)

It asks your computer’s `ffmpeg` for that ~28s of audio.

- If the first grab is silence, it tries another spot.  
- On long tracks, two tastes are compared. If the intro and the drop feel like different songs, it keeps the **steadier** taste instead of averaging them into something fake in the middle.

If **aubio** is installed, it also hears tempo / beat-ish clues. Without aubio, Meridian still works; it just has less rhythm info.

### 4. What it measures in that snippet

Still on that same short buffer (no extra “go fetch more audio”):

- Bright vs dark tone  
- Bass-heavy vs treble-heavy  
- Steady tone vs noisy / hissy  
- How much the sound changes over time  
- How even or punchy the loudness is  
- How regular or jumpy the hits are  

Then it squashes all of that into the two map directions: **Glow** and **Kinetic**.

Simple rules of thumb Meridian tries to follow:

- Quiet hiss should **not** look bright and happy.  
- Brightness belongs on Glow, not “fake energy.”  
- Weird / jumpy timing is a **texture**, not automatic “this is energetic.”  
- Uneven, punchy loudness feels more Kinetic than flat, even loudness.

### 5. Save the result

It stores the map position, a confidence note (“how sure are we”), and a few leftover clues (brightness, flux, steady rhythm) for later tidy-ups — **without** listening again.

### 6. Tidy the whole library (after many tracks)

When a batch of listens finishes, Meridian does light housekeeping with **no more audio decode**:

- Nudge unpinned songs a little toward their album/artist neighbors  
- Gently unstick songs that landed on top of each other  
- Stretch positions so your collection uses the map more evenly  

If you **pinned** a star, that pin stays. Analyze will not drag it.

## What this is *not*

- Not “pro studio analysis of the full album.”  
- Not surround / 3D spatial audio. “Spatial” here means **where it sits on the mood map**.  
- Not a promise that every song will feel perfectly placed — short listens can miss weird intros or long builds.

## Where the code lives (if you care)

| File | Job |
|---|---|
| `meridian/scanner.py` | Import worker + analyze worker |
| `meridian/features.py` | Tags, short decode, glue |
| `meridian/acoustic.py` | Measuring the snippet |
| `meridian/library.py` | Saving moods and tidy-ups |
