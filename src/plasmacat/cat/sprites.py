"""Pixel-art cat sprites, built procedurally and recolored at runtime.

Sprites are authored as code (ellipses, rects, lines on a character canvas) and
stored as the classic text-matrix format, one char per palette slot:
  '.' transparent      'o' outline        'f' fur (primary)
  'F' fur shade        'b' belly/light fur 'e' eye
  'n' nose/inner ear   'w' eye white       'a' accessory

Build order per frame: silhouette shapes -> shading -> auto-outline -> face.
Auto-outline marks every transparent cell that touches a non-transparent cell
(8-neighborhood) with 'o', giving a consistent chunky retro outline for free.

Customization = palette swap + pattern overlay (solid/tabby/tuxedo/spots/tortie),
see apply_pattern(). All frames are CANVAS_W x CANVAS_H with feet on the bottom
row. Style: chibi side-view cat facing right (flip for left), tall pointy ears,
big pupiled eye, whiskers. Canvas 64x48, displayed at 2x (P8e: finer contours).
"""

from __future__ import annotations

CANVAS_W = 64
CANVAS_H = 48

# -- growth stages (P47) -------------------------------------------------------
# 16 life stages: 0 = kitten … 5 = grown, 6-10 = prime adult, 11+ = senior,
# 15 = very old. The sprites are NOT redrawn per stage: every pose is built
# through the same procedural code, and the Canvas applies the stage's
# proportions as a continuous coordinate transform (feet stay on the bottom
# row, heads grow/shrink smoothly — no silhouette gaps).
STAGES = 16
_HEAD_WARP_R = 20.0      # radius of the smooth head-size warp field
_HEAD_SURFACE = 10.5     # reference head radius (poses draw ~10.5px heads)


def stage_profile(stage: int) -> dict[str, float]:
    """Proportions for a life stage: overall scale, head-size factor, hunch
    (extra vertical squash for the old, stiff cats)."""
    s = min(max(int(stage), 0), STAGES - 1)
    if s <= 5:                     # growing up: kitten -> adult
        t = s / 5.0
        return {"scale": 0.55 + 0.45 * t,   # 0.55 -> 1.0
                "head": 1.50 - 0.50 * t,    # huge kitten head -> adult
                "hunch": 1.0}
    if s <= 10:                    # prime adult
        return {"scale": 1.0, "head": 1.0, "hunch": 1.0}
    t = (s - 10) / 5.0             # senior: shrinking + hunched
    return {"scale": 1.0 - 0.06 * t,        # 0.94 at 15
            "head": 1.0 - 0.04 * t,         # 0.96 at 15
            "hunch": 1.0 - 0.05 * t}        # 0.95 at 15


# Build-time only: the profile the next _build() call renders with. Poses read
# it through Canvas; NOT part of any runtime state.
_PROFILE = stage_profile(6)


def aged_palette(palette: dict[str, tuple[int, int, int]],
                 stage: int) -> dict[str, tuple[int, int, int]]:
    """Seniors grey out: fur slots blend toward their own luminance from
    stage 11 on (up to 45% at 15). Eyes/outline keep their color."""
    s = min(max(int(stage), 0), STAGES - 1)
    if s < 11:
        return palette
    t = (s - 10) / 5.0 * 0.45
    out = dict(palette)
    for k in ("f", "F", "b"):
        r, g, b = out[k]
        grey = (r + g + b) / 3.0
        out[k] = (int(round(r + (grey - r) * t)),
                  int(round(g + (grey - g) * t)),
                  int(round(b + (grey - b) * t)))
    return out


DEFAULT_PALETTE: dict[str, tuple[int, int, int]] = {
    "o": (40, 30, 30),        # outline
    "f": (230, 145, 60),      # fur
    "F": (190, 100, 40),      # fur shade
    "b": (250, 220, 180),     # belly / light
    "e": (90, 200, 90),       # eye
    "n": (240, 140, 150),     # nose / inner ear
    "w": (255, 255, 255),     # eye white / whiskers
    "a": (200, 60, 80),       # accessory
}


class Canvas:
    def __init__(self) -> None:
        self.g = [["."] * CANVAS_W for _ in range(CANVAS_H)]
        self._hz: tuple[float, float] | None = None  # head warp center (P47)

    def head_zone(self, hx: float, hy: float) -> None:
        """Register the head center for the growth-stage warp. draw_ears does
        this automatically; poses with inline ears call it explicitly."""
        self._hz = (hx, hy)

    def _map(self, x: float, y: float) -> tuple[float, float]:
        """Growth-stage transform (P47), applied to every drawing coordinate:
        1. a smooth radial warp around the head (kitten: big head; the field
           falls off to 0 at _HEAD_WARP_R so body and head stay connected),
        2. a global scale anchored at the feet (bottom row stays the feet).
        Stage 6 is the identity — adult sprites are byte-identical to before."""
        if self._hz is not None:
            target = _PROFILE["head"]
            if target != 1.0:
                hx, hy = self._hz
                dx, dy = x - hx, y - hy
                d = (dx * dx + dy * dy) ** 0.5
                if 0.0 < d < _HEAD_WARP_R:
                    k = (target - 1.0) * (1.0 - d / _HEAD_WARP_R) \
                        / (1.0 - _HEAD_SURFACE / _HEAD_WARP_R)
                    x += dx * k
                    y += dy * k
        s = _PROFILE["scale"]
        if s != 1.0 or _PROFILE["hunch"] != 1.0:
            x = CANVAS_W / 2 + (x - CANVAS_W / 2) * s
            y = CANVAS_H - (CANVAS_H - y) * s * _PROFILE["hunch"]
        return x, y

    def set(self, x: float, y: float, ch: str) -> None:
        x, y = self._map(x, y)
        x, y = int(round(x)), int(round(y))
        if 0 <= x < CANVAS_W and 0 <= y < CANVAS_H:
            self.g[y][x] = ch

    def get(self, x: int, y: int) -> str:
        x, y = self._map(x, y)
        x, y = int(round(x)), int(round(y))
        if 0 <= x < CANVAS_W and 0 <= y < CANVAS_H:
            return self.g[y][x]
        return "."

    def rect(self, x0: float, y0: float, x1: float, y1: float, ch: str) -> None:
        for y in range(int(round(y0)), int(round(y1)) + 1):
            for x in range(int(round(x0)), int(round(x1)) + 1):
                self.set(x, y, ch)

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, ch: str) -> None:
        for y in range(int(cy - ry - 1), int(cy + ry + 2)):
            for x in range(int(cx - rx - 1), int(cx + rx + 2)):
                if ((x - cx) / max(rx, 0.1)) ** 2 + ((y - cy) / max(ry, 0.1)) ** 2 <= 1.0:
                    self.set(x, y, ch)

    def disc(self, cx: float, cy: float, r: float, ch: str) -> None:
        self.ellipse(cx, cy, r, r, ch)

    def thick_line(self, x0: float, y0: float, x1: float, y1: float, r: float, ch: str) -> None:
        steps = max(abs(x1 - x0), abs(y1 - y0), 1) * 2
        for i in range(int(steps) + 1):
            t = i / steps
            self.disc(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r, ch)

    def triangle(self, x0, y0, x1, y1, x2, y2, ch: str) -> None:
        xs, ys = [x0, x1, x2], [y0, y1, y2]
        for y in range(int(min(ys)), int(max(ys)) + 1):
            for x in range(int(min(xs)), int(max(xs)) + 1):
                den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
                if den == 0:
                    continue
                a = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / den
                b = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / den
                cc = 1 - a - b
                if a >= 0 and b >= 0 and cc >= 0:
                    self.set(x, y, ch)

    def auto_outline(self) -> None:
        self._heal()  # close warp tears first, or they get outlined (P47)
        add = []
        for y in range(CANVAS_H):
            for x in range(CANVAS_W):
                if self.g[y][x] != ".":
                    continue
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < CANVAS_W and 0 <= ny < CANVAS_H and self.g[ny][nx] != ".":
                            add.append((x, y))
                            dx, dy = 99, 99  # break both loops
                            break
        for x, y in add:
            self.g[y][x] = "o"

    def _heal(self) -> None:
        """Fill isolated 1px holes: the growth-stage warp maps integer cells
        with rounding, which can tear small features (pupil, nose). A hole
        with 3+ orthogonal neighbors of the same color takes that color."""
        for y in range(1, CANVAS_H - 1):
            for x in range(1, CANVAS_W - 1):
                if self.g[y][x] != ".":
                    continue
                nb = (self.g[y - 1][x], self.g[y + 1][x],
                      self.g[y][x - 1], self.g[y][x + 1])
                for ch in ("e", "n", "f", "F", "b", "a"):
                    if nb.count(ch) >= 3:
                        self.g[y][x] = ch
                        break

    def rows(self) -> list[str]:
        self._heal()  # face details are drawn after auto_outline: heal again
        return ["".join(r) for r in self.g]


