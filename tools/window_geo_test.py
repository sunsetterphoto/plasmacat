#!/usr/bin/env python
"""Offscreen test for the P37 small-window logic: content bounds, geometry
sync (recenter/shrink), and the placement-mode fullscreen round trip.
Run: QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python tools/window_geo_test.py
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from plasmacat.overlay import Overlay, WIN_MIN_W, WIN_MIN_H


class FakeBridge(QObject):
    cursorChanged = Signal(int, int)
    windowsChanged = Signal(list)
    workAreaChanged = Signal(dict)
    workAreasChanged = Signal(list)
    keyEvent = Signal(str)

    def set_control_mode(self, on: bool) -> None:
        self.control_mode = on


def main() -> None:
    app = QApplication([])
    o = Overlay(FakeBridge(), debug=False)
    app.processEvents()

    # 1. starts small, title carries the encoded rect
    assert not o.isFullScreen(), "must not start fullscreen"
    assert o.windowTitle().startswith("plasmacat@"), o.windowTitle()
    assert o.width() >= WIN_MIN_W and o.height() >= WIN_MIN_H

    # 2. window follows when the cat teleports away
    far = o.desktop.screen_w - 100.0
    o.cat.body.x = far
    o._sync_window_geometry()
    app.processEvents()
    assert o._win_x + o.width() >= far, (o._win_x, o.width(), far)

    # 3. P42 layer rule: a resting ball lives on the BACK layer and must NOT
    # stretch the front window; front toys (string/laser/carried) still do
    o.toys.spawn("ball", 200.0, 900.0)
    b = o._front_bounds()
    assert b.x() > 200 - 20, ("floor toy must stay out of front bounds", b)
    assert b.x() <= far and b.right() >= far - 20, b
    o.toys.spawn("string", 300.0, 800.0)
    b = o._front_bounds()
    assert b.x() <= 300 - 20, ("cursor tool must be covered", b)
    o.clear_toys()
    assert not o.toys.toys

    # 4. shrink after the delay: cat back to a compact spot, no toys
    o.clear_toys()
    o.cat.body.x = 800.0
    o._sync_window_geometry()
    first_w = o.width()
    o._shrink_since = o._time - 99.0   # pretend the delay already passed
    o._sync_window_geometry()
    assert o.width() <= first_w, (first_w, o.width())

    # 5. placement round trip: fullscreen while placing, small after
    o.begin_placement("ball")
    app.processEvents()
    assert o._placing == "ball"
    assert o.windowTitle() == "plasmacat", o.windowTitle()
    assert o.isFullScreen(), "placement needs the fullscreen window"
    from PySide6.QtCore import Qt
    assert not (o.windowFlags() & Qt.WindowType.WindowTransparentForInput)
    o._end_placement()
    app.processEvents()
    assert o._placing is None
    assert not o.isFullScreen(), "must return to the small window"
    assert o.windowTitle().startswith("plasmacat@"), o.windowTitle()
    assert o.windowFlags() & Qt.WindowType.WindowTransparentForInput

    # 6. P40: each litter deposit renders as one pile inside the tray
    o.cat.brain.litter_x = 400.0
    o.cat.brain.litter_deposits = ["poop", "pee", "poop"]
    rects = o._litter_deposit_rects()
    assert len(rects) == 3
    br = o._bowl_rect(400.0, "litter_0")
    for r, kind in rects:
        assert br.contains(r), (r, br)
        assert kind in ("poop", "pee")

    # 7. P42: pinned status board — toggle, default rect, placement round trip
    from plasmacat.overlay import STATUS_W, STATUS_H
    o.set_status_window(True)
    assert o.cust.status_window
    r = o._status_rect()
    assert not r.isNull() and r.width() == STATUS_W and r.height() == STATUS_H
    assert o._status_sig() != ()
    o.begin_placement("status")
    o.desktop.set_cursor(1000, 500)
    gr = o._ghost_rect()
    assert gr.width() == STATUS_W and abs(gr.center().x() - 1000) <= 1
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(1000, 500),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    o.mousePressEvent(ev)
    assert o._placing is None, "left click must end the placement"
    assert o.cust.status_pos is not None
    exp_x = min(max(1000 - STATUS_W // 2, o.desktop.floor_x0),
                o.desktop.floor_x1 - STATUS_W)
    assert abs(o.cust.status_pos[0] - exp_x) < 2, o.cust.status_pos
    o.set_status_window(False)
    assert not o.cust.status_window
    assert o._status_rect().isNull() and o._status_sig() == ()

    print("WINDOW_GEO_OK")


if __name__ == "__main__":
    main()
