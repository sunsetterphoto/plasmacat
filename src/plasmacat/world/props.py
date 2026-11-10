"""Non-cat pixel art: bowls, thought-bubble icons, toys, furniture.

Props are drawn in "prop pixel" coordinates (1 prop pixel = 1.5 cat pose
pixels, the scale the furniture was designed at) but rasterized K = 3 times
finer — on the same grid cell size as the cat — so round shapes are smooth
and the auto-outline is one cell thin. Small icons are hand-authored
matrices, upscaled. Palette:
  '.' transparent  'o' outline
  reds   r R h p     browns/wood  k K W V     cardboard  B b
  water  u U         metal/grey   g m M f F   cream      c C   white w
  green  G l         teal carpet  t T         yellow     y Y   sand  s
"""

from __future__ import annotations

import math

K = 3   # grid cells per prop pixel

PROP_PALETTE: dict[str, tuple[int, int, int]] = {
    "o": (40, 30, 30),
    "r": (200, 70, 70), "R": (158, 48, 54), "h": (230, 80, 100), "p": (238, 160, 168),
    "k": (120, 80, 40), "K": (84, 54, 30), "W": (186, 142, 94), "V": (146, 104, 64),
    "B": (198, 160, 112), "b": (166, 128, 86),
    "u": (90, 160, 230), "U": (58, 118, 196),
    "w": (255, 255, 255), "c": (242, 234, 216), "C": (214, 202, 180),
    "z": (150, 170, 220),
    "f": (190, 200, 210), "F": (130, 145, 160),
    "g": (120, 120, 130), "m": (204, 208, 218), "M": (150, 156, 172),
    "y": (240, 210, 90), "Y": (204, 164, 60),
    "G": (100, 190, 90), "l": (150, 220, 120),
    "t": (88, 164, 172), "T": (58, 122, 134),
    "s": (210, 185, 140),
}