# ---------------------------------------------------------------------------
# Cat part helpers
# ---------------------------------------------------------------------------

def draw_eye(c: Canvas, x: float, y: float, closed: bool = False,
             lid: bool = False) -> None:
    if closed:
        c.rect(x, y + 2, x + 4, y + 2, "F")      # contented closed eye: slit
        c.set(x + 1, y + 3, "F")
        c.set(x + 3, y + 3, "F")
    elif lid:
        c.rect(x, y, x + 3, y + 2, "F")          # heavy upper lid (half-mast)
        c.rect(x, y + 3, x + 3, y + 5, "e")      # iris peeking out below
        c.rect(x + 2, y + 4, x + 3, y + 5, "o")  # pupil sliver
    else:
        c.rect(x, y, x + 3, y + 5, "e")          # iris 4x6
        c.rect(x + 2, y + 1, x + 3, y + 4, "o")  # pupil
        c.set(x, y, "w")                         # shine
        c.set(x + 1, y + 1, "w")


def draw_whiskers(c: Canvas, hx: float, hy: float) -> None:
    """Relaxed whiskers: two fine lines from the muzzle, arcing gently
    DOWNWARD (research: relaxed cat whiskers droop). Drawn after auto_outline
    so they stay thin 'w' lines, not a blob."""
    for i in range(5):
        c.set(hx + 11.5 + i, hy + 1.6 + i * 0.45, "w")   # upper line, slight droop
    for i in range(4):
        c.set(hx + 11.5 + i, hy + 3.4 + i * 0.6, "w")    # lower line, more droop


def draw_ears(c: Canvas, hx: float, hy: float, back_dx: int = -7, front_dx: int = 3) -> None:
    """Two tall, pointy ears (attentive cat) on a head centered near (hx, hy).
    Drawn BEFORE the head ellipse so the ear bases merge into the skull.
    Also registers the head center for the growth-stage warp (P47)."""
    c.head_zone(hx, hy)
    c.triangle(hx + back_dx - 2, hy - 3, hx + back_dx + 2, hy - 15, hx + back_dx + 5, hy - 3, "f")
    c.triangle(hx + front_dx - 2, hy - 3, hx + front_dx + 3, hy - 15, hx + front_dx + 7, hy - 3, "f")
    # inner ears
    c.set(hx + back_dx + 2, hy - 9, "n")
    c.set(hx + back_dx + 2, hy - 8, "n")
    c.set(hx + back_dx + 1, hy - 7, "n")
    c.set(hx + front_dx + 3, hy - 9, "n")
    c.set(hx + front_dx + 3, hy - 8, "n")
    c.set(hx + front_dx + 4, hy - 7, "n")


def draw_collar(c: Canvas, hx: float, hy: float) -> None:
    """Accessory collar ('a' slot) at the neck + tiny white bell ('w')."""
    for x in range(int(hx - 6), int(hx + 10)):
        for y in range(int(hy + 5.6), int(hy + 8.6)):
            if c.get(x, y) != ".":
                c.set(x, y, "a")
    if c.get(int(hx + 2), int(hy + 9.6)) != ".":
        c.set(hx + 2, hy + 9.6, "w")  # bell


def draw_tail(c: Canvas, x0: float, y0: float, tip: tuple[float, float]) -> None:
    """Tail from body rear to tip, with shade stripes near the tip."""
    c.thick_line(x0, y0, tip[0], tip[1], 2.5, "f")
    c.disc(tip[0], tip[1], 3.0, "f")
    # two darker rings near the tip (classic tabby tail)
    t1x = x0 + (tip[0] - x0) * 0.75
    t1y = y0 + (tip[1] - y0) * 0.75
    c.disc(t1x, t1y, 2.2, "F")
    c.disc(tip[0], tip[1], 1.8, "F")
    c.disc(tip[0], tip[1], 1.1, "f")


def draw_paws(c: Canvas, xs: list[float]) -> None:
    """Toe beans on the front edge of each given paw column."""
    for x in xs:
        c.set(x, CANVAS_H - 2, "F")
        c.set(x, CANVAS_H - 1, "F")


# -- legs (research-grounded, P8f) --------------------------------------------
# Front leg: straight column from the shoulder, paw slightly forward.
# Hind leg: thigh angled from hip to hock, then a near-vertical shin — the
# classic cat hock bend. Far-side legs use shade 'F' for depth.
# Walk gait = PACE (lateral pairs step together); run = GALLOP (spine flexes).

def leg_front(c: Canvas, x: float, top: float, ch: str, lift: float = 0,
              forward: float = 0) -> None:
    x += forward
    c.rect(x, top, x + 2, CANVAS_H - 3 - lift, ch)
    c.rect(x, CANVAS_H - 2 - lift, x + 3, CANVAS_H - 1 - lift, ch)  # paw


def leg_hind(c: Canvas, x: float, top: float, ch: str, lift: float = 0,
             forward: float = 0) -> None:
    x += forward
    c.thick_line(x + 3, top, x + 1, 42 - lift, 2.2, ch)            # thigh -> hock
    c.rect(x, 42 - lift, x + 2, CANVAS_H - 2 - lift, ch)           # shin
    c.rect(x, CANVAS_H - 2 - lift, x + 3, CANVAS_H - 1 - lift, ch)  # paw


def draw_muzzle(c: Canvas, hx: float, hy: float) -> None:
    """Nose + philtrum + mouth on the snout edge (research: small inverted
    triangle with a short line down to the mouth). Drawn after auto_outline."""
    c.set(hx + 10.4, hy + 2.4, "n")  # nose tip at the silhouette edge
    c.set(hx + 10.4, hy + 3.4, "o")  # philtrum
    c.set(hx + 9.6, hy + 4.2, "o")   # mouth corner


