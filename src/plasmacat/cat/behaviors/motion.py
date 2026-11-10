"""Movement and attention: hops, landings, wandering, alerts, greetings.

State handlers moved verbatim out of Brain._continue: each takes the
brain as `self` so the bodies read exactly like the methods they were.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from plasmacat.cat.needs import FURNITURE_CAPTIONS, HOP_COOLDOWN_S
from plasmacat.cat.physics import RUN_SPEED

if TYPE_CHECKING:
    from plasmacat.bridge.desktop import DesktopState
    from plasmacat.cat.brain import Brain
    from plasmacat.cat.physics import CatBody


def hop_walk(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.target_x is None:
        if self.hop_target is not None:
            self._try_jump_up(body)
        else:
            self.state_left = 0.0


def air_up(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if not body.airborne:
        # absorb the landing first, then supervise (P26)
        self._land_then = "supervise"
        self.state = "land"
        self.state_left = 0.22


def land(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if self.state_left <= 0:
        if self._land_then == "supervise":
            self.state = "supervise"
            self.state_left = self.rng.uniform(8, 18)
        else:
            self.state = "idle"
            self.state_left = 0.0


def prep_jump(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if self.state_left <= 0:
        nxt = self._jump_then
        self._jump_then = None
        if nxt is not None and body.jump_to(nxt[0], nxt[1]):
            self.state = nxt[2]
            self.state_left = 6.0
            if nxt[2] == "air_up" and self.hop_target is not None:
                self.log.append(f"hop onto {self.hop_target.caption!r}")
        else:
            self.state = "sit"
            self.state_left = 4.0
            self.hop_cooldown = HOP_COOLDOWN_S
            self.hop_target = None


def supervise(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if self.state_left <= 0:
        plat = body.platform
        if (plat is not None and plat.caption in FURNITURE_CAPTIONS
                and self.needs["energy"] < 80 and self.rng.random() < 0.5):
            # so comfy up here: nap on the furniture (user wish: she
            # loves sleeping on the post/tree platforms)
            self.state = "sleep"
            self.state_left = self.rng.uniform(120, 7200)
            self.log.append(f"napping on the {plat.caption}")
        else:
            floor = desktop.floor_under(body.x)
            hop_x = min(max(body.x + self.rng.uniform(-140, 140),
                            floor.x0 + 70), floor.x1 - 70)
            # short crouch, then the drop (resolved in prep_jump)
            self._jump_then = (hop_x, floor.y, "air_down")
            self.state = "prep_jump"
            self.state_left = 0.18


def air_down(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if not body.airborne:
        self._land_then = "idle"
        self.state = "land"
        self.state_left = 0.22


def wander(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.target_x is None:
        self.state_left = 0.0


def startle_air(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if not body.airborne:
        self.state = "alert"
        self.state_left = 2.5


def alert(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    body.facing = 1 if desktop.cursor[0] > body.x else -1
    if self.state_left <= 0:
        self.state = "idle"


def greet(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.target_x is None:
        self.state = "headrub"
        self.state_left = 2.5
        self.gain("affection", 4)
        self.add_xp(2.0, "welcome back")


def annoyed(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.target_x is None:
        self.state = "idle"
        self.state_left = 0.0

# -- P48: cat-cat social sequences --------------------------------------


def watch(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    body.facing = 1 if desktop.cursor[0] > body.x else -1
    # excited chattering at fast-moving 'prey' (P26)
    if desktop.cursor_speed > 250 and self.rng.random() < 0.4 * dt:
        self.sounds.append("chirp")
    if self.state_left <= 0:
        self.state = "idle"


def zoomies(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    self._fx_t -= dt
    if self._fx_t <= 0:
        self._fx_t = self.rng.uniform(0.5, 1.0)
        floor = desktop.floor_under(body.x)
        wins = [p for p in desktop.platforms
                if not p.floor and p.caption not in FURNITURE_CAPTIONS]
        if self.rng.random() < 0.25 and wins:
            tgt = self.rng.choice(wins)
            body.jump_to((tgt.x0 + tgt.x1) / 2, tgt.y)  # sprint up a window
        else:
            lo, hi = self._walk_range(floor)
            body.walk_to(self.rng.uniform(lo, hi), RUN_SPEED)
    if self.state_left <= 0:
        body.walk_to((self.litter_x or 500) - 30, RUN_SPEED)
        self.state = "to_litter"
        self.state_left = 20.0


STATES = {
    "hop_walk": hop_walk,
    "air_up": air_up,
    "land": land,
    "prep_jump": prep_jump,
    "supervise": supervise,
    "air_down": air_down,
    "wander": wander,
    "startle_air": startle_air,
    "alert": alert,
    "greet": greet,
    "annoyed": annoyed,
    "watch": watch,
    "zoomies": zoomies,
}
