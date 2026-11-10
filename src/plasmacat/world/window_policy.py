"""The small front window (P37): which rect it covers and when it moves or resizes."""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication

WIN_MIN_W = 240
WIN_MIN_H = 180
WIN_MARGIN = 24         # breathing room around the content bbox
WIN_SHRINK_DELAY = 5.0  # seconds of small content before the window shrinks
WIN_SHRINK_FRAC = 0.6   # … to below this fraction of the window size


class WindowPolicyMixin:
    """Mixed into Overlay; uses its state (self.desktop, self.cats, …)."""

    def _origin(self) -> tuple[int, int]:
        """World coords of the window's top-left corner. (0,0) while
        fullscreen (placement mode): the buffer then maps 1:1 to the world."""
        if self.isFullScreen():
            return (0, 0)
        return (self._win_x, self._win_y)
    def _front_bounds(self) -> QRect:
        """World-coords bounding rect of everything the front layer draws:
        the front-level cats, their bubbles, cat doors and the front toys
        (string/laser/carried — floor toys live on the back layer since P42),
        margin, minimum size."""
        r = QRect()
        for cat in self.cats:
            if self.cat_layer(cat) == "front":
                r = r.united(self._cat_rect(cat)).united(self._bubble_rect(cat))
            # doors are always front-window content, even mid-crossing (P27)
            r = r.united(self._door_rect(cat))
        for tr in self._toy_rects("front"):  # only front-layer content (P42)
            r = r.united(tr)
        if r.isNull():
            # every cat is on the back level: no front content — stay put
            return QRect(self._win_x, self._win_y, self.width(), self.height())
        r = r.adjusted(-WIN_MARGIN, -WIN_MARGIN, WIN_MARGIN, WIN_MARGIN)
        if r.width() < WIN_MIN_W:
            r.moveLeft(r.center().x() - WIN_MIN_W // 2)
            r.setWidth(WIN_MIN_W)
        if r.height() < WIN_MIN_H:
            r.moveTop(r.center().y() - WIN_MIN_H // 2)
            r.setHeight(WIN_MIN_H)
        return r
    def _sync_window_geometry(self, force: bool = False) -> None:
        """Keep the small front window covering all front-layer content.
        Wayland clients cannot self-position: the desired rect goes into the
        window title and the KWin script applies it (frameGeometry)."""
        if self._placing or self.isFullScreen():
            return
        need = self._front_bounds()
        cur = QRect(self._win_x, self._win_y, self.width(), self.height())
        new = QRect(cur)
        if force:
            new = need
        elif not cur.contains(need):
            if need.width() > cur.width() or need.height() > cur.height():
                # content bigger than the window (rare): grow + recenter
                new = QRect(0, 0, max(cur.width(), need.width()),
                            max(cur.height(), need.height()))
                new.moveCenter(need.center())
            else:
                # follow with the SMALLEST move that keeps the content inside
                # (P44): recentering used to snap the window by hundreds of
                # px, and since KWin applies the new position a frame later,
                # the cat visibly jumped while walking
                if need.left() < cur.left():
                    new.moveLeft(need.left())
                if need.right() > cur.right():
                    new.moveRight(need.right())
                if need.top() < cur.top():
                    new.moveTop(need.top())
                if need.bottom() > cur.bottom():
                    new.moveBottom(need.bottom())
        else:
            small = (need.width() < cur.width() * WIN_SHRINK_FRAC
                     and need.height() < cur.height() * WIN_SHRINK_FRAC)
            if small:
                if self._shrink_since is None:
                    self._shrink_since = self._time
                elif self._time - self._shrink_since >= WIN_SHRINK_DELAY:
                    new = need
            else:
                self._shrink_since = None
        vg = QRect()
        for s in QGuiApplication.screens():
            vg = vg.united(s.geometry())
        if new.width() >= vg.width() or new.height() >= vg.height():
            new = QRect(vg)
        else:
            new.moveLeft(min(max(new.x(), vg.x()),
                             vg.x() + vg.width() - new.width()))
            new.moveTop(min(max(new.y(), vg.y()),
                            vg.y() + vg.height() - new.height()))
        if new == cur:
            return
        self._shrink_since = None
        self._win_x, self._win_y = new.x(), new.y()
        if new.size() != self.size():
            self.resize(new.size())
        self.setWindowTitle(
            f"plasmacat@{new.x()},{new.y()},{new.width()},{new.height()}")
        self.update()  # content moved relative to the window
