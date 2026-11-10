"""Toy play is consistent: she plays where the toy is, never 'at' a toy on
another level from up on a window."""
import random

import pytest

from plasmacat.bridge.desktop import DesktopState
from plasmacat.cat.cat import Cat
from plasmacat.cat.toys import ToyManager

DT = 1 / 60
PLAY_STATES = {"wiggle", "toy_watch", "pounce_toy"}


def _world(kind):
    d = DesktopState(1920, 1080)
    d.set_windows([{"id": "W", "x": 600, "y": 500, "w": 700, "h": 400}])
    cat = Cat(750, 500, rng=random.Random(4))
    cat.body.platform = next(p for p in d.platforms if p.win_id == "W")
    cat.body.airborne = False
    toys = ToyManager(random.Random(0))
    toy = toys.spawn(kind, 1000.0, 1080.0)         # on the floor BELOW her window
    cat.brain.toys = toys
    cat.brain.fav_toy = kind
    cat.brain.needs["play"] = 20.0
    return d, cat, toys, toy


@pytest.mark.parametrize("kind", ["plush", "ball"])
def test_she_goes_down_to_the_toy_before_playing(kind):
    d, cat, toys, toy = _world(kind)
    cat.brain._start("play_toy", cat.body, d)
    seen_at_wrong_level = set()
    reached = False
    for _ in range(int(25 / DT)):
        cat.tick(DT, d)
        toys.tick(DT, d, [cat], [])
        cat.brain.sounds.clear()
        if cat.brain.state in PLAY_STATES and not cat.body.airborne \
                and abs(cat.body.y - toy.y) > 60:
            seen_at_wrong_level.add(cat.brain.state)
        if not cat.body.airborne and abs(cat.body.y - toy.y) < 40 and abs(cat.body.x - toy.x) < 200:
            reached = True
    assert not seen_at_wrong_level, seen_at_wrong_level
    assert reached, (cat.brain.state, cat.body.x, cat.body.y)


def test_toy_watch_ignores_toys_on_another_level():
    d, cat, toys, toy = _world("ball")
    cat.brain.state, cat.brain.state_left, cat.brain._fx_t = "toy_watch", 30.0, 0.0
    x0 = cat.body.x
    for _ in range(int(3 / DT)):
        cat.brain._continue(DT, cat.body, d)
        cat.body.tick(DT, d)
    # she does not pace along the window edge above a ball down on the floor
    assert cat.brain.state != "toy_watch" or abs(cat.body.x - x0) < 5 or abs(cat.body.y - toy.y) < 40


def test_laser_chase_ends_in_a_pounce():
    d = DesktopState(1920, 1080)
    d.set_cursor(900, 800)
    d.cursor_active = True
    cat = Cat(400, 1080, rng=random.Random(501))
    toys = ToyManager(random.Random(501))
    cat.brain.toys = toys
    cat.brain.needs["play"] = 50.0
    toys.spawn("laser", 900.0, 900.0)
    cat.brain._start("laser_chase", cat.body, d)      # straight in: no lucky pre-walk
    seen = set()
    for _ in range(int(12 / DT)):
        cat.tick(DT, d)
        toys.tick(DT, d, [cat], cat.brain.sounds)
        seen.add(cat.brain.state)
        cat.brain.sounds.clear()
    assert "wiggle" in seen and "laser_pounce" in seen, seen


def test_play_toy_never_targets_the_laser_dot():
    d = DesktopState(1920, 1080)
    cat = Cat(400, 1080, rng=random.Random(3))
    toys = ToyManager(random.Random(3))
    cat.brain.toys = toys
    toys.spawn("laser", 900.0, 900.0)
    cat.brain._start("play_toy", cat.body, d)
    assert cat.brain._play_toy_target is None


def test_string_at_the_cursor_is_still_played_from_below():
    d = DesktopState(1920, 1080)
    cat = Cat(400, 1080, rng=random.Random(3))
    toys = ToyManager(random.Random(3))
    cat.brain.toys = toys
    cat.brain.fav_toy = "string"
    toys.spawn("string", 700.0, 850.0)           # dangling in the air
    cat.brain._start("play_toy", cat.body, d)
    assert cat.brain.state == "to_toy"           # walks under it, no level jump
