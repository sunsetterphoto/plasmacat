#!/usr/bin/env python
"""Generate the PlasmaCat app icon from the procedural sprite art (so the
icon always matches the cat): the sit pose on a dark rounded tile, exported
in the standard hicolor sizes to assets/icons/.

Run: QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python tools/make_icon.py
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QRadialGradient
from PySide6.QtWidgets import QApplication

from plasmacat.cat.render import SpriteBank

SIZES = (256, 128, 64, 48, 32, 22, 16)
OUT = Path(__file__).resolve().parents[1] / "assets" / "icons"

# tile look: the status-board slate, lit softly from the top left
BG_TOP = QColor(52, 52, 68)
BG_BOTTOM = QColor(24, 24, 34)
CAT_RGBA = 0.78      # cat width as a fraction of the tile
RADIUS_RGBA = 0.22   # corner radius as a fraction of the tile


def render_icon(size: int, bank: SpriteBank) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # rounded squircle tile with a soft vertical light
    path = QPainterPath()
    path.addRoundedRect(0.5, 0.5, size - 1, size - 1,
                        size * RADIUS_RGBA, size * RADIUS_RGBA)
    grad = QRadialGradient(QPointF(size * 0.3, size * 0.2), size * 1.1)
    grad.setColorAt(0.0, BG_TOP)
    grad.setColorAt(1.0, BG_BOTTOM)
    p.fillPath(path, grad)
    # subtle lighter rim on the top edge
    p.setPen(QColor(255, 255, 255, 26))
    p.drawPath(path)

    # the cat: sit pose, nearest-neighbor upscale (crisp pixel art)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    frame = bank.frame("sit", 0)
    cw = int(size * CAT_RGBA)
    ch = int(cw * frame.height() / frame.width())
    x = (size - cw) // 2
    y = int(size * 0.88) - ch          # feet rest on a common base line
    p.setClipPath(path)
    p.drawPixmap(x, y, cw, ch, frame.scaled(cw, ch,
                                            Qt.AspectRatioMode.IgnoreAspectRatio,
                                            Qt.TransformationMode.FastTransformation))
    p.end()
    return img


def main() -> None:
    app = QApplication([])
    bank = SpriteBank(scale=8, facing="right")  # big source, crisp downscale
    OUT.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        img = render_icon(size, bank)
        target = OUT / f"plasmacat-{size}.png"
        img.save(str(target))
        print("wrote", target)


if __name__ == "__main__":
    main()