class _C:
    """Prop canvas. Coordinates are prop pixels; the grid is K times finer.
    rect/set/outline_box take whole prop pixels (inclusive, the classic
    blocky API); box/ellipse/round_box/trapezoid/line take continuous
    coordinates and rasterize at grid resolution. rows() adds a one-cell
    outline around everything (and one cell of padding to hold it)."""

    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.gw, self.gh = w * K + 2, h * K + 2
        self.g = [["."] * self.gw for _ in range(self.gh)]

    def _fill(self, x0: float, y0: float, x1: float, y1: float, inside, ch: str) -> None:
        gx0 = max(0, int(math.floor(x0 * K)) + 1)
        gx1 = min(self.gw - 1, int(math.ceil(x1 * K)) + 1)
        gy0 = max(0, int(math.floor(y0 * K)) + 1)
        gy1 = min(self.gh - 1, int(math.ceil(y1 * K)) + 1)
        for gy in range(gy0, gy1 + 1):
            py = (gy - 1 + 0.5) / K
            row = self.g[gy]
            for gx in range(gx0, gx1 + 1):
                if inside((gx - 1 + 0.5) / K, py):
                    row[gx] = ch

    # -- blocky API (whole prop pixels, inclusive) ---------------------------------
    def rect(self, x0: int, y0: int, x1: int, y1: int, ch: str) -> None:
        self.box(x0, y0, x1 + 1, y1 + 1, ch)

    def set(self, x: int, y: int, ch: str) -> None:
        self.box(x, y, x + 1, y + 1, ch)

    def outline_box(self, x0: int, y0: int, x1: int, y1: int, fill: str) -> None:
        self.box(x0, y0, x1 + 1, y1 + 1, fill)

    # -- fine API (continuous prop-pixel coordinates) ------------------------------
    def box(self, x0: float, y0: float, x1: float, y1: float, ch: str) -> None:
        self._fill(x0, y0, x1, y1, lambda x, y: x0 <= x < x1 and y0 <= y < y1, ch)

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, ch: str) -> None:
        self._fill(cx - rx, cy - ry, cx + rx, cy + ry,
                   lambda x, y: ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0, ch)

    def round_box(self, x0: float, y0: float, x1: float, y1: float, r: float, ch: str) -> None:
        def inside(x: float, y: float) -> bool:
            if not (x0 <= x < x1 and y0 <= y < y1):
                return False
            dx = max(x0 + r - x, 0.0, x - (x1 - r))
            dy = max(y0 + r - y, 0.0, y - (y1 - r))
            return dx * dx + dy * dy <= r * r
        self._fill(x0, y0, x1, y1, inside, ch)

    def trapezoid(self, xt0: float, xt1: float, y0: float,
                  xb0: float, xb1: float, y1: float, ch: str) -> None:
        def inside(x: float, y: float) -> bool:
            if not y0 <= y < y1:
                return False
            t = (y - y0) / (y1 - y0)
            return xt0 + (xb0 - xt0) * t <= x < xt1 + (xb1 - xt1) * t
        self._fill(min(xt0, xb0), y0, max(xt1, xb1), y1, inside, ch)

    def line(self, x0: float, y0: float, x1: float, y1: float, width: float, ch: str) -> None:
        dx, dy = x1 - x0, y1 - y0
        ll = dx * dx + dy * dy or 1e-9
        r = width / 2

        def inside(x: float, y: float) -> bool:
            t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / ll))
            ex, ey = x - (x0 + dx * t), y - (y0 + dy * t)
            return ex * ex + ey * ey <= r * r
        self._fill(min(x0, x1) - r, min(y0, y1) - r, max(x0, x1) + r, max(y0, y1) + r, inside, ch)

    def ring(self, cx: float, cy: float, r0: float, r1: float, ch: str) -> None:
        self._fill(cx - r1, cy - r1, cx + r1, cy + r1,
                   lambda x, y: r0 <= ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 <= r1, ch)

    def rows(self) -> list[str]:
        g = self.g
        add = [(x, y) for y in range(self.gh) for x in range(self.gw)
               if g[y][x] == "." and any(
                   0 <= x + dx < self.gw and 0 <= y + dy < self.gh and g[y + dy][x + dx] not in ".o"
                   for dy in (-1, 0, 1) for dx in (-1, 0, 1))]
        for x, y in add:
            g[y][x] = "o"
        return ["".join(r) for r in g]


def _from_matrix(rows: list[str]) -> list[str]:
    """A hand-authored icon on the fine grid: upscaled K times, its outer
    outline thinned to one cell, padded like the built props."""
    g = [list(ch * K for ch in r) for r in rows]
    g = [list("".join(r)) for r in g for _ in range(K)]
    h, w = len(g), len(g[0])
    while True:
        drop = [(x, y) for y in range(h) for x in range(w) if g[y][x] == "o"
                and any(not (0 <= x + dx < w and 0 <= y + dy < h) or g[y + dy][x + dx] == "."
                        for dy in (-1, 0, 1) for dx in (-1, 0, 1))
                and not any(0 <= x + dx < w and 0 <= y + dy < h and g[y + dy][x + dx] not in ".o"
                            for dy in (-1, 0, 1) for dx in (-1, 0, 1))]
        if not drop:
            break
        for x, y in drop:
            g[y][x] = "."
    pad = ["." * (w + 2)]
    return pad + ["." + "".join(r) + "." for r in g] + pad


def _rope(c: _C, x0: float, x1: float, y0: float, y1: float) -> None:
    """A sisal-wrapped trunk: sand body with slanted rope turns."""
    c.box(x0, y0, x1, y1, "s")
    y = y0 + 0.4
    while y < y1 - 0.6:
        c.line(x0 + 0.2, y + 1.0, x1 - 0.2, y, 0.55, "k")
        y += 2.0
    c.box(x0, y0, x0 + 0.7, y1, "W")          # lit side


