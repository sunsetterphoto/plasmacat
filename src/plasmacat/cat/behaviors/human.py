"""The human's hand: following, chasing the cursor, cuddling.

State handlers moved verbatim out of Brain._continue: each takes the
brain as `self` so the bodies read exactly like the methods they were.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from plasmacat.cat.physics import WALK_SPEED

if TYPE_CHECKING:
    from plasmacat.bridge.desktop import DesktopState
    from plasmacat.cat.brain import Brain
    from plasmacat.cat.physics import CatBody


def chase(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    self.gain("play", 1.2 * dt)
    if body.target_x is None and self.state_left > 0:
        self._chase_step(body, desktop)
    if not desktop.cursor_active or self.state_left <= 0:
        body.stop()
        self.state_left = 0.0


def follow(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    # padding after the human at a polite 130-170 px distance (P26)
    cx, _cy = desktop.cursor
    dist = cx - body.x
    self._fx_t -= dt
    if self._fx_t <= 0:
        self._fx_t = 0.7
        if abs(dist) > 170:
            dest = self._floor_target(desktop, cx, cx - (1 if dist > 0 else -1) * 150)
            body.walk_to(dest, WALK_SPEED)
        elif abs(dist) < 110:
            body.stop()  # close enough: just watch them
    if body.target_x is None:
        body.facing = 1 if dist > 0 else -1
    if not desktop.cursor_active or self.state_left <= 0:
        body.stop()
        self.state = "sit"
        self.state_left = 2.0


def cuddle_walk(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.target_x is None:
        cx, _cy = desktop.cursor
        if abs(cx - body.x) < 140:
            self.state = "cuddle_rub"
            self.state_left = self.rng.uniform(2.5, 4.0)
        else:
            self.state_left = 0.0
            self.state = "idle"


def cuddle_rub(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    self.gain("affection", 2.0 * dt)
    if self.state_left <= 0:
        if self.attachment_level >= 2 and self.rng.random() < 0.6:
            self.state = "tailwrap"
            self.state_left = 3.5
        else:
            self.state = "idle"
            self.state_left = 0.0


def tailwrap(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    self.gain("affection", 2.5 * dt)
    if self.state_left <= 0:
        self.state = "idle"


STATES = {
    "chase": chase,
    "follow": follow,
    "cuddle_walk": cuddle_walk,
    "cuddle_rub": cuddle_rub,
    "tailwrap": tailwrap,
}
