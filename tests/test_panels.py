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
