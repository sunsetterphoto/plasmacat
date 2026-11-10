import random

from plasmacat.bridge.desktop import DesktopState
from plasmacat.cat.cat import Cat
from plasmacat.cat.household import Household
from plasmacat.cat.toys import String, ToyManager

DT = 1 / 60


def _grass_after(n_cats: int, seconds: float) -> float:
    home = Household()
    home.grass_charges = 0.0
    cats = [Cat(400 + 100 * i, 1080, rng=random.Random(i), household=home)
            for i in range(n_cats)]
    for _ in range(int(seconds / DT)):
        home.tick(DT)                 # the overlay ticks the home once
        for c in cats:
            c.brain.decay(DT)         # brains never advance shared timers
    return home.grass_charges


def test_grass_regrow_independent_of_cat_count():
    assert _grass_after(1, 650) == _grass_after(4, 650) == 1.0


def test_private_household_still_regrows():
    cat = Cat(400, 1080, rng=random.Random(1))   # tests/single cat: own home
    cat.brain.grass_charges = 0.0
    for _ in range(int(650 / DT)):
        cat.brain.decay(DT)
    assert cat.brain.grass_charges == 1.0


def test_gift_toy_single_owner():
    d = DesktopState(1920, 1080)
    home, toys = Household(), ToyManager(random.Random(0))
    toys.spawn("plush", 900, 1080)
    a = Cat(400, 1080, rng=random.Random(1), household=home)
    b = Cat(1400, 1080, rng=random.Random(2), household=home)
    a.brain.toys = b.brain.toys = toys
    a.brain._start("gift", a.body, d)
    b.brain._start("gift", b.body, d)
    assert a.brain.state == "to_gift"
    assert b.brain.state != "to_gift"


def test_brain_log_is_bounded():
    cat = Cat(400, 1080, rng=random.Random(1))
    for i in range(5000):
        cat.brain.log.append(f"event {i}")
    assert len(cat.brain.log) <= 200


def test_land_then_initialised():
    cat = Cat(400, 1080, rng=random.Random(1))
    assert cat.brain._land_then == "idle"


def _string_speed_after(dt: float) -> float:
    s = String(500, 500)
    s.anchor = (500, 350)          # target == position: only damping acts
    s.vx = 200.0
    d = DesktopState(1920, 1080)
    for _ in range(round(1.0 / dt)):
        s.tick_physics(dt, d)
    return abs(s.vx)


def test_string_damping_framerate_independent():
    fast, slow = _string_speed_after(1 / 30), _string_speed_after(1 / 15)
    assert abs(fast - slow) <= 0.05 * max(fast, slow) + 0.5