# ---------------------------------------------------------------------------
# Poses (all facing right)
# ---------------------------------------------------------------------------

def pose_stand(leg_phase: int = 0, stretch: float = 0.0, head_dx: float = 0,
               head_dy: float = 0, eye_closed: bool = False, eye_lid: bool = False,
               tail_tip: tuple[float, float] = (4.0, 8.0),
               collar: bool = False) -> list[str]:
    """Standing/walking cat. leg_phase 0-3 animates legs; stretch>0 elongates
    the body (run/jump); head_dx/dy move the head (rub/beg); tail_tip sets the
    tail end point (wrap toward the cursor)."""
    c = Canvas()
    rx = 17.0 + stretch * 2.5
    ry = 9.0 - stretch * 1.0
    cx, cy = 29.0, 32.0
    hx, hy = 44.0 + head_dx, 19.0 + head_dy
    # tail first (behind body)
    draw_tail(c, cx - rx + 2, cy - 2, tail_tip)
    # body + head (ears first so their bases merge into the skull)
    c.ellipse(cx, cy, rx, ry, "f")
    draw_ears(c, hx, hy)
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    # cheek fluff
    c.disc(hx + 8.5, hy + 4.5, 2.0, "f")
    # legs: far side shaded 'F' (depth), near side 'f'. Gait: pace (walk) —
    # lateral pairs step together; gallop (run) — both pairs + spine flex.
    leg_top = cy + ry - 2
    if stretch > 0.8:  # gallop
        near = [(2, -3), (0, 3), (2, -3), (0, 3)][leg_phase % 4]
        far = near
    else:              # pace: lateral leg pairs alternate
        near = [(0, 1), (3, 2), (0, 1), (0, 0)][leg_phase % 4]
        far = [(0, 0), (0, 1), (3, 2), (0, 1)][leg_phase % 4]
    leg_hind(c, cx - rx + 5, leg_top, "F", *far)
    leg_front(c, cx + rx - 9, leg_top, "F", *far)
    leg_hind(c, cx - rx + 10, leg_top, "f", *near)
    leg_front(c, cx + rx - 4, leg_top, "f", *near)
    # shading: haunch
    c.ellipse(cx - rx + 9, cy + 4, 6.5, 5.0, "F")
    # belly
    c.ellipse(cx + 3, cy + ry - 3, rx - 6.5, 4.0, "b")
    c.auto_outline()
    draw_eye(c, hx + 4.0, hy - 2.0, closed=eye_closed, lid=eye_lid)
    draw_muzzle(c, hx, hy)
    draw_whiskers(c, hx, hy)
    if collar:
        draw_collar(c, hx, hy)
    return c.rows()


def pose_sit(tail_wave: int = 0, eye_closed: bool = False, paw_up: bool = False,
             head_down: bool = False, tongue: bool = False,
             collar: bool = False) -> list[str]:
    """Sitting cat (also base for beg/groom/eat). tongue adds a lapping tip
    below the snout (drinking)."""
    c = Canvas()
    cx, cy = 30.0, 34.0
    hx, hy = 41.0, (25.0 if head_down else 17.0)
    # sitting body: tall egg shape
    c.ellipse(cx, cy, 16.0, 12.0, "f")
    c.ellipse(cx - 3, cy + 8, 16.0, 7.0, "f")  # haunch base
    # front legs straight down
    c.rect(cx + 8, cy + 2, cx + 11, CANVAS_H - 1, "f")
    # tail wrapping around the front along the ground
    tip_y = CANVAS_H - 5 - tail_wave * 3
    draw_tail(c, cx - 14, CANVAS_H - 5, (cx + 20, tip_y))
    draw_ears(c, hx, hy)
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    c.disc(hx + 8.5, hy + 4.5, 2.0, "f")  # cheek fluff
    if paw_up:
        c.rect(cx + 16, cy - 8, cx + 18, cy + 4, "f")  # raised begging paw
    c.ellipse(cx + 8, cy + 6, 6.0, 5.0, "b")  # chest/belly patch
    c.auto_outline()
    draw_paws(c, [cx + 11])
    draw_eye(c, hx + 4.0, hy - 2.0, closed=eye_closed)
    draw_muzzle(c, hx, hy)
    if tongue:  # lapping at the water (drink frames)
        c.set(hx + 9.4, hy + 6.4, "n")
        c.set(hx + 10.4, hy + 7.2, "n")
    draw_whiskers(c, hx, hy)
    if collar:
        draw_collar(c, hx, hy)
    return c.rows()


def pose_sleep(breath: int = 0) -> list[str]:
    """Curled loaf, eyes closed. breath raises the back slightly on frame 1."""
    c = Canvas()
    lift = 1.2 * breath
    cx, cy = 32.0, 38.0 - lift
    # curled body
    c.ellipse(cx, cy, 22.0, 9.0, "f")
    # head resting at the left
    draw_ears(c, 16.0, 34.0 - lift, back_dx=-7, front_dx=3)
    c.ellipse(16.0, 34.0 - lift, 10.0, 8.0, "f")
    # tail wrapping around the right side
    draw_tail(c, 48, CANVAS_H - 5, (58, CANVAS_H - 6))
    c.auto_outline()
    draw_eye(c, 19.0, 31.0 - lift, closed=True)
    c.set(9.0, 36.0 - lift, "n")
    return c.rows()


def pose_scratch(paw_phase: int = 0) -> list[str]:
    """Upright scratching: hind legs planted, front legs stretched high against
    a post (to the right), tail back for balance. paw_phase alternates the
    clawing paws."""
    c = Canvas()
    # upright body (taller than wide), head high
    draw_tail(c, 20, 38, (8, 42))
    c.ellipse(26, 34, 9.5, 11.0, "f")
    draw_ears(c, 32, 20)
    c.ellipse(32, 20, 10.5, 9.0, "f")
    # hind legs planted
    leg_hind(c, 21, 40, "F")
    leg_hind(c, 27, 40, "f")
    # front legs stretched UP against the post, alternating claw strokes
    c.thick_line(33, 30, 44, 14 + paw_phase * 3, 2.2, "f")   # near front leg
    c.thick_line(30, 32, 41, 17 - paw_phase * 3, 2.2, "F")   # far front leg
    # belly + haunch shading
    c.ellipse(29, 38, 5.5, 6.5, "b")
    c.auto_outline()
    draw_eye(c, 36.0, 18.0)
    draw_muzzle(c, 32, 20)
    draw_whiskers(c, 32, 20)
    return c.rows()


def pose_scratch_self(phase: int = 0) -> list[str]:
    """Sitting, hind leg raised scratching the cheek, eyes closed in bliss —
    part of the pre-sleep ritual (and general self-care)."""
    c = Canvas()
    cx, cy = 30.0, 34.0
    hx, hy = 38.0, 19.0
    c.ellipse(cx, cy, 16.0, 12.0, "f")
    c.ellipse(cx - 3, cy + 8, 16.0, 7.0, "f")
    c.rect(cx + 8, cy + 2, cx + 11, CANVAS_H - 1, "f")  # front legs down
    draw_tail(c, cx - 14, CANVAS_H - 5, (cx + 20, CANVAS_H - 5 - phase))
    draw_ears(c, hx, hy)
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    # hind leg raised to the cheek (the scratching leg)
    c.thick_line(cx - 2, cy + 10, hx - 6, hy + 5 + phase * 2, 2.5, "f")
    c.disc(hx - 6, hy + 5 + phase * 2, 2.8, "f")  # paw at the cheek
    c.ellipse(cx + 8, cy + 6, 6.0, 5.0, "b")  # chest patch
    c.auto_outline()
    draw_eye(c, hx + 4.0, hy - 2.0, closed=True)
    draw_muzzle(c, hx, hy)
    draw_whiskers(c, hx, hy)
    return c.rows()


