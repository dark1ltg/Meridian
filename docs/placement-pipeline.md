# How stars get placed (placement)

This guide explains, in plain language, how Meridian decides **where a song’s star sits** on the mood map.

For how it takes the short listen, see [How Meridian listens](audio-analysis-pipeline.md).

## The map in one sentence

- Left ↔ right: **Shadow ↔ Glow** (darker/softer vs brighter/more open)  
- Down ↔ up: **Still ↔ Kinetic** (calm vs moving)

Every track ends up with two numbers that mean those directions. That’s placement.

## The big idea

Placement is a **compromise**:

1. What the **sticker / folder** suggests (genre, path, words)  
2. What the **short listen** actually sounded like  

Meridian decides **how much to trust each side**.  
Good labels keep songs in a sensible neighborhood. A clear, steady listen can still pull a wrong label toward the truth. A muddy listen does **not** get to boss the map around.

## Step by step

### 1. Start with the sticker guess

From tags and folders, Meridian picks a starting spot — the “genre cloud.”

### 2. Compare to the short listen

After analysis, it has a second opinion from the waveform.

It asks: *How far apart are the sticker guess and the listen?*  
And: *Did the listen sound steady and trustworthy, or shaky?*

### 3. Blend the two (the important part)

Depending on the file, Meridian uses different rules:

**Well-tagged song with a real BPM**  
Stay near the sticker. Only allow a **small** nudge from the listen.  
If the listen is clear, steady, and *obviously* elsewhere, allow a **bigger** nudge — especially on Glow (brightness), a bit less on Kinetic (pace often matches genre/BPM already).

**Genre known, but BPM missing / weak**  
Mix sticker and listen, but don’t let the listen yank the star too far from the genre neighborhood.

**Messy / empty tags (common on raw dumps)**  
Trust the listen much more.

**Tag says one genre, folder says another** (example: tag “jazz”, folder “DrumAndBass”)  
That means the **labels are arguing**, not that the listen is automatically right.  
Meridian **trusts the labels less**. The listen only gets as much of that freed trust as it earned (steady listen → more; shaky listen → little).  
It does **not** mean “ignore everything and max out the waveform.”

### 4. Tiny tempo tweak

BPM can give Kinetic a small push.  
If the tag tempo and the heard tempo disagree, Meridian picks carefully (steady rhythm → heard tempo can win the nudge; otherwise the tag stays in charge).  
On the “stay near the sticker” path, tempo still can’t kick the star outside that soft neighborhood.

### 5. How sure are we?

Meridian stores a confidence note (tag? path? listen? conflict?).  
Low confidence means “take this with a grain of salt” in the UI — it doesn’t invent a third map axis.

### 6. Save (pins stay put)

The star’s position is written to the library.  
If you dragged and **pinned** a star, analyze will not overwrite that pin.

### 7. Light tidy after a big analyze

Without listening again:

- Soft pull toward album/artist neighbors (unpinned only)  
- Unstick clones that stacked on the same spot  
- Spread the sky a bit relative to *your* collection  

## How listening feeds placement

| From the short listen | What placement does with it |
|---|---|
| “Sounds bright / dark” | Pushes Glow |
| “Sounds calm / punchy” | Pushes Kinetic |
| “Listen was steady” | Allowed to move the star more |
| “Listen was shaky / intro≠drop” | Keep the sticker closer; don’t over-trust the waveform |
| Leftover brightness / change / steady-beat clues | Later tidy-ups and Focus ranking — not a second map |

**One line:** listening *feels* the file; placement decides *how far that feeling may move the star* away from the label.

## What placement is not

- Not “always matches your personal taste.” Feel is human and subjective.  
- Not a full-song deep dive (only that short listen).  
- Not the lens chasing whatever is playing — you (or search) move the lens.  
- Not permission for bad tags to be ignored forever, or for noisy audio to rewrite the whole sky.

## After the star is placed

While you listen, finishes and skips can gently nudge **unpinned** stars relative to where your lens is.  
The matrix and context queue use those positions to pick “what’s near the lens” — that’s ranking, not a brand-new analyze.

## Where the code lives (if you care)

| File | Job |
|---|---|
| `meridian/features.py` | Sticker seed + blend rules |
| `meridian/acoustic.py` | Short-listen measurements |
| `meridian/library.py` | Save, tidy, listen nudges |
| `meridian/ui/mood_map.py` | Draw the stars |
| `meridian/queue_engine.py` | Queue from lens distance (uses placement; doesn’t create it) |
