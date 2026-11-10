import math
import random

from plasmacat.bridge.desktop import DesktopState
from plasmacat.cat.cat import Cat
from plasmacat.cat.interactions import CursorTracker, InteractionDetector

DT = 1 / 60


def test_speed_decays_when_cursor_rests():
    tr = CursorTracker()
    t = 0.0
    for i in range(30):
        t += DT
        tr.add(500 + 300 * math.sin(i), 400, t)
    assert tr.speed(now=t) > 100
    assert tr.reversals(now=t) >= 2
    assert tr.speed(now=t + 3.0) == 0.0
    assert tr.reversals(now=t + 3.0) == 0


def test_dist_hist_bounded_while_cursor_parked():
    det = InteractionDetector(CursorTracker())
    det.tracker.add(100, 100, 5.0)
    for _ in range(10_000):
        det.tick(DT, (900, 900, 100, 80), (100, 100))
    assert len(det._dist_hist) <= 64


def test_no_hunt_events_after_the_cursor_rests():
    det = InteractionDetector(CursorTracker())
    t = 0.0
    for i in range(30):   # erratic swooshing next to the cat, then stop
        t += DT
        cx = 960 + 300 * math.sin(t * 25)
        det.tracker.add(cx, 900, t)
        det.tick(DT, (912, 1008, 96, 72), (cx, 900))
    hunt_ticks = [k for k in range(180)  # 3 s parked
                  if "hunt" in det.tick(DT, (912, 1008, 96, 72), (cx, 900))]
    assert not [k for k in hunt_ticks if k >= 60]   # silent after 1 s


def test_headrub_fires_with_two_cats_sharing_the_tracker():
    tracker = CursorTracker()
    det_a, det_b = InteractionDetector(tracker), InteractionDetector(tracker)
    rect_a, rect_b = (500, 500, 128, 96), (1200, 500, 128, 96)
    t, events = 0.0, []
    for i in range(90):   # 1.5 s lingering gently on A's head
        t += DT
        cx, cy = 560 + (i % 2), 520
        tracker.add(cx, cy, t)
        events += det_a.tick(DT, rect_a, (cx, cy))
        det_b.tick(DT, rect_b, (cx, cy))
    assert "rub" in events


def test_no_hunt_when_cursor_inactive():
    d = DesktopState(1920, 1080)
    cat = Cat(960, 1080, rng=random.Random(2))
    cat.brain.needs["play"] = 80
    d.cursor_active = False
    before = cat.brain.state
    cat.brain.on_hunt_trigger(cat.body, (900, 900), d)
    assert cat.brain.state == before
