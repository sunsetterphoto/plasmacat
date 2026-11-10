"""Qt-facing sprite rendering: turns text-matrix frames into cached QPixmaps.

Pixel-exact on fractional scaling: every art pixel is an INTEGER number of
device pixels, and the pixmap carries the window's device pixel ratio, so the
compositor never resamples it (at 1.65 a 2-logical-px art pixel would be 3.3
device px — uneven 3/4 px columns). Code that needs the on-screen size uses
logical_size(pm); QPixmap.width() is in device pixels.

A SpriteBank is keyed by (palette, pattern, size, facing) — exactly what the
customization changes, so re-skinning the cat = new bank params.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from plasmacat.cat import sprites
from plasmacat.world.props import prop_to_pixels


# logical px per art pixel for each pixel-size preference (at canvas detail 1)
PIXEL_SIZES = {"fine": 1.5, "normal": 2.0, "chunky": 2.5}


def art_pixel_device(dpr: float, preference: str = "normal",
                     factor: float = 1.0) -> int:
    """Device pixels per art pixel: the preference's logical size times the
    device pixel ratio, rounded to a whole number (never below 1)."""
    logical = PIXEL_SIZES.get(preference, PIXEL_SIZES["normal"]) * factor
    return max(1, round(logical * dpr))


def logical_size(pm: QPixmap) -> tuple[int, int]:
    """On-screen (logical) size of a pixmap that carries a device pixel ratio."""
    r = pm.devicePixelRatio() or 1.0
    return round(pm.width() / r), round(pm.height() / r)


def lw(pm: QPixmap) -> int:
    """Logical width of a pixmap (see logical_size)."""
    return logical_size(pm)[0]


def lh(pm: QPixmap) -> int:
    """Logical height of a pixmap (see logical_size)."""
    return logical_size(pm)[1]


def _scaled(img: QImage, w: int, h: int, device_px: int, dpr: float) -> QPixmap:
    pm = QPixmap.fromImage(img.copy()).scaled(
        w * device_px, h * device_px,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,  # nearest neighbor: crisp pixels
    )
    pm.setDevicePixelRatio(dpr)
    return pm


def prop_pixmap(name: str, device_px: int = 3, dpr: float = 1.0) -> QPixmap:
    """QPixmap for a non-cat prop (bowl, bubble icon, toy), pixel-exact."""
    w, h, px = prop_to_pixels(name)
    raw = bytes(c for rgba in px for c in rgba)
    img = QImage(raw, w, h, w * 4, QImage.Format.Format_RGBA8888)
    return _scaled(img, w, h, device_px, dpr)


class SpriteBank:
    def __init__(self, palette: dict[str, tuple[int, int, int]] | None = None,
                 pattern: str = "solid", device_px: int = 2, dpr: float = 1.0,
                 facing: str = "right", accessory: bool = False,
                 stage: int = 6) -> None:
        # seniors grey out (P47): the palette ages with the growth stage
        self.palette = sprites.aged_palette(dict(palette or sprites.DEFAULT_PALETTE),
                                            stage)
        self.pattern = pattern
        self.device_px = device_px
        self.dpr = dpr
        self.facing = facing
        self.accessory = accessory
        self.stage = stage
        self._cache: dict[tuple[str, int], QPixmap] = {}
        self._acc_cache: dict[tuple[str, int], QPixmap] = {}

    def _pixmap(self, mat: list[str]) -> QPixmap:
        w, h, px = sprites.sprite_to_pixels(mat, self.palette)
        raw = bytes(c for rgba in px for c in rgba)
        img = QImage(raw, w, h, w * 4, QImage.Format.Format_RGBA8888)
        return _scaled(img, w, h, self.device_px, self.dpr)

    def frame(self, state: str, index: int) -> QPixmap:
        key = (state, index)
        pm = self._cache.get(key)
        if pm is None:
            mat = sprites.sprites_for(self.stage)[state][index % self.frame_count(state)]
            mat = sprites.apply_pattern(mat, self.pattern)
            if self.facing == "left":
                mat = sprites.flip(mat)
            pm = self._pixmap(mat)
            self._cache[key] = pm
        return pm

    def accessory_frame(self, state: str, index: int) -> QPixmap | None:
        """The collar overlay for a frame, or None when accessories are off
        or the pose has none."""
        if not self.accessory:
            return None
        key = (state, index)
        if key not in self._acc_cache:
            layers = sprites.accessories_for(self.stage)[state]
            mat = layers[index % len(layers)]
            if self.facing == "left":
                mat = sprites.flip(mat)
            self._acc_cache[key] = self._pixmap(mat)
        return self._acc_cache[key]

    def frame_count(self, state: str) -> int:
        return len(sprites.sprites_for(self.stage)[state])
