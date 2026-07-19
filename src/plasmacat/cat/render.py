"""Qt-facing sprite rendering: turns text-matrix frames into cached QPixmaps.

A SpriteBank is keyed by (palette, pattern, scale, facing) — exactly what the
customization wizard changes, so re-skinning the cat = new bank params.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from plasmacat.cat import sprites
from plasmacat.props import prop_to_pixels


def prop_pixmap(name: str, scale: int = 3) -> QPixmap:
    """QPixmap for a non-cat prop (bowl, bubble icon, toy), nearest-neighbor scaled."""
    w, h, px = prop_to_pixels(name)
    raw = bytes(c for rgba in px for c in rgba)
    img = QImage(raw, w, h, w * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(img.copy()).scaled(
        w * scale, h * scale,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )


class SpriteBank:
    def __init__(self, palette: dict[str, tuple[int, int, int]] | None = None,
                 pattern: str = "solid", scale: int = 4, facing: str = "right",
                 accessory: bool = False) -> None:
        self.palette = dict(palette or sprites.DEFAULT_PALETTE)
        self.pattern = pattern
        self.scale = scale
        self.facing = facing
        self.accessory = accessory
        self._cache: dict[tuple[str, int], QPixmap] = {}
        self._acc_cache: dict[tuple[str, int], QPixmap] = {}

    def _pixmap(self, mat: list[str]) -> QPixmap:
        w, h, px = sprites.sprite_to_pixels(mat, self.palette)
        raw = bytes(c for rgba in px for c in rgba)
        img = QImage(raw, w, h, w * 4, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(img.copy()).scaled(
            w * self.scale, h * self.scale,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,  # nearest neighbor: crisp pixels
        )

    def frame(self, state: str, index: int) -> QPixmap:
        key = (state, index)
        pm = self._cache.get(key)
        if pm is None:
            mat = sprites.SPRITES[state][index % self.frame_count(state)]
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
            layers = sprites.ACCESSORIES[state]
            mat = layers[index % len(layers)]
            if self.facing == "left":
                mat = sprites.flip(mat)
            self._acc_cache[key] = self._pixmap(mat)
        return self._acc_cache[key]

    def frame_count(self, state: str) -> int:
        return len(sprites.SPRITES[state])
