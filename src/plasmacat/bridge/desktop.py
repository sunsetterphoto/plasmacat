"""Desktop world state: cursor, work area, and the platforms the cat can stand on.

Platforms are the work-area floor (screen minus panels, reported by the KWin
bridge via clientArea(WorkArea)) plus the top edges of visible normal windows.
Bogus micro-windows (DECISIONS.md D11) are filtered by size.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_WINDOW_W = 60   # ignore slivers and helper windows (D11)
MIN_WINDOW_H = 40
MIN_TOP_Y = 90      # ignore tops flush with the screen edge: the cat (~75 px
                    # tall) would render mostly off-screen up there


@dataclass(frozen=True)
class Platform:
    x0: float
    x1: float
    y: float          # top edge: the cat's feet rest at this y
    caption: str = ""
    floor: bool = False

    def contains_x(self, x: float, margin: float = 0.0) -> bool:
        return self.x0 - margin <= x <= self.x1 + margin


class DesktopState:
    def __init__(self, screen_w: int, screen_h: int) -> None:
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.work_area = (0, 0, screen_w, screen_h)  # x, y, w, h (pre-bridge default)
        self.cursor: tuple[int, int] = (-100, -100)
        self.cursor_active: bool = False   # moved within the last ~2 s (set by overlay)
        self.cursor_speed: float = 0.0     # px/s, from the overlay's CursorTracker
        self._windows: list[dict] = []
        self._extra: list[Platform] = []   # synthetic platforms (cat tree)
        self.platforms: list[Platform] = []
        self._rebuild_platforms()

    # -- work area ------------------------------------------------------------

    @property
    def floor_y(self) -> float:
        return self.work_area[1] + self.work_area[3]

    @property
    def floor_x0(self) -> float:
        return self.work_area[0]

    @property
    def floor_x1(self) -> float:
        return self.work_area[0] + self.work_area[2]

    def set_work_area(self, d: dict) -> None:
        wa = (float(d["x"]), float(d["y"]), float(d["w"]), float(d["h"]))
        if wa != self.work_area:
            self.work_area = wa
            self._rebuild_platforms()

    # -- inputs -----------------------------------------------------------------

    def set_cursor(self, x: int, y: int) -> None:
        self.cursor = (x, y)

    def set_windows(self, wins: list[dict]) -> None:
        self._windows = wins
        self._rebuild_platforms()

    def set_extra_platforms(self, plats: list[Platform]) -> None:
        """Synthetic platforms from furniture (big cat tree levels)."""
        self._extra = list(plats)
        self._rebuild_platforms()

    # -- platforms --------------------------------------------------------------

    def _rebuild_platforms(self) -> None:
        plats = [Platform(self.floor_x0, self.floor_x1, self.floor_y, "floor", True)]
        wins = [w for w in self._windows
                if w["w"] >= MIN_WINDOW_W and w["h"] >= MIN_WINDOW_H and w["y"] >= MIN_TOP_Y]
        # stacking order: later windows cover earlier ones (KWin stackingOrder)
        for i, w in enumerate(wins):
            above = [a for a in wins[i + 1:]
                     if a["y"] <= w["y"] <= a["y"] + a["h"]]
            for x0, x1 in self._visible_segments(w, above):
                plats.append(Platform(x0, x1, w["y"], w.get("caption", "")))
        plats.extend(self._extra)
        # Highest surfaces first makes landing checks natural.
        plats.sort(key=lambda p: p.y)
        self.platforms = plats

    @staticmethod
    def _visible_segments(w: dict, above: list[dict]) -> list[tuple[float, float]]:
        """The parts of w's top edge not covered by windows above it
        (P16: a background window is jumpable only along its visible edge)."""
        segs = [(float(w["x"]), float(w["x"] + w["w"]))]
        for a in above:
            ax0, ax1 = float(a["x"]), float(a["x"] + a["w"])
            rest = []
            for s0, s1 in segs:
                if ax1 <= s0 or ax0 >= s1:
                    rest.append((s0, s1))
                else:
                    if s0 < ax0:
                        rest.append((s0, ax0))
                    if ax1 < s1:
                        rest.append((ax1, s1))
            segs = rest
        return [(s0, s1) for s0, s1 in segs if s1 - s0 >= 30.0]

    def find_platform(self, ref: Platform) -> Platform | None:
        """The current platform matching a stale reference (window moved):
        same kind, nearest position."""
        best: Platform | None = None
        best_d = 1e18
        for p in self.platforms:
            if p.floor != ref.floor:
                continue
            if not ref.floor and p.caption != ref.caption:
                continue
            d = (p.x0 - ref.x0) ** 2 + (p.y - ref.y) ** 2
            if d < best_d:
                best, best_d = p, d
        return best

    def platform_below(self, x: float, y: float) -> Platform:
        """The platform the cat at (x, y) would land on: highest top edge that
        is at or below y and spans x. The floor always matches."""
        best = self.platforms[-1]  # floor (largest y after sorting)
        for p in self.platforms:
            if p.y >= y and p.contains_x(x) and p.y < best.y:
                best = p
        return best