def _carpet(c: _C, x0: float, y0: float, x1: float, y1: float) -> None:
    """A carpeted platform: teal top with a darker underside and tufts."""
    c.round_box(x0, y0, x1, y1, 1.6, "T")
    c.round_box(x0, y0, x1, y0 + (y1 - y0) * 0.55, 1.4, "t")
    x = x0 + 2.0
    while x < x1 - 1.5:
        c.box(x, y0 + 0.5, x + 0.4, y0 + 1.3, "T")
        x += 3.0


# ---------------------------------------------------------------------------
# Hand-authored small items
# ---------------------------------------------------------------------------

def _bowl(c: _C) -> None:
    c.trapezoid(2, 22, 8.2, 4.4, 19.6, 14, "r")          # body, narrower foot
    c.trapezoid(3.4, 20.6, 11.6, 4.4, 19.6, 14, "R")     # shaded lower half
    c.round_box(1.4, 7.6, 22.6, 9.4, 0.9, "h")           # thick glossy rim
    c.line(4.2, 8.4, 8.2, 8.4, 0.5, "w")                 # rim highlight
    c.ellipse(12, 11.6, 2.0, 1.5, "c")                   # little fish badge
    c.trapezoid(13.6, 15.2, 10.6, 13.6, 15.2, 12.6, "c")
    c.ellipse(11.2, 11.3, 0.35, 0.35, "o")


def _food_bowl_full() -> list[str]:
    """Food bowl heaped with kibble (24x14 prop px)."""
    c = _C(24, 14)
    c.ellipse(12, 7.0, 8.2, 4.4, "k")                    # the mound
    c.ellipse(9.2, 5.0, 3.0, 2.0, "k")
    c.ellipse(14.6, 4.6, 3.2, 2.2, "k")
    for x, y, ch in ((7.4, 5.2, "K"), (10.6, 3.6, "W"), (13.2, 5.4, "K"), (15.8, 3.9, "W"),
                     (12.0, 6.6, "W"), (9.0, 6.9, "K"), (16.4, 6.4, "K"), (14.0, 3.0, "K"),
                     (6.2, 6.8, "W"), (17.8, 6.9, "W")):
        c.ellipse(x, y, 0.75, 0.6, ch)                   # single kibbles
    _bowl(c)
    return c.rows()


def _food_bowl_empty() -> list[str]:
    """The same bowl, visibly EMPTY: dark inside, a few crumbs."""
    c = _C(24, 14)
    _bowl(c)
    c.ellipse(12, 8.5, 9.2, 0.75, "K")                   # dark opening
    for x in (8.0, 12.6, 15.4):
        c.ellipse(x, 8.5, 0.4, 0.3, "W")                 # crumbs
    return c.rows()


def _fountain(phase: int) -> list[str]:
    """Perpetual drinking fountain (24x20 prop px): a basin with a little
    dome and a bubbling jet, 3 animation phases."""
    c = _C(24, 20)
    c.round_box(1, 14, 23, 20, 2.2, "M")                 # basin
    c.round_box(1, 14, 23, 16.6, 1.6, "m")               # lit rim
    c.ellipse(12, 15.4, 9.6, 1.2, "u")                   # water
    c.ellipse(12, 15.7, 7.0, 0.7, "U")
    c.line(4.0, 15.1, 7.5, 15.1, 0.45, "w")              # sparkle
    c.box(10.4, 7.5, 13.6, 14.6, "M")                    # column
    c.box(10.4, 7.5, 11.3, 14.6, "m")
    c.ellipse(12, 6.8, 3.3, 2.7, "m")                    # dome
    c.ellipse(11.0, 5.9, 1.0, 0.7, "w")
    jets = (((12.0, 2.6), (11.2, 1.2), (12.9, 3.6)),
            ((12.0, 1.4), (10.6, 3.0), (13.3, 2.4)),
            ((12.4, 2.0), (11.4, 3.6), (10.8, 1.6)))
    for x, y in jets[phase % 3]:                         # bubbling jet
        c.ellipse(x, y, 0.55, 0.65, "u")
    for x, y in ((9.6, 9.0), (14.4, 10.0)):              # trickles down the dome
        c.line(x, y + phase % 2, x, y + 1.6 + phase % 2, 0.5, "u")
    return c.rows()



