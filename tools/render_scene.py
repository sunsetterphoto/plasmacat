#!/usr/bin/env python3
"""Render a promo scene (furniture + cats on a neutral backdrop) for the README.

Usage: PYTHONPATH=src python3 tools/render_scene.py [--out docs/screenshot.png]
Headless (offscreen + fake bridge): no real desktop, nothing private in it.
"""

from __future__ import annotations

import argparse
import os
import random
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

W, H = 1400, 560
FLOOR = H - 40


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/screenshot.png")
    args = ap.parse_args()
    app = QApplication([])  # noqa: F841
    from plasmacat.bridge.kwin import FakeBridge
    from plasmacat.persist import Customization, Settings
    from plasmacat.world.overlay import Overlay

    bridge = FakeBridge()
    ov = Overlay(bridge, cust=Customization(name="Minka"), settings=Settings())
    bridge.workAreasChanged.emit([{"x": 0, "y": 0, "w": W, "h": FLOOR}])
    b = ov.cat.brain
    b.food_x, b.water_x = 90.0, 190.0
    b.scratch_x, b.bed_x, b.litter_x = 330.0, 560.0, 1290.0
    b.tree_x, b.grass_x = 1110.0, 450.0
    b.shelves[:] = [(800.0, 250.0)]
    ov._sync_furniture_platforms()
    luna = ov.add_cat(Customization(name="Luna", fur=(60, 60, 70), pattern="tuxedo",
                                    eye=(240, 200, 80)), age=6.0)
    kiki = ov.add_cat(Customization(name="Kiki", fur=(160, 160, 170), pattern="tabby",
                                    collar=(200, 60, 80)), age=1.0)
    ov.toys.spawn("ball", 700.0, float(FLOOR))
    # pose the cats: Minka on the shelf, Luna sitting on the tree top, Kiki walking
    for cat, x, y, state in ((ov.cat, 800.0, 250.0, "sit"), (luna, 1126.0, FLOOR - 192.0, "loaf"),
                             (kiki, 640.0, float(FLOOR), "stand")):
        cat.body.x, cat.body.y, cat.body.airborne = x, y, False
        cat.body.platform = ov.desktop.platform_below(x, y - 1)
        cat.brain.state, cat.brain.state_left = state, 999.0
        cat.brain.rng = random.Random(1)
    kiki.body.facing = 1
    for _ in range(3):
        ov._clock.restart()
        time.sleep(0.01)
        ov._tick()

    img = QImage(W, H, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    g = QLinearGradient(0, 0, 0, H)
    g.setColorAt(0.0, QColor(46, 52, 78))
    g.setColorAt(1.0, QColor(96, 70, 112))
    p.fillRect(0, 0, W, H, g)
    p.fillRect(0, FLOOR, W, H - FLOOR, QColor(28, 30, 40))      # a panel
    layer = ov.furniture_layers[0]
    layer.resize(W, H)
    p.drawPixmap(0, 0, layer.grab())
    ov.resize(W, H)
    ov.move(0, 0)
    ov._origin = lambda: (0, 0)
    p.drawPixmap(QPoint(0, 0), ov.grab())
    p.end()
    img.save(args.out)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
