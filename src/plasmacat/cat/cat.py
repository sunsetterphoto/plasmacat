"""The Cat entity: ties brain + body + animation state together."""

from __future__ import annotations

import random

from plasmacat.bridge.desktop import DesktopState
from plasmacat.cat.animations import ANIMATIONS
from plasmacat.cat.brain import Brain
from plasmacat.cat.physics import WALK_SPEED, CatBody


class Cat:
    def __init__(self, x: float, y: float, rng: random.Random | None = None) -> None:
        self.body = CatBody(x, y)
        self.brain = Brain(rng)
        self.anim_state = "stand"
        self.frame = 0
        self._frame_t = 0.0
        self._rng = rng or random.Random()
        self._blink_countdown = self._rng.uniform(3.0, 7.0)
        self._blink_left = 0.0

    def tick(self, dt: float, desktop: DesktopState) -> None:
        self.brain.tick(dt, self.body, desktop)
        self.body.tick(dt, desktop)
        self._update_anim(dt)
        self._update_blink(dt)

    @property
    def blink_active(self) -> bool:
        return self._blink_left > 0.0

    def _update_blink(self, dt: float) -> None:
        if self._blink_left > 0:
            self._blink_left -= dt
            return
        self._blink_countdown -= dt
        if self._blink_countdown <= 0 and self.anim_state in ("stand", "sit"):
            self._blink_left = 0.16
            self._blink_countdown = self._rng.uniform(3.0, 7.0)

    def _update_anim(self, dt: float) -> None:
        b = self.body
        if b.airborne:
            state = "jump"
        elif b.target_x is not None:
            state = "walk" if b.speed <= WALK_SPEED else "run"
        else:
            state = {
                "sleep": "sleep",
                "sleep_belly": "sleep_belly",
                "beg": "beg",
                "groom": "groom",
                "supervise": "sit",
                "sit": "sit",
                "loaf": "loaf",
                "enjoy": "enjoy",
                "headrub": "rub",
                "cuddle_rub": "rub",
                "tailwrap": "tailwrap",
                "hunt_stalk": "crouch",
                "eating": "eat",
                "drinking": "drink",
                "scratching": "scratch",
                "nibbling": "eat",
                "littering": "squat",
                "litter_cover": "cover",
                "litter_beg": "beg",
                "wheel_run": "run",
                "to_wheel": "run",
                "watch": "watch",
                "annoyed": "tail_lash",
                "alert": "alert",
                "yawn": "yawn",
                "stretch": "stretch",
                "knead": "knead",
                "wiggle": "wiggle",
                "retch": "retch",
                "box_hide": "box_peek",
                "prep_jump": "crouch",
                "land": "crouch",
                "paw_bat": "paw_bat",
                "ritual_sit": "sit",
                "ritual_scratch": "scratch_self",
                "ritual_groom": "groom",
                "ear_fold": "ear_fold",
                "lick_paw": "lick_paw",
            }.get(self.brain.state, "stand")
        if state != self.anim_state:
            self.anim_state = state
            self.frame = 0
            self._frame_t = 0.0
        else:
            anim = ANIMATIONS[state]
            self._frame_t += dt
            frame_dur = 1.0 / anim.fps
            if self._frame_t >= frame_dur:
                self._frame_t -= frame_dur
                self.frame += 1