def _wall_shelf() -> list[str]:
    """Floating cat shelf (48x10 prop px): wooden board with a carpet top
    and two metal brackets. Fixed to the 'wall' at any height."""
    c = _C(48, 10)
    c.trapezoid(6, 9.4, 3.4, 6, 7.0, 9.4, "M")           # brackets
    c.trapezoid(38.6, 42, 3.4, 41, 42, 9.4, "M")
    c.round_box(0, 0.9, 48, 3.8, 0.9, "W")               # board
    c.box(0.6, 2.9, 47.4, 3.8, "V")                      # underside
    for x in (9.0, 21.0, 30.5, 40.0):
        c.line(x, 2.0, x + 3.0, 2.0, 0.3, "V")           # wood grain
    c.round_box(0.4, 0, 47.6, 1.3, 0.6, "t")             # carpet strip
    return c.rows()


def _cat_door(flap: int) -> list[str]:
    """Pet door portal (60x72 px at scale 3): appears for a moment whenever
    the cat switches between the desktop level and the window level (P27).
    flap: 0 = closed, 1 = swinging, 2 = open."""
    c = _C(20, 24)
    # brown frame with a little arch, standing on the ground
    c.outline_box(2, 3, 17, 23, "k")
    c.rect(4, 1, 15, 3, "k")
    c.rect(5, 2, 14, 1, "s")
    c.rect(5, 6, 14, 21, "o")            # dark opening
    if flap == 0:                        # closed: flap covers the opening
        c.rect(6, 7, 13, 21, "s")
        c.rect(7, 8, 12, 9, "k")         # panel inset
        c.set(8, 13, "o")                # handle dot
    elif flap == 1:                      # swinging: flap half-lifted
        c.rect(6, 7, 13, 11, "s")
        c.rect(7, 8, 12, 4, "k")
        c.set(13, 12, "s")
        c.set(14, 13, "s")
    else:                                # open: flap tucked away at the top
        c.rect(6, 7, 13, 9, "s")
        c.rect(7, 8, 12, 3, "k")
    return c.rows()


def _box() -> list[str]:
    """Cardboard box, BACK part (48x28 prop px): open top with a dark
    inside and flaps. The front wall (_box_front) is drawn OVER the cat."""
    c = _C(48, 28)
    c.trapezoid(1.0, 13.0, 1.0, 0.0, 10.0, 5.0, "B")      # left flap, folded out
    c.trapezoid(35.0, 47.0, 1.0, 38.0, 48.0, 5.0, "b")    # right flap
    c.box(0, 4.6, 48, 28, "B")                            # body
    c.box(1.6, 6.0, 46.4, 10.0, "K")                      # dark inside
    c.box(1.6, 6.0, 46.4, 6.9, "b")                       # inner back rim
    return c.rows()


def _box_front() -> list[str]:
    """Front wall of the cardboard box, drawn over the cat."""
    c = _C(48, 28)
    c.box(0, 12, 48, 28, "B")                             # front wall
    c.box(0, 24.5, 48, 28, "b")                           # shaded foot
    c.box(21.4, 12, 26.6, 28, "c")                        # packing tape
    c.ellipse(11.5, 18.5, 3.6, 1.7, "K")                  # carry hole
    c.line(31.0, 16.0, 43.0, 16.0, 0.4, "b")              # print lines
    c.line(31.0, 18.2, 40.0, 18.2, 0.4, "b")
    c.line(33.0, 22.0, 36.5, 20.0, 0.5, "b")              # 'this side up' arrow
    c.line(36.5, 20.0, 40.0, 22.0, 0.5, "b")
    return c.rows()


