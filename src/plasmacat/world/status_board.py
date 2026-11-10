"""The pinned status board painted on the furniture layer (display-only, P42)."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen

STATUS_W = 250
STATUS_H = 32 + 8 * 17 + 8  # title + 8 bar rows + bottom margin


class StatusBoardMixin:
    """Mixed into Overlay; uses its state (self.desktop, self.cats, …)."""

    def _status_rect(self) -> QRect:
        """World-coords rect of the pinned status board — null when disabled.
        Without a placed position it defaults to bottom-left over the panel."""
        if not self.cust.status_window:
            return QRect()
        pos = self.cust.status_pos
        if pos is None:
            return QRect(int(self.desktop.floor_x0 + 40),
                         int(self.desktop.floor_y - STATUS_H - 40),
                         STATUS_W, STATUS_H)
        return QRect(int(pos[0]), int(pos[1]), STATUS_W, STATUS_H)
    def _status_sig(self) -> tuple:
        """Everything the status board shows (rounded) — repaint on change."""
        if not self.cust.status_window:
            return ()
        b = self.active.brain
        r = self._status_rect()
        return (tuple(round(v) for v in b.needs.values()), round(b.food_fill),
                round(b.litter_fill), len(b.litter_deposits),
                round(b.attachment_xp), b.attachment_level, self.active.cust.name,
                round(b.age, 1), r.x(), r.y())
    def _paint_status(self, p: QPainter) -> None:
        """Draw the board (world coords; the painter is already translated).
        Pure QPainter, display-only: the FurnitureLayer is click-through, so
        the care actions (treat/refill/clean) stay in the tray menu. Shows
        the ACTIVE cat (nearest the cursor, P47)."""
        brain = self.active.brain
        sr = self._status_rect()
        x, y = sr.x(), sr.y()
        p.setPen(QPen(QColor(80, 80, 96, 220), 1))
        p.setBrush(QColor(20, 20, 26, 205))
        p.drawRoundedRect(sr, 8.0, 8.0)
        font = p.font()
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(240, 240, 240))
        p.drawText(x + 12, y + 20,
                   f"{self.active.cust.name} — {brain.life_stage} — "
                   f"{brain.attachment_name} ({int(brain.attachment_xp)} XP)")
        font.setBold(False)
        p.setFont(font)
        rows = [(label, brain.needs[key]) for key, label in
                (("hunger", "Food"), ("thirst", "Water"), ("energy", "Energy"),
                 ("play", "Play"), ("affection", "Affection"),
                 ("bladder", "Litter"))]
        rows.append(("Food bowl", brain.food_fill))
        rows.append((f"Litter box ({len(brain.litter_deposits)})",
                     brain.litter_fill / 5 * 100))
        ry = y + 32
        for label, value in rows:
            p.setPen(QColor(200, 200, 210))
            p.drawText(x + 12, ry + 9, label)
            bx = x + 112
            bw = STATUS_W - 112 - 12
            v = min(max(value, 0.0), 100.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(60, 60, 72, 220))
            p.drawRoundedRect(bx, ry, bw, 10, 4.0, 4.0)
            if v > 0:
                p.setBrush(QColor(90, 200, 90) if v > 50
                           else QColor(230, 180, 60) if v > 25
                           else QColor(220, 80, 70))
                p.drawRoundedRect(bx, ry, max(4, int(bw * v / 100)), 10, 4.0, 4.0)
            ry += 17
    def set_status_window(self, on: bool) -> None:
        """Tray toggle: the pinned status board on the desktop level (P42) —
        painted on the FurnitureLayer behind windows, click-through. (Was a
        real tool window in P39; it could be minimized and get lost.)"""
        self.cust.status_window = on
        self._last_status_sig = ()     # force a repaint of the new state
        self._furn_update_all()
        act = getattr(self, "_status_action", None)
        if act is not None and act.isChecked() != on:
            act.setChecked(on)
