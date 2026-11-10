"""Furniture: cardboard box, scratching post, exercise wheel.

State handlers moved verbatim out of Brain._continue: each takes the
brain as `self` so the bodies read exactly like the methods they were.
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from plasmacat.bridge.desktop import DesktopState
    from plasmacat.cat.brain import Brain
    from plasmacat.cat.physics import CatBody


def to_box(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.target_x is None:
        box_plat = next((p for p in desktop.platforms
                         if p.caption == "Karton"), None)
        if box_plat is not None and body.jump_to(
                (box_plat.x0 + box_plat.x1) / 2, box_plat.y):
            self.state = "to_box_air"
            self.state_left = 4.0
        else:
            self.state = "idle"
            self.state_left = 0.0


def to_box_air(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if not body.airborne:
        self.state = "box_hide"
        self.state_left = self.rng.uniform(8, 30)
        self.log.append("hiding in the box")


def box_hide(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    self.gain("play", 1.5 * dt)
    cx, _cy = desktop.cursor
    body.facing = 1 if cx >= body.x else -1
    if (desktop.cursor_active and abs(cx - body.x) < 350
            and self.rng.random() < 0.5 * dt):
        # AMBUSH: burst out of the box at the 'prey'
        plat = desktop.floor_under(cx)
        tx = min(max(cx, plat.x0 + 90), plat.x1 - 90)
        self._wiggle_then = ("hunt", tx, plat.y)
        self.state = "wiggle"
        self.state_left = 0.5
    elif self.state_left <= 0:
        floor = desktop.floor_under(body.x)
        hop_x = min(max(body.x + self.rng.uniform(-160, 160),
                        floor.x0 + 70), floor.x1 - 70)
        if body.jump_to(hop_x, floor.y):
            self.state = "air_down"
            self.state_left = 4.0
        else:
            self.state = "idle"


def to_scratch(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.target_x is None:
        body.facing = 1 if (self.scratch_x or 0) > body.x else -1
        self.state = "scratching"
        self.state_left = 4.0
        self._fx_t = 0.0


def scratching(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    self.gain("play", 5.0 * dt)
    self._fx_t -= dt
    if self._fx_t <= 0:
        self.sounds.append("scratch")
        self._fx_t = 1.0
    if self.state_left <= 0:
        self.add_xp(2.0, "scratching post")
        self.state = "idle"


def to_wheel(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.target_x is None:
        wheel_plat = next((p for p in desktop.platforms
                           if p.caption == "Laufrad"), None)
        if wheel_plat is not None and body.jump_to(wheel_plat.x0 + 60,
                                                   wheel_plat.y):
            self.state = "to_wheel_air"
            self.state_left = 4.0
        else:
            self.state = "idle"
            self.state_left = 0.0


def to_wheel_air(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if not body.airborne:
        self.state = "wheel_run"
        self.state_left = self.rng.uniform(20, 240)
        self._fx_t = 0.0
        self.log.append("exercise wheel!")


def wheel_run(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    self.gain("play", 6.0 * dt)
    self.needs["energy"] = max(0.0, self.needs["energy"] - 2.5 * dt)  # workout!
    self._fx_t -= dt
    if self._fx_t <= 0:
        self.sounds.append("chirp" if self.rng.random() < 0.5 else "boing")
        self._fx_t = 1.5
    if self.state_left <= 0 or self.needs["energy"] < 15 or self.needs["play"] >= 98:
        # hop out — far enough to clear the wheel's platform span,
        # or she lands right back on the track (P46)
        tx = body.x + body.facing * 110
        plat = desktop.platform_below(tx, body.y)
        if body.jump_to(tx, plat.y):
            self.state = "air_down"
            self.state_left = 4.0
            self.add_xp(3.0, "exercise wheel")
        else:
            self.state = "idle"


STATES = {
    "to_box": to_box,
    "to_box_air": to_box_air,
    "box_hide": box_hide,
    "to_scratch": to_scratch,
    "scratching": scratching,
    "to_wheel": to_wheel,
    "to_wheel_air": to_wheel_air,
    "wheel_run": wheel_run,
}