ICON_FISH = [
    "..........",
    "..ooo.....",
    ".offfooo..",
    "offwfffofo",
    "offffFFfof",
    ".offfooo..",
    "..ooo.....",
    "..........",
]

ICON_DROP = [
    "..........",
    "....oo....",
    "...ouuo...",
    "...ouuo...",
    "..ouuuuo..",
    ".ouwuuuuo.",
    ".ouuuuuuo.",
    "..oooooo..",
]

def _draw_z(c: _C, x: int, y: int, size: int) -> None:
    """One Z glyph: top bar, diagonal, bottom bar."""
    c.rect(x, y, x + size - 1, y, "z")
    for i in range(1, size - 1):
        c.set(x + size - 1 - i, y + i, "z")
    c.rect(x, y + size - 1, x + size - 1, y + size - 1, "z")


def _zzz_icon() -> list[str]:
    """Readable 'Zzz': three Zs ascending in size (classic comic style)."""
    c = _C(17, 14)
    _draw_z(c, 1, 1, 6)
    _draw_z(c, 8, 6, 5)
    _draw_z(c, 13, 11, 3)
    return c.rows()


ICON_HEART = [
    "..........",
    "..oo.oo...",
    ".ohhohhho.",
    "ohhhhhhhho",
    "ohhhhhhhho",
    ".ohhhhhho.",
    "..ohhhho..",
    "...oho....",
]

# P42 mouse-hunt mini-game: a LIVE mouse (facing left, tail trailing right)
MOUSE = [
    "..............",
    "..oo..........",
    ".oggo.........",
    "oggggoooooo...",
    "oggggggggggoo.",
    ".ogggggggggg.o",
    "..oo..oo....o.",
    ".............o",
]

LURE = [
    "......",
    ".yy...",
    "oyyo..",
    ".yyyo.",
    "..oyo.",
    "......",
]

LASER_DOT = [
    "..........",
    "....oo....",
    "..orrrro..",
    ".orrwwrro.",
    ".orwwwwro.",
    ".orrwwrro.",
    "..orrrro..",
    "....oo....",
    "..........",
]

# ---------------------------------------------------------------------------
# Furniture (built): sized to the cat (64x48 sprite @ 2x = 128x96 px)
# ---------------------------------------------------------------------------

def _scratch_post() -> list[str]:
    """Sisal post, ~2x cat height (24x64 prop px): carpeted top platform
    wide enough to lie on, rope-wrapped trunk, a pom-pom on a string."""
    c = _C(24, 64)
    _rope(c, 10.2, 15.8, 4.6, 55.5)
    c.line(18.6, 4.6, 18.6, 11.0, 0.35, "c")              # string
    c.ellipse(18.6, 12.2, 1.6, 1.6, "p")                  # pom-pom
    c.ellipse(18.1, 11.7, 0.5, 0.5, "w")
    _carpet(c, 2, 0, 22, 4.8)
    _carpet(c, 1, 55.2, 23, 64)
    return c.rows()


def _cat_bed() -> list[str]:
    """Wicker basket with a cushion, fits the whole cat (40x16 prop px)."""
    c = _C(40, 16)
    c.round_box(0, 3.6, 40, 16, 4.2, "V")                 # basket back + sides
    c.ellipse(20, 8.2, 16.2, 4.0, "c")                    # cushion
    c.ellipse(20, 8.9, 11.0, 2.2, "C")                    # the dip she lies in
    c.round_box(0, 9.6, 40, 16, 3.6, "W")                 # front wall
    y = 10.8
    while y < 15.6:                                       # woven rows
        c.line(1.4, y, 38.6, y, 0.3, "V")
        y += 1.6
    x = 4.0
    while x < 37.0:
        c.line(x, 10.0, x, 15.6, 0.3, "V")
        x += 3.2
    c.round_box(0, 9.2, 40, 10.6, 0.7, "B")               # rolled rim
    return c.rows()


