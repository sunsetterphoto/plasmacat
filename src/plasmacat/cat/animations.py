"""Animation metadata: per-state playback settings for SPRITES frames."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Animation:
    fps: float
    loop: bool = True


ANIMATIONS: dict[str, Animation] = {
    "stand": Animation(fps=0.8),
    "walk": Animation(fps=8),
    "run": Animation(fps=12),
    "jump": Animation(fps=1, loop=False),
    "sit": Animation(fps=2),
    "sit_blink": Animation(fps=1, loop=False),
    "beg": Animation(fps=3),
    "groom": Animation(fps=2),
    "ear_fold": Animation(fps=1, loop=False),
    "lick_paw": Animation(fps=5),  # 2 frames = 2.5 lick cycles/s
    "eat": Animation(fps=4),
    "sleep": Animation(fps=1),
    "crouch": Animation(fps=2),
    "scratch": Animation(fps=3),
    "scratch_self": Animation(fps=3),
    "rub": Animation(fps=2),
    "enjoy": Animation(fps=2),   # 4 frames: slow-blink cycle (~2 s)
    "tailwrap": Animation(fps=2),
    # P24 realism pack
    "loaf": Animation(fps=1.5),        # tail-tip flick
    "stretch": Animation(fps=2, loop=False),
    "yawn": Animation(fps=2, loop=False),
    "knead": Animation(fps=3),         # alternating paw presses
    "sleep_belly": Animation(fps=1),   # breathing
    "wiggle": Animation(fps=10),       # fast pre-pounce butt wiggle
    "tail_lash": Animation(fps=4),     # annoyed whip
    "alert": Animation(fps=1.5),       # tense, micro head perk
    "squat": Animation(fps=1.5),       # litter hunch, tail sways
    "cover": Animation(fps=4),         # scraping strokes
    "drink": Animation(fps=3),         # tongue laps
    "watch": Animation(fps=0.5),       # head tilt every ~2 s
    # P25
    "retch": Animation(fps=6, loop=False),   # convulsive lurching
    "box_peek": Animation(fps=1.5),          # ear twitch over the box rim
    # P26
    "paw_bat": Animation(fps=4, loop=False),  # raise -> swat
}

# mood-tail variants share the base state's timing
for _base in ("stand", "walk"):
    for _variant in ("mid", "low"):
        ANIMATIONS[f"{_base}:{_variant}"] = ANIMATIONS[_base]
