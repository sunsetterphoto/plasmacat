"""Non-cat pixel art: bowls, thought-bubble icons, toys, furniture.

Small items are hand-authored matrices; furniture is built programmatically
(bigger canvases, fewer counting mistakes). Shared palette:
  '.' transparent  'o' outline   'r' red        'k' kibble brown
  'u' water blue   'w' white     'h' heart red  'z' zzz blue-grey
  'f' fish silver  'F' fish shade 'g' grey      'y' yellow
  'G' grass green  's' sisal/sand
"""

from __future__ import annotations

PROP_PALETTE: dict[str, tuple[int, int, int]] = {
    "o": (40, 30, 30),
    "r": (200, 70, 70),
    "k": (120, 80, 40),
    "u": (90, 160, 230),
    "w": (255, 255, 255),
    "h": (230, 80, 100),
    "z": (150, 170, 220),
    "f": (190, 200, 210),
    "F": (130, 145, 160),
    "g": (120, 120, 130),
    "y": (240, 210, 90),
    "G": (100, 190, 90),      # grass green
    "s": (210, 185, 140),     # sisal beige / litter sand
}


class _C:
    """Tiny canvas for furniture (rect/outline boxes/circles only)."""

    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.g = [["."] * w for _ in range(h)]

    def set(self, x: int, y: int, ch: str) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.g[y][x] = ch

    def rect(self, x0: int, y0: int, x1: int, y1: int, ch: str) -> None:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.set(x, y, ch)

    def outline_box(self, x0: int, y0: int, x1: int, y1: int, fill: str) -> None:
        self.rect(x0, y0, x1, y1, "o")
        self.rect(x0 + 1, y0 + 1, x1 - 1, y1 - 1, fill)

    def ring(self, cx: float, cy: float, r0: float, r1: float, ch: str) -> None:
        for y in range(int(cy - r1 - 1), int(cy + r1 + 2)):
            for x in range(int(cx - r1 - 1), int(cx + r1 + 2)):
                d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                if r0 <= d <= r1:
                    self.set(x, y, ch)

    def rows(self) -> list[str]:
        return ["".join(r) for r in self.g]


# ---------------------------------------------------------------------------
# Hand-authored small items
# ---------------------------------------------------------------------------

def _food_bowl_full() -> list[str]:
    """Big, clearly visible food bowl (72x42 px at scale 3): red trapezoid
    heaped with a kibble mound."""
    c = _C(24, 14)
    c.outline_box(2, 8, 21, 13, "r")       # bowl body, wider at the rim
    c.rect(3, 9, 20, 12, "r")
    c.rect(4, 9, 6, 9, "w")                # glossy rim highlight
    # kibble mound heaped above the rim (stepped pixel heap)
    c.rect(5, 5, 18, 9, "k")
    c.rect(8, 3, 15, 4, "k")
    c.rect(10, 2, 13, 2, "k")
    for x, y in ((8, 3), (11, 2), (14, 4), (12, 5), (9, 6), (16, 6)):
        c.set(x, y, "o")                   # dark crumbs give it texture
    return c.rows()


def _food_bowl_empty() -> list[str]:
    """The same bowl, visibly EMPTY: dark interior + shine (user request:
    an empty bowl must be obvious at a glance)."""
    c = _C(24, 14)
    c.outline_box(2, 8, 21, 13, "r")
    c.rect(3, 9, 20, 10, "o")              # dark inside: clearly nothing left
    c.rect(4, 9, 6, 9, "w")                # shine on the empty rim
    c.rect(5, 12, 8, 12, "g")              # scuff mark
    return c.rows()


def _fountain(phase: int) -> list[str]:
    """Perpetual drinking fountain (72x60 px at scale 3): dome with a
    bubbling jet, 3 animation phases. Replaces the water bowl (P25) — the
    user never has to refill water."""
    c = _C(24, 20)
    c.outline_box(1, 14, 22, 19, "g")      # basin
    c.rect(2, 15, 21, 16, "u")             # water surface
    c.rect(3, 15, 6, 15, "w")              # sparkle
    c.rect(10, 6, 13, 14, "g")             # dome column
    c.ring(11.5, 6, 0, 3, "g")             # rounded dome cap
    c.set(10, 4, "w")                      # dome highlight
    jets = (((11, 1), (12, 2)),
            ((11, 0), (10, 2), (12, 2)),
            ((12, 1), (11, 3), (10, 1)))
    for x, y in jets[phase % 3]:           # bubbling jet
        c.set(x, y, "u")
    for x, y in ((9, 8), (14, 9)):         # trickles down the dome
        c.set(x, y + phase % 2, "u")
    return c.rows()