def pose_groom(phase: int = 0) -> list[str]:
    """Body grooming: head bent down-left INTO the flank (tongue licking the
    fur on even frames). Clearly distinct from eating (head to the bowl) and
    from face washing (ear fold + paw licking)."""
    c = Canvas()
    cx, cy = 30.0, 34.0
    c.ellipse(cx, cy, 16.0, 12.0, "f")
    c.ellipse(cx - 3, cy + 8, 16.0, 7.0, "f")
    c.rect(cx + 8, cy + 2, cx + 11, CANVAS_H - 1, "f")
    draw_tail(c, cx - 14, CANVAS_H - 5, (cx + 20, CANVAS_H - 5))
    # head bent down-left into the flank
    hx, hy = 24.0, 26.0
    draw_ears(c, hx, hy)
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    if phase == 0:  # tongue out to the flank
        c.set(cx + 2, cy + 3, "n")
        c.set(cx + 1, cy + 4, "n")
    c.ellipse(cx + 8, cy + 6, 6.0, 5.0, "b")
    c.auto_outline()
    draw_eye(c, hx + 3.0, hy - 1.0, closed=True)
    c.set(hx + 10.4, hy + 2.4, "n")  # nose into the fur
    return c.rows()


def pose_ear_fold() -> list[str]:
    """Face-wash step 1: the near paw presses the near ear down flat."""
    c = Canvas()
    cx, cy = 30.0, 34.0
    hx, hy = 41.0, 17.0
    c.head_zone(hx, hy)  # inline ears here: register the warp center (P47)
    c.ellipse(cx, cy, 16.0, 12.0, "f")
    c.ellipse(cx - 3, cy + 8, 16.0, 7.0, "f")
    draw_tail(c, cx - 14, CANVAS_H - 5, (cx + 20, CANVAS_H - 5))
    # only the FAR ear stands; the near one is folded under the paw
    c.triangle(hx + 1, hy - 3, hx + 4, hy - 15, hx + 9, hy - 3, "f")
    c.set(hx + 4, hy - 9, "n")
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    # far front leg down
    c.rect(cx + 9, cy + 2, cx + 11, CANVAS_H - 1, "f")
    # near leg raised OVER the head, paw pressing the near ear flat
    c.thick_line(cx + 6, cy + 2, hx + 1, hy - 7, 2.5, "f")
    c.disc(hx + 1, hy - 7, 3.0, "f")
    c.triangle(hx - 2, hy - 5, hx + 3, hy - 8, hx + 3, hy - 4, "F")  # folded ear
    c.ellipse(cx + 8, cy + 6, 6.0, 5.0, "b")
    c.auto_outline()
    draw_eye(c, hx + 4.0, hy - 1.0, closed=True)
    draw_muzzle(c, hx, hy)
    draw_whiskers(c, hx, hy)
    return c.rows()


def pose_lick_paw(phase: int = 0) -> list[str]:
    """Face-wash step 2: licking the raised front paw (tongue out on even
    frames). 2 frames alternating = one lick cycle."""
    c = Canvas()
    cx, cy = 30.0, 34.0
    hx, hy = 41.0, 19.0  # head slightly lowered toward the paw
    c.ellipse(cx, cy, 16.0, 12.0, "f")
    c.ellipse(cx - 3, cy + 8, 16.0, 7.0, "f")
    draw_tail(c, cx - 14, CANVAS_H - 5, (cx + 20, CANVAS_H - 5))
    draw_ears(c, hx, hy)
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    # far front leg down
    c.rect(cx + 9, cy + 2, cx + 11, CANVAS_H - 1, "f")
    # near front leg raised forward to the mouth
    c.thick_line(cx + 6, cy + 2, hx + 9, hy + 3, 2.5, "f")
    c.disc(hx + 9, hy + 3, 2.8, "f")  # paw at the mouth
    if phase == 0:  # tongue out onto the paw
        c.set(hx + 10.2, hy + 3.4, "n")
        c.set(hx + 11.2, hy + 3.8, "n")
    c.ellipse(cx + 8, cy + 6, 6.0, 5.0, "b")
    c.auto_outline()
    draw_eye(c, hx + 4.0, hy - 2.0, closed=True)
    draw_muzzle(c, hx, hy)
    draw_whiskers(c, hx, hy)
    return c.rows()


def pose_crouch(lash: int = 0) -> list[str]:
    """Pre-pounce crouch/stalk: body low, each leg steps independently (real
    stalk gait), tail low and lashing."""
    c = Canvas()
    draw_tail(c, 10, 30, (2, 26 + lash * 3))
    c.ellipse(30.0, 38.0, 18.0, 7.5, "f")
    draw_ears(c, 44.0, 28.0)
    c.ellipse(44.0, 28.0, 10.5, 9.0, "f")
    c.disc(52.0, 32.0, 2.0, "f")  # cheek fluff
    leg_hind(c, 17, 40, "F", lift=1 if lash else 0)
    leg_front(c, 39, 40, "F")
    leg_hind(c, 22, 40, "f")
    leg_front(c, 44, 40, "f", lift=0 if lash else 1)
    c.auto_outline()
    draw_eye(c, 48.0, 26.0)
    draw_muzzle(c, 44.0, 28.0)
    draw_whiskers(c, 44.0, 28.0)
    return c.rows()


def pose_loaf(phase: int = 0, collar: bool = False) -> list[str]:
    """The loaf: all four paws tucked under, a content dome of cat. The tail
    wraps around the side; its tip flicks up on phase 1."""
    c = Canvas()
    cx, cy = 30.0, 40.0
    hx, hy = 42.0, 30.0
    # tucked body: smooth dome touching the ground
    c.ellipse(cx, cy, 19.0, 7.5, "f")
    c.ellipse(cx - 4, cy - 4, 13.0, 5.5, "f")   # raised back/shoulders
    # tail wraps around the front along the ground; tip flicks
    draw_tail(c, cx - 17, CANVAS_H - 4, (cx + 20, CANVAS_H - 4 - phase * 4))
    draw_ears(c, hx, hy)
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    c.disc(hx + 8.5, hy + 4.5, 2.0, "f")  # cheek fluff
    c.ellipse(cx + 10, cy + 2, 6.0, 4.0, "b")  # chest hint
    c.auto_outline()
    draw_eye(c, hx + 4.0, hy - 2.0, lid=True)  # drowsy half-mast
    draw_muzzle(c, hx, hy)
    draw_whiskers(c, hx, hy)
    if collar:
        draw_collar(c, hx, hy)
    return c.rows()


