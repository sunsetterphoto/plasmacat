"""Play and hunting: toys, laser dot, gifts, cursor hunts.

State handlers moved verbatim out of Brain._continue: each takes the
brain as `self` so the bodies read exactly like the methods they were.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from plasmacat.cat.needs import CATCH_RANGE
from plasmacat.cat.physics import RUN_SPEED, WALK_SPEED

if TYPE_CHECKING:
    from plasmacat.bridge.desktop import DesktopState
    from plasmacat.cat.brain import Brain
    from plasmacat.cat.physics import CatBody


def to_toy(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    toy = self._play_toy_target
    if toy is None or (self.toys is not None
                       and toy not in self.toys.toys):
        # gone mid-approach ('Clear toys'): drop it, don't pounce air
        self._play_toy_target = None
        self.state = "idle"
        self.state_left = 0.0
    elif body.target_x is None:
        if toy.kind == "ball":
            # batting happens via proximity (ToyManager); watch it roll
            self.state = "toy_watch"
            self.state_left = self.rng.uniform(10, 1200)
            self._fx_t = 0.0
        else:
            plat = desktop.platform_below(toy.x, toy.y)
            # the butt wiggle telegraphs the pounce (classic cat)
            self._wiggle_then = ("toy", toy.x, plat.y)
            self.state = "wiggle"
            self.state_left = 0.6


def wiggle(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if self._wiggle_then is not None:
        body.facing = 1 if self._wiggle_then[1] >= body.x else -1
    if self.state_left <= 0:
        nxt = self._wiggle_then
        self._wiggle_then = None
        if nxt is None:
            self.state = "idle"
            self.state_left = 0.0
        elif body.jump_to(nxt[1], nxt[2]):
            self.state = ("hunt_pounce" if nxt[0] == "hunt"
                          else "laser_pounce" if nxt[0] == "laser"
                          else "pounce_toy")
            self.state_left = 4.0
        else:
            self.state = "idle" if nxt[0] == "hunt" else "sit"
            self.state_left = 0.0 if nxt[0] == "hunt" else 2.0


def toy_watch(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if not self.toys or not self.toys.toys:
        self.state = "idle"
        self.state_left = 0.0
    else:
        # a real cat follows the ball it batted (bat -> chase -> bat)
        self._fx_t -= dt
        if self._fx_t <= 0:
            self._fx_t = 1.0
            t = self.toys.nearest(body.x, body.y)
            if t is not None and abs(t.x - body.x) > 80:
                off = 45 * (-1 if t.x < body.x else 1)
                spd = RUN_SPEED if abs(t.x - body.x) > 250 else WALK_SPEED
                body.walk_to(t.x + off, spd)
    if self.state_left <= 0 or self.needs["play"] >= 95:
        body.stop()
        self.state = "idle"


def pounce_toy(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if not body.airborne:
        toy = self._play_toy_target
        self._play_toy_target = None
        caught = (toy is not None
                  and (self.toys is None or toy in self.toys.toys)
                  and ((toy.x - body.x) ** 2 + (toy.y - body.y) ** 2) ** 0.5 < 70)
        if caught:
            self.gain("play", 14)
            self.add_xp(3.0, f"caught {toy.kind}")
            self._care(0.06)
            self.sounds.append("boing")
            self.log.append(f"caught the {toy.kind}!")
            if toy.kind == "plush" and self.rng.random() < 0.4:
                toy.x = min(max(body.x + self.rng.uniform(-400, 400),
                                desktop.floor_x0 + 30),
                            desktop.floor_x1 - 30)
                toy.vy = -250  # 'escapes' with a hop
                self.log.append("the plush mouse 'escaped'!")
            elif toy.kind == "string":
                toy.interactions += 1
                toy.vy -= 350
                toy.vx += self.rng.uniform(-150, 150)
            self.state = "enjoy"
            self.state_left = 2.0
        else:
            self.state = "sit"
            self.state_left = 1.5


def laser_chase(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    laser = self._laser()
    if laser is None or not desktop.cursor_active:
        body.stop()
        self.state = "idle"
        self.state_left = 0.0
    elif self.needs["energy"] < 25:
        # out of steam: she gives up on the uncatchable dot (P34)
        body.stop()
        self.state = "sit"
        self.state_left = 3.0
        self._laser_cd = 60.0
        self.log.append("too tired for the laser")
    else:
        # chasing the dot is a workout
        self.needs["energy"] = max(0.0, self.needs["energy"] - 2.0 * dt)
        self.gain("play", 3.0 * dt)
        dist = abs(laser.x - body.x)
        body.facing = 1 if laser.x >= body.x else -1
        if body.target_x is None:
            plat = desktop.floor_under(laser.x)
            if dist < 55:
                # in striking range: wiggle, then pounce on the dot
                tx = min(max(laser.x, plat.x0 + 90), plat.x1 - 90)
                self._wiggle_then = ("laser", tx, plat.y)
                self.state = "wiggle"
                self.state_left = 0.5
            else:
                lo, hi = self._walk_range(plat)
                off = 70 * (-1 if laser.x < body.x else 1)
                spd = RUN_SPEED if dist > 150 else WALK_SPEED
                body.walk_to(min(max(laser.x + off, lo), hi), spd)
        if self.state_left <= 0:
            body.stop()
            self.state = "idle"
            self.state_left = 0.0
            self._laser_cd = 45.0   # she needs a break from the dot


def laser_pounce(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if not body.airborne:
        laser = self._laser()
        caught = laser is not None and abs(laser.x - body.x) < 60
        if caught:
            # GOT IT — well, almost: the dot blinks out and reappears
            laser.escape()
            self.gain("play", 10)
            self.gain("affection", 1)
            self.add_xp(2.0, "caught the dot")
            self._care(0.04)
            self.sounds.append("boing")
            self.log.append("caught the laser dot!")
        self.state = "laser_chase"
        self.state_left = self.rng.uniform(8, 15)


def to_gift(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if self._gift_toy is None or self._gift_toy not in self.toys.toys:
        self._gift_toy = None
        self.state = "idle"
        self.state_left = 0.0
    elif self._gift_toy.carried or self._claimed_by_other(self._gift_toy):
        self._gift_toy = None   # another cat got there first
        self.state = "idle"
        self.state_left = 0.0
    elif body.target_x is None:
        # picked it up: the plush rides at her mouth now
        self._gift_toy.carried = True
        self.state = "carry_gift"
        self.state_left = 25.0
        self._fx_t = 0.0


def carry_gift(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    toy = self._gift_toy
    if toy is None or not getattr(toy, "carried", False) \
            or toy not in self.toys.toys:
        self._gift_toy = None
        self.state = "idle"
        self.state_left = 0.0
    else:
        cx, _cy = desktop.cursor
        self._fx_t -= dt
        if self._fx_t <= 0:
            self._fx_t = 1.5
            offset = 60 * (-1 if cx < body.x else 1)
            body.walk_to(self._floor_target(desktop, cx, cx + offset), WALK_SPEED)
        if body.target_x is None and abs(cx - body.x) < 100:
            # presented! drops it at your feet, so proud
            toy.carried = False
            toy.vy = -120.0
            toy.vx = body.facing * 60.0
            self._gift_toy = None
            self.sounds.append(self._meow())
            self.gain("affection", 6)
            self.add_xp(6.0, "gift for you")
            self._care(0.08)
            self.log.append("brought you a gift!")
            self.state = "enjoy"
            self.state_left = 2.5
        elif self.state_left <= 0:
            toy.carried = False
            self._gift_toy = None
            self.state = "idle"


def hunt_stalk(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if self.hunt_target is not None:
        tx, ty = self.hunt_target
        body.facing = 1 if tx > body.x else -1
        dist = abs(tx - body.x)
        if not desktop.cursor_active or self.state_left <= 0:
            self.state = "idle"
            self.state_left = 0.0
        elif dist < 260 or desktop.cursor_speed < 150:
            plat = desktop.floor_under(tx)
            if plat.floor:
                tx = min(max(tx, plat.x0 + 90), plat.x1 - 90)
            # butt wiggle first, then the pounce (resolved in "wiggle")
            self._wiggle_then = ("hunt", tx, plat.y)
            self.state = "wiggle"
            self.state_left = 0.7


def hunt_pounce(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if not body.airborne:
        cx, _cy = desktop.cursor
        if abs(cx - body.x) < CATCH_RANGE:
            self.gain("play", 18)
            self.gain("affection", 4)
            self.add_xp(5.0, "catch")
            self.log.append("caught the 'prey'!")
            self.state = "enjoy"
            self.state_left = 2.5
        else:
            self.state = "sit"
            self.state_left = 1.5


STATES = {
    "to_toy": to_toy,
    "wiggle": wiggle,
    "toy_watch": toy_watch,
    "pounce_toy": pounce_toy,
    "laser_chase": laser_chase,
    "laser_pounce": laser_pounce,
    "to_gift": to_gift,
    "carry_gift": carry_gift,
    "hunt_stalk": hunt_stalk,
    "hunt_pounce": hunt_pounce,
}
