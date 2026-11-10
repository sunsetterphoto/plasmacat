"""Overlay/player APIs the Control Center drives (headless, fake bridge)."""
import pytest
from conftest import dispose

from plasmacat.persist import Customization, Settings


@pytest.fixture
def overlay(qapp):
    from plasmacat.bridge.kwin import FakeBridge
    from plasmacat.world.overlay import Overlay
    b = FakeBridge()
    ov = Overlay(b, settings=Settings())
    b.start()
    yield ov
    dispose(*ov.furniture_layers, ov)


def test_furniture_items_lists_each_placed_piece(overlay):
    b = overlay.cat.brain
    b.tree_x, b.bed_x = 500.0, 900.0
    b.shelves[:] = [(300.0, 400.0), (700.0, 500.0)]
    keys = [(k, i) for k, _label, i in overlay.furniture_items()]
    assert ("cat_tree", None) in keys and ("cat_bed", None) in keys
    assert ("wall_shelf", 0) in keys and ("wall_shelf", 1) in keys


def test_remove_single_furniture_item(overlay):
    b = overlay.cat.brain
    b.tree_x, b.bed_x = 500.0, 900.0
    b.shelves[:] = [(300.0, 400.0), (700.0, 500.0)]
    overlay.remove_furniture("cat_tree")
    overlay.remove_furniture("wall_shelf", 0)
    assert b.tree_x is None and b.bed_x == 900.0
    assert b.shelves == [(700.0, 500.0)]
    assert not any(p.caption == "Katzenbaum" for p in overlay.desktop.platforms)


def test_remove_cat_keeps_at_least_one(overlay):
    kitten = overlay.add_cat(Customization(name="Luna"), age=0.0)
    assert len(overlay.cats) == 2
    assert overlay.remove_cat(kitten) is True
    assert overlay.cats == [overlay.cat]
    assert overlay.remove_cat(overlay.cat) is False


def test_notifications_respect_settings(overlay):
    got = []
    overlay.notify = lambda title, msg: got.append(title)
    overlay.settings.notify["games"] = False
    overlay.start_mouse_hunt()
    assert got == []
    overlay._hunt = None
    overlay.settings.notify["games"] = True
    overlay.start_mouse_hunt()
    assert got == ["Mouse hunt"]


def test_status_board_rows_follow_settings(overlay):
    overlay.settings.status_board = True
    full = overlay._status_rect().height()
    overlay.settings.status_rows["play"] = False
    overlay.settings.status_rows["litter_box"] = False
    assert overlay._status_rect().height() == full - 2 * 17


def test_sound_groups_mute_their_effects(qapp, monkeypatch):
    from plasmacat.paths import data_file
    from plasmacat.sound.player import SoundPlayer
    p = SoundPlayer(data_file("sounds"))
    played = []
    for name, eff in p._effects.items():
        monkeypatch.setattr(eff, "play", lambda n=name: played.append(n))
    p.set_group_enabled("purr", False)
    p.play("purr")
    p.play("meow")
    assert played == ["meow"]


def test_move_shelf_replaces_it_instead_of_adding(overlay):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent
    b = overlay.cat.brain
    b.shelves[:] = [(300.0, 400.0), (700.0, 500.0)]
    overlay.begin_move("wall_shelf", 0)
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(1000, 450), QPointF(1000, 450),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    overlay.mousePressEvent(ev)
    assert len(b.shelves) == 2 and b.shelves[1] == (700.0, 500.0)
    assert b.shelves[0][0] == 1000.0


def test_hidden_reasons_hide_and_restore_all_layers(overlay):
    overlay.show()
    for layer in overlay.furniture_layers:
        layer.show()
    overlay.set_hidden("pause", True)
    overlay.set_hidden("fullscreen", True)
    assert not overlay.isVisible()
    assert not any(l.isVisible() for l in overlay.furniture_layers)
    overlay.set_hidden("pause", False)
    assert not overlay.isVisible()           # still fullscreen
    overlay.set_hidden("fullscreen", False)
    assert overlay.isVisible() and all(l.isVisible() for l in overlay.furniture_layers)


def test_props_and_cat_share_one_scale(overlay):
    from plasmacat.cat import sprites
    from plasmacat.cat.render import PROP_DETAIL, logical_size
    from plasmacat.world.props import PROPS
    w, h = logical_size(overlay._props["cat_tree"])
    # props are authored on the fine grid: PROP_DETAIL cells per prop pixel
    assert h == pytest.approx(len(PROPS["cat_tree"]) / PROP_DETAIL * overlay.prop_scale, abs=1)
    cw, _ = logical_size(overlay._banks_for(overlay.cat)[0].frame("sit", 0))
    # one prop pixel = 1.5 old cat pixels, exactly as the art was designed
    assert overlay.prop_scale / (cw / sprites.CANVAS_W) == pytest.approx(1.5)
    assert overlay.prop_device_px == overlay.device_px


def test_cat_tree_surfaces_lie_on_the_drawn_boards(overlay):
    b = overlay.cat.brain
    b.tree_x = 800.0
    overlay._sync_furniture_platforms()
    top = min(p.y for p in overlay.desktop.platforms if p.caption == "Katzenbaum")
    floor = overlay.desktop.floor_y_at(800.0)
    from plasmacat.cat.render import logical_size
    _w, h = logical_size(overlay._props["cat_tree"])
    assert floor - h <= top <= floor           # inside the drawn tree
