from plasmacat.bridge.desktop import DesktopState
from plasmacat.cat.physics import CatBody


def _win(id_, x, y, w=400, h=300):
    return {"id": id_, "x": x, "y": y, "w": w, "h": h}


def _stand_on(body, desktop, win_id):
    body.platform = next(p for p in desktop.platforms if p.win_id == win_id)
    body.y = body.platform.y
    body.airborne = False


def test_platform_identity_is_the_window_id():
    d = DesktopState(1920, 1080)
    d.set_windows([_win("A", 200, 400), _win("B", 900, 400)])
    ref = next(p for p in d.platforms if p.win_id == "A")
    # A moves far right, B moves to where A was: the nearest platform is B now
    d.set_windows([_win("A", 1300, 400), _win("B", 210, 400)])
    cur = d.find_platform(ref)
    assert cur is not None and cur.win_id == "A"


def test_platform_survives_window_changes_without_dropping_the_cat():
    d = DesktopState(1920, 1080)
    d.set_windows([_win("A", 200, 400)])
    body = CatBody(400, 400)
    _stand_on(body, d, "A")
    d.set_windows([_win("A", 200, 400)])   # e.g. a title change: same geometry
    body.tick(1 / 60, d)
    assert not body.airborne
    assert body.platform.win_id == "A"


def test_ride_uses_window_x_not_segment():
    d = DesktopState(1920, 1080)
    # B (on top) covers A's left part: A's visible top edge starts at 500
    d.set_windows([_win("A", 200, 400, w=800), _win("B", 100, 300, w=400, h=400)])
    body = CatBody(800, 400)
    _stand_on(body, d, "A")
    assert body.platform.x0 == 500
    d.set_windows([_win("A", 200, 400, w=800), _win("B", 1300, 300, w=400, h=400)])
    body.tick(1 / 60, d)
    assert body.x == 800      # A never moved, so the cat must not either


def test_ride_follows_a_moving_window():
    d = DesktopState(1920, 1080)
    d.set_windows([_win("A", 200, 400, w=800)])
    body = CatBody(600, 400)
    _stand_on(body, d, "A")
    d.set_windows([_win("A", 260, 380, w=800)])
    body.tick(1 / 60, d)
    assert (body.x, body.y) == (660, 380)


def test_floor_under_picks_the_cats_own_screen():
    d = DesktopState(3840, 1080)
    d.set_work_areas([{"x": 0, "y": 0, "w": 1920, "h": 1040},
                      {"x": 1920, "y": 0, "w": 1920, "h": 1000}])
    assert d.floor_under(2500).y == 1000
    assert d.floor_under(300).y == 1040
    assert d.floor_under(5000).y == 1000   # off-world: nearest floor


def test_windows_property_is_public():
    d = DesktopState(1920, 1080)
    d.set_windows([_win("A", 200, 400)])
    assert d.windows[0]["id"] == "A"


def test_chase_target_stays_on_the_cursors_screen():
    import random
    from plasmacat.cat.cat import Cat
    d = DesktopState(3840, 1080)
    d.set_work_areas([{"x": 0, "y": 0, "w": 1920, "h": 1040},
                      {"x": 1920, "y": 0, "w": 1920, "h": 1000}])
    cat = Cat(2600, 1000, rng=random.Random(1))
    cat.body.platform = d.floor_under(2600)
    d.set_cursor(3000, 900)
    cat.brain._chase_step(cat.body, d)
    assert cat.body.target_x is not None
    assert 1920 < cat.body.target_x < 3840
