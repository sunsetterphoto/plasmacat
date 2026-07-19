#!/usr/bin/env python
"""Trail repro with a forced FULL repaint every frame: if the trail stops
forming, KWin drops partial shm damage for the translucent overlay.
Usage: PYTHONPATH=src .venv/bin/python tools/trail_repro_full.py <seconds>
"""
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from plasmacat.bridge.kwin import KWinBridge
from plasmacat.cat.physics import RUN_SPEED
from plasmacat.overlay import Overlay

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    app = QApplication(sys.argv)
    bridge = KWinBridge(str(ROOT / "kwin" / "plasmacat-bridge.js"))
    if not bridge.start():
        print("bridge failed")
        return
    o = Overlay(bridge, debug=False)
    brain = o.cat.brain
    body = o.cat.body
    body.x = 500.0
    body.y = o.desktop.floor_y
    brain.state = "wander"
    brain.state_left = 999.0
    # force full-widget repaints at frame rate (workaround test)
    flush = QTimer(o)
    flush.timeout.connect(o.update)
    flush.start(33)
    from PySide6.QtCore import QEventLoop
    for i in range(6):
        body.walk_to(500.0 + (700.0 if i % 2 == 0 else -200.0), RUN_SPEED)
        loop = QEventLoop()
        QTimer.singleShot(1500, loop.quit)
        loop.exec()
        print("step", i, body.x)
    flush.stop()
    bridge.stop()
    print("FULL_REPRO_DONE")


if __name__ == "__main__":
    main()
