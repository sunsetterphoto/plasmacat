"""Bodily needs: food, water, litter box, cat grass, vomiting.

State handlers moved verbatim out of Brain._continue: each takes the
brain as `self` so the bodies read exactly like the methods they were.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from plasmacat.cat.needs import LITTER_CAPACITY, GRASS_FRENZY_S, NEGLECT_EAT_S, FOODS, CATNIP_HIGH_S

if TYPE_CHECKING:
    from plasmacat.bridge.desktop import DesktopState
    from plasmacat.cat.brain import Brain
    from plasmacat.cat.physics import CatBody


def retch(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    self._fx_t -= dt
    if self._fx_t <= 0:
        self.sounds.append("puke")
        self._fx_t = 0.8
    if self.state_left <= 0:
        # the puddle lands on the floor below (gravity applies)
        floor = desktop.floor_under(body.x)
        px = min(max(body.x, floor.x0 + 40), floor.x1 - 40)
        self.puke_spots.append(px)
        del self.puke_spots[:-3]  # cap the mess
        self.needs["hunger"] = 55.0   # ...and she feels better
        self.needs["affection"] = max(0.0, self.needs["affection"] - 3)
        self.log.append("vomited — the floor needs cleaning")
        self.state = "idle"
        self.state_left = 0.0


def to_grass(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.target_x is None:
        body.facing = 1 if (self.grass_x or 0) > body.x else -1
        self.state = "nibbling"
        self.state_left = 2.5
        self._fx_t = 0.0


def nibbling(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    self._fx_t -= dt
    if self._fx_t <= 0:
        self.sounds.append("eat")
        self._fx_t = 1.0
    if self.state_left <= 0:
        self.grass_charges = max(0.0, self.grass_charges - 1)
        self.gain("affection", 3)
        self.gain("hunger", 3)
        self.add_xp(3.0, "cat grass")
        # too much grass (or grass on a neglected stomach) comes back
        # up — real cats do exactly this (P25)
        chance = 0.10
        if self._grass_recent > 0:
            chance += 0.40
        if self._neglect_s > NEGLECT_EAT_S:
            chance += 0.30
        self._grass_recent = 120.0
        if self.rng.random() < chance:
            self._start_retch("too much cat grass")
        else:
            # grass really winds her up: proper frenzy after nibbling
            self.catnip_high = GRASS_FRENZY_S
            self.needs["play"] = 100.0
            self.sounds.append("boing")
            self.log.append("cat grass FRENZY!")
            self.state = "idle"


def to_litter(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.target_x is None:
        if self.litter_fill >= LITTER_CAPACITY:
            # dirty box: refuses, complains loudly
            self.state = "litter_beg"
            self.state_left = 5.0
            self._fx_t = 0.0
        else:
            body.facing = 1 if (self.litter_x or 0) > body.x else -1
            self.state = "littering"
            self.state_left = 3.0
            self._fx_t = 0.0


def littering(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    # quiet squat; the effect lands when the covering is done
    if self.state_left <= 0:
        # a real cat always covers the evidence afterwards
        self.state = "litter_cover"
        self.state_left = 1.6
        self._fx_t = 0.0


def litter_cover(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    self._fx_t -= dt
    if self._fx_t <= 0:
        self.sounds.append("scratch")  # scraping litter over the pile
        self._fx_t = 0.7
    if self.state_left <= 0:
        self.needs["bladder"] = 100.0
        poop = self.rng.random() < 0.4  # ~2 poop / 3 pee per full box
        self.litter_fill += 1.0 if poop else 0.5
        self.litter_deposits.append("poop" if poop else "pee")
        self.add_xp(0.5, "litter box")
        self.log.append(f"litter used ({self.litter_deposits[-1]}, "
                        f"fill {self.litter_fill:.1f})")
        self.state = "idle"


def litter_beg(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    self._fx_t -= dt
    if self._fx_t <= 0:
        self.sounds.append("beg")
        self._fx_t = 1.5
    if self.state_left <= 0:
        self.state = "idle"


def to_food(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.target_x is None:
        body.facing = 1 if (self.food_x or 0) > body.x else -1  # face the bowl
        self.state = "eating"
        self.state_left = self.rng.uniform(20, 300)
        self._fx_t = 0.0


def eating(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if self.food_fill > 0:
        food = FOODS[self.food_type]
        self.gain("hunger", 1.0 * food["hunger_mult"] * dt)
        if food["thirst"]:
            self.gain("thirst", food["thirst"] * dt / 5.0)
        self.food_fill = max(0.0, self.food_fill - 1.0 * dt)
        self._fx_t -= dt
        if self._fx_t <= 0:
            self.sounds.append("eat")
            self._fx_t = 1.2
        if self.needs["hunger"] >= 99.0 and not self._bored_eat:
            self.state_left = min(self.state_left, 0.5)  # full: wrap up
        if self._bored_eat:
            self.state_left = min(self.state_left, 22.0)  # joyless meal
            if self.needs["hunger"] >= 97.0:
                self._overate_s += dt  # munching past full: this ends badly
    else:
        # empty bowl: a few pitiful meows, then she gives up for a
        # while instead of camping there for minutes (P24)
        self.state_left = min(self.state_left, 3.5)
        self._fx_t -= dt
        if self._fx_t <= 0:
            self.sounds.append("beg")
            self._fx_t = 1.8
    if self.state_left <= 0:
        if self.food_fill <= 0:
            self._food_beg_cd = 60.0
        food = FOODS[self.food_type]
        if self.food_fill > 0:
            self.gain("hunger", 10)
            self.gain("affection", food["affection"])
            self.add_xp(2.0, "meal")
            if self.food_type == "catnip" and self.catnip_high <= 0:
                self.catnip_high = CATNIP_HIGH_S
                self.needs["play"] = 100.0
                self.add_xp(8.0, "catnip!")
                self.sounds.append("boing")
                self.log.append("CATNIP FRENZY!")
        if self.treat_pending:
            self.treat_pending = False
            self.gain("affection", 6)
            self.add_xp(5.0, "treat")
        if self._overate_s > 5.0:
            # kept munching past full from sheer boredom — and now
            self._bored_eat = False
            self._start_retch("boredom eating")
        elif self.rng.random() < 0.6:
            # after eating: groom, then (often) sleep
            self.state = "groom"
            self.state_left = self.rng.uniform(4, 10)
            self._chain_groom_sleep = True
        else:
            self.state = "idle"


def to_water(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.target_x is None:
        body.facing = 1 if (self.water_x or 0) > body.x else -1  # face the bowl
        self.state = "drinking"
        self.state_left = self.rng.uniform(20, 120)
        self._fx_t = 0.0
        self._lap_t = 0.0


def drinking(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    # the fountain never runs dry (P25): nothing to drain or beg for
    self.gain("thirst", 1.5 * dt)
    # the fountain bubbles softly; a quiet lap only now and then
    self._fx_t -= dt
    if self._fx_t <= 0:
        self.sounds.append("bubble")
        self._fx_t = 4.0
    self._lap_t -= dt
    if self._lap_t <= 0:
        self.sounds.append("drink")
        self._lap_t = 9.0
    if self.needs["thirst"] >= 99.0:
        self.state_left = min(self.state_left, 0.5)  # had enough
    if self.state_left <= 0:
        self.gain("thirst", 10)
        self.state = "idle"


STATES = {
    "retch": retch,
    "to_grass": to_grass,
    "nibbling": nibbling,
    "to_litter": to_litter,
    "littering": littering,
    "litter_cover": litter_cover,
    "litter_beg": litter_beg,
    "to_food": to_food,
    "eating": eating,
    "to_water": to_water,
    "drinking": drinking,
}
