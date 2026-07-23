#!/usr/bin/env python
"""Live wheel check: place the exercise wheel at a visible spot with a
FakeBridge, force the cat into wheel_run, and let the compositor show it.
Usage: PYTHONPATH=src .venv/bin/python tools/wheel_check.py <x> <seconds>
"""
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from plasmacat.overlay import Overlay


class FakeBridge(QObject):
    cursorChanged = Signal(int, int)
    windowsChanged = Signal(list)
    workAreaChanged = Signal(dict)
    workAreasChanged = Signal(list)


def main() -> None:
    app = QApplication(sys.argv)
    x = float(sys.argv[1]) if len(sys.argv) > 1 else 2000.0
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    o = Overlay(FakeBridge(), debug=False)
    brain = o.cat.brain
    body = o.cat.body
    brain.wheel_x = x
    o._sync_furniture_platforms()
    # drop her straight into the wheel run
    plat = next(p for p in o.desktop.platforms if p.caption == "Laufrad")
    body.platform = plat
    body.x, body.y = (plat.x0 + plat.x1) / 2, plat.y
    brain.state = "wheel_run"
    brain.state_left = secs
    brain._level = "back"
    brain._level_t = 0.0
    brain.needs["play"] = 50.0
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(int(secs * 1000), loop.quit)
    loop.exec()
    print("WHEEL_CHECK_DONE", "angle:", round(o._wheel_angle, 1),
                  "state:", brain.state, "anim:", o.cat.anim_state)


if __name__ == "__main__":
    main()
