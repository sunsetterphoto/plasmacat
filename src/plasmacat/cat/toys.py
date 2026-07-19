"""Toys: ball, plush mouse, string, laser pointer. Physics + cat glue.

Toys live on the overlay's floor/platforms like the cat. The ball can be
batted by the cat (proximity + facing). The plush mouse and the string's lure
are pounce targets for the brain's play behavior. Pure python, no Qt.
"""

from __future__ import annotations

import math
import random

from plasmacat.bridge.desktop import DesktopState
from plasmacat.cat.physics import GRAVITY

BOUNCE_DAMP = 0.6       # vertical energy kept per bounce
BOUNCE_VX_KEEP = 0.85   # horizontal energy kept per bounce
ROLL_FRICTION = 0.985
BAT_RANGE = 60.0
CATCH_RANGE = 55.0


class Toy:
    kind = "toy"

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.carried = False       # in the cat's mouth (gift delivery, P26)
        self.last_bat = 0.0  # monotonic time of last bat (spam guard)

    def bat(self, from_x: float, desktop: DesktopState, power: float = 1.0) -> None:
        direction = 1 if self.x >= from_x else -1
        # never bat into a wall: at the edges the ball always goes inward,
        # otherwise it jams in the corner with the cat stuck behind it
        if self.x < desktop.floor_x0 + 80:
            direction = 1
        elif self.x > desktop.floor_x1 - 80:
            direction = -1
        self.vx = direction * 380 * power   # a real kick
        self.vy = -420 * power              # ...and up it goes; gravity does
                                            # the accelerating on the way down
        self.on_ground = False              # airborne: no roll friction (P24)

    def tick_physics(self, dt: float, desktop: DesktopState) -> bool:
        """Gravity + platform bounce. Returns True if it bounced (for sound)."""
        bounced = False
        old_y = self.y
        self.vy += GRAVITY * dt
        self.vy = min(self.vy, 4000.0)      # terminal velocity (safety, P25)
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.x <= desktop.floor_x0 + 20 and self.vx < 0:
            self.vx = -self.vx * 0.6      # side walls bounce, never stick
            self.x = desktop.floor_x0 + 20
        elif self.x >= desktop.floor_x1 - 20 and self.vx > 0:
            self.vx = -self.vx * 0.6
            self.x = desktop.floor_x1 - 20
        if self.vy > 0:
            for p in desktop.platforms:
                # contact point = the ball's bottom; radius margin so it only
                # rolls off when about half of it is over the edge (P22)
                if old_y <= p.y <= self.y and p.contains_x(self.x, 12.0):
                    self.y = p.y
                    self.vy = -self.vy * BOUNCE_DAMP
                    self.vx *= BOUNCE_VX_KEEP
                    bounced = abs(self.vy) > 60
                    if abs(self.vy) <= 60:
                        self.vy = 0.0
                        self.on_ground = True
                    break
            else:
                self.on_ground = False  # free fall past every edge (P24)
        # the floor is the unconditional catch: a toy can end up BELOW it
        # when the work area moves (panel grows). Without this snap it falls
        # into the void until the float overflows (observed live, P25)
        if self.y > desktop.floor_y:
            self.y = desktop.floor_y
            if abs(self.vy) > 60:
                self.vy = -self.vy * BOUNCE_DAMP
                bounced = True
            else:
                self.vy = 0.0
            self.on_ground = True
        if self.on_ground:
            self.vx *= ROLL_FRICTION ** (dt * 60)
            if abs(self.vx) < 4:
                self.vx = 0.0
        return bounced


class Ball(Toy):
    kind = "ball"


class Plush(Toy):
    kind = "plush"

    def tick_physics(self, dt: float, desktop: DesktopState) -> bool:
        bounced = super().tick_physics(dt, desktop)
        self.vx = 0.0  # a plush mouse doesn't roll
        return bounced