def _cat_grass() -> list[str]:
    """Cat grass in a terracotta pot (16x20 prop px)."""
    c = _C(16, 20)
    blades = ((3.0, 4.6, -0.8), (4.6, 2.4, 0.3), (6.2, 4.0, -0.4), (7.8, 1.0, 0.2),
              (9.4, 3.2, 0.6), (11.0, 2.0, -0.3), (12.6, 5.0, 0.8), (5.4, 6.0, 0.5),
              (10.2, 6.4, -0.6))
    for i, (x, top, lean) in enumerate(blades):
        c.line(x, 12.6, x + lean, top, 0.75, "G" if i % 3 else "l")
    c.trapezoid(2.2, 13.8, 12.4, 3.6, 12.4, 20, "r")      # pot
    c.trapezoid(3.0, 13.0, 16.5, 3.6, 12.4, 20, "R")
    c.round_box(1.4, 12.0, 14.6, 14.0, 0.8, "h")          # rim
    return c.rows()


def _litter_box(fill: int) -> list[str]:
    """Litter tray (28x14 prop px); fill 0-2 = poop level."""
    c = _C(28, 14)
    c.trapezoid(0, 28, 3.6, 1.6, 26.4, 14, "t")           # tray
    c.trapezoid(0.8, 27.2, 9.0, 1.6, 26.4, 14, "T")
    c.round_box(0, 3.0, 28, 5.0, 0.9, "t")                # rim
    c.line(2.0, 3.7, 7.0, 3.7, 0.4, "w")
    c.ellipse(14, 5.4, 12.0, 1.5, "s")                    # litter
    for tx, ty in ((5.0, 5.2), (9.5, 5.9), (15.5, 5.0), (21.5, 5.8), (12.5, 6.2), (24.0, 5.3)):
        c.ellipse(tx, ty, 0.4, 0.3, "C")                  # grains
    if fill >= 1:
        c.ellipse(7.0, 5.0, 1.4, 0.9, "k")
        c.ellipse(14.0, 5.6, 1.4, 0.9, "k")
    if fill >= 2:
        c.ellipse(20.5, 5.0, 1.4, 0.9, "k")
    return c.rows()


def _litter_poop() -> list[str]:
    """One visible poop pile in the tray (P40): ~12x9 px at scale 3."""
    c = _C(4, 3)
    c.set(1, 0, "k")
    c.set(2, 0, "k")
    c.rect(0, 1, 3, 2, "k")
    return c.rows()


def _litter_pee() -> list[str]:
    """One visible dark wet pee spot in the tray (P40): ~15x6 px at scale 3."""
    c = _C(5, 2)
    c.rect(0, 0, 4, 1, "F")
    return c.rows()


def _wheel_stand() -> list[str]:
    """Exercise wheel STAND only (static): base rail, A-frame, axle. The
    rim (_wheel_rim) rotates around the same center; the stand does not."""
    c = _C(64, 72)
    c.line(32, 34, 15, 65, 2.6, "M")                      # A-frame
    c.line(32, 34, 49, 65, 2.6, "M")
    c.line(31.4, 34, 14.4, 65, 0.7, "m")
    c.round_box(8, 64, 56, 72, 2.4, "M")                  # base rail
    c.round_box(8, 64, 56, 67, 1.6, "m")
    c.ellipse(32, 34, 3.0, 3.0, "g")                      # axle
    c.ellipse(32, 34, 1.1, 1.1, "m")
    return c.rows()