PUKE = [
    "..............",
    ".....oo.......",
    "...ooyyoo.....",
    "..oyyyyyyo....",
    ".oyyGyyyyyo...",
    ".oyyykyyyyo...",
    "..oyyyyyyo....",
    "...oooooo.....",
]


def _wall_shelf() -> list[str]:
    """Floating cat shelf (144x30 px at scale 3): carpeted board + brackets.
    Fixed to the 'wall' — placed at ANY height, never falls (P25)."""
    c = _C(48, 10)
    c.outline_box(0, 0, 47, 3, "k")        # board
    c.rect(1, 1, 46, 1, "s")               # carpeted top
    c.rect(6, 4, 8, 8, "g")                # left bracket
    c.rect(39, 4, 41, 8, "g")              # right bracket
    c.set(7, 9, "o")
    c.set(40, 9, "o")                      # bolt hints
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
    """Cardboard box, BACK part drawn with the furniture (144x84 px at
    scale 3): open top with dark interior, flaps. The front wall
    (_box_front) is drawn OVER the cat so she sits IN the box."""
    c = _C(48, 28)
    c.outline_box(0, 4, 47, 27, "s")       # cardboard body
    c.rect(2, 6, 45, 9, "o")               # dark interior under the rim
    c.rect(2, 0, 12, 2, "s")               # open flaps
    c.rect(35, 0, 45, 2, "s")
    c.rect(14, 1, 22, 3, "k")              # tape strip
    return c.rows()


def _box_front() -> list[str]:
    """Front wall of the cardboard box, drawn over the cat (inside illusion,
    same trick as the exercise wheel)."""
    c = _C(48, 28)
    c.outline_box(0, 12, 47, 27, "s")      # front wall from mid-height down
    c.rect(2, 14, 45, 15, "k")             # tape line
    c.rect(20, 18, 27, 24, "k")            # paw hole
    c.rect(21, 19, 26, 23, "o")
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

BALL = [
    "........",
    "..oooo..",
    ".oryyro.",
    "oyyyyyro",
    "oyyyyyro",
    ".orryyo.",
    "..oooo..",
    "........",
]

