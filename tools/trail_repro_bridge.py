#!/usr/bin/env python
"""Real-bridge trail repro: the cat walks back and forth with the actual KWin
bridge streaming windows/work-area (the difference vs the FakeBridge repro).
Usage: PYTHONPATH=src .venv/bin/python tools/trail_repro_bridge.py <seconds>
"""
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from plasmacat.bridge.kwin import KWinBridge
from plasmacat.cat.physics import WALK_SPEED
from plasmacat.overlay import Overlay

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    app = QApplication(sys.argv)
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 14.0
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
    brain.state_left = secs + 60.0
    steps = int(secs / 3.0)
    direction = 1
    for i in range(steps):
        target = 500.0 + direction * 700.0
        body.walk_to(target, WALK_SPEED)   # WALK speed like the real trail
        direction = -direction
        from PySide6.QtCore import QEventLoop, QTimer
        loop = QEventLoop()
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
    bridge.stop()
    print("REPRO_BRIDGE_DONE")


if __name__ == "__main__":
    main()
