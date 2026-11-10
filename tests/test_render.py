import pytest

from plasmacat.cat import sprites
from plasmacat.cat.render import SpriteBank, art_pixel_device, logical_size, prop_pixmap

DPRS = [1.0, 1.25, 1.5, 1.65, 2.0]


@pytest.mark.parametrize("dpr", DPRS)
def test_art_pixel_is_integer_device_pixels(qapp, dpr):
    n = art_pixel_device(dpr, "normal")
    assert isinstance(n, int) and n >= 1
    pm = SpriteBank(device_px=n, dpr=dpr).frame("sit", 0)
    assert pm.width() == sprites.GRID_W * n          # device pixels
    assert pm.height() == sprites.GRID_H * n
    assert pm.devicePixelRatio() == pytest.approx(dpr)


@pytest.mark.parametrize("dpr", DPRS)
def test_logical_size_matches_dpr(qapp, dpr):
    n = art_pixel_device(dpr, "normal")
    pm = SpriteBank(device_px=n, dpr=dpr).frame("sit", 0)
    w, h = logical_size(pm)
    assert w == round(sprites.GRID_W * n / dpr)
    assert h == round(sprites.GRID_H * n / dpr)


def test_pixel_size_preferences_at_165():
    sizes = [art_pixel_device(1.65, p) for p in ("fine", "normal", "chunky")]
    assert sizes == sorted(sizes) and len(set(sizes)) == 3


def test_unknown_preference_falls_back_to_normal():
    assert art_pixel_device(1.65, "bogus") == art_pixel_device(1.65, "normal")


def test_prop_pixmap_device_exact(qapp):
    pm = prop_pixmap("food_bowl", device_px=5, dpr=1.65)
    assert pm.devicePixelRatio() == pytest.approx(1.65)
    assert pm.width() % 5 == 0
