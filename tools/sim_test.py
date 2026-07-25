#!/usr/bin/env python
"""Headless simulation test for the cat core (no Qt, no screen).

Runs a few virtual minutes on a fake desktop (floor + one window) and checks:
needs decay, the cat hops onto the window and back, positions stay sane.

Usage: PYTHONPATH=src .venv/bin/python tools/sim_test.py
"""
import random
import time

import plasmacat.cat.brain as _brain_mod
from plasmacat.bridge.desktop import DesktopState
from plasmacat.cat.cat import Cat

DT = 1 / 60.0


class _FixedTime:
    """Pin the sim clock to dusk (19:xx, active playtime): the P26 circadian
    scoring must not make behavior tests depend on the wall clock."""
    @staticmethod
    def localtime():
        return time.struct_time((2026, 7, 19, 19, 0, 0, 6, 200, 1))


_brain_mod.time = _FixedTime()


def main() -> None:
    desktop = DesktopState(1920, 1080)
    desktop.set_windows([
        {"x": 700, "y": 500, "w": 500, "h": 400, "caption": "Fake Window"},
        {"x": 0, "y": 0, "w": 1, "h": 1, "caption": "bogus helper"},  # filtered (D11)
    ])
    assert len(desktop.platforms) == 2, desktop.platforms  # floor + window only

    cat = Cat(400, 1080, rng=random.Random(42))
    hopped = False
    min_energy = 100.0
    states_seen = set()

    for step in range(int(180 / DT)):  # 3 virtual minutes
        cat.tick(DT, desktop)
        states_seen.add(cat.anim_state)
        min_energy = min(min_energy, cat.brain.needs["energy"])
        if cat.body.platform and cat.body.platform.caption == "Fake Window":
            hopped = True
        assert 0 <= cat.body.x <= 1920, cat.body.x
        assert 0 <= cat.body.y <= 1080, cat.body.y

    print("states seen:", sorted(states_seen))
    print("needs after 3 min:", {k: round(v, 1) for k, v in cat.brain.needs.items()})
    print("hopped onto window:", hopped)
    print("brain log:", cat.brain.log[:5])

    assert cat.brain.needs["hunger"] < 80.0, "hunger did not decay"
    assert hopped, "cat never jumped onto the window"
    assert "walk" in states_seen or "run" in states_seen, "cat never walked"
    assert "jump" in states_seen, "cat never was airborne"

    # -- P4: petting raises attachment -------------------------------------
    import math

    from plasmacat.cat.animations import ANIMATIONS
    from plasmacat.cat.interactions import InteractionDetector
    from plasmacat.cat import sprites

    for k in sprites.SPRITES:
        assert k in ANIMATIONS, f"no animation timing for sprite state {k}"

    cat2 = Cat(960, 1080, rng=random.Random(1))
    det = InteractionDetector()
    cat_rect = (960 - 48, 1080 - 72, 96, 72)
    strokes = 0
    t = 1000.0
    for _ in range(600):  # 10 s of gentle back-and-forth over the cat
        t += DT
        cx = 960 + 40 * math.sin(t * 4)
        cy = 1080 - 30
        det.tracker.add(cx, cy, t)
        for ev in det.tick(DT, cat_rect, (cx, cy)):
            if ev == "stroke":
                cat2.brain.on_stroke(cat2.body)
                strokes += 1
        cat2.tick(DT, desktop)
    print(f"P4 petting: {strokes} strokes, xp={cat2.brain.attachment_xp}")
    assert strokes >= 3, strokes
    assert cat2.brain.attachment_xp >= 3.0

    # -- P4: fast erratic cursor triggers a hunt ----------------------------
    cat3 = Cat(960, 1080, rng=random.Random(2))
    det2 = InteractionDetector()
    hunted = False
    for _ in range(300):  # 5 s of erratic swooshing near the cat
        t += DT
        cx = 960 + 300 * math.sin(t * 25)
        cy = 900.0
        det2.tracker.add(cx, cy, t)
        for ev in det2.tick(DT, (912, 1008, 96, 72), (cx, cy)):
            if ev == "hunt":
                cat3.brain.on_hunt_trigger(cat3.body, (cx, cy), desktop)
                hunted = True
        cat3.tick(DT, desktop)
    print("P4 hunt triggered:", hunted, "| cat3 state:", cat3.brain.state)
    assert hunted

    # -- P5: hunger -> bowl -> eat -> satisfied ------------------------------
    cat4 = Cat(600, 1080, rng=random.Random(7))
    cat4.brain.food_x = 110.0
    cat4.brain.water_x = 200.0
    cat4.brain.needs["hunger"] = 20.0
    desktop4 = DesktopState(1920, 1080)
    sounds_seen: set[str] = set()
    bubbles_seen: set[str] = set()
    ate = False
    for _ in range(int(120 / DT)):
        cat4.tick(DT, desktop4)
        sounds_seen.update(cat4.brain.sounds)
        cat4.brain.sounds.clear()
        if cat4.brain.bubble:
            bubbles_seen.add(cat4.brain.bubble)
        if cat4.brain.state == "eating":
            ate = True
    print(f"P5: ate={ate}, hunger={cat4.brain.needs['hunger']:.0f}, "
          f"sounds={sorted(sounds_seen)}, bubbles={sorted(bubbles_seen)}")
    assert ate, "cat never went to eat"
    assert cat4.brain.needs["hunger"] > 50.0, cat4.brain.needs
    assert "eat" in sounds_seen, "no eat sound intents"
    assert "fish" in bubbles_seen, "no hunger bubble shown"

    # -- P6: the cat plays with toys ------------------------------------------
    from plasmacat.cat.toys import Ball, ToyManager

    cat5 = Cat(500, 1080, rng=random.Random(3))
    cat5.brain.food_x = 110.0
    cat5.brain.water_x = 200.0
    desktop5 = DesktopState(1920, 1080)
    tm = ToyManager(rng=random.Random(3))
    cat5.brain.toys = tm
    ball = tm.spawn("ball", 800, 1080)
    tm.spawn("plush", 1400, 1080)
    ball_moved = False
    for _ in range(int(90 / DT)):
        cat5.tick(DT, desktop5)
        tm.tick(DT, desktop5, cat5, cat5.brain.sounds)
        cat5.brain.sounds.clear()
        if abs(ball.x - 800) > 50:
            ball_moved = True
    print(f"P6: ball batted={ball_moved}, xp={cat5.brain.attachment_xp:.1f}, "
          f"log={cat5.brain.log[:3]}")
    assert ball_moved, "cat never batted the ball"
    assert cat5.brain.attachment_xp > 0, "no XP from playing"

    # corner trap: ball against the left wall must always be batted INWARD,
    # so the cat can never jam it (and itself) into the corner
    d6 = DesktopState(1920, 1080)
    corner_ball = Ball(25, 1080)
    corner_ball.bat(60.0, d6)  # cat stands to the right, would push it into the wall
    assert corner_ball.vx > 0, f"ball batted into the wall: vx={corner_ball.vx}"
    for _ in range(int(3 / DT)):
        corner_ball.tick_physics(DT, d6)
        assert corner_ball.x >= d6.floor_x0 + 19, corner_ball.x
    print("P6b: corner trap OK (ball bounces off walls, bats inward)")

    # -- P7: persistence roundtrip, offline decay, accessory layers ----------
    import tempfile
    import time
    from pathlib import Path

    from plasmacat import persist
    from plasmacat.cat import sprites

    cust = persist.Customization(name="Test", fur=(100, 50, 25), pattern="tabby",
                                 collar=(9, 9, 9))
    pal = cust.to_palette()
    assert pal["f"] == (100, 50, 25)
    assert pal["F"] == (72, 36, 18), pal["F"]  # derived shade = fur * 0.72
    assert pal["a"] == (9, 9, 9)
    st = persist.GameState(customization=cust, needs={"hunger": 50.0},
                           attachment_xp=42.0)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "save.json"
        persist.save(p, st)
        st2 = persist.load(p)
    assert st2 is not None
    assert st2.customization.name == "Test" and st2.attachment_xp == 42.0
    assert st2.customization.fur == (100, 50, 25)
    decayed = persist.offline_decay({"hunger": 50.0}, time.time() - 3600,
                                    {"hunger": 100 / 5400.0})
    assert decayed["hunger"] < 50.0, decayed
    # collar pixels exist in upright accessory layers, none in sleep
    assert any("a" in "".join(f) for f in sprites.ACCESSORIES["stand"])
    assert not any("a" in "".join(f) for f in sprites.ACCESSORIES["sleep"])
    print("P7: persistence + accessory layers OK")

    # -- P8d: bowl fills, food preferences, catnip ----------------------------
    from plasmacat.cat.brain import FOODS  # noqa: F401

    cat6 = Cat(500, 1080, rng=random.Random(11))
    cat6.brain.food_x = 110.0
    cat6.brain.water_x = 200.0
    cat6.brain.needs["hunger"] = 20.0
    cat6.brain.food_fill = 30.0
    d6b = DesktopState(1920, 1080)
    for _ in range(int(90 / DT)):
        cat6.tick(DT, d6b)
        cat6.brain.sounds.clear()
    assert cat6.brain.food_fill < 30.0, "food fill did not drain"
    assert cat6.brain.needs["hunger"] > 20.0, "cat did not eat"
    print(f"P8d: fill drains ({cat6.brain.food_fill:.0f}), cat eats")

    cat7 = Cat(500, 1080, rng=random.Random(12))
    cat7.brain.food_x = 110.0
    cat7.brain.water_x = 200.0
    cat7.brain.needs["hunger"] = 20.0
    cat7.brain.food_fill = 0.0
    h_before = cat7.brain.needs["hunger"]
    meows = 0
    cat7.brain.state = "eating"
    cat7.brain.state_left = 3.0
    for _ in range(int(3 / DT)):
        cat7.tick(DT, DesktopState(1920, 1080))
        meows += cat7.brain.sounds.count("beg")  # pleading meow at empty bowl
        cat7.brain.sounds.clear()
    assert cat7.brain.needs["hunger"] <= h_before + 1, "ate from an empty bowl!"
    assert meows >= 1, "no pleading meow at the empty bowl"
    print("P8d: empty bowl -> meow, no intake")

    cat7.brain.food_fill = 100.0
    cat7.brain.buy_food("tuna")
    aff_before = cat7.brain.needs["affection"]
    cat7.brain.state = "eating"
    cat7.brain.state_left = 0.01
    cat7.tick(DT, DesktopState(1920, 1080))
    assert cat7.brain.food_type == "tuna"
    assert cat7.brain.needs["affection"] > aff_before, "tuna gave no affection"
    print("P8d: tuna affection bonus OK")

    cat7.brain.buy_food("catnip")
    cat7.brain.food_fill = 100.0
    cat7.brain.state = "eating"
    cat7.brain.state_left = 0.01
    cat7.tick(DT, DesktopState(1920, 1080))
    assert cat7.brain.catnip_high > 0, "no catnip frenzy"
    assert cat7.brain.needs["play"] >= 99.0
    print("P8d: CATNIP FRENZY OK")

    # -- P9: furniture --------------------------------------------------------
    cat8 = Cat(600, 1080, rng=random.Random(21))
    cat8.brain.food_x = 110.0
    cat8.brain.water_x = 200.0
    cat8.brain.scratch_x = 1000.0
    cat8.brain.bed_x = 1400.0
    cat8.brain.grass_x = 400.0
    cat8.brain.needs["play"] = 10.0
    cat8.brain.needs["energy"] = 60.0  # rested enough to not hibernate the test away
    d8 = DesktopState(1920, 1080)
    seen: set[str] = set()
    for _ in range(int(150 / DT)):
        cat8.tick(DT, d8)
        seen.add(cat8.brain.state)
        cat8.brain.sounds.clear()
    print(f"P9: states={sorted(seen)}")
    assert "scratching" in seen, "cat never used the scratching post"
    # P24: she naps in place 60% of the time now; bed-walk has its own
    # deterministic test in the P24 block
    assert seen & {"to_bed", "sleep", "sleep_belly", "knead"}, "cat never slept"

    # cat grass: nibbling consumes a charge
    cat9 = Cat(500, 1080, rng=random.Random(22))
    cat9.brain.grass_x = 400.0
    d9 = DesktopState(1920, 1080)
    cat9.brain._start("nibble", cat9.body, d9)
    for _ in range(int(30 / DT)):
        cat9.tick(DT, d9)
        cat9.brain.sounds.clear()
    assert cat9.brain.grass_charges < 3.0, "no grass was nibbled"
    print("P9: scratch post, cat bed, cat grass OK")

    # -- P10: litter box, grass frenzy, cat tree platforms ---------------------
    from plasmacat.bridge.desktop import Platform

    catA = Cat(600, 1080, rng=random.Random(31))
    catA.brain.food_x = 110.0
    catA.brain.water_x = 200.0
    catA.brain.litter_x = 900.0
    catA.brain.needs["bladder"] = 20.0
    dA = DesktopState(1920, 1080)
    seenA: set[str] = set()
    for _ in range(int(90 / DT)):
        catA.tick(DT, dA)
        seenA.add(catA.brain.state)
        catA.brain.sounds.clear()
    assert "littering" in seenA, seenA
    assert catA.brain.needs["bladder"] > 90, catA.brain.needs
    assert catA.brain.litter_fill > 0, "box did not fill"
    # dirty box is refused
    catA.brain.litter_fill = 5.0
    catA.brain.needs["bladder"] = 10.0
    catA.brain.state = "to_litter"
    catA.brain.state_left = 20.0
    catA.body.target_x = None
    catA.brain._continue(DT, catA.body, dA)
    assert catA.brain.state == "litter_beg", catA.brain.state
    # grass really winds her up now
    catA.brain.grass_x = 400.0
    catA.brain._start("nibble", catA.body, dA)
    frenzy_seen = False
    for _ in range(int(30 / DT)):
        catA.tick(DT, dA)
        catA.brain.sounds.clear()
        frenzy_seen = frenzy_seen or catA.brain.catnip_high > 0
    assert frenzy_seen, "no grass frenzy"
    # tree platforms are jumpable/landable
    dT = DesktopState(1920, 1080)
    dT.set_extra_platforms([Platform(500, 560, 900, "Katzenbaum"),
                            Platform(600, 660, 800, "Katzenbaum")])
    p = dT.platform_below(530, 800)
    assert p.caption == "Katzenbaum" and p.y == 900, p
    print("P10: litter, grass frenzy, tree platforms OK")

    # -- P11: exercise wheel ---------------------------------------------------
    catW = Cat(400, 1080, rng=random.Random(41))
    catW.brain.food_x = 110.0
    catW.brain.water_x = 200.0
    catW.brain.wheel_x = 1000.0
    catW.brain.needs["play"] = 20.0
    dW = DesktopState(1920, 1080)
    dW.set_extra_platforms([Platform(940, 1060, 1038, "Laufrad")])
    seenW: set[str] = set()
    play_before = catW.brain.needs["play"]
    energy_before = catW.brain.needs["energy"]
    for _ in range(int(120 / DT)):
        catW.tick(DT, dW)
        seenW.add(catW.brain.state)
        catW.brain.sounds.clear()
    print(f"P11: states={sorted(seenW)}")
    assert "wheel_run" in seenW, "cat never ran in the wheel"
    assert catW.brain.needs["play"] > play_before, "wheel gave no play"
    assert catW.brain.needs["energy"] < energy_before, "wheel was no workout"

    # -- P12a: the cat blinks --------------------------------------------------
    catZ = Cat(960, 1080, rng=random.Random(50))
    dZ = DesktopState(1920, 1080)
    blinked = False
    for _ in range(int(30 / DT)):
        catZ.tick(DT, dZ)
        catZ.brain.sounds.clear()
        if catZ.anim_state == "stand" and catZ.blink_active:
            blinked = True
            break
    assert blinked, "cat never blinked in 30 idle seconds"
    print("P12a: blink OK")

    # -- P12b: startle, greet, annoyed, watch ----------------------------------
    catB = Cat(960, 1080, rng=random.Random(51))
    catB.brain.food_x = 110.0
    catB.brain.water_x = 200.0
    dB = DesktopState(1920, 1080)
    catB.brain.on_startle(catB.body, dB)
    assert catB.brain.state in ("startle_air", "alert"), catB.brain.state
    for _ in range(int(6 / DT)):
        catB.tick(DT, dB)
        catB.brain.sounds.clear()
    catB.brain.attachment_xp = 150
    catB.brain.on_user_return(catB.body, dB)
    assert catB.brain.state == "greet", catB.brain.state
    catB2 = Cat(500, 1080, rng=random.Random(52))
    for k in catB2.brain.needs:
        catB2.brain.needs[k] = 15.0
    catB2.tick(DT, dB)  # resolve floor platform first
    annoyed = False
    for _ in range(20):
        catB2.brain.on_stroke(catB2.body)
        if catB2.brain.state == "annoyed":
            annoyed = True
            break
    assert annoyed, "grumpy cat never got annoyed"
    catB2.brain._start("watch", catB2.body, dB)
    assert catB2.brain.state == "watch"
    print("P12b: startle, greet, annoyed, watch OK")

    # startle event from the detector: slow far cursor, then a fast approach
    detB = InteractionDetector()
    rectB = (960 - 48, 1080 - 96, 96, 96)
    tb = 2000.0
    fired = False
    for i in range(90):  # 1.5 s: far away, then a 1000 px/s rush at the cat
        tb += DT
        if i < 30:
            cx, cy = 400.0, 700.0
        else:
            cx = 400 + (i - 30) * 18.0
            cy = 700 + (i - 30) * 5.0
        detB.tracker.add(cx, cy, tb)
        for ev in detB.tick(DT, rectB, (cx, cy)):
            if ev == "startle":
                fired = True
    assert fired, "detector never fired startle"
    print("P12b: detector startle OK")

    # -- P13: furniture platforms are preferred hop + sleep spots ---------------
    from plasmacat.bridge.desktop import Platform as _P

    class _LowRng(random.Random):  # rigged: always picks the preferred option
        def random(self) -> float:
            return 0.1

    catF = Cat(500, 1080, rng=_LowRng(61))
    catF.brain.food_x = 110.0
    catF.brain.water_x = 200.0
    dF = DesktopState(1920, 1080)
    dF.set_extra_platforms([
        _P(1322, 1382, 972, "Katzenbaum"), _P(1418, 1478, 888, "Katzenbaum"),
        _P(882, 921, 888, "Kratzbaum"),
    ])
    catF.brain._start_hop(catF.body, dF)
    assert catF.brain.hop_target is not None
    assert catF.brain.hop_target.caption in ("Katzenbaum", "Kratzbaum"), \
        catF.brain.hop_target.caption
    # supervise on furniture -> naps there (rigged rng, energy < 80)
    catF.brain.needs["energy"] = 70.0
    post = next(p for p in dF.platforms if p.caption == "Kratzbaum")
    catF.body.platform = post
    catF.body.y = post.y
    catF.brain.state = "supervise"
    catF.brain.state_left = 0.005
    catF.brain.tick(DT, catF.body, dF)  # tick decrements and resolves supervise
    assert catF.brain.state == "sleep", catF.brain.state
    # sleep chosen while on furniture -> stays in place (no bed walk)
    catF.brain.state_left = 0.0
    catF.brain.bed_x = 100.0
    catF.body.target_x = None  # clear the hop-walk remainder
    catF.brain._ritual_done = True  # test the in-place branch specifically
    catF.brain._start("sleep", catF.body, dF)
    assert catF.brain.state == "sleep" and catF.body.target_x is None
    print("P13: furniture hop + nap preference OK")

    # -- P15: narrow-platform jitter fix, rituals, zoomies, chains -------------
    dN = DesktopState(1920, 1080)
    narrow = _P(882, 921, 900, "Kratzbaum")  # 39 px wide (scratch post top)
    dN.set_extra_platforms([narrow])
    catN = Cat(900, 900, rng=random.Random(71))
    catN.body.platform = narrow
    catN.body.y = narrow.y
    falls = 0
    for _ in range(int(40 / DT)):
        was_air = catN.body.airborne
        catN.tick(DT, dN)
        if catN.body.airborne and not was_air:
            falls += 1
        catN.brain.sounds.clear()
    assert falls <= 1, f"jitter loop on narrow platform: {falls} falls"

    class _LowRng2(random.Random):
        def random(self) -> float:
            return 0.1

    catR = Cat(500, 1080, rng=_LowRng2(72))
    dR = DesktopState(1920, 1080)
    catR.brain._start("sleep", catR.body, dR)
    assert catR.brain.state == "ritual_sit", catR.brain.state

    catZ2 = Cat(400, 1080, rng=random.Random(73))
    catZ2.brain.litter_x = 900.0
    catZ2.brain.needs["bladder"] = 25.0
    dZ2 = DesktopState(1920, 1080)
    seenZ: set[str] = set()
    for _ in range(int(40 / DT)):
        catZ2.tick(DT, dZ2)
        seenZ.add(catZ2.brain.state)
        catZ2.brain.sounds.clear()
    assert "zoomies" in seenZ, seenZ

    catE = Cat(500, 1080, rng=_LowRng2(74))
    catE.brain.food_x = 110.0
    catE.brain.food_fill = 100.0
    catE.brain.state = "eating"
    catE.brain.state_left = 0.01
    catE.tick(DT, DesktopState(1920, 1080))
    catE.brain.sounds.clear()
    assert catE.brain.state == "groom" and catE.brain._chain_groom_sleep
    print("P15: jitter, ritual, zoomies, chain OK")

    # -- P16: occlusion-clipped platforms + windows as walls --------------------
    dO = DesktopState(1920, 1080)
    dO.set_windows([
        {"x": 100, "y": 500, "w": 600, "h": 400, "caption": "back"},
        {"x": 500, "y": 400, "w": 700, "h": 500, "caption": "front"},
    ])
    tops = sorted((p.x0, p.x1, p.caption) for p in dO.platforms if not p.floor)
    # 'back' is only jumpable on its visible edge (100..500); 'front' is full
    assert (100.0, 500.0, "back") in tops, tops
    assert (500.0, 1200.0, "front") in tops, tops
    assert not any(p[2] == "back" and p[1] > 500.0 for p in tops), tops
    # wall: the cat walks right, foreground window at x=600 -> never stands
    # on the floor INSIDE the wall's span (jumping ONTO the window is legal)
    dW = DesktopState(1920, 1080)
    dW.set_windows([{"x": 600, "y": 600, "w": 500, "h": 480, "caption": "wall"}])
    catW2 = Cat(500, 1080, rng=random.Random(81))
    catW2.tick(DT, dW)  # resolve floor
    catW2.body.walk_to(1000.0, 230.0)
    turned = False
    crossed_floor = False
    for _ in range(int(10 / DT)):
        catW2.tick(DT, dW)
        catW2.brain.sounds.clear()
        if catW2.body.facing == -1 and catW2.body.x <= 600:
            turned = True
        if (catW2.body.platform is not None and catW2.body.platform.floor
                and 610 < catW2.body.x < 1090):
            crossed_floor = True
    assert turned, "cat never turned around at the wall"
    assert not crossed_floor, "cat stood on the floor inside the wall span"
    print("P16: occlusion platforms + walls OK")

    # -- P20: face wash = ear fold + 8 paw licks, distinct from groom ----------
    catG = Cat(500, 1080, rng=_LowRng2(91))
    dG = DesktopState(1920, 1080)
    catG.brain._start("groom", catG.body, dG)
    assert catG.brain.state == "ear_fold" and catG.brain._lick_cycles == 8, \
        catG.brain.state
    seenG: set[str] = set()
    for _ in range(int(8 / DT)):
        catG.tick(DT, dG)
        seenG.add(catG.brain.state)
        catG.brain.sounds.clear()
    assert "lick_paw" in seenG, seenG
    assert catG.brain._lick_cycles == 0
    assert {"groom", "ear_fold", "lick_paw"} <= set(sprites.SPRITES), \
        "distinct self-care poses missing"
    print("P20: face wash sequence OK")

    # -- P24: logic fixes + new animations ------------------------------------
    from plasmacat.cat.toys import Ball as _Ball

    # same-level long hops must work (the ~140 px startle jump silently
    # failed before: the fixed -350 impulse needed vx > cap)
    dH = DesktopState(1920, 1080)
    catH = Cat(400, 1080, rng=random.Random(101))
    catH.tick(DT, dH)  # resolve the floor platform
    assert catH.body.jump_to(catH.body.x + 200, catH.body.y), \
        "same-level long hop refused"
    while catH.body.airborne:
        catH.body.tick(DT, dH)
    assert abs(catH.body.x - 600) < 30, catH.body.x
    # startle now really hops backward (used to degrade to 'alert' always)
    catH2 = Cat(960, 1080, rng=random.Random(102))
    catH2.tick(DT, dH)
    dH.set_cursor(1000, 1000)
    catH2.brain.on_startle(catH2.body, dH)
    assert catH2.brain.state == "startle_air", catH2.brain.state
    # a batted ball flies freely (no roll friction in the air anymore)
    bb = _Ball(500, 1080)
    bb.on_ground = True
    bb.bat(400.0, dH, power=1.0)
    assert not bb.on_ground, "bat left on_ground set (air friction bug)"
    x_at_05 = None
    for i in range(int(1.0 / DT)):
        bb.tick_physics(DT, dH)
        if x_at_05 is None and i >= int(0.5 / DT):
            x_at_05 = bb.x
    assert bb.x > 560, f"kicked ball barely moved: {bb.x:.0f}"
    # a wall block feeds the brain's wander cooldown (was dead code before)
    catH3 = Cat(500, 1080, rng=random.Random(103))
    catH3.body.blocked = True
    catH3.tick(DT, dH)
    assert catH3.brain.wander_cooldown > 0, "wall block never reached the brain"
    # eating ends early when full, and the empty bowl is not camped forever
    catH4 = Cat(500, 1080, rng=random.Random(104))
    catH4.brain.food_x = 110.0
    catH4.brain.needs["hunger"] = 98.0
    catH4.brain.food_fill = 100.0
    catH4.brain.state = "eating"
    catH4.brain.state_left = 300.0
    for _ in range(int(8 / DT)):
        catH4.tick(DT, dH)
        catH4.brain.sounds.clear()
    assert catH4.brain.state != "eating", "cat kept eating with a full stomach"
    catH4.brain.needs["hunger"] = 20.0
    catH4.brain.food_fill = 0.0
    catH4.brain.state = "eating"
    catH4.brain.state_left = 300.0
    for _ in range(int(6 / DT)):
        catH4.tick(DT, dH)
        catH4.brain.sounds.clear()
    assert catH4.brain.state != "eating", "cat camped the empty bowl forever"
    assert catH4.brain._food_beg_cd > 0, "no empty-bowl cooldown"
    # the hunt trigger must not interrupt private business
    catH5 = Cat(500, 1080, rng=random.Random(105))
    catH5.brain.state = "littering"
    catH5.brain.on_hunt_trigger(catH5.body, (600, 900), dH)
    assert catH5.brain.state == "littering", "hunt interrupted the litter box"
    catH5.brain.state = "wheel_run"
    catH5.brain.on_hunt_trigger(catH5.body, (600, 900), dH)
    assert catH5.brain.state == "wheel_run", "hunt interrupted the wheel"
    # wake sequence: sleep end -> yawn or stretch before anything else
    catH6 = Cat(500, 1080, rng=random.Random(106))
    catH6.tick(DT, dH)
    catH6.brain.state = "sleep"
    catH6.brain.state_left = 0.01
    catH6.brain._was_sleeping = True
    seenH: set[str] = set()
    for _ in range(int(6 / DT)):
        catH6.tick(DT, dH)
        seenH.add(catH6.brain.state)
        catH6.brain.sounds.clear()
    assert seenH & {"yawn", "stretch"}, f"no wake sequence: {seenH}"
    # littering is squat -> cover -> relieved
    catH7 = Cat(500, 1080, rng=random.Random(107))
    catH7.brain.litter_x = 900.0
    catH7.tick(DT, dH)
    catH7.brain.state = "littering"
    catH7.brain.state_left = 0.01
    seenL: set[str] = set()
    for _ in range(int(4 / DT)):
        catH7.tick(DT, dH)
        seenL.add(catH7.brain.state)
        catH7.brain.sounds.clear()
    assert "litter_cover" in seenL, seenL
    assert catH7.brain.needs["bladder"] > 90
    # belly-up sleep needs deep trust (attachment level 3+) and regenerates
    catH8 = Cat(500, 1080, rng=_LowRng2(108))
    catH8.brain.attachment_xp = 1600.0
    catH8.brain._ritual_done = True
    catH8.tick(DT, dH)  # resolve the floor platform
    catH8.brain._start("sleep", catH8.body, dH)
    assert catH8.brain.state == "sleep_belly", catH8.brain.state
    catH8.brain.needs["energy"] = 50.0
    for _ in range(int(3 / DT)):
        catH8.tick(DT, dH)
        catH8.brain.sounds.clear()
    assert catH8.brain.needs["energy"] > 50.0, "no energy regen in belly sleep"
    # the bed walk still exists (rigged rng picks it) and kneading comes first
    catH9 = Cat(500, 1080, rng=_LowRng2(109))
    catH9.brain.bed_x = 1400.0
    catH9.brain._ritual_done = True
    catH9.tick(DT, dH)
    catH9.brain._start("sleep", catH9.body, dH)
    assert catH9.brain.state == "to_bed", catH9.brain.state
    while catH9.body.target_x is not None:
        catH9.tick(DT, dH)
        catH9.brain.sounds.clear()
    catH9.tick(DT, dH)  # let _continue() notice the arrival
    catH9.brain.sounds.clear()
    assert catH9.brain.state == "knead", catH9.brain.state
    # the pounce is telegraphed by the butt wiggle
    catHA = Cat(500, 1080, rng=random.Random(110))
    catHA.tick(DT, dH)
    dH.set_cursor(600, 1000)
    catHA.brain.on_hunt_trigger(catHA.body, (600.0, 1000.0), dH)
    catHA.brain.state_left = 4.0
    seenW: set[str] = set()
    for _ in range(int(6 / DT)):
        dH.cursor_speed = 0.0
        dH.cursor_active = True
        catHA.tick(DT, dH)
        seenW.add(catHA.brain.state)
        catHA.brain.sounds.clear()
    assert "wiggle" in seenW, f"no butt wiggle before the pounce: {seenW}"
    # the toy-watch follows the ball instead of standing still
    from plasmacat.cat.toys import ToyManager as _TM

    catHB = Cat(500, 1080, rng=random.Random(111))
    tmB = _TM(rng=random.Random(111))
    catHB.brain.toys = tmB
    ballB = tmB.spawn("ball", 800, 1080)
    catHB.brain.state = "toy_watch"
    catHB.brain.state_left = 30.0
    catHB.brain._fx_t = 0.0
    catHB.tick(DT, dH)
    catHB.brain.sounds.clear()
    for _ in range(int(3 / DT)):
        catHB.tick(DT, dH)
        tmB.tick(DT, dH, catHB, catHB.brain.sounds)
        catHB.brain.sounds.clear()
    assert catHB.body.x > 700, \
        f"toy_watch must follow the ball (cat={catHB.body.x:.0f})"
    assert abs(catHB.body.x - ballB.x) < 500, \
        f"cat lost the ball entirely (cat={catHB.body.x:.0f}, ball={ballB.x:.0f})"
    # sprite table integrity for the new poses
    for k in ("loaf", "stretch", "yawn", "knead", "sleep_belly", "wiggle",
              "tail_lash", "alert", "squat", "cover", "drink", "watch"):
        assert k in sprites.SPRITES and k in ANIMATIONS, k
    assert set(sprites.SPRITES) == set(sprites.ACCESSORIES)
    sprites.validate()
    print("P24: logic fixes + new animations OK")

    # -- P25: vomit mechanic, fountain, shelves, box, floor snap --------------
    # boredom eating requires neglect; a cared-for cat never overeats
    catV = Cat(500, 1080, rng=random.Random(201))
    dV = DesktopState(1920, 1080)
    catV.brain.food_x = 110.0
    catV.brain.food_fill = 100.0
    catV.brain.needs["hunger"] = 70.0
    catV.tick(DT, dV)
    assert catV.brain._score("eat", dV) == 0.0, "ate from boredom while cared for"
    catV.brain._neglect_s = 5000.0
    assert catV.brain._score("eat", dV) > 0.0, "no boredom eating when neglected"
    # overeating from boredom ends in vomit
    catV2 = Cat(500, 1080, rng=random.Random(202))
    catV2.brain.food_x = 110.0
    catV2.brain.food_fill = 100.0
    catV2.brain.needs["hunger"] = 96.0
    catV2.brain._neglect_s = 5000.0
    catV2.brain._bored_eat = True
    catV2.brain.state = "eating"
    catV2.brain.state_left = 60.0
    seenV: set[str] = set()
    for _ in range(int(30 / DT)):
        catV2.tick(DT, dV)
        seenV.add(catV2.brain.state)
        catV2.brain.sounds.clear()
    assert "retch" in seenV, f"no vomit after overeating: {seenV}"
    assert catV2.brain.puke_spots, "no puddle after vomiting"
    assert catV2.brain.needs["hunger"] <= 56.0
    catV2.brain.clean_puke()
    assert not catV2.brain.puke_spots
    # stacked grass + neglect: vomit chance is real
    catV3 = Cat(500, 1080, rng=random.Random(203))
    catV3.brain.grass_x = 400.0
    catV3.brain._neglect_s = 5000.0
    puked = 0
    for trial in range(20):
        catV3.rng = random.Random(300 + trial)
        catV3.brain._grass_recent = 60.0
        catV3.brain.grass_charges = 3.0
        catV3.brain.state = "nibbling"
        catV3.brain.state_left = 0.01
        for _ in range(int(2 / DT)):
            catV3.tick(DT, dV)
            catV3.brain.sounds.clear()
        if catV3.brain.state == "retch":
            puked += 1
        catV3.brain.state = "idle"
    assert puked >= 10, f"stacked grass only puked {puked}/20 times"
    # the fountain never runs dry
    catV4 = Cat(500, 1080, rng=random.Random(204))
    catV4.brain.water_x = 200.0
    catV4.brain.needs["thirst"] = 30.0
    catV4.brain.state = "drinking"
    catV4.brain.state_left = 30.0
    for _ in range(int(10 / DT)):
        catV4.tick(DT, dV)
        catV4.brain.sounds.clear()
    assert catV4.brain.water_fill == 100.0, "fountain lost water?!"
    assert catV4.brain.needs["thirst"] > 30.0
    # a toy can never fall through the floor (work-area moved under it)
    dV5 = DesktopState(1920, 1080)
    lost_ball = _Ball(500, dV5.floor_y + 500)   # below the floor (panel grew)
    for _ in range(int(3 / DT)):
        lost_ball.tick_physics(DT, dV5)
    assert lost_ball.y <= dV5.floor_y + 1, f"ball fell into the void: {lost_ball.y}"
    # wall shelves are jumpable platforms at their placed height
    dV6 = DesktopState(1920, 1080)
    dV6.set_extra_platforms([_P(600, 720, 700, "Regal")])
    p = dV6.platform_below(660, 600)  # falling from above the shelf
    assert p.caption == "Regal" and p.y == 700, p
    # the cardboard box: approach -> hop in -> hide
    catV7 = Cat(500, 1080, rng=random.Random(205))
    catV7.brain.box_x = 900.0
    dV7 = DesktopState(1920, 1080)
    dV7.set_extra_platforms([_P(845, 955, 1050, "Karton")])
    catV7.brain._start("hide", catV7.body, dV7)
    assert catV7.brain.state == "to_box"
    seenB: set[str] = set()
    for _ in range(int(20 / DT)):
        catV7.tick(DT, dV7)
        seenB.add(catV7.brain.state)
        catV7.brain.sounds.clear()
    assert "box_hide" in seenB, seenB
    # sprite/prop integrity for the new states and props
    for k in ("retch", "box_peek"):
        assert k in sprites.SPRITES and k in ANIMATIONS, k
    from plasmacat.props import PROPS
    for k in ("food_bowl", "food_bowl_empty", "fountain_0", "fountain_1",
              "fountain_2", "puke", "wall_shelf", "box", "box_front",
              "cat_door_0", "cat_door_1", "cat_door_2"):
        assert k in PROPS, k
    sprites.validate()
    print("P25: vomit, fountain, shelves, box, floor snap OK")

    # -- P26: state-of-the-art refinement --------------------------------------
    from plasmacat.cat.brain import circadian

    # acceleration/braking: no instant speed, no overshoot
    dA = DesktopState(1920, 1080)
    catA2 = Cat(200, 1080, rng=random.Random(301))
    catA2.tick(DT, dA)  # resolve the floor platform
    body = catA2.body
    body.walk_to(700.0, 230.0)
    speeds = []
    max_x = 0.0
    for _ in range(int(6 / DT)):
        body.tick(DT, dA)
        speeds.append(body.cur_speed)
        max_x = max(max_x, body.x)
        if body.target_x is None:
            break
    assert speeds[1] < 230.0, f"instant full speed: {speeds[1]}"
    assert max(speeds) > 200.0, f"never reached run speed: {max(speeds)}"
    assert max_x <= 701.0, f"overshot the target: {max_x}"
    assert body.target_x is None and abs(body.x - 700.0) < 2.0
    # jump anticipation (prep) + landing absorb (land)
    dA3 = DesktopState(1920, 1080)
    dA3.set_windows([{"x": 700, "y": 500, "w": 500, "h": 400, "caption": "Hop"}])
    catA3 = Cat(800, 1080, rng=random.Random(302))
    catA3.tick(DT, dA3)
    catA3.brain.hop_target = next(p for p in dA3.platforms if p.caption == "Hop")
    catA3.brain._try_jump_up(catA3.body)
    assert catA3.brain.state == "prep_jump", catA3.brain.state
    seenA: set[str] = set()
    for _ in range(int(6 / DT)):
        catA3.tick(DT, dA3)
        seenA.add(catA3.brain.state)
        catA3.brain.sounds.clear()
    assert "air_up" in seenA, seenA
    # follow: keeps a polite distance from the cursor
    catA4 = Cat(400, 1080, rng=random.Random(303))
    catA4.brain.attachment_xp = 400.0  # level 2
    dA4 = DesktopState(1920, 1080)
    dA4.set_cursor(1000, 1000)
    dA4.cursor_active = True
    catA4.tick(DT, dA4)
    catA4.brain._start("follow", catA4.body, dA4)
    for _ in range(int(8 / DT)):
        catA4.tick(DT, dA4)
        catA4.brain.sounds.clear()
    assert 110 <= abs(catA4.body.x - 1000) <= 400, catA4.body.x
    # gift: the plush is carried to the cursor and dropped there
    from plasmacat.cat.toys import ToyManager as _TM2

    catA5 = Cat(400, 1080, rng=random.Random(304))
    catA5.brain.attachment_xp = 1600.0
    tmA = _TM2(rng=random.Random(304))
    plushA = tmA.spawn("plush", 600, 1080)
    catA5.brain.toys = tmA
    dA5 = DesktopState(1920, 1080)
    dA5.set_cursor(1200, 1000)
    dA5.cursor_active = True
    catA5.tick(DT, dA5)
    catA5.brain._start("gift", catA5.body, dA5)
    delivered = False
    for _ in range(int(30 / DT)):
        catA5.tick(DT, dA5)
        tmA.tick(DT, dA5, catA5, catA5.brain.sounds)
        catA5.brain.sounds.clear()
        if plushA.carried:
            delivered = True
        if delivered and not plushA.carried and abs(plushA.x - 1200) < 400:
            break
    assert delivered, "plush was never carried"
    assert not plushA.carried, "plush was never dropped"
    assert abs(plushA.x - 1200) < 400, f"dropped far from the cursor: {plushA.x}"
    # paw bat: a teasing cursor in front of her face gets patted
    detA = InteractionDetector()
    rectA = (500 - 48, 1080 - 96, 96, 96)
    ta = 3000.0
    pats = 0
    for i in range(300):  # 5 s of slow teasing in front of her face
        ta += DT
        cx = 500 + 60 * math.sin(ta * 3)
        cy = 1080 - 70
        detA.tracker.add(cx, cy, ta)
        for ev in detA.tick(DT, rectA, (cx, cy)):
            if ev == "pat":
                pats += 1
    assert pats >= 1, "teasing cursor never triggered a paw bat"
    # circadian: night is sleepier than dusk; dawn is active
    assert circadian(2)[0] > circadian(19)[0]
    assert circadian(6)[1] > 1.0
    # the favorite toy is preferred over a closer other toy
    catA6 = Cat(400, 1080, rng=random.Random(305))
    tmB = _TM2(rng=random.Random(305))
    tmB.spawn("ball", 450, 1080)     # closer
    tmB.spawn("plush", 900, 1080)
    catA6.brain.toys = tmB
    catA6.brain.fav_toy = "plush"
    dA6 = DesktopState(1920, 1080)
    catA6.tick(DT, dA6)
    catA6.brain._start("play_toy", catA6.body, dA6)
    assert catA6.brain._play_toy_target.kind == "plush"
    assert "paw_bat" in sprites.SPRITES and "paw_bat" in ANIMATIONS
    sprites.validate()
    print("P26: accel/brake, prep/land, follow, gift, pat, circadian, fav OK")

    # -- P28: level dwell (no chaotic flip-flopping) ---------------------------
    from plasmacat.cat.brain import LEVEL_DWELL_S

    # lying down on the floor commits to the desktop (back) level
    catL = Cat(500, 1080, rng=random.Random(401))
    dL = DesktopState(1920, 1080)
    catL.tick(DT, dL)
    assert catL.brain.level == "front"
    catL.brain._ritual_done = True
    catL.brain._start("sleep", catL.body, dL)
    catL.tick(DT, dL)
    catL.brain.sounds.clear()
    assert catL.brain.level == "back", catL.brain.level
    # for 30 s every choice stays back/neutral — no front behaviors
    picks = set()
    for _ in range(300):
        picks.add(catL.brain._choose(dL, catL.body))
    assert not (picks & {"chase", "follow", "gift", "play_toy", "wander"}), picks
    # after the dwell, front is allowed again
    catL.brain._level_t = LEVEL_DWELL_S
    picks2 = set()
    for _ in range(300):
        picks2.add(catL.brain._choose(dL, catL.body))
    assert picks2 & {"chase", "follow", "gift", "play_toy", "wander"}, picks2
    # neutral states never flip the level
    catL2 = Cat(500, 1080, rng=random.Random(402))
    catL2.tick(DT, dL)
    catL2.brain._level = "back"
    catL2.brain._level_t = 5.0  # mid-dwell
    for st in ("groom", "sit", "loaf", "yawn", "watch"):
        catL2.brain.state = st
        catL2.brain.state_left = 0.01
        catL2.tick(DT, dL)
        catL2.brain.sounds.clear()
        assert catL2.brain.level == "back", (st, catL2.brain.level)
    # hop targets are filtered by the dwell level
    catL3 = Cat(500, 1080, rng=random.Random(403))
    dL3 = DesktopState(1920, 1080)
    dL3.set_windows([{"x": 700, "y": 500, "w": 500, "h": 400, "caption": "Win"}])
    dL3.set_extra_platforms([_P(1300, 1400, 900, "Katzenbaum")])
    catL3.tick(DT, dL3)
    catL3.brain._level = "front"
    catL3.brain._level_t = 5.0
    catL3.brain._start_hop(catL3.body, dL3)
    assert catL3.brain.hop_target is None or \
        catL3.brain.hop_target.caption == "Win", catL3.brain.hop_target
    # a committed behavior can't flip mid-dwell: redirect instead
    catL4 = Cat(500, 1080, rng=random.Random(404))
    catL4.brain.food_x = 110.0
    catL4.brain.needs["hunger"] = 10.0   # starving: eat would score max
    catL4.tick(DT, dL)
    catL4.brain._level = "front"
    catL4.brain._level_t = 5.0
    for _ in range(int(6 / DT)):
        catL4.tick(DT, dL)
        catL4.brain.sounds.clear()
    assert catL4.brain.level == "front", catL4.brain.level
    assert catL4.brain.state not in ("to_food", "eating"), catL4.brain.state
    # user events override the dwell (the hunt comes forward immediately)
    catL5 = Cat(500, 1080, rng=random.Random(405))
    catL5.tick(DT, dL)
    catL5.brain._level = "back"
    catL5.brain._level_t = 5.0
    catL5.brain.on_hunt_trigger(catL5.body, (600.0, 900.0), dL)
    assert catL5.brain.state == "hunt_stalk"
    catL5.tick(DT, dL)
    catL5.brain.sounds.clear()
    assert catL5.brain.level == "front", catL5.brain.level
    # the eat -> groom -> sleep chain stays on the back level now
    catL6 = Cat(500, 1080, rng=_LowRng2(406))
    catL6.brain.food_x = 110.0
    catL6.brain.food_fill = 100.0
    catL6.brain.state = "eating"
    catL6.brain.state_left = 0.01
    catL6.tick(DT, dL)
    assert catL6.brain.level == "back"
    catL6.brain.sounds.clear()
    assert catL6.brain.state == "groom" and catL6.brain._chain_groom_sleep
    catL6.brain.state_left = 0.01
    catL6.tick(DT, dL)
    catL6.brain.sounds.clear()
    assert catL6.brain.level == "back", catL6.brain.level
    print("P28: level dwell OK")

    # -- P34: laser pointer ------------------------------------------------------
    from plasmacat.cat.toys import Laser, ToyManager as _TM3

    # the dot follows the cursor with lag, blinks out on escape
    dZ = DesktopState(1920, 1080)
    dZ.set_cursor(1000, 800)
    lz = Laser(100.0, 100.0)
    for _ in range(int(2 / DT)):
        lz.tick_physics(DT, dZ)
    assert abs(lz.x - 1000) < 50 and abs(lz.y - 800) < 50, (lz.x, lz.y)
    lz.escape()
    assert not lz.visible
    for _ in range(int(1.0 / DT)):
        lz.tick_physics(DT, dZ)
    assert lz.visible
    # she chases the dot across the floor and pounces it
    catZ = Cat(400, 1080, rng=random.Random(501))
    tmZ = _TM3(rng=random.Random(501))
    catZ.brain.toys = tmZ
    catZ.brain.needs["play"] = 50.0
    tmZ.spawn("laser", 900.0, 900.0)
    dZ.set_cursor(900, 800)
    dZ.cursor_active = True
    catZ.tick(DT, dZ)
    assert catZ.brain._score("laser_chase", dZ) > 0.0
    catZ.brain._start("laser_chase", catZ.body, dZ)
    seenZ: set[str] = set()
    for _ in range(int(25 / DT)):
        catZ.tick(DT, dZ)
        tmZ.tick(DT, dZ, catZ, catZ.brain.sounds)
        seenZ.add(catZ.brain.state)
        catZ.brain.sounds.clear()
    assert "laser_pounce" in seenZ or "wiggle" in seenZ, seenZ
    assert catZ.brain.attachment_xp > 0, "never caught the dot (no XP)"
    # tired cats give up and take a break
    catZ3 = Cat(400, 1080, rng=random.Random(503))
    tmZ3 = _TM3(rng=random.Random(503))
    catZ3.brain.toys = tmZ3
    tmZ3.spawn("laser", 900.0, 900.0)
    catZ3.brain.needs["energy"] = 26.0
    catZ3.tick(DT, dZ)
    catZ3.brain.state = "laser_chase"
    catZ3.brain.state_left = 30.0
    for _ in range(int(2 / DT)):
        catZ3.tick(DT, dZ)
        catZ3.brain.sounds.clear()
    assert catZ3.brain.state != "laser_chase", catZ3.brain.state
    assert catZ3.brain._laser_cd > 0, "no laser cooldown after giving up"
    # and a tired cat won't even start
    assert catZ3.brain._score("laser_chase", dZ) == 0.0
    print("P34: laser pointer OK")

    # -- P38: multi-monitor (multiple work areas) -------------------------------
    from plasmacat.cat.physics import CatBody, WALK_SPEED
    from plasmacat.cat.toys import Ball

    # two side-by-side screens, aligned bottoms: seamless crossing
    dM = DesktopState(1920, 1080)
    dM.set_work_areas([{"x": 0, "y": 0, "w": 1920, "h": 1080},
                       {"x": 1920, "y": 0, "w": 1920, "h": 1080}])
    floors = [p for p in dM.platforms if p.floor]
    assert len(floors) == 2, floors
    assert dM.floor_y == 1080.0 and dM.floor_y_at(2500) == 1080.0
    assert dM.floor_x1 == 3840.0
    body = CatBody(1800.0, 1080.0)
    body.walk_to(2200.0, WALK_SPEED)
    for _ in range(int(30 / DT)):
        body.tick(DT, dM)
        assert not body.airborne, "same-height crossing must not fall"
    assert abs(body.x - 2200.0) < 1.0 and body.y == 1080.0, (body.x, body.y)
    assert body.platform is not None and body.platform.floor

    # a small height step (<= STEP_UP_MAX): she steps up, keeps walking
    dM2 = DesktopState(1920, 1080)
    dM2.set_work_areas([{"x": 0, "y": 0, "w": 1920, "h": 1080},
                        {"x": 1920, "y": -30, "w": 1920, "h": 1080}])  # floor 1050
    assert dM2.floor_y_at(2500) == 1050.0
    body2 = CatBody(1800.0, 1080.0)
    body2.walk_to(2200.0, WALK_SPEED)
    for _ in range(int(30 / DT)):
        body2.tick(DT, dM2)
    assert abs(body2.x - 2200.0) < 1.0 and body2.y == 1050.0, (body2.x, body2.y)

    # a tall step (> STEP_UP_MAX): a wall — she stops and turns around
    dM3 = DesktopState(1920, 1080)
    dM3.set_work_areas([{"x": 0, "y": 0, "w": 1920, "h": 1080},
                        {"x": 1920, "y": -100, "w": 1920, "h": 1080}])  # floor 980
    body3 = CatBody(1800.0, 1080.0)
    body3.walk_to(2200.0, WALK_SPEED)
    for _ in range(int(10 / DT)):
        body3.tick(DT, dM3)
    assert body3.x <= 1920.0 and body3.blocked and body3.facing == -1, \
        (body3.x, body3.blocked, body3.facing)

    # a gap between screens: a wall too, and a fall into it is caught
    dM4 = DesktopState(1920, 1080)
    dM4.set_work_areas([{"x": 0, "y": 0, "w": 1920, "h": 1080},
                        {"x": 2100, "y": 0, "w": 1920, "h": 1080}])
    assert dM4.floor_platform_at(2000.0) is None
    body4 = CatBody(1800.0, 1080.0)
    body4.walk_to(2500.0, WALK_SPEED)
    for _ in range(int(10 / DT)):
        body4.tick(DT, dM4)
    assert body4.x <= 1920.0 and body4.blocked, (body4.x, body4.blocked)
    body4.airborne = True
    body4.vy = 500.0
    body4.platform = None
    body4.x = 2000.0  # falling in the gap: the safety net lands her on A's seam
    for _ in range(int(3 / DT)):
        body4.tick(DT, dM4)
    assert not body4.airborne and body4.y == 1080.0 and body4.x == 1920.0, \
        (body4.x, body4.y, body4.airborne)

    # a toy rests on the second screen's own floor height
    ball = Ball(2500.0, 300.0)
    for _ in range(int(6 / DT)):
        ball.tick_physics(DT, dM2)
    assert ball.on_ground and abs(ball.y - 1050.0) < 1.0, ball.y

    # single-area regression: floor_y unchanged, one floor platform
    dM5 = DesktopState(1920, 1080)
    assert dM5.floor_y == 1080.0
    assert len([p for p in dM5.platforms if p.floor]) == 1
    print("P38: multi-monitor OK")

    # -- P40: litter deposits (visible poop/pee per event) ---------------------
    dP = DesktopState(1920, 1080)
    catP = Cat(400, 1080, rng=random.Random(701))
    catP.brain.litter_x = 600.0
    for _ in range(5):
        catP.brain.state = "litter_cover"
        catP.brain.state_left = 0.0
        catP.tick(DT, dP)
    assert len(catP.brain.litter_deposits) >= 2, catP.brain.litter_deposits
    assert all(d in ("poop", "pee") for d in catP.brain.litter_deposits)
    expected = sum(1.0 if d == "poop" else 0.5
                   for d in catP.brain.litter_deposits)
    assert abs(catP.brain.litter_fill - expected) < 1e-9, \
        (catP.brain.litter_fill, expected)
    catP.brain.clean_litter()
    assert catP.brain.litter_fill == 0.0 and not catP.brain.litter_deposits

    # persistence round-trip (P39 status flag + P40 deposits)
    from pathlib import Path
    import tempfile
    from plasmacat.persist import Customization, GameState, load, save
    st = GameState(customization=Customization(status_window=True),
                   litter_fill=1.5, litter_deposits=["poop", "pee"])
    with tempfile.TemporaryDirectory() as td:
        save(Path(td) / "save.json", st)
        back = load(Path(td) / "save.json")
    assert back is not None and back.litter_deposits == ["poop", "pee"]
    assert back.customization.status_window is True
    print("P39/P40: litter deposits + persistence OK")

    # -- P42: toy consistency fixes ---------------------------------------------
    # 1. 'Clear toys' mid-approach: to_toy must drop the stale target instead
    #    of pouncing at air (and pounce_toy must not 'catch' a deleted toy)
    dC = DesktopState(1920, 1080)
    catC = Cat(400, 1080, rng=random.Random(910))
    tmC = ToyManager(rng=random.Random(910))
    catC.brain.toys = tmC
    toyC = tmC.spawn("plush", 700.0, 1080.0)
    catC.brain._play_toy_target = toyC
    catC.brain.state = "to_toy"
    catC.brain.state_left = 10.0
    tmC.toys.clear()  # the tray's 'Clear toys'
    catC.tick(DT, dC)
    # the stale target is dropped (she may immediately pick a new behavior —
    # the point is: no pounce at a deleted toy)
    assert catC.brain._play_toy_target is None
    assert catC.brain.state not in ("to_toy", "pounce_toy"), catC.brain.state
    # mid-air pounce on a removed toy: no catch, no XP
    catC.brain._play_toy_target = toyC
    catC.brain.state = "pounce_toy"
    catC.brain.state_left = 4.0
    xp0 = catC.brain.attachment_xp
    catC.tick(DT, dC)
    assert catC.brain.state != "enjoy", "caught a toy that no longer exists"
    assert catC.brain.attachment_xp == xp0
    # clear_toy_state resets every toy-targeting behavior
    catC.brain.state = "laser_chase"
    catC.brain.state_left = 30.0
    catC.brain._wiggle_then = ("toy", 500.0, 1080.0)
    catC.brain._gift_toy = toyC
    catC.brain.clear_toy_state()
    assert catC.brain.state == "idle" and catC.brain.state_left == 0.0
    assert catC.brain._wiggle_then is None and catC.brain._gift_toy is None
    # a hunt wiggle survives (it never targeted a toy)
    catC.brain.state = "wiggle"
    catC.brain.state_left = 0.5
    catC.brain._wiggle_then = ("hunt", 500.0, 1080.0)
    catC.brain.clear_toy_state()
    assert catC.brain.state == "wiggle" and catC.brain._wiggle_then is not None
    # 2. string lure clamps to ITS screen's floor, not the primary's (P38)
    dC.set_work_areas([{"x": 0, "y": 0, "w": 1920, "h": 1000},
                       {"x": 1920, "y": 0, "w": 1920, "h": 800}])
    st = tmC.spawn("string", 2500.0, 500.0)
    st.anchor = (2500.0, 300.0)
    for _ in range(int(3 / DT)):
        st.tick_physics(DT, dC)
    assert st.y <= dC.floor_y_at(2500.0) - 6 + 1e-9, (st.y, dC.floor_y_at(2500.0))
    # 3. the plush 'escape' teleport respects the combined work-area span
    catC2 = Cat(400, 1000, rng=random.Random(911))
    tmC2 = ToyManager(rng=random.Random(911))
    catC2.brain.toys = tmC2
    toyC2 = tmC2.spawn("plush", 405.0, 1000.0)  # right next to her: caught
    catC2.brain._play_toy_target = toyC2
    catC2.brain.state = "pounce_toy"
    catC2.brain.state_left = 4.0
    catC2.brain.rng = random.Random(1)  # random() < 0.4 -> the 'escape' fires
    catC2.tick(DT, dC)
    assert dC.floor_x0 + 30 <= toyC2.x <= dC.floor_x1 - 30, toyC2.x
    # 4. status board position persists (P42)
    st2 = GameState(customization=Customization(status_window=True,
                                                status_pos=[100.0, 200.0]))
    with tempfile.TemporaryDirectory() as td:
        save(Path(td) / "s2.json", st2)
        back2 = load(Path(td) / "s2.json")
    assert back2 is not None
    assert back2.customization.status_pos == [100.0, 200.0]
    print("P42: toy fixes (stale target, clear toys, clamps) OK")

    # -- P42b: user control mode (WASD/arrows) ---------------------------------
    dU = DesktopState(1920, 1080)
    catU = Cat(400, 1080, rng=random.Random(920))
    catU.brain._level = "back"  # she starts on the desktop level
    catU.brain.set_user_control(True)
    # key events without control mode are ignored (guard check)
    catU.brain.set_user_control(False)
    catU.brain.on_key_event("right")
    assert not catU.brain.held
    catU.brain.set_user_control(True)
    catU.brain.on_key_event("right")
    assert catU.brain.held.get("right", 0.0) > 0
    x0 = catU.body.x
    for _ in range(int(1.0 / DT)):
        catU.brain.on_key_event("right")  # auto-repeat keeps the key 'held'
        catU.tick(DT, dU)
    assert catU.brain.state == "user", catU.brain.state
    assert catU.body.x > x0 + 50, (x0, catU.body.x)
    assert catU.brain.level == "front", "user control must pull her forward"
    # key held only via auto-repeat refresh: after ~0.4 s silence she stops
    for _ in range(int(0.6 / DT)):
        catU.tick(DT, dU)
    assert not catU.brain.held and catU.body.target_x is None
    # left works too; opposite keys cancel out
    catU.brain.on_key_event("left")
    catU.tick(DT, dU)
    assert catU.body.facing == -1
    catU.brain.on_key_event("right")
    for _ in range(int(0.2 / DT)):
        catU.tick(DT, dU)
    assert catU.body.target_x is None, "left+right = stand still"
    # jump is an edge event; stop clears held keys
    catU.brain.on_key_event("jump")
    catU.tick(DT, dU)
    assert catU.body.airborne, "jump key must start a hop"
    catU.brain.on_key_event("right")
    catU.brain.on_key_event("stop")
    assert not catU.brain.held
    # reflexes never seize a user-driven cat
    while catU.body.airborne:
        catU.tick(DT, dU)
    catU.brain.on_hunt_trigger(catU.body, (900, 900), dU)
    assert catU.brain.state == "user", catU.brain.state
    catU.brain.on_startle(catU.body, dU)
    assert catU.brain.state == "user", catU.brain.state
    # switching the mode off hands her back to the brain
    catU.brain.set_user_control(False)
    assert catU.brain.state == "idle" and catU.brain.state_left == 0.0
    print("P42b: user control mode OK")

    # -- P42c: mouse hunt mini-game ---------------------------------------------
    from plasmacat.cat.minigames import MAX_CAUGHT, MouseHunt
    from plasmacat.props import prop_to_pixels

    w, h, _px = prop_to_pixels("mouse")  # sprite is valid + registered
    assert w == 14 and h == 8, (w, h)
    dM = DesktopState(1920, 1080)
    catM = Cat(600, 1080, rng=random.Random(930))
    tmM = ToyManager(rng=random.Random(930))
    catM.brain.toys = tmM
    # a mouse flees the cat (cat left of it -> it sprints right)
    m = tmM.spawn("mouse", 700.0, 1080.0)
    for _ in range(int(0.3 / DT)):  # within the flee sprint: no wander yet
        tmM.tick(DT, dM, catM, catM.brain.sounds)
    assert m.vx > 0 and m.x > 720.0, (m.vx, m.x)
    assert m.y == dM.floor_y_at(m.x)
    # and she gets CORNERED at the world's wall (flee can't beat the wall)
    m.x = dM.floor_x1 - 25.0
    catM.body.x = dM.floor_x1 - 200.0
    for _ in range(int(1.0 / DT)):
        tmM.tick(DT, dM, catM, catM.brain.sounds)
    assert m.x < dM.floor_x1 - 20, m.x  # never pushed through the wall
    assert m.vx == 0.0, ("cornered mouse must be catchable", m.vx)
    # session: spawns mice, a touch catches one (score + XP), ends on limit
    hunt = MouseHunt(rng=random.Random(931))
    hunt._spawn_t = 0.0
    hunt.tick(DT, dM, catM, tmM, catM.brain.sounds)
    assert any(t.kind == "mouse" for t in tmM.toys), "no mouse spawned"
    prey = next(t for t in tmM.toys if t.kind == "mouse")
    prey.x, prey.y = catM.body.x + 10, catM.body.y  # practically in her paws
    xp0 = catM.brain.attachment_xp
    hunt.tick(DT, dM, catM, tmM, catM.brain.sounds)
    assert hunt.score == 1 and catM.brain.attachment_xp > xp0
    assert prey not in tmM.toys
    hunt.score = MAX_CAUGHT  # simulate a finished hunt
    hunt.tick(DT, dM, catM, tmM, catM.brain.sounds)
    assert not hunt.active
    assert not [t for t in tmM.toys if t.kind == "mouse"], "mice must leave"
    print("P42c: mouse hunt OK")

    # -- P43: resting ball must not micro-bounce at the idle frame rate --------
    dR = DesktopState(1920, 1080)
    catR = Cat(400, 1080, rng=random.Random(940))
    tmR = ToyManager(rng=random.Random(940))
    rb = tmR.spawn("ball", 600.0, 1080.0)
    rb.on_ground = True
    for _ in range(30):
        b = rb.tick_physics(0.066, dR)  # 15 fps idle cadence
        assert not b, "resting ball must never bounce"
    assert rb.y == 1080.0 and rb.vy == 0.0 and rb.on_ground
    # ...but rolling off an edge still falls
    rb2 = tmR.spawn("ball", 900.0, 1080.0)
    rb2.on_ground = True
    dR.set_work_areas([{"x": 0, "y": 0, "w": 800, "h": 1080}])  # floor shrinks
    for _ in range(30):
        rb2.tick_physics(0.066, dR)
    assert rb2.y == dR.floor_y_at(rb2.x), "ball must land on the new floor"
    print("P43: resting ball OK")

    print("SIM_TEST_OK")


if __name__ == "__main__":
    main()
