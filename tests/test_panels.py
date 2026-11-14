"""Floor refinement with Plasma's real panel settings (floating? thickness?)."""
from plasmacat.bridge.panels import refine_floor

AREA = {"x": 0, "y": 0, "w": 1745, "raw_bottom": 1091}


def test_floating_strutless_panel_floor_on_visible_top():
    area = dict(AREA, h=1039, panels=[{"y": 1031, "h": 60, "reserved": 0}])
    plasma = [{"loc": "bottom", "floating": True, "height": 44}]
    assert refine_floor(area, plasma) == 1039


def test_docked_strutless_panel_floor_on_its_frame_top():
    # 'dodge windows' without floating: no strut, no float gap
    area = dict(AREA, h=1055, panels=[{"y": 1047, "h": 44, "reserved": 0}])
    plasma = [{"loc": "bottom", "floating": False, "height": 44}]
    assert refine_floor(area, plasma) == 1047


def test_unknown_panels_keep_the_bridge_value():
    area = dict(AREA, h=1055, panels=[{"y": 1047, "h": 44, "reserved": 0}])
    assert refine_floor(area, None) == 1055
    assert refine_floor(area, [{"loc": "top", "floating": False, "height": 30}]) == 1055


def test_never_below_the_raw_bottom():
    area = dict(AREA, h=1091, panels=[])
    assert refine_floor(area, [{"loc": "bottom", "floating": True, "height": 44}]) == 1091


# -- stable floor for hiding panels ---------------------------------------------

def test_dodging_panel_keeps_the_floor_while_hidden():
    area = dict(AREA, h=1091, panels=[{"y": 1047, "h": 44, "reserved": 0, "hidden": True}])
    plasma = [{"loc": "bottom", "floating": False, "height": 44, "hiding": "dodgewindows"}]
    assert refine_floor(area, plasma) == 1047


def test_autohide_panel_never_lifts_the_floor():
    for hidden in (True, False):
        area = dict(AREA, h=1091 if hidden else 1047,
                    panels=[{"y": 1047, "h": 44, "reserved": 0, "hidden": hidden}])
        plasma = [{"loc": "bottom", "floating": False, "height": 44, "hiding": "autohide"}]
        assert refine_floor(area, plasma) == 1091


def test_hidden_panel_without_plasma_info_is_ignored():
    area = dict(AREA, h=1091, panels=[{"y": 1047, "h": 44, "reserved": 0, "hidden": True}])
    assert refine_floor(area, None) == 1091


# -- Krema dock (layer-shell dock, not a Plasma panel) ---------------------------
# Measured 2026-11-14 on z13g2 (1745x1091 logical): Krema's surface is y=977 h=114
# (bar + zoom headroom), plus a 1 px probe surface at the screen edge. The visible
# bar top is surface bottom - (IconSize + 2*8 + FloatingMargin) = 1091 - 68 = 1023.

from plasmacat.bridge.panels import krema_bar_height, read_kremarc  # noqa: E402

KREMA = {"icon_size": 44, "floating": True, "floating_margin": 8}


def test_krema_bar_height_follows_krema_formula():
    assert krema_bar_height(KREMA) == 44 + 16 + 8
    assert krema_bar_height(dict(KREMA, floating=False)) == 60


def test_krema_dock_floor_on_its_visible_bar():
    area = dict(AREA, h=953, y=32, panels=[
        {"y": 1090, "h": 1, "reserved": 0, "hidden": False, "cls": "krema"},
        {"y": 977, "h": 114, "reserved": 0, "hidden": False, "cls": "krema"}])
    assert refine_floor(area, [], KREMA) == 1023


def test_krema_matched_by_desktop_file_name_too():
    area = dict(AREA, h=985, panels=[{"y": 977, "h": 114, "reserved": 0, "cls": "com.bhyoo.krema"}])
    assert refine_floor(area, None, KREMA) == 1023


def test_krema_dodging_keeps_the_floor():
    # dodge slides the bar off-screen inside the surface; the surface stays
    area = dict(AREA, h=1091, panels=[{"y": 977, "h": 114, "reserved": 0, "hidden": True, "cls": "krema"}])
    assert refine_floor(area, [], KREMA) == 1023


def test_one_pixel_edge_surfaces_never_carry_the_floor():
    area = dict(AREA, h=1090, panels=[{"y": 1090, "h": 1, "reserved": 0, "hidden": False}])
    assert refine_floor(area, []) == 1091


def test_read_kremarc_defaults_and_values(tmp_path):
    assert read_kremarc(tmp_path / "missing") == {"icon_size": 48, "floating": True,
                                                  "floating_margin": 8}
    rc = tmp_path / "kremarc"
    rc.write_text("[General]\nIconSize=44\nFloating=false\nFloatingMargin=12\n")
    assert read_kremarc(rc) == {"icon_size": 44, "floating": False, "floating_margin": 12}


# -- docking the bottom panel while PlasmaCat runs --------------------------------

from plasmacat.bridge.panels import PanelDock  # noqa: E402


class FakePlasma:
    def __init__(self, panels):
        self.panels = panels
        self.scripts = []

    def query(self):
        return [dict(p) for p in self.panels]

    def set_floating(self, ids, floating):
        self.scripts.append((sorted(ids), floating))
        for p in self.panels:
            if p["id"] in ids:
                p["floating"] = floating


def test_dock_then_restore_only_what_we_changed(tmp_path):
    plasma = FakePlasma([{"id": 2, "loc": "bottom", "floating": True},
                         {"id": 5, "loc": "bottom", "floating": False},   # the user's choice
                         {"id": 82, "loc": "top", "floating": True}])
    dock = PanelDock(tmp_path / "panels.json", plasma.query, plasma.set_floating)
    assert dock.dock() == [2]
    assert [p["floating"] for p in plasma.panels] == [False, False, True]
    assert dock.restore() == [2]
    assert [p["floating"] for p in plasma.panels] == [True, False, True]
    assert not (tmp_path / "panels.json").exists()


def test_a_crash_is_recovered_on_the_next_run(tmp_path):
    plasma = FakePlasma([{"id": 2, "loc": "bottom", "floating": True}])
    PanelDock(tmp_path / "panels.json", plasma.query, plasma.set_floating).dock()
    # ... the app dies without restoring; next start:
    dock = PanelDock(tmp_path / "panels.json", plasma.query, plasma.set_floating)
    assert dock.dock() == [2]                     # still ours to give back
    assert dock.restore() == [2]
    assert plasma.panels[0]["floating"] is True


def test_dock_without_plasma_is_a_noop(tmp_path):
    dock = PanelDock(tmp_path / "panels.json", lambda: None, lambda ids, f: None)
    assert dock.dock() == [] and dock.restore() == []