def _wheel_rim() -> list[str]:
    """Exercise wheel RIM only (rotates): ring with tread marks, spokes and
    a red spin marker."""
    c = _C(64, 72)
    for i in range(6):                                    # spokes
        a = math.pi * i / 3
        c.line(32 + 4 * math.cos(a), 34 + 4 * math.sin(a),
               32 + 27 * math.cos(a), 34 + 27 * math.sin(a), 0.55, "M")
    c.ring(32, 34, 26.6, 31.4, "m")                       # rim
    c.ring(32, 34, 26.6, 27.8, "M")                       # inner tread
    for i in range(24):                                   # tread marks
        a = math.pi * i / 12
        c.line(32 + 28.6 * math.cos(a), 34 + 28.6 * math.sin(a),
               32 + 30.6 * math.cos(a), 34 + 30.6 * math.sin(a), 0.45, "M")
    c.ellipse(32, 4.2, 1.5, 1.2, "r")                     # rotation marker (top)
    return c.rows()


def _wheel_front() -> list[str]:
    """Front-bottom arc of the rim, drawn OVER the cat (inside illusion)."""
    c = _C(64, 72)

    def arc(r0: float, r1: float, ch: str) -> None:
        c._fill(2, 56, 62, 66, lambda x, y: 56 <= y < 66
                and r0 <= ((x - 32) ** 2 + (y - 34) ** 2) ** 0.5 <= r1, ch)
    arc(26.6, 31.4, "m")
    arc(26.6, 27.8, "M")
    return c.rows()


def _cat_tree() -> list[str]:
    """Big cat tree (56x72 prop px): base, rope trunk, two carpeted
    platforms that STRADDLE the trunk. Platform tops (rows 8 and 36) feed
    FURNITURE_SURFACES."""
    c = _C(56, 72)
    _rope(c, 24.2, 31.8, 13.4, 64.4)
    c.line(14.0, 41.4, 14.0, 47.0, 0.35, "c")             # dangling toy
    c.ellipse(14.0, 48.2, 1.7, 1.7, "y")
    c.ellipse(13.5, 47.7, 0.5, 0.5, "w")
    _carpet(c, 20, 8, 51, 13.8)                           # top platform
    c.round_box(44.0, 4.6, 51, 9.0, 1.4, "t")             # raised back rest
    _carpet(c, 10, 36, 43, 41.8)                          # mid platform
    _carpet(c, 14, 64, 43, 72)                            # base
    return c.rows()


def _ball() -> list[str]:
    """A rubber ball with a stripe and a shine (8x8 prop px)."""
    c = _C(8, 8)
    c.ellipse(4, 4, 3.3, 3.3, "y")
    c.ellipse(4.6, 4.9, 2.6, 2.4, "Y")                    # shaded lower right
    c.ellipse(3.7, 3.7, 2.7, 2.7, "y")
    c._fill(0.7, 0.7, 7.3, 7.3, lambda x, y: (x - 4) ** 2 + (y - 4) ** 2 <= 3.3 ** 2
            and abs((y - 4) - 0.45 * (x - 4) - 0.5 * math.sin((x - 4) * 1.1)) < 0.75, "r")
    c.ellipse(2.8, 2.6, 0.8, 0.6, "w")
    return c.rows()


def _plush_mouse() -> list[str]:
    """A plush mouse: grey felt, pink ears, a ribbon tail (10x8 prop px)."""
    c = _C(10, 8)
    c.line(7.6, 5.4, 9.6, 3.6, 0.5, "p")                  # ribbon tail
    c.ellipse(5.4, 5.2, 3.6, 2.2, "g")                    # body
    c.ellipse(5.8, 5.9, 2.6, 1.3, "F")                    # felt shade
    c.ellipse(2.4, 5.4, 1.8, 1.5, "g")                    # head
    c.ellipse(3.3, 3.4, 1.25, 1.25, "g")                  # ear
    c.ellipse(3.3, 3.5, 0.65, 0.65, "p")
    c.ellipse(0.9, 5.7, 0.4, 0.4, "p")                    # nose
    c.ellipse(2.1, 4.9, 0.3, 0.3, "o")                    # eye
    c.line(4.2, 4.0, 6.6, 4.0, 0.3, "c")                  # stitching
    return c.rows()


