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


# logical px per sprite GRID cell for each pixel-size preference (the cat's
# grid is sprites.DETAIL times finer than its 64x48 pose space; props are
# drawn at PROP_DETAIL cells per prop pixel with the same cell size)
PIXEL_SIZES = {"fine": 0.6, "normal": 1.0, "chunky": 1.9}
PROP_DETAIL = 3   # 1 prop pixel = 1.5 old cat pixels = 3 grid cells


def _mix(a: tuple, b: tuple, t: float) -> tuple[int, int, int]:
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a[:3], b[:3]))  # type: ignore[return-value]


def shade_rgba(w: int, h: int, px: list, outline: tuple[int, int, int]) -> list:
    """Light from above: a rim light under the top silhouette edge, ambient
    occlusion along the bottom edge, and a soft (selective) outline on the
    lit top side. Works on any RGBA sprite whose outline color is known."""
    def opaque(x: int, y: int) -> bool:
        return 0 <= x < w and 0 <= y < h and px[y * w + x][3] > 0

    def is_outline(i: int) -> bool:
        return px[i][3] > 0 and px[i][:3] == outline

    # exterior outline = outline cells that touch transparency
    ext = [False] * (w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if is_outline(i) and any(not opaque(x + dx, y + dy)
                                     for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                ext[i] = True

    def edge(x: int, y: int) -> bool:   # transparent or exterior outline
        return not opaque(x, y) or ext[y * w + x]

    out = list(px)
    white, black = (255, 255, 255), (0, 0, 0)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            p = px[i]
            if p[3] == 0:
                continue
            if ext[i]:
                # soft outline where the light hits (top side, fill below)
                if not opaque(x, y - 1) and opaque(x, y + 1) and not is_outline(i + w):
                    out[i] = (*_mix(outline, px[i + w], 0.45), 255)
                continue
            if is_outline(i):
                continue  # inner lines (pupils, mouth) stay crisp
            if edge(x, y - 1):
                out[i] = (*_mix(p, white, 0.24), 255)
            elif y >= 2 and edge(x, y - 2):
                out[i] = (*_mix(p, white, 0.10), 255)
            elif edge(x, y + 1):
                out[i] = (*_mix(p, black, 0.18), 255)
    return out


def sprite_rgba(frame: list[str], palette: dict) -> tuple[int, int, list]:
    """A cat frame as shaded RGBA (w, h, flat list)."""
    pal = sprites.complete_palette(palette)
    w, h, px = sprites.sprite_to_pixels(frame, pal)
    return w, h, shade_rgba(w, h, px, pal["o"])


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


def prop_rgba(name: str) -> tuple[int, int, list]:
    """A prop as shaded RGBA. Props are authored on the fine grid already
    (PROP_DETAIL cells per prop pixel, one-cell outline)."""
    from plasmacat.world.props import PROP_PALETTE, PROPS
    rows = PROPS[name]
    w, h = len(rows[0]), len(rows)
    px = [(0, 0, 0, 0) if ch == "." else (*PROP_PALETTE[ch], 255)
          for r in rows for ch in r]
    return w, h, shade_rgba(w, h, px, PROP_PALETTE["o"])


def prop_pixmap(name: str, device_px: int = 1, dpr: float = 1.0) -> QPixmap:
    """QPixmap for a non-cat prop (bowl, bubble icon, toy), pixel-exact.
    device_px is the size of one grid cell (the same as the cat's)."""
    w, h, px = prop_rgba(name)
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
        w, h, px = sprite_rgba(mat, self.palette)
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
