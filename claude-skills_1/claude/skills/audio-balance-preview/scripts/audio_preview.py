#!/usr/bin/env python3
"""
audio_preview.py — quickly A/B a sound volume ratio without booting the game.

Usage:
    python audio_preview.py --bed assets/game.mp3:0.2 \
                             --oneshot assets/hit_sound.mp3:0.6 \
                             --oneshot assets/pie_sound.mp3:0.2 \
                             --duration 6

Run from the repo root (paths are relative to it), or pass absolute paths.
"""
import argparse
import os
import sys
import time

try:
    import pygame
except ImportError:
    sys.exit(
        "pygame is required (it's already a project dependency). "
        "Install it with: pip install pygame"
    )


def parse_spec(spec):
    """Split 'path:volume' into (path, float_volume)."""
    if ":" not in spec:
        raise argparse.ArgumentTypeError(
            f"expected PATH:VOLUME, got {spec!r}"
        )
    path, _, vol = spec.rpartition(":")
    try:
        volume = float(vol)
    except ValueError:
        raise argparse.ArgumentTypeError(f"volume must be a number, got {vol!r}")
    if not 0.0 <= volume <= 1.0:
        raise argparse.ArgumentTypeError("volume must be between 0.0 and 1.0")
    if not os.path.exists(path):
        raise argparse.ArgumentTypeError(f"asset not found: {path}")
    return path, volume


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bed", type=parse_spec, default=None,
        help="Looping background asset as PATH:VOLUME (e.g. assets/game.mp3:0.2)"
    )
    parser.add_argument(
        "--oneshot", type=parse_spec, action="append", default=[],
        help="One-shot effect as PATH:VOLUME. Repeatable.",
    )
    parser.add_argument(
        "--duration", type=float, default=5.0,
        help="Total seconds to play before exiting (default: 5)",
    )
    parser.add_argument(
        "--oneshot-delay", type=float, default=1.0,
        help="Seconds after start before one-shots fire (default: 1.0)",
    )
    args = parser.parse_args()

    if not args.bed and not args.oneshot:
        parser.error("pass at least one --bed or --oneshot")

    pygame.mixer.init()

    if args.bed:
        path, volume = args.bed
        print(f"[bed]     {path}  volume={volume}")
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(volume)
        pygame.mixer.music.play(-1)

    loaded_oneshots = []
    for path, volume in args.oneshot:
        sound = pygame.mixer.Sound(path)
        sound.set_volume(volume)
        loaded_oneshots.append((path, volume, sound))

    start = time.time()
    fired = False
    try:
        while time.time() - start < args.duration:
            if not fired and time.time() - start >= args.oneshot_delay:
                for path, volume, sound in loaded_oneshots:
                    print(f"[oneshot] {path}  volume={volume}")
                    sound.play()
                fired = True
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        pygame.mixer.music.stop()
        pygame.mixer.quit()

    print("done")


if __name__ == "__main__":
    main()
