"""Fullscreen desktop-level layer per screen: furniture, bowls, floor toys, status board."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from plasmacat.world.overlay import Overlay


class FurnitureLayer(QWidget):
    """Desktop-level layer rendered BEHIND all windows (keepBelow, tagged by
    the bridge via its window title): bowls and static furniture. One instance
    per screen (P38), each showing the world slice of its screen. Repainted
    only when its content changes."""

    def __init__(self, overlay: "Overlay", screen, parent=None) -> None:
        super().__init__(parent)
        self.o = overlay
        self._ox = screen.geometry().x()   # the screen's world position (P38)
        self._oy = screen.geometry().y()
        self.setWindowTitle("plasmacat-furniture")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.winId()  # realize so windowHandle() exists for setScreen
        if self.windowHandle() is not None:
            self.windowHandle().setScreen(screen)
        self.showFullScreen()

    def refresh(self) -> None:
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        o = self.o
        p = QPainter(self)
        # P30: an exception mid-paint leaves Qt's painter active and wedges
        # the Wayland backing store (observed: SIGSEGV in finalizeBackBuffer
        # after the out-of-world toy OverflowErrors). finally: always end it.
        try:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(event.rect(), QColor(0, 0, 0, 0))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            # everything below is drawn in world coordinates, translated by
            # this screen's world position (P38)
            p.translate(-self._ox, -self._oy)
            region = event.rect().translated(self._ox, self._oy)
            # 1. static furniture (bowls, post, tree, bed, grass, litter, box…)
            for name, x in ((n, fx) for fx, n in o._floor_props()):
                br = o._bowl_rect(x, name)
                if region.intersects(br):
                    p.drawPixmap(br.x(), br.y(), o._props[name])
            # 1b. floating wall shelves (P25): fixed to the 'wall', any height
            for sr in o._shelf_rects():
                if region.intersects(sr):
                    p.drawPixmap(sr.x(), sr.y(), o._props["wall_shelf"])
            # 1c. litter deposits (P40): every poop/pee visible in the tray
            for dr, kind in o._litter_deposit_rects():
                if region.intersects(dr):
                    pm = o._props["litter_poop" if kind == "poop" else "litter_pee"]
                    p.drawPixmap(dr.x(), dr.y(), pm)
            # 1d. floor toys (ball/plush/…): desktop level like the furniture
            # they rest on. Only cursor tools + carried toys stay front (P42).
            for toy in o.toys.toys:
                if o._toy_front(toy):
                    continue
                if not (math.isfinite(toy.x) and math.isfinite(toy.y)) \
                        or abs(toy.x) > 10000 or abs(toy.y) > 10000:
                    continue
                pm = o._props[toy.kind]
                tr = QRect(int(toy.x) - pm.width() // 2,
                           int(toy.y) - pm.height(), pm.width(), pm.height())
                if region.intersects(tr):
                    p.drawPixmap(tr.x(), tr.y(), pm)
            # 2. exercise wheel: static stand, then rim rotating around the axle —
            #    the full illusion lives on THIS layer (P23)
            if o.cat.brain.wheel_x is not None:
                wr = o._wheel_rect()
                if region.intersects(wr):
                    cxm = wr.x() + 32 * o.prop_scale   # rim center (canvas 32,34)
                    cym = wr.y() + 34 * o.prop_scale
                    p.drawPixmap(wr.x(), wr.y(), o._props["wheel_stand"])
                    p.save()
                    p.translate(cxm, cym)
                    # clockwise (positive in Qt's y-down space): the bottom
                    # surface moves left, matching the right-facing runner
                    # (was counterclockwise = visibly backwards, P46)
                    p.rotate(o._wheel_angle)
                    p.translate(-cxm, -cym)
                    p.drawPixmap(wr.x(), wr.y(), o._props["wheel_rim"])
                    p.restore()
            # 3. the cats that have "stepped back" to this level (P47: loop)
            for cat in o.cats:
                if o.cat_layer(cat) != "back":
                    continue
                frame, acc, cr, br_b, bubble = o.current_cat(cat)
                p.drawPixmap(cr.x(), cr.y(), frame)
                if acc is not None:
                    p.drawPixmap(cr.x(), cr.y(), acc)
                if bubble:
                    p.drawPixmap(br_b.x(), br_b.y(), o._props[bubble])
            # 4. wheel front arc / box front wall over the cat (inside illusion)
            if o.cat.brain.wheel_x is not None:
                wr = o._wheel_rect()
                if region.intersects(wr):
                    p.drawPixmap(wr.x(), wr.y(), o._props["wheel_front"])
            if o.cat.brain.box_x is not None:
                br2 = o._box_rect()
                if region.intersects(br2):
                    p.drawPixmap(br2.x(), br2.y(), o._props["box_front"])
            # 6. the pinned status board (P42): display-only panel
            sr = o._status_rect()
            if not sr.isNull() and region.intersects(sr):
                o._paint_status(p)
        except Exception as exc:
            print(f"[paint] furniture layer error: {exc!r}")
        finally:
            p.end()
