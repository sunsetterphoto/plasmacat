"""Cursor interaction detection: petting, head-rubs and hunt triggers.

The overlay feeds the global cursor stream (from the KWin bridge) into a
CursorTracker; the InteractionDetector interprets it relative to the cat:

- petting: cursor inside the cat's body rect moving back and forth (strokes)
- head-rub: cursor lingering/gentle in the head zone
- hunt trigger: fast, erratic cursor movement near an idle cat

Pure python, no Qt.
"""

from __future__ import annotations

import time
from collections import deque

# cursor speed thresholds (px/s)
PET_MIN_SPEED = 10.0
PET_MAX_SPEED = 700.0
HUNT_SPEED = 700.0
HUNT_RANGE = 650.0
RUB_MAX_SPEED = 120.0
PAT_RANGE = 170.0        # cursor hovering near her face teases a paw bat (P26)
PAT_MIN_SPEED = 20.0
PAT_MAX_SPEED = 250.0


class CursorTracker:
    def __init__(self, history_s: float = 0.6) -> None:
        self.hist: deque[tuple[float, float, float]] = deque()  # (t, x, y)
        self.history_s = history_s
        self.last_move_t = 0.0

    def add(self, x: float, y: float, t: float | None = None) -> None:
        t = time.monotonic() if t is None else t
        if self.hist and (x, y) == (self.hist[-1][1], self.hist[-1][2]):
            return
        self.hist.append((t, x, y))
        self.last_move_t = t
        while self.hist and self.hist[0][0] < t - self.history_s:
            self.hist.popleft()

    def idle_for(self, t: float | None = None) -> float:
        t = time.monotonic() if t is None else t
        return t - self.last_move_t if self.last_move_t else 1e9

    def speed(self) -> float:
        """Mean cursor speed (px/s) over the tracked window."""
        if len(self.hist) < 2:
            return 0.0
        dist = 0.0
        for (t0, x0, y0), (t1, x1, y1) in zip(self.hist, list(self.hist)[1:]):
            dist += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        span = self.hist[-1][0] - self.hist[0][0]
        return dist / span if span > 0 else 0.0

    def reversals(self) -> int:
        """Dominant-axis direction reversals in the window (stroke/erratic count)."""
        if len(self.hist) < 3:
            return 0
        pts = [(x, y) for _, x, y in self.hist]
        dx_total = abs(pts[-1][0] - pts[0][0])
        dy_total = abs(pts[-1][1] - pts[0][1])
        axis = 0 if dx_total >= dy_total else 1
        rev = 0
        prev_sign = 0
        for a, b in zip(pts, pts[1:]):
            d = b[axis] - a[axis]
            sign = (d > 2) - (d < -2)
            if sign and prev_sign and sign != prev_sign:
                rev += 1
            if sign:
                prev_sign = sign
        return rev


class InteractionDetector:
    """Emits high-level events by inspecting cursor vs. cat each frame."""

    def __init__(self) -> None:
        self.tracker = CursorTracker()
        self._stroke_cooldown = 0.0
        self._last_reversals = 0
        self._rub_t = 0.0
        self._pat_cd = 0.0             # paw-bat tease cooldown (P26)
        self._path_inside = 0.0        # petting path accumulator
        self._last_pos: tuple[float, float] | None = None
        self._dist_hist: deque[tuple[float, float]] = deque()  # (t, dist to cat)

    def tick(self, dt: float, cat_rect: tuple[float, float, float, float],
             cursor: tuple[float, float]):
        """Returns a list of events: 'stroke', 'rub', 'hunt', 'startle', 'pat'."""
        events: list[str] = []
        self._stroke_cooldown = max(0.0, self._stroke_cooldown - dt)
        self._pat_cd = max(0.0, self._pat_cd - dt)
        cx, cy = cursor
        rx, ry, rw, rh = cat_rect
        inside = rx <= cx <= rx + rw and ry <= cy <= ry + rh
        speed = self.tracker.speed()

        # startle detection: fast approach toward the cat
        cat_cx, cat_cy = rx + rw / 2, ry + rh / 2
        dist = ((cx - cat_cx) ** 2 + (cy - cat_cy) ** 2) ** 0.5
        t_now = self.tracker.hist[-1][0] if self.tracker.hist else 0.0
        self._dist_hist.append((t_now, dist))
        while self._dist_hist and self._dist_hist[0][0] < t_now - 0.4:
            self._dist_hist.popleft()
        if speed > 900.0 and len(self._dist_hist) >= 2 and dist < 250.0:
            d0 = self._dist_hist[0][1]
            if d0 - dist > 100.0:
                events.append("startle")

        if inside:
            if self._last_pos is not None:
                self._path_inside += ((cx - self._last_pos[0]) ** 2
                                      + (cy - self._last_pos[1]) ** 2) ** 0.5
            # head zone: front 45% (in facing direction — rect is already
            # facing-agnostic here; use upper part), upper 55%
            head = ry + rh * 0.45 >= cy
            if head and speed < RUB_MAX_SPEED:
                self._rub_t += dt
                if self._rub_t > 0.7:
                    events.append("rub")
                    self._rub_t = 0.0
            else:
                self._rub_t = 0.0
            # stroke: either ~110 px of petting motion, or a fresh reversal
            rev = self.tracker.reversals()
            in_pet_range = PET_MIN_SPEED < speed < PET_MAX_SPEED
            stroke_by_path = in_pet_range and self._path_inside > 110.0
            stroke_by_rev = in_pet_range and rev > self._last_reversals
            if (stroke_by_path or stroke_by_rev) and self._stroke_cooldown <= 0:
                events.append("stroke")
                self._stroke_cooldown = 0.3
                self._path_inside = 0.0
            self._last_reversals = rev
        else:
            self._last_reversals = 0
            self._rub_t = 0.0
            self._path_inside = 0.0
            self._last_pos = None
            cat_cx = rx + rw / 2
            if (speed > HUNT_SPEED and self.tracker.reversals() >= 2
                    and abs(cx - cat_cx) < HUNT_RANGE):
                events.append("hunt")
            # teasing cursor right in front of her face -> paw bat (P26)
            if (self._pat_cd <= 0 and PAT_MIN_SPEED < speed < PAT_MAX_SPEED
                    and dist < PAT_RANGE and cy < ry + rh * 0.6):
                events.append("pat")
                self._pat_cd = 4.0
            return events
        self._last_pos = (cx, cy)
        return events
