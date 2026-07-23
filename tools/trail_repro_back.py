#!/usr/bin/env python
"""Back-layer trail repro: cat walks back and forth on the furniture layer.
Usage: PYTHONPATH=src .venv/bin/python tools/trail_repro_back.py <seconds>
"""
import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from plasmacat.cat.physics import RUN_SPEED
from plasmacat.overlay import Overlay


class FakeBridge(QObject):
    cursorChanged = Signal(int, int)
    windowsChanged = Signal(list)
    workAreaChanged = Signal(dict)
    workAreasChanged = Signal(list)


def main() -> None:
    app = QApplication(sys.argv)
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    o = Overlay(FakeBridge(), debug=False)
    brain = o.cat.brain
    body = o.cat.body
    body.x = 400.0
    body.y = o.desktop.floor_y
    brain.food_x = 1300.0
    brain.state = "to_food"          # BACK layer while walking
    brain.state_left = secs + 60.0
    brain._level = "back"
    brain._level_t = 0.0
    steps = int(secs / 2.0)
    direction = 1
    for i in range(steps):
        target = 400.0 + direction * 900.0
        body.walk_to(target, RUN_SPEED)
        direction = -direction
        from PySide6.QtCore import QEventLoop, QTimer
        loop = QEventLoop()
        QTimer.singleShot(2000, loop.quit)
        loop.exec()
    print("REPRO_BACK_DONE", "level:", brain.level)


if __name__ == "__main__":
    main()
