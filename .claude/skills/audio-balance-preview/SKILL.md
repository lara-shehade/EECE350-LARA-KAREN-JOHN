---
name: audio-balance-preview
description: Preview and A/B-test the relative volume of two or more sound assets in the Πthon Arena project (e.g. background music vs. a sound effect) without launching the full game through login and lobby. Use when the user wants to tune, check, or compare sound/volume levels for assets under assets/, or mentions volume ratio, sound balance, or "does this sound too loud/quiet".
---

# Audio Balance Preview

The game sets each sound's volume as an inline magic number in `game_screen.py`
(e.g. `sound.set_volume(0.6)`). Checking whether a ratio "feels right" normally
means editing a number, then going through the full login → lobby → game flow
to hear it — this skill replaces that loop with a one-line command.

## When to use

- The user wants to compare or tune the volume of two or more assets from
  `assets/` (background music vs. an effect, or effect vs. effect).
- The user asks "is this too loud/quiet", "check the ratio", or similar.

## How to run a preview

Use `scripts/audio_preview.py`. It uses `pygame.mixer` directly — no new
dependencies — and mirrors how the game actually plays sound: one asset can
loop as a "bed" (like the background track) while others play as one-shots
on top of it, at the exact volume values you're about to put in the code.

```bash
python .claude/skills/audio-balance-preview/scripts/audio_preview.py \
    --bed assets/game.mp3:0.2 \
    --oneshot assets/hit_sound.mp3:0.6 \
    --oneshot assets/pie_sound.mp3:0.2 \
    --duration 6
```

- `--bed PATH:VOLUME` — looping background track (optional, at most one).
- `--oneshot PATH:VOLUME` — a one-shot effect, played ~1s after playback
  starts, overlapping the bed (repeatable).
- `--duration SECONDS` — how long to play before exiting (default 5).
- Volumes are 0.0–1.0, matching `pygame.mixer.Sound.set_volume` /
  `pygame.mixer.music.set_volume` directly, so a value that sounds right here
  is the value to paste into `game_screen.py`.

## Workflow

1. Ask the user which assets and current volumes they're comparing (or read
   the current values straight out of `game_screen.py` if not given).
2. Run the script with those values so the user can listen.
3. Adjust volumes based on feedback and re-run — this is the fast iteration
   loop, no game boot required.
4. Once a ratio is confirmed, update the corresponding `set_volume(...)` call
   in `game_screen.py` to match.

## Note

This script only reproduces the *volume relationship*, not the full game
context (e.g. concurrent UI sounds, music ducking). Treat it as a fast way to
narrow in on values, with a final check in-game before calling it done.
