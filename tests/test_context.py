"""Right-click targets and their menus (headless, fake bridge)."""
import pytest
from conftest import dispose

from plasmacat.persist import Settings


@pytest.fixture
def ctl(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    from plasmacat.bridge.kwin import FakeBridge
    from plasmacat.controller import AppController
    from plasmacat.paths import data_file
    from plasmacat.sound.player import SoundPlayer
    from plasmacat.world.overlay import Overlay
    settings = Settings()
    b = FakeBridge()
    ov = Overlay(b, settings=settings)
    b.start()
    c = AppController(overlay=ov, player=SoundPlayer(data_file("sounds")), bridge=b,
                      settings=settings, save=lambda: None)
    yield c
    dispose(*ov.furniture_layers, ov)


def labels(entries):
    return [e[0] for e in entries if e is not None]


def test_thing_at_finds_cat_prop_toy_and_mess(ctl):
    ov = ctl.overlay
    r = ov._cat_rect(ov.cat)
    assert ov.thing_at(r.center().x(), r.center().y()) == ("cat", ov.cat)
    b = ov.cat.brain
    b.tree_x = 1500.0
    tr = ov._prop_rect("cat_tree", None)
    assert ov.thing_at(tr.center().x(), tr.center().y()) == ("prop", "cat_tree", None)
    toy = ov.toys.spawn("ball", 1100.0, ov.desktop.floor_y_at(1100.0))
    kind, found = ov.thing_at(toy.x, toy.y - 4)
    assert (kind, found) == ("toy", toy)
    b.puke_spots.append(1300.0)
    assert ov.thing_at(1300.0, ov.desktop.floor_y_at(1300.0) - 3)[0] == "puke"
    assert ov.thing_at(5.0, 5.0) is None


def test_interactive_region_covers_cats_and_props_only(ctl):
    ov = ctl.overlay
    front = ov.interactive_rects("front")
    back = ov.interactive_rects("back")
    assert any(r.contains(ov._cat_rect(ov.cat).center()) for r in front + back)
    bowl = ov._prop_rect("food_bowl", None)
    assert any(r.contains(bowl.center()) for r in back)
    from PySide6.QtCore import QPoint
    assert not any(r.contains(QPoint(900, 200)) for r in front + back)


def test_cat_menu_has_the_main_actions(ctl):
    from plasmacat.ui.context_menus import entries_for
    names = labels(entries_for(ctl, ("cat", ctl.overlay.cat)))
    for wanted in ("Give treat", "Pet", "Appearance…", "Control Center…"):
        assert wanted in names, names


def test_food_bowl_menu_fits_the_bowl(ctl):
    from plasmacat.ui.context_menus import entries_for
    b = ctl.overlay.cat.brain
    b.food_fill = 10.0
    entries = entries_for(ctl, ("prop", "food_bowl", None))
    names = labels(entries)
    assert "Refill" in names and "Move" in names and "Remove" not in names
    assert any(n.startswith("Food:") for n in names)
    dict((e[0], e[1]) for e in entries if e)["Refill"]()
    assert b.food_fill == 100.0


def test_litter_box_and_furniture_menus(ctl):
    from plasmacat.ui.context_menus import entries_for
    b = ctl.overlay.cat.brain
    b.litter_x, b.bed_x = 1200.0, 900.0
    b.litter_deposits.append("poop")
    names = labels(entries_for(ctl, ("prop", "litter_0", None)))
    assert any(n.startswith("Clean") for n in names) and "Remove" in names
    entries = entries_for(ctl, ("prop", "cat_bed", None))
    dict((e[0], e[1]) for e in entries if e)["Remove"]()
    assert b.bed_x is None


def test_toy_and_mess_menus(ctl):
    from plasmacat.ui.context_menus import entries_for
    ov = ctl.overlay
    toy = ov.toys.spawn("plush", 800.0, 1000.0)
    entries = entries_for(ctl, ("toy", toy))
    assert "Put away" in labels(entries)
    dict((e[0], e[1]) for e in entries if e)["Put away"]()
    assert toy not in ov.toys.toys
    ov.cat.brain.puke_spots.append(500.0)
    entries = entries_for(ctl, ("puke", 0))
    dict((e[0], e[1]) for e in entries if e)["Clean up"]()
    assert ov.cat.brain.puke_spots == []


def test_input_mask_is_only_cleared_while_placing(ctl):
    ov = ctl.overlay
    ov.show()
    ov.update_input_masks(force=True)
    assert not ov.windowHandle().mask().isEmpty()        # only the cat takes clicks
    ov.begin_placement("cat_bed")
    assert ov.windowHandle().mask().isEmpty()            # whole screen takes the click
    ov._end_placement()
    assert not ov.windowHandle().mask().isEmpty()