class String(Toy):
    kind = "string"

    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y)
        self.anchor: tuple[float, float] = (x, y - 150)
        self.interactions = 0

    def tick_physics(self, dt: float, desktop: DesktopState) -> bool:
        # spring toward a point dangling below the cursor (pendulum-ish lag)
        tx, ty = self.anchor[0], self.anchor[1] + 150
        self.vx += (tx - self.x) * 14 * dt
        self.vy += (ty - self.y) * 14 * dt
        self.vx *= 0.94
        self.vy *= 0.94
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.y = min(self.y, desktop.screen_h - 6)
        return False


class Laser(Toy):
    """The laser-pointer dot (P34): no physics, it is light. Follows the
    cursor with a springy lag plus hand tremble; 'escapes' (blinks out) for
    a moment after being caught — the way real cats never catch the dot."""

    kind = "laser"

    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y)
        self._bx, self._by = x, y   # springed base (tremble is added on top)
        self._t = 0.0
        self._escape_t = 0.0

    @property
    def visible(self) -> bool:
        return self._escape_t <= 0

    def escape(self) -> None:
        self._escape_t = 0.8  # blink out briefly after being 'caught'

    def tick_physics(self, dt: float, desktop: DesktopState) -> bool:
        self._t += dt
        self._escape_t = max(0.0, self._escape_t - dt)
        tx, ty = desktop.cursor
        if not self.visible:
            self._bx, self._by = tx, ty  # reappear right at the cursor
            self.x, self.y = tx, ty
            return False
        k = 14.0  # springy follow lag
        self._bx += (tx - self._bx) * min(1.0, k * dt)
        self._by += (ty - self._by) * min(1.0, k * dt)
        # bounded hand tremble around the base
        self.x = self._bx + 2.2 * math.sin(self._t * 9.0)
        self.y = self._by + 1.6 * math.cos(self._t * 11.0)
        return False


class ToyManager:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.toys: list[Toy] = []
        self.rng = rng or random.Random()
        self._time = 0.0

    def spawn(self, kind: str, x: float, y: float) -> Toy:
        cls = {"ball": Ball, "plush": Plush, "string": String, "laser": Laser}[kind]
        # only one string / one laser dot at a time
        if kind in ("string", "laser"):
            self.toys = [t for t in self.toys if t.kind != kind]
        toy = cls(x, y)
        self.toys.append(toy)
        return toy

    def remove(self, kind: str) -> None:
        self.toys = [t for t in self.toys if t.kind != kind]

    def nearest(self, x: float, y: float) -> Toy | None:
        best, best_d = None, 1e9
        for t in self.toys:
            d = ((t.x - x) ** 2 + (t.y - y) ** 2) ** 0.5
            if d < best_d:
                best, best_d = t, d
        return best

    def tick(self, dt: float, desktop: DesktopState, cat, sounds: list[str]) -> None:
        self._time += dt
        for toy in self.toys:
            if getattr(toy, "carried", False):
                # riding in the cat's mouth: gift delivery (P26)
                toy.x = cat.body.x + cat.body.facing * 45
                toy.y = cat.body.y - 42
                toy.vx = toy.vy = 0.0
                continue
            if toy.kind == "string":
                toy.anchor = desktop.cursor
            if toy.tick_physics(dt, desktop):
                sounds.append("boing")
            # cat bats the ball when close and facing it
            if toy.kind == "ball" and self._time - toy.last_bat > 0.8:
                d = abs(cat.body.x - toy.x)
                same_level = abs(cat.body.y - toy.y) < 40
                facing_it = (cat.body.facing > 0) == (toy.x >= cat.body.x)
                if d < BAT_RANGE and same_level and facing_it and not cat.body.airborne:
                    toy.bat(cat.body.x, desktop, power=self.rng.uniform(0.7, 1.3))
                    toy.last_bat = self._time
                    sounds.append("boing")
                    cat.brain.gain("play", 4)
                    cat.brain.add_xp(0.5, "ball bat")
