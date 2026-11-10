"""Coat patterns: rewrite the fur cells of a finished sprite frame.

Patterns are organic but deterministic (hash-based noise on grid
coordinates), so a cat keeps the same markings in every frame and session:
  solid   plain fur
  tabby   stripes that follow the back line (depth below the silhouette top)
  spots   round patches on a jittered lattice
  tortie  smooth two-tone mottling (value noise, two octaves)
  tuxedo  white bib, belly and socks with a soft wavy border
Pure python, no Qt.
"""

from __future__ import annotations

import math

PATTERNS = ("solid", "tabby", "tuxedo", "spots", "tortie")


def _hash(x: int, y: int, seed: int) -> float:
    """Deterministic pseudo-random value in [0, 1) for a lattice point."""
    h = (x * 374761393 + y * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65536.0


def _noise(x: float, y: float, cell: float, seed: int) -> float:
    """Smooth value noise in [0, 1): bilinear lattice values, smoothstep."""
    fx, fy = x / cell, y / cell
    x0, y0 = math.floor(fx), math.floor(fy)
    tx, ty = fx - x0, fy - y0
    tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
    a, b = _hash(x0, y0, seed), _hash(x0 + 1, y0, seed)
    c, d = _hash(x0, y0 + 1, seed), _hash(x0 + 1, y0 + 1, seed)
    return (a + (b - a) * tx) * (1 - ty) + (c + (d - c) * tx) * ty


def _spot(x: int, y: int, cell: int = 11) -> bool:
    """Inside one of the round spots scattered on a jittered lattice."""
    cx, cy = x // cell, y // cell
    for gx in (cx - 1, cx, cx + 1):
        for gy in (cy - 1, cy, cy + 1):
            if _hash(gx, gy, 7) < 0.25:
                continue  # an empty lattice cell: irregular spacing
            sx = gx * cell + 2 + _hash(gx, gy, 3) * (cell - 4)
            sy = gy * cell + 2 + _hash(gx, gy, 5) * (cell - 4)
            r = 2.0 + _hash(gx, gy, 9) * 1.8
            if (x - sx) ** 2 + ((y - sy) * 1.15) ** 2 <= r * r:
                return True
    return False


def _distance_to(grid: list[list[str]], chars: str) -> list[list[float]]:
    """Chamfer distance (in cells) of every cell to the nearest cell whose
    char is in chars: the tuxedo white grows out of the belly patch, so it
    fits every pose."""
    h, w = len(grid), len(grid[0])
    inf = 1e9
    d = [[0.0 if grid[y][x] in chars else inf for x in range(w)] for y in range(h)]
    for y in range(h):
        for x in range(w):
            v = d[y][x]
            if x > 0: v = min(v, d[y][x - 1] + 1)
            if y > 0:
                v = min(v, d[y - 1][x] + 1)
                if x > 0: v = min(v, d[y - 1][x - 1] + 1.414)
                if x < w - 1: v = min(v, d[y - 1][x + 1] + 1.414)
            d[y][x] = v
    for y in range(h - 1, -1, -1):
        for x in range(w - 1, -1, -1):
            v = d[y][x]
            if x < w - 1: v = min(v, d[y][x + 1] + 1)
            if y < h - 1:
                v = min(v, d[y + 1][x] + 1)
                if x < w - 1: v = min(v, d[y + 1][x + 1] + 1.414)
                if x > 0: v = min(v, d[y + 1][x - 1] + 1.414)
            d[y][x] = v
    return d


def apply_pattern(frame: list[str], pattern: str) -> list[str]:
    """Return a copy of frame with the pattern applied to its 'f' cells."""
    if pattern == "solid":
        return frame
    grid = [list(row) for row in frame]
    h, w = len(grid), len(grid[0]) if grid else 0
    rows_with_f = [y for y, row in enumerate(grid) if "f" in row]
    if not rows_with_f:
        return frame
    y_top, y_bot = min(rows_with_f), max(rows_with_f)
    span = max(y_bot - y_top, 1)
    # silhouette top per column: stripes follow the back line
    tops = [next((y for y in range(h) if grid[y][x] != "."), h) for x in range(w)]
    bib_dist = _distance_to(grid, "b") if pattern == "tuxedo" else None
    for y in range(h):
        row = grid[y]
        for x in range(w):
            if row[x] != "f":
                continue
            rel_y = (y - y_top) / span
            if pattern == "tabby":
                depth = y - tops[x]
                if 1 <= depth <= 3:
                    row[x] = "F"                     # dark line along the spine
                elif depth < span * 0.6:
                    phase = (x + depth * 0.35) / 11.0 + 0.10 * _noise(x, y, 6.0, 4)
                    if phase % 1.0 < 0.34:
                        row[x] = "F"                 # mackerel stripes down the flanks
            elif pattern == "spots":
                if _spot(x, y):
                    row[x] = "F"
            elif pattern == "tortie":
                n = 0.65 * _noise(x, y, 13.0, 1) + 0.35 * _noise(x, y, 5.0, 2)
                if n > 0.72:
                    row[x] = "D"
                elif n > 0.55:
                    row[x] = "F"
            elif pattern == "tuxedo":
                reach = 6.0 + 4.0 * _noise(x, y, 5.0, 6)
                if bib_dist[y][x] <= reach or y >= h - 4:
                    row[x] = "b"                     # bib, belly, chin and socks
    return ["".join(r) for r in grid]
