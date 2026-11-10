"""Control Center + appearance editor (headless)."""
import pytest

from plasmacat.persist import Customization, Settings


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
    saves = []
    c = AppController(overlay=ov, player=SoundPlayer(data_file("sounds")), bridge=b,
                      settings=settings, save=lambda: saves.append(1))
    yield c
    for layer in ov.furniture_layers:
        layer.close()
    ov.close()


@pytest.fixture
def cc(ctl):
    from plasmacat.ui.control_center import ControlCenter
    w = ControlCenter(ctl)
    yield w
    w.close()


def test_cancel_customize_keeps_original(qapp):
    from plasmacat.ui.appearance_editor import AppearanceEditor
    original = Customization(name="Minka", eye=(240, 200, 80))
    ed = AppearanceEditor(original)
    ed.name_edit.setText("Changed")
    ed._set_fur((1, 2, 3))
    assert original.name == "Minka" and original.fur != (1, 2, 3)
    assert ed.result().name == "Changed"


def test_editor_keeps_the_current_eye_color(qapp):
    from plasmacat.ui.appearance_editor import AppearanceEditor
    ed = AppearanceEditor(Customization(eye=(240, 200, 80), collar=(80, 120, 220)))
    res = ed.result()
    assert res.eye == (240, 200, 80) and res.collar == (80, 120, 220)


def test_preview_not_cropped(qapp):
    from plasmacat.cat.render import logical_size
    from plasmacat.ui.appearance_editor import AppearanceEditor
    ed = AppearanceEditor(Customization())
    w, h = logical_size(ed.preview.pixmap())
    assert w <= ed.preview.width() and h <= ed.preview.height()


def test_reset_sound_tab_restores_defaults(cc, ctl):
    tab = cc.tabs["sound"]
    tab.volume.setValue(20)
    assert ctl.settings.volume == pytest.approx(0.2)
    tab.groups["purr"].setChecked(False)
    assert ctl.settings.sound_groups["purr"] is False
    tab.reset_button.click()
    assert ctl.settings.volume == pytest.approx(0.7)
    assert tab.volume.value() == 70 and tab.groups["purr"].isChecked()


def test_status_rows_toggle_persists(cc, ctl):
    home = cc.tabs["home"]
    home.status_rows["play"].setChecked(False)
    assert ctl.settings.status_rows["play"] is False


def test_remove_single_furniture_item(cc, ctl):
    b = ctl.overlay.cat.brain
    b.tree_x, b.bed_x = 500.0, 900.0
    home = cc.tabs["home"]
    home.refresh()
    home.remove_buttons[("cat_tree", None)].click()
    assert b.tree_x is None and b.bed_x == 900.0


def test_cats_tab_shows_each_cat(cc, ctl):
    ctl.overlay.add_cat(Customization(name="Luna"), age=0.0)
    cats = cc.tabs["cats"]
    cats.refresh()
    assert [card.cat.cust.name for card in cats.cards] == ["Minka", "Luna"]


def test_system_tab_pixel_size_applies(cc, ctl):
    sysw = cc.tabs["system"]
    sysw.pixel_size.setCurrentIndex(sysw.pixel_size.findData("chunky"))
    assert ctl.settings.pixel_size == "chunky"
    assert ctl.overlay.pixel_size == "chunky"