PLUSH_MOUSE = [
    "..........",
    ".oo.......",
    ".ggo......",
    "ogggoooo..",
    "ogggggggo.",
    ".ggggggggo",
    "..ooooooo.",
    "..........",
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
    """Sisal post, ~2x cat height at scale 3 (72x192 px) — tall enough for the
    cat to fully stretch her front legs while scratching. The top platform
    spans nearly the full width so the cat can actually lie on it."""
    c = _C(24, 64)
    c.outline_box(2, 0, 21, 4, "r")          # wide top platform (cols 2-21)
    c.outline_box(1, 55, 22, 63, "r")        # base platform
    for y in range(5, 55):                    # trunk with sisal wrap
        ch = "k" if y % 2 == 0 else "s"
        c.rect(10, y, 15, y, "o")
        c.rect(11, y, 14, y, ch)
    return c.rows()


def _cat_bed() -> list[str]:
    """Cushioned nest, fits the whole cat (120x48 px at scale 3)."""
    c = _C(40, 16)
    c.outline_box(0, 4, 6, 15, "r")          # left rim
    c.outline_box(33, 4, 39, 15, "r")        # right rim
    c.outline_box(0, 10, 39, 15, "r")        # bottom rim
    c.rect(5, 4, 34, 11, "o")                # cushion outline
    c.rect(6, 5, 33, 10, "w")                # cushion
    c.rect(10, 7, 29, 9, "F")                # cushion dip
    return c.rows()


def _cat_grass() -> list[str]:
    """Grass pot (48x60 px at scale 3)."""
    c = _C(16, 20)
    blades = [(2, 6), (4, 3), (6, 5), (8, 2), (10, 4), (12, 6), (5, 7), (11, 7)]
    for bx, by in blades:
        for i in range(12 - by):
            c.set(bx + (1 if i > 6 else 0), 11 - i, "G")
    c.outline_box(2, 12, 13, 19, "r")        # pot
    return c.rows()


def _litter_box(fill: int) -> list[str]:
    """Litter tray (84x42 px at scale 3); fill 0-2 = poop level."""
    c = _C(28, 14)
    c.outline_box(0, 3, 27, 13, "r")         # tray
    c.rect(2, 5, 25, 11, "s")                # litter sand
    for tx, ty in ((4, 6), (9, 9), (16, 6), (22, 9), (13, 10), (24, 7), (7, 11)):
        c.set(tx, ty, "F")                   # sand texture (darker grains)
    if fill >= 1:
        c.rect(5, 7, 7, 9, "k")
        c.rect(12, 8, 14, 10, "k")
    if fill >= 2:
        c.rect(19, 6, 21, 8, "k")
        c.rect(9, 6, 10, 7, "k")
    return c.rows()


def _wheel_stand() -> list[str]:
    """Exercise wheel STAND only (static): base rail + strut + axle. The rim
    (_wheel_rim) rotates around the same center; the stand must NOT rotate."""
    c = _C(64, 72)
    c.outline_box(8, 62, 56, 71, "g")         # base rail
    c.rect(30, 52, 34, 62, "o")               # center strut
    c.rect(30, 32, 34, 36, "o")               # axle
    c.set(32, 34, "g")
    return c.rows()


def _wheel_rim() -> list[str]:
    """Exercise wheel RIM only (rotates): ring + red spin marker."""
    c = _C(64, 72)
    c.ring(32, 34, 30, 32, "o")               # rim outline
    c.ring(32, 34, 27, 30, "g")               # rim metal
    c.ring(32, 34, 26, 27, "o")
    c.set(32, 3, "r"); c.set(33, 3, "r")      # rotation marker (top)
    c.set(32, 4, "r")
    return c.rows()


def _wheel_front() -> list[str]:
    """Front-bottom arc of the rim, drawn OVER the cat (inside illusion)."""
    c = _C(64, 72)
    for y in range(56, 66):
        for x in range(2, 62):
            d = ((x - 32) ** 2 + (y - 34) ** 2) ** 0.5
            if 26 <= d <= 32:
                c.set(x, y, "o" if d > 30 or d < 28 else "g")
    return c.rows()


def _cat_tree() -> list[str]:
    """Big cat tree (168x216 px at scale 3): base, sisal trunk, two platforms
    that STRADDLE the trunk (so the sleeping cat lies centered over the trunk
    on the surface, not beside it). Platform tops (canvas coords) feed the
    synthetic platforms in the overlay: mid rows 36-41 cols 10-42, top rows
    8-13 cols 20-50."""
    c = _C(56, 72)
    c.outline_box(14, 64, 42, 71, "r")       # base
    c.outline_box(20, 8, 50, 13, "r")        # top platform (trunk-centered)
    c.outline_box(10, 36, 42, 41, "r")       # mid platform (trunk-centered)
    for y in range(14, 64):                  # trunk with sisal wrap
        ch = "k" if y % 2 == 0 else "s"
        c.rect(24, y, 31, y, "o")
        c.rect(25, y, 30, y, ch)
    return c.rows()


PROPS: dict[str, list[str]] = {
    "food_bowl": _food_bowl_full(),
    "food_bowl_empty": _food_bowl_empty(),
    "fountain_0": _fountain(0),
    "fountain_1": _fountain(1),
    "fountain_2": _fountain(2),
    "puke": PUKE,
    "wall_shelf": _wall_shelf(),
    "box": _box(),
    "box_front": _box_front(),
    "cat_door_0": _cat_door(0),
    "cat_door_1": _cat_door(1),
    "cat_door_2": _cat_door(2),
    "fish": ICON_FISH,
    "drop": ICON_DROP,
    "zzz": _zzz_icon(),
    "heart": ICON_HEART,
    "ball": BALL,
    "plush": PLUSH_MOUSE,
    "lure": LURE,
    "laser_dot": LASER_DOT,
    "scratch_post": _scratch_post(),
    "cat_bed": _cat_bed(),
    "cat_grass": _cat_grass(),
    "litter_0": _litter_box(0),
    "litter_1": _litter_box(1),
    "litter_2": _litter_box(2),
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