def pose_stretch(phase: int = 0, collar: bool = False) -> list[str]:
    """The after-nap stretch: front-down bow — chest low, front legs reaching
    forward, hindquarters high, tail straight up. Phase 1 lifts the head."""
    c = Canvas()
    # hindquarters high (left), chest low (right): the classic yoga bow
    c.ellipse(19.0, 30.0, 9.0, 8.0, "f")                    # haunches up
    c.thick_line(22, 33, 38, 40, 5.5, "f")                  # back slopes down
    c.ellipse(40.0, 40.0, 9.5, 6.5, "f")                    # chest near ground
    # hind legs: hock bent, paws planted
    c.thick_line(17, 34, 15, 42, 2.2, "F")
    c.rect(13, 42, 16, CANVAS_H - 1, "F")
    c.thick_line(22, 35, 20, 42, 2.2, "f")
    c.rect(18, 42, 21, CANVAS_H - 1, "f")
    # front legs reaching far forward along the ground
    c.thick_line(44, 42, 55, 46, 2.2, "F")
    c.disc(56, 46, 2.2, "F")
    c.thick_line(46, 44, 58, 47, 2.2, "f")
    c.disc(59, 47, 2.4, "f")
    # tail straight up
    draw_tail(c, 13, 26, (9, 5))
    # head: low in frame 0, lifting in frame 1
    hx, hy = 50.0, 33.0 - phase * 4
    draw_ears(c, hx, hy)
    c.ellipse(hx, hy, 10.0, 8.5, "f")
    c.disc(hx + 8.0, hy + 4.5, 2.0, "f")
    c.ellipse(38, 43, 6.0, 3.5, "b")                        # stretched belly
    c.auto_outline()
    draw_eye(c, hx + 3.5, hy - 2.0)
    draw_muzzle(c, hx, hy)
    draw_whiskers(c, hx, hy)
    if collar:
        draw_collar(c, hx, hy)
    return c.rows()


def pose_yawn(phase: int = 0, collar: bool = False) -> list[str]:
    """The big yawn: sitting, head thrown up, mouth wide open (dark maw with
    a tongue), eyes squeezed shut. Frame 1 = full gape."""
    c = Canvas()
    cx, cy = 30.0, 34.0
    hx, hy = 42.0, 14.0   # head raised high
    c.ellipse(cx, cy, 16.0, 12.0, "f")
    c.ellipse(cx - 3, cy + 8, 16.0, 7.0, "f")
    c.rect(cx + 8, cy + 2, cx + 11, CANVAS_H - 1, "f")
    draw_tail(c, cx - 14, CANVAS_H - 5, (cx + 20, CANVAS_H - 5))
    draw_ears(c, hx, hy, back_dx=-8, front_dx=2)  # ears pushed back by the yawn
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    c.disc(hx + 8.5, hy + 4.5, 2.0, "f")
    c.ellipse(cx + 8, cy + 6, 6.0, 5.0, "b")
    c.auto_outline()
    draw_eye(c, hx + 4.0, hy - 2.0, closed=True)   # squeezed shut
    # wide open mouth at the snout edge: dark maw + tongue, nose above
    c.set(hx + 10.4, hy + 0.4, "n")                # nose tip
    depth = 2 + phase * 2
    c.rect(hx + 8.6, hy + 2, hx + 11.4, hy + 2 + depth, "o")       # dark maw
    c.rect(hx + 9.4, hy + 1 + depth, hx + 10.6, hy + 2 + depth, "n")  # tongue
    draw_whiskers(c, hx, hy)
    if collar:
        draw_collar(c, hx, hy)
    return c.rows()


def pose_knead(phase: int = 0, collar: bool = False) -> list[str]:
    """Kneading ('making biscuits') on a soft spot: sitting, front paws press
    down alternately, eyes half closed in bliss — usually with purring."""
    c = Canvas()
    cx, cy = 30.0, 34.0
    hx, hy = 41.0, 17.0
    c.ellipse(cx, cy, 16.0, 12.0, "f")
    c.ellipse(cx - 3, cy + 8, 16.0, 7.0, "f")
    draw_tail(c, cx - 14, CANVAS_H - 5, (cx + 20, CANVAS_H - 5))
    draw_ears(c, hx, hy)
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    c.disc(hx + 8.5, hy + 4.5, 2.0, "f")
    # alternating paw presses: the active paw reaches forward-down
    if phase == 0:
        c.rect(cx + 7, cy + 2, cx + 9, CANVAS_H - 1, "F")          # far planted
        c.thick_line(cx + 10, cy + 4, cx + 17, CANVAS_H - 2, 2.2, "f")
        c.disc(cx + 18, CANVAS_H - 2, 2.6, "f")                    # pressing paw
    else:
        c.thick_line(cx + 8, cy + 4, cx + 15, CANVAS_H - 2, 2.2, "F")
        c.disc(cx + 16, CANVAS_H - 2, 2.6, "F")
        c.rect(cx + 9, cy + 2, cx + 11, CANVAS_H - 1, "f")         # near planted
    c.ellipse(cx + 8, cy + 6, 6.0, 5.0, "b")
    c.auto_outline()
    draw_eye(c, hx + 4.0, hy - 2.0, lid=True)      # blissful half-mast
    draw_muzzle(c, hx, hy)
    draw_whiskers(c, hx, hy)
    if collar:
        draw_collar(c, hx, hy)
    return c.rows()


def pose_sleep_belly(breath: int = 0) -> list[str]:
    """Deep-trust sleep: flat on her back, belly exposed, paws curled up.
    A cat only sleeps like this where it feels completely safe — the game
    shows it once attachment is high."""
    c = Canvas()
    lift = breath
    cx, cy = 32.0, 41.0
    c.head_zone(13.0, 40.0)  # head lies sideways at the left (P47 warp)
    # body flat on the ground, belly side UP
    c.ellipse(cx, cy, 20.0, 6.5, "f")
    c.ellipse(cx, cy - 2 - lift, 13.0, 4.5, "b")   # exposed belly on top
    # four paws curled upward
    for px, py in ((23, 32), (28, 31), (37, 31), (42, 32)):
        c.rect(px, py - lift, px + 1, py + 3 - lift, "f")
        c.set(px, py - lift, "F")
    # head lying on its side at the left
    hx, hy = 13.0, 40.0
    c.ellipse(hx, hy, 9.5, 7.5, "f")
    c.triangle(hx - 8, hy - 3, hx - 6, hy - 12, hx - 1, hy - 4, "f")  # flopped ears
    c.triangle(hx + 1, hy - 6, hx + 5, hy - 14, hx + 8, hy - 5, "f")
    # tail curled up over the hip
    draw_tail(c, 50, 44, (41, 33))
    c.auto_outline()
    draw_eye(c, hx + 3, hy - 3, closed=True)
    c.set(hx - 7.4, hy + 1.4, "n")   # nose at the sideways snout edge
    return c.rows()