def _puke() -> list[str]:
    """A little accident on the floor (14x8 prop px)."""
    c = _C(14, 8)
    c.ellipse(6.4, 5.6, 5.4, 1.9, "y")
    c.ellipse(9.4, 6.2, 2.4, 1.1, "Y")
    c.ellipse(4.6, 5.2, 1.0, 0.6, "G")
    c.ellipse(7.6, 5.8, 0.7, 0.5, "k")
    c.ellipse(11.8, 6.6, 0.7, 0.4, "y")
    return c.rows()


PROPS: dict[str, list[str]] = {
    "food_bowl": _food_bowl_full(),
    "food_bowl_empty": _food_bowl_empty(),
    "fountain_0": _fountain(0),
    "fountain_1": _fountain(1),
    "fountain_2": _fountain(2),
    "puke": _puke(),
    "wall_shelf": _wall_shelf(),
    "box": _box(),
    "box_front": _box_front(),
    "cat_door_0": _cat_door(0),
    "cat_door_1": _cat_door(1),
    "cat_door_2": _cat_door(2),
    "fish": _from_matrix(ICON_FISH),
    "drop": _from_matrix(ICON_DROP),
    "zzz": _zzz_icon(),
    "heart": _from_matrix(ICON_HEART),
    "ball": _ball(),
    "plush": _plush_mouse(),
    "mouse": _from_matrix(MOUSE),
    "lure": _from_matrix(LURE),
    "laser_dot": _from_matrix(LASER_DOT),
    "scratch_post": _scratch_post(),
    "cat_bed": _cat_bed(),
    "cat_grass": _cat_grass(),
    "litter_0": _litter_box(0),
    "litter_1": _litter_box(1),
    "litter_2": _litter_box(2),
    "litter_poop": _litter_poop(),   # one visible deposit per event
    "litter_pee": _litter_pee(),
    "cat_tree": _cat_tree(),
    "wheel_stand": _wheel_stand(),
    "wheel_rim": _wheel_rim(),
    "wheel_front": _wheel_front(),
}


def prop_to_pixels(name: str):
    """Return (width, height, flat RGBA list) for a prop."""
    frame = PROPS[name]
    out = []
    for row in frame:
        assert all(ch in PROP_PALETTE or ch == "." for ch in row), f"{name}: bad char in {row!r}"
        assert len(row) == len(frame[0]), f"{name}: ragged row {row!r}"
        for ch in row:
            if ch == ".":
                out.append((0, 0, 0, 0))
            else:
                r, g, b = PROP_PALETTE[ch]
                out.append((r, g, b, 255))
    return len(frame[0]), len(frame), out


# Surfaces a cat can stand on, per furniture prop, measured against the art
# at prop scale 3: (dx0, dx1, height above the floor, label). The label is the
# platform's identity for the brain ("Karton", "Laufrad", …).
FURNITURE_SURFACES: dict[str, list[tuple[float, float, float, str]]] = {
    "cat_tree": [(-54, 42, 108, "Katzenbaum"), (-24, 66, 192, "Katzenbaum")],
    "scratch_post": [(-30, 27, 192, "Kratzbaum")],   # wide top (canvas cols 2-21)
    "cat_bed": [(-55, 55, 27, "Katzennest")],        # she lies IN the cushion
    "wheel_stand": [(-60, 60, 36, "Laufrad")],       # inner track (canvas row 60)
    "box": [(-55, 55, 30, "Karton")],                # she sits IN the box
}


def furniture_surfaces(kind: str, x: float, floor_y: float,
                       prop_scale: int) -> list[tuple[float, float, float, str]]:
    """World-space standing surfaces (x0, x1, y, label) of a prop at x."""
    k = prop_scale / 3.0
    return [(x + dx0 * k, x + dx1 * k, floor_y - h * k, label)
            for dx0, dx1, h, label in FURNITURE_SURFACES.get(kind, [])]
