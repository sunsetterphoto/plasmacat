#!/usr/bin/env python
"""Repro test for repaint trails: run the real overlay on the live compositor
with the cat sprinting back and forth; screenshot externally and scan for
residue. Usage: PYTHONPATH=src .venv/bin/python tools/trail_repro.py <seconds>
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


def main() -> None:
    app = QApplication(sys.argv)
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    o = Overlay(FakeBridge(), debug=False)
    brain = o.cat.brain
    body = o.cat.body
    body.x = 400.0
    body.y = o.desktop.floor_y
    brain.state = "wander"
    brain.state_left = secs + 60.0   # keep the brain from re-choosing
    brain.needs["energy"] = 100.0

    steps = int(secs / 2.0)
    direction = 1
    for i in range(steps):
        target = 400.0 + direction * 900.0
        body.walk_to(target, RUN_SPEED)
        direction = -direction
        # let the real QTimer run for 2 s of wall time
        from PySide6.QtCore import QEventLoop, QTimer
        loop = QEventLoop()
        QTimer.singleShot(2000, loop.quit)
        loop.exec()
    print("REPRO_DONE")


if __name__ == "__main__":
    main()
