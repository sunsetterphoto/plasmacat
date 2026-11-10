"""Control Center + appearance editor (headless)."""
import pytest
from conftest import dispose

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
    dispose(*ov.furniture_layers, ov)


@pytest.fixture
def cc(ctl):
    from plasmacat.ui.control_center import ControlCenter
    w = ControlCenter(ctl)
    yield w
    dispose(w)


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


def test_home_tab_arrange_button_starts_arrange_mode(cc, ctl):
    cc.tabs["home"].arrange_button.click()
    assert ctl.overlay._arranging
    ctl.overlay._end_placement()


def test_available_release_is_offered_once(ctl, tmp_path):
    import json
    import time
    got = []
    ctl.overlay.notify = lambda title, msg: got.append(msg)
    ctl.watch_updates(tmp_path)
    (tmp_path / ".available").write_text(json.dumps({"version": "v9.9.9", "at": time.time()}))
    ctl._check_update_marker()
    assert got and "v9.9.9" in got[0] and "click" in got[0]
    assert ctl.pending_update == "v9.9.9"
    ctl._check_update_marker()          # only once per release
    assert len(got) == 1


def test_apply_update_runs_the_updater_then_restarts(ctl, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ctl, "_run_updater", lambda args, done: (calls.append(args), done("updated to v9.9.9")))
    monkeypatch.setattr(ctl, "restart", lambda: calls.append("restart"))
    ctl.pending_update = "v9.9.9"
    ctl.apply_update()
    assert calls == [["--apply"], "restart"]


def test_only_the_update_offer_click_installs(ctl, monkeypatch):
    applied = []
    monkeypatch.setattr(ctl, "apply_update", lambda *a: applied.append(1))
    ctl.pending_update = "v9.9.9"
    ctl.overlay.notify = lambda title, msg: None
    ctl.overlay._notify("litter", "PlasmaCat", "litter box full")
    ctl.notification_clicked()
    assert applied == []
    ctl.overlay._notify("update", "PlasmaCat update", "v9.9.9 is available")
    ctl.notification_clicked()
    assert applied == [1]


def test_hidden_cats_are_silent(ctl, monkeypatch):
    played = []
    monkeypatch.setattr(ctl.player, "play", lambda name, cooldown=0.4: played.append(name))
    ov = ctl.overlay
    ov.set_hidden("fullscreen", True)
    ov.cat.brain.sounds.append("meow")
    ov._clock.restart()
    import time
    time.sleep(0.01)
    ov._tick()
    assert played == []
    assert ov.cat.brain.sounds == []          # dropped, not queued for later


class FakeDock:
    def __init__(self):
        self.calls = []

    def dock(self):
        self.calls.append("dock")
        return [2]

    def restore(self):
        self.calls.append("restore")
        return [2]


def test_panel_is_docked_while_running_and_restored(ctl):
    assert ctl.settings.dock_panel is True          # default: docked while she's active
    ctl.panel_dock = FakeDock()
    ctl.apply_settings()
    assert ctl.panel_dock.calls == ["dock"]
    ctl.update_settings(dock_panel=False)
    assert ctl.panel_dock.calls[-1] == "restore"
    ctl.update_settings(dock_panel=True)
    ctl.shutdown()
    assert ctl.panel_dock.calls[-1] == "restore"


def test_system_tab_has_the_dock_switch(cc, ctl):
    ctl.panel_dock = FakeDock()
    box = cc.tabs["system"].dock_panel
    box.setChecked(False)
    assert ctl.settings.dock_panel is False
