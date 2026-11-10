#!/usr/bin/env python3
"""Render a sprite review sheet (poses x coat patterns x life stages) to PNG.

Usage: PYTHONPATH=src python3 tools/render_sheet.py [--out docs/sprites.png] [--px 2]
Qt only (offscreen), no extra dependencies.
"""

from __future__ import annotations

import argparse
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plasmacat.cat import sprites  # noqa: E402
from plasmacat.cat.render import SpriteBank, prop_pixmap  # noqa: E402
from plasmacat.persist import Customization  # noqa: E402

POSES = ["stand", "walk", "run", "sit", "loaf", "sleep", "groom", "crouch",
         "stretch", "yawn", "scratch", "alert"]
LOOKS = [
    ("solid", Customization()),
    ("tabby", Customization(fur=(160, 160, 170), pattern="tabby")),
    ("tuxedo", Customization(fur=(60, 60, 70), pattern="tuxedo", eye=(240, 200, 80))),
    ("spots", Customization(fur=(225, 210, 190), pattern="spots", eye=(100, 160, 240))),
    ("tortie", Customization(fur=(140, 90, 55), pattern="tortie", collar=(80, 120, 220))),
]
STAGES = [0, 3, 6, 13]
PROPS = ["food_bowl", "fountain_1", "scratch_post", "cat_bed", "cat_tree",
         "litter_0", "wheel_stand", "box", "wall_shelf", "ball", "plush", "cat_grass"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/sprites.png")
    ap.add_argument("--px", type=int, default=2, help="device px per grid cell")
    args = ap.parse_args()
    app = QApplication([])  # noqa: F841
    px = args.px
    cw, ch = sprites.GRID_W * px, sprites.GRID_H * px
    pad, label_h = 10, 22
    rows = len(LOOKS) + len(STAGES) + 1
    cols = len(POSES)
    img = QImage(pad + cols * (cw + pad), rows * (ch + pad + label_h) + 220,
                 QImage.Format.Format_ARGB32)
    img.fill(QColor(58, 60, 72))
    p = QPainter(img)
    p.setFont(QFont("sans", 10))
    p.setPen(QColor(220, 220, 230))
    y = pad
    for name, cust in LOOKS:              # every pose, each coat (adult)
        bank = SpriteBank(cust.to_palette(), cust.pattern, device_px=px,
                          accessory=cust.collar is not None)
        p.drawText(pad, y + 14, name)
        for i, pose in enumerate(POSES):
            x = pad + i * (cw + pad)
            p.drawPixmap(x, y + label_h, bank.frame(pose, 0))
            acc = bank.accessory_frame(pose, 0)
            if acc is not None:
                p.drawPixmap(x, y + label_h, acc)
        y += ch + pad + label_h
    for stage in STAGES:                  # growth stages (stand/sit/loaf/walk)
        bank = SpriteBank(Customization().to_palette(), "solid", device_px=px, stage=stage)
        p.drawText(pad, y + 14, f"stage {stage}")
        for i, pose in enumerate(["stand", "walk", "sit", "loaf", "sleep", "crouch"]):
            p.drawPixmap(pad + i * (cw + pad), y + label_h, bank.frame(pose, 0))
        y += ch + pad + label_h
    p.drawText(pad, y + 14, "props")
    x = pad
    for name in PROPS:
        pm = prop_pixmap(name, device_px=px - 1 if px > 1 else 1)
        p.drawPixmap(x, y + label_h, pm)
        x += pm.width() + pad
    p.end()
    img.save(args.out)
    print("wrote", args.out, img.width(), "x", img.height())


if __name__ == "__main__":
    main()
