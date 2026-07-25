#!/usr/bin/env python
"""Render all sprites to a PNG contact sheet for visual review.

Usage: PYTHONPATH=src .venv/bin/python tools/render_sheet.py [out.png]
"""
import sys
from pathlib import Path

from PIL import Image

from plasmacat.cat import sprites

SCALE = 5
PAD = 4
LABEL_H = 12  # pixels reserved under each sprite (no font rendering; just spacing)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/plasmacat_sheet.png")
    sprites.validate()

    entries = []
    if "--stages" in sys.argv:  # P47: one row of growth stages x key poses
        for s in range(sprites.STAGES):
            table = sprites.sprites_for(s)
            pal = sprites.aged_palette(dict(sprites.DEFAULT_PALETTE), s)
            for pose in ("sit", "stand", "walk", "sleep"):
                entries.append((f"s{s}/{pose}", table[pose][0], pal))
    else:
        for name, frames in sprites.SPRITES.items():
            for i, frame in enumerate(frames):
                entries.append((f"{name}[{i}]", frame, sprites.DEFAULT_PALETTE))

    # Customization variants of the stand pose: fur palettes x patterns.
    variants = {
        "grey":    {"f": (160, 160, 170), "F": (110, 110, 125)},
        "black":   {"f": (60, 60, 70), "F": (35, 35, 45), "e": (240, 200, 80)},
        "white":   {"f": (235, 230, 225), "F": (200, 190, 185), "o": (90, 80, 80)},
        "brown":   {"f": (140, 90, 55), "F": (95, 60, 35)},
        "siamese": {"f": (225, 210, 190), "F": (120, 90, 70), "e": (100, 160, 240)},
    }
    if "--stages" not in sys.argv:
        for pname, overrides in variants.items():
            pal = dict(sprites.DEFAULT_PALETTE)
            pal.update(overrides)
            for pattern in ("solid", "tabby", "tuxedo", "spots", "tortie"):
                mat = sprites.apply_pattern(sprites.SPRITES["stand"][0], pattern)
                entries.append((f"{pname}/{pattern}", mat, pal))

    cols = 8 if "--stages" in sys.argv else 6
    rows = (len(entries) + cols - 1) // cols
    cell_w = (sprites.CANVAS_W + PAD * 2) * SCALE
    cell_h = (sprites.CANVAS_H + PAD * 2) * SCALE + LABEL_H
    sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (60, 60, 70, 255))

    for idx, (name, frame, pal) in enumerate(entries):
        w, h, px = sprites.sprite_to_pixels(frame, pal)
        img = Image.new("RGBA", (w, h))
        img.putdata(px)
        img = img.resize((w * SCALE, h * SCALE), Image.NEAREST)
        cx = (idx % cols) * cell_w
        cy = (idx // cols) * cell_h
        sheet.paste(img, (cx + PAD * SCALE, cy + PAD * SCALE), img)
        print(f"cell {idx}: {name}")

    sheet.save(out)
    print("saved:", out)


if __name__ == "__main__":
    main()
