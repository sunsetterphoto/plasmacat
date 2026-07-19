#!/usr/bin/env python
"""Widget-grab trail repro: while the cat walks with the real bridge, grab
the overlay widget's OWN backing store every second. If the widget content
is clean but the compositor output shows a trail, the problem is between
backing store and screen (downsampling); else it's our paint logic.
Usage: PYTHONPATH=src .venv/bin/python tools/trail_repro_grab.py <seconds>
"""
import sys
from pathlib import Path

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
    from PySide6.QtCore import QEventLoop, QTimer
    for i in range(6):
        body.walk_to(500.0 + (700.0 if i % 2 == 0 else -200.0), RUN_SPEED)
        loop = QEventLoop()
        QTimer.singleShot(1500, loop.quit)
        loop.exec()
        pm = o.grab()
        pm.save(f"/tmp/grab_{i}.png")
        o.furniture_layer.grab().save(f"/tmp/grabf_{i}.png")
        print("grabbed", i, body.x)
    bridge.stop()
    print("GRAB_DONE")


if __name__ == "__main__":
    main()