def pose_wiggle(phase: int = 0, collar: bool = False) -> list[str]:
    """Pre-pounce butt wiggle: crouched low, hindquarters shaking side to
    side, eyes wide and locked on the target."""
    c = Canvas()
    wob = (-2, 0, 2)[phase % 3]
    # low crouched body, front end steady, rear end oscillates
    c.ellipse(30.0, 39.0, 17.0, 7.0, "f")
    c.ellipse(19.0 + wob, 37.0, 8.5, 6.5, "f")     # wiggling haunches
    # coiled hind legs
    leg_hind(c, 15, 42, "F")
    leg_hind(c, 20, 42, "f")
    # front paws stretched forward, ready to launch
    c.thick_line(38, 42, 46, 46, 2.2, "F")
    c.thick_line(41, 42, 50, 46, 2.2, "f")
    c.disc(51, 46, 2.3, "f")
    # tail low, lashing along with the wiggle
    draw_tail(c, 13, 42, (4, 44 - phase * 2))
    hx, hy = 44.0, 29.0
    draw_ears(c, hx, hy)
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    c.disc(hx + 8.5, hy + 4.5, 2.0, "f")
    c.auto_outline()
    draw_eye(c, hx + 4.0, hy - 2.0)                # wide, locked on
    draw_muzzle(c, hx, hy)
    draw_whiskers(c, hx, hy)
    if collar:
        draw_collar(c, hx, hy)
    return c.rows()


def pose_tail_lash(phase: int = 0, collar: bool = False) -> list[str]:
    """Annoyed: sitting stiffly, ears pinned back, eyes narrowed, tail
    whipping left-right across the ground."""
    c = Canvas()
    cx, cy = 30.0, 34.0
    hx, hy = 41.0, 17.0
    c.ellipse(cx, cy, 16.0, 12.0, "f")
    c.ellipse(cx - 3, cy + 8, 16.0, 7.0, "f")
    c.rect(cx + 8, cy + 2, cx + 11, CANVAS_H - 1, "f")
    # the tail whips: phase 0 flung left, phase 1 swept right
    tip = (6.0, CANVAS_H - 4) if phase == 0 else (cx + 18, CANVAS_H - 4)
    draw_tail(c, cx - 14, CANVAS_H - 5, tip)
    draw_ears(c, hx, hy, back_dx=-9, front_dx=1)   # ears pinned back
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    c.disc(hx + 8.5, hy + 4.5, 2.0, "f")
    c.ellipse(cx + 8, cy + 6, 6.0, 5.0, "b")
    c.auto_outline()
    draw_eye(c, hx + 4.0, hy - 2.0, lid=True)      # narrowed, unimpressed
    draw_muzzle(c, hx, hy)
    draw_whiskers(c, hx, hy)
    if collar:
        draw_collar(c, hx, hy)
    return c.rows()


def pose_alert(phase: int = 0, collar: bool = False) -> list[str]:
    """Startled-alert: frozen upright, stiff legs, head high, ears swiveled
    forward, puffed bottle-brush tail hanging low."""
    c = Canvas()
    cx, cy = 29.0, 31.0
    hx, hy = 44.0, 16.0 - phase   # frame 1: head perks even higher
    # puffed low tail (bottle brush, thicker than draw_tail)
    c.thick_line(cx - 16, cy - 2, 6, 36, 3.4, "f")
    c.disc(6, 36, 3.6, "f")
    c.disc(6, 36, 1.6, "F")
    c.ellipse(cx, cy, 16.0, 8.5, "f")
    # stiff straight legs
    leg_hind(c, cx - 12, cy + 7, "F")
    leg_front(c, cx + 8, cy + 7, "F")
    leg_hind(c, cx - 8, cy + 7, "f")
    leg_front(c, cx + 12, cy + 7, "f")
    draw_ears(c, hx, hy)
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    c.disc(hx + 8.5, hy + 4.5, 2.0, "f")
    c.ellipse(cx - 9, cy + 4, 6.0, 4.5, "F")   # tense haunch
    c.ellipse(cx + 3, cy + 6, 9.0, 3.5, "b")
    c.auto_outline()
    draw_eye(c, hx + 4.0, hy - 2.0)
    draw_muzzle(c, hx, hy)
    draw_whiskers(c, hx, hy)
    if collar:
        draw_collar(c, hx, hy)
    return c.rows()


def pose_squat(phase: int = 0, collar: bool = False) -> list[str]:
    """The litter-box hunch: hindquarters dropped low, front legs straight,
    tail held high and vertical, dignified far-away stare."""
    c = Canvas()
    cx, cy = 30.0, 40.0
    hx, hy = 44.0, 29.0
    # tail straight up first (drawn behind the body)
    draw_tail(c, 14, 38, (10 + phase * 2, 7))
    c.ellipse(cx, cy, 17.0, 7.0, "f")
    c.ellipse(20.0, 42.0, 9.0, 5.5, "f")     # dropped hindquarters
    # hind legs folded under
    c.ellipse(17.0, 44.0, 5.0, 3.5, "F")
    # front legs straight down
    c.rect(40, 42, 43, CANVAS_H - 1, "F")
    c.rect(44, 42, 47, CANVAS_H - 1, "f")
    draw_ears(c, hx, hy)
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    c.disc(hx + 8.5, hy + 4.5, 2.0, "f")
    c.auto_outline()
    draw_eye(c, hx + 4.0, hy - 2.0, lid=True)   # the far-away litter stare
    draw_muzzle(c, hx, hy)
    draw_whiskers(c, hx, hy)
    if collar:
        draw_collar(c, hx, hy)
    return c.rows()


def pose_cover(phase: int = 0, collar: bool = False) -> list[str]:
    """Covering the evidence: standing by the tray, one front paw sweeping
    litter backward (alternating strokes)."""
    c = Canvas()
    cx, cy = 29.0, 33.0
    hx, hy = 44.0, 22.0
    draw_tail(c, 13, 31, (5, 15))
    c.ellipse(cx, cy, 16.0, 8.5, "f")
    leg_hind(c, cx - 12, cy + 6, "F")
    leg_hind(c, cx - 8, cy + 6, "f")
    # near front leg sweeps backward; far leg planted
    c.rect(cx + 6, cy + 6, cx + 8, CANVAS_H - 1, "F")
    c.thick_line(cx + 12, cy + 4, cx + 14 - phase * 10, CANVAS_H - 2, 2.2, "f")
    c.disc(cx + 14 - phase * 10, CANVAS_H - 2, 2.4, "f")
    draw_ears(c, hx, hy)
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    c.disc(hx + 8.5, hy + 4.5, 2.0, "f")
    c.ellipse(cx - 9, cy + 4, 6.0, 4.5, "F")
    c.auto_outline()
    draw_eye(c, hx + 4.0, hy - 2.0)
    draw_muzzle(c, hx, hy)
    draw_whiskers(c, hx, hy)
    if collar:
        draw_collar(c, hx, hy)
    return c.rows()


