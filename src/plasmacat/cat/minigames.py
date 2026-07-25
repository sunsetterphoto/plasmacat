"""Mini-games (P42): the mouse hunt. Qt-free, ticked by the overlay.

Mice are regular toys (kind "mouse", desktop/back layer): the cat can hunt
them autonomously through the normal play_toy behavior, or the user steers
her into them in control mode. A session spawns mice for 60 s; catching one
(touching it) scores.
"""

from __future__ import annotations

import random

from plasmacat.bridge.desktop import DesktopState
from plasmacat.cat.cat import Cat
from plasmacat.cat.toys import ToyManager

DURATION_S = 60.0
MAX_CAUGHT = 8
MAX_ALIVE = 4
CATCH_DIST = 40.0


class MouseHunt:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.time_left = DURATION_S
        self.score = 0
        self.active = True
        self._spawn_t = 0.0

    def tick(self, dt: float, desktop: DesktopState, cat: Cat,
             toys: ToyManager, sounds: list[str]) -> None:
        if not self.active:
            return
        self.time_left -= dt
        self._spawn_t -= dt
        mice = [t for t in toys.toys if t.kind == "mouse"]
        if self._spawn_t <= 0.0 and len(mice) < MAX_ALIVE \
                and self.time_left > 5.0:
            self._spawn_t = self.rng.uniform(6.0, 9.0)
            x = self.rng.uniform(desktop.floor_x0 + 100,
                                 desktop.floor_x1 - 100)
            toys.spawn("mouse", x, desktop.floor_y_at(x))
        for m in mice:
            if abs(m.x - cat.body.x) < CATCH_DIST \
                    and abs(m.y - cat.body.y) < CATCH_DIST:
                toys.toys.remove(m)
                self.score += 1
                cat.brain.gain("play", 8)
                cat.brain.add_xp(2.0, "caught a mouse")
                sounds.append("mew")
                cat.brain.log.append("caught a mouse!")
        if self.time_left <= 0.0 or self.score >= MAX_CAUGHT:
            self.active = False
            # session over: the surviving mice scurry off
            toys.toys[:] = [t for t in toys.toys if t.kind != "mouse"]
