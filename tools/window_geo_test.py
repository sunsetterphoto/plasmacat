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

    # 3. a resting ball far from the cat must be covered too
    o.toys.spawn("ball", 200.0, 900.0)
    b = o._front_bounds()
    assert b.x() <= 200 - 20 and b.right() >= far - 20, b

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

    # 7. P39: status window toggle, refresh, buttons wired to the brain
    o.set_status_window(True)
    app.processEvents()
    assert o._status_win is not None and o.cust.status_window
    o.cat.brain.litter_fill = 3.0
    o._status_win.refresh()
    assert o._status_win.btn_litter.text() == "Clean litter (3)"
    o._status_win.btn_litter.click()
    assert o.cat.brain.litter_fill == 0.0 and not o.cat.brain.litter_deposits
    o.set_status_window(False)
    assert not o.cust.status_window

    print("WINDOW_GEO_OK")


if __name__ == "__main__":
    main()