def pose_watch(phase: int = 0, collar: bool = False) -> list[str]:
    """Curious watching: sitting tall — and every couple of seconds the head
    TILTS to the side (the classic 'what is that?' cat look)."""
    c = Canvas()
    cx, cy = 30.0, 34.0
    hx, hy = 41.0, 17.0
    tilt = 3 if phase else 0
    c.head_zone(hx + tilt, hy + tilt * 0.5)  # inline tilt ears (P47 warp)
    c.ellipse(cx, cy, 16.0, 12.0, "f")
    c.ellipse(cx - 3, cy + 8, 16.0, 7.0, "f")
    c.rect(cx + 8, cy + 2, cx + 11, CANVAS_H - 1, "f")
    draw_tail(c, cx - 14, CANVAS_H - 5, (cx + 20, CANVAS_H - 5))
    if tilt:
        # tilted skull: ears at an angle, head blob shifted right-down
        c.triangle(hx - 8, hy - 4, hx - 3, hy - 15, hx + 1, hy - 3, "f")
        c.triangle(hx + 3, hy - 2, hx + 9, hy - 11, hx + 12, hy - 1, "f")
        c.set(hx - 3, hy - 9, "n")
        c.set(hx + 8, hy - 6, "n")
        c.ellipse(hx + 3, hy + 1, 10.5, 9.0, "f")
        c.disc(hx + 11.5, hy + 5.5, 2.0, "f")
    else:
        draw_ears(c, hx, hy)
        c.ellipse(hx, hy, 10.5, 9.0, "f")
        c.disc(hx + 8.5, hy + 4.5, 2.0, "f")
    c.ellipse(cx + 8, cy + 6, 6.0, 5.0, "b")
    c.auto_outline()
    draw_eye(c, hx + 4.0 + tilt, hy - 2.0 + tilt * 0.5)
    draw_muzzle(c, hx + tilt, hy + tilt * 0.5)
    draw_whiskers(c, hx + tilt, hy + tilt * 0.5)
    if collar:
        draw_collar(c, hx + tilt, hy + tilt * 0.5)
    return c.rows()


def pose_retch(phase: int = 0, collar: bool = False) -> list[str]:
    """Retching: hunched low, neck stretched forward and DOWN, body lurching
    (the phase convulses), eyes squeezed, mouth straining open."""
    c = Canvas()
    lurch = (-2, 1, 0)[phase % 3]
    cx, cy = 28.0 + lurch, 36.0
    draw_tail(c, 12, 33, (3, 41))
    c.ellipse(cx, cy, 17.0, 9.0, "f")
    c.ellipse(cx - 4, cy - 6, 10.0, 5.0, "f")   # arched back
    # stiff braced legs
    leg_hind(c, cx - 13, cy + 4, "F")
    leg_front(c, cx + 9, cy + 4, "F")
    leg_hind(c, cx - 9, cy + 4, "f")
    leg_front(c, cx + 13, cy + 4, "f")
    # head stretched forward and down (the retch posture)
    hx, hy = 47.0, 34.0 + lurch
    draw_ears(c, hx, hy, back_dx=-8, front_dx=1)
    c.ellipse(hx, hy, 10.0, 8.0, "f")
    c.auto_outline()
    draw_eye(c, hx + 3.0, hy - 2.0, closed=True)
    # straining open mouth at the lowered snout
    c.set(hx + 9.6, hy + 1.6, "n")
    c.rect(hx + 8.4, hy + 3, hx + 10.4, hy + 4 + phase % 2, "o")
    if collar:
        draw_collar(c, hx, hy)
    return c.rows()


def pose_box_peek(phase: int = 0, collar: bool = False) -> list[str]:
    """Hiding in the cardboard box: crouched flat, wide eyes and ears peeking
    over the rim — ready to ambush anything that passes."""
    c = Canvas()
    cx, cy = 30.0, 44.0
    # flattened body low on the canvas (the box front hides the rest)
    c.ellipse(cx, cy, 18.0, 5.0, "f")
    draw_tail(c, 14, 45, (5, 45 - phase * 2))
    hx, hy = 40.0, 38.0
    draw_ears(c, hx, hy)
    c.ellipse(hx, hy, 10.5, 8.5, "f")
    c.disc(hx + 8.5, hy + 4.0, 2.0, "f")
    c.auto_outline()
    draw_eye(c, hx + 4.0, hy - 2.0)   # wide awake
    draw_muzzle(c, hx, hy)
    if collar:
        draw_collar(c, hx, hy)
    return c.rows()


def pose_paw_bat(phase: int = 0, collar: bool = False) -> list[str]:
    """The gentle paw bat: standing, one front paw reaches out and pats at
    the teasing cursor (frame 0: raised, frame 1: swiping down)."""
    c = Canvas()
    cx, cy = 29.0, 32.0
    hx, hy = 44.0, 18.0
    # tail mid-height, tip flicks with the bat
    draw_tail(c, cx - 15, cy - 2, (4.0, 20.0 - phase * 3))
    c.ellipse(cx, cy, 17.0, 9.0, "f")
    draw_ears(c, hx, hy)
    c.ellipse(hx, hy, 10.5, 9.0, "f")
    c.disc(hx + 8.5, hy + 4.5, 2.0, "f")
    leg_top = cy + 7.0
    leg_hind(c, cx - 12, leg_top, "F")
    leg_front(c, cx + 4, leg_top, "F")
    leg_hind(c, cx - 7, leg_top, "f")
    # near front paw reaches OUT and bats (down on frame 1)
    bx, by = (56.0, 26.0) if phase == 0 else (57.0, 36.0)
    c.thick_line(cx + 12, leg_top - 4, bx, by, 2.3, "f")
    c.disc(bx + 1, by, 2.6, "f")
    c.ellipse(cx - 8, cy + 4, 6.5, 5.0, "F")
    c.ellipse(cx + 3, cy + 6, 9.0, 4.0, "b")
    c.auto_outline()
    draw_eye(c, hx + 4.0, hy - 2.0)   # focused on the target
    draw_muzzle(c, hx, hy)
    draw_whiskers(c, hx, hy)
    if collar:
        draw_collar(c, hx, hy)
    return c.rows()


# ---------------------------------------------------------------------------
# Animation table
# ---------------------------------------------------------------------------

def _build_table(collar: bool = False) -> dict[str, list[list[str]]]:
    return {
        "stand": [pose_stand(collar=collar), pose_stand(tail_tip=(3.0, 10.0), collar=collar)],
        "walk": [pose_stand(leg_phase=p, collar=collar) for p in range(4)],
        "run": [pose_stand(leg_phase=p, stretch=1.2, tail_tip=(6.0, 24.0), collar=collar)
                for p in range(4)],
        "jump": [pose_stand(stretch=1.5, tail_tip=(7.0, 22.0), collar=collar)],
        "sit": [pose_sit(collar=collar), pose_sit(tail_wave=1, collar=collar)],
        "sit_blink": [pose_sit(eye_closed=True, collar=collar)],
        "beg": [pose_sit(paw_up=True, collar=collar),
               pose_sit(paw_up=True, tail_wave=1, collar=collar)],
        "groom": [pose_groom(0), pose_groom(1)],
        "ear_fold": [pose_ear_fold()],
        "lick_paw": [pose_lick_paw(0), pose_lick_paw(1)],
        "eat": [pose_sit(head_down=True, collar=collar),
               pose_sit(head_down=True, tail_wave=1, collar=collar)],
        "sleep": [pose_sleep(0), pose_sleep(1)],
        "crouch": [pose_crouch(0), pose_crouch(1)],
        "scratch": [pose_scratch(0), pose_scratch(1)],
        "scratch_self": [pose_scratch_self(0), pose_scratch_self(1)],
        "rub": [pose_stand(head_dx=2.0, head_dy=-2.0, eye_closed=True, collar=collar)],
        # the "cat kiss": a slow-blink cycle while being petted (open -> half
        # -> closed -> half), the strongest sign of feline trust
        "enjoy": [pose_stand(collar=collar),
                  pose_stand(eye_lid=True, collar=collar),
                  pose_stand(eye_closed=True, collar=collar),
                  pose_stand(eye_lid=True, collar=collar)],
        # tail extended forward toward the cursor (the "tail snuggle")
        "tailwrap": [pose_stand(tail_tip=(24.0, 36.0), eye_closed=True, collar=collar)],
        # P24 realism pack
        "loaf": [pose_loaf(0, collar=collar), pose_loaf(1, collar=collar)],
        "stretch": [pose_stretch(0, collar=collar), pose_stretch(1, collar=collar)],
        "yawn": [pose_yawn(0, collar=collar), pose_yawn(1, collar=collar)],
        "knead": [pose_knead(0, collar=collar), pose_knead(1, collar=collar)],
        "sleep_belly": [pose_sleep_belly(0), pose_sleep_belly(1)],
        "wiggle": [pose_wiggle(p, collar=collar) for p in range(3)],
        "tail_lash": [pose_tail_lash(0, collar=collar), pose_tail_lash(1, collar=collar)],
        "alert": [pose_alert(0, collar=collar), pose_alert(1, collar=collar)],
        "squat": [pose_squat(0, collar=collar), pose_squat(1, collar=collar)],
        "cover": [pose_cover(0, collar=collar), pose_cover(1, collar=collar)],
        "drink": [pose_sit(head_down=True, tongue=True, collar=collar),
                  pose_sit(head_down=True, collar=collar)],
        "watch": [pose_watch(0, collar=collar), pose_watch(1, collar=collar)],
        # P25
        "retch": [pose_retch(p, collar=collar) for p in range(3)],
        "box_peek": [pose_box_peek(0, collar=collar), pose_box_peek(1, collar=collar)],
        # P26
        "paw_bat": [pose_paw_bat(0, collar=collar), pose_paw_bat(1, collar=collar)],
        # mood-dependent tail variants (P8g): mid = neutral, low = grumpy
        "stand:mid": [pose_stand(tail_tip=(2.0, 20.0), collar=collar)],
        "stand:low": [pose_stand(tail_tip=(4.0, 33.0), collar=collar)],
        "walk:mid": [pose_stand(leg_phase=p, tail_tip=(2.0, 20.0), collar=collar)
                     for p in range(4)],
        "walk:low": [pose_stand(leg_phase=p, tail_tip=(4.0, 33.0), collar=collar)
                     for p in range(4)],
    }


def _build(collar: bool = False, stage: int = 6) -> dict[str, list[list[str]]]:
    """Build the full animation table with a growth stage's proportions (P47).
    The default stage 6 is the identity transform = the classic adult art."""
    global _PROFILE
    old = _PROFILE
    _PROFILE = stage_profile(stage)
    try:
        return _build_table(collar)
    finally:
        _PROFILE = old


SPRITES: dict[str, list[list[str]]] = _build(collar=False)
_COLLARED = _build(collar=True)


def _diff_layers(base: dict, collared: dict) -> dict[str, list[list[str]]]:
    """Accessory overlay matrices: only the pixels that the collar adds."""
    out: dict[str, list[list[str]]] = {}
    for state, frames in base.items():
        out[state] = []
        for bf, cf in zip(frames, collared[state]):
            out[state].append([
                "".join(c2 if c2 != c1 else "." for c1, c2 in zip(r1, r2))
                for r1, r2 in zip(bf, cf)
            ])
    return out


ACCESSORIES: dict[str, list[list[str]]] = _diff_layers(SPRITES, _COLLARED)

# Per-stage tables, built and cached on first use (P47). Stage 6 is served
# from the shared SPRITES/ACCESSORIES above (byte-identical legacy art).
_SPRITES_BY_STAGE: dict[int, dict[str, list[list[str]]]] = {}
_ACCESSORIES_BY_STAGE: dict[int, dict[str, list[list[str]]]] = {}


def sprites_for(stage: int) -> dict[str, list[list[str]]]:
    """The animation table for a growth stage (0-15)."""
    s = min(max(int(stage), 0), STAGES - 1)
    if s == 6:
        return SPRITES
    if s not in _SPRITES_BY_STAGE:
        base = _build(collar=False, stage=s)
        _SPRITES_BY_STAGE[s] = base
        _ACCESSORIES_BY_STAGE[s] = _diff_layers(base, _build(collar=True, stage=s))
    return _SPRITES_BY_STAGE[s]


def accessories_for(stage: int) -> dict[str, list[list[str]]]:
    """The collar diff layers for a growth stage (0-15)."""
    s = min(max(int(stage), 0), STAGES - 1)
    if s == 6:
        return ACCESSORIES
    sprites_for(s)  # builds both caches
    return _ACCESSORIES_BY_STAGE[s]


# ---------------------------------------------------------------------------
# Patterns (customization): rewrite fur pixels after building
# ---------------------------------------------------------------------------

def apply_pattern(frame: list[str], pattern: str) -> list[str]:
    """pattern: 'solid' | 'tabby' | 'tuxedo' | 'spots' | 'tortie'.
    Rewrites 'f' cells."""
    if pattern == "solid":
        return frame
    grid = [list(row) for row in frame]
    rows_with_f = [y for y, row in enumerate(grid) if "f" in row]
    if not rows_with_f:
        return frame
    y_top, y_bot = min(rows_with_f), max(rows_with_f)
    span = max(y_bot - y_top, 1)
    for y in range(CANVAS_H):
        for x in range(CANVAS_W):
            if grid[y][x] != "f":
                continue
            rel_y = (y - y_top) / span
            if pattern == "tabby":
                if rel_y < 0.45 and x % 12 in (0, 1, 2):  # vertical stripes on the back
                    grid[y][x] = "F"
            elif pattern == "spots":
                if (x * 7 + y * 13) % 29 in (0, 1, 2, 3):  # deterministic pseudo-random spots
                    grid[y][x] = "F"
            elif pattern == "tortie":
                # tortoiseshell: big mottled shade patches (coarse cell noise)
                h = ((x // 10) * 31 + (y // 10) * 17) % 13
                if h < 5:
                    grid[y][x] = "F"
            elif pattern == "tuxedo":
                if rel_y > 0.6 or (rel_y > 0.4 and x > CANVAS_W * 0.6):  # belly+chest white
                    grid[y][x] = "b"
    return ["".join(r) for r in grid]


# ---------------------------------------------------------------------------
# Runtime helpers
# ---------------------------------------------------------------------------

def validate(table: dict[str, list[list[str]]] | None = None) -> None:
    for name, frames in (SPRITES if table is None else table).items():
        for frame in frames:
            assert len(frame) == CANVAS_H, f"{name}: {len(frame)} rows != {CANVAS_H}"
            for row in frame:
                assert len(row) == CANVAS_W, f"{name}: row {len(row)} != {CANVAS_W}: {row!r}"
                bad = set(row) - set(DEFAULT_PALETTE) - {"."}
                assert not bad, f"{name}: unknown chars {bad}"


def sprite_to_pixels(frame: list[str], palette: dict[str, tuple[int, int, int]]):
    """Return (width, height, flat RGBA list). Pure python, no Qt."""
    out = []
    for row in frame:
        for ch in row:
            if ch == ".":
                out.append((0, 0, 0, 0))
            else:
                r, g, b = palette[ch]
                out.append((r, g, b, 255))
    return CANVAS_W, CANVAS_H, out


def flip(frame: list[str]) -> list[str]:
    """Mirror horizontally (for facing left)."""
    return [row[::-1] for row in frame]
