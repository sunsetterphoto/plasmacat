"""The pinned status board painted on the furniture layer (display-only, P42)."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen

STATUS_W = 250
STATUS_H = 32 + 8 * 17 + 8  # with all 8 rows: title + rows + bottom margin
ROW_H = 17
ROW_LABELS = (("hunger", "Food"), ("thirst", "Water"), ("energy", "Energy"),
              ("play", "Play"), ("affection", "Affection"), ("bladder", "Litter"),
              ("food_bowl", "Food bowl"), ("litter_box", "Litter box"))


class StatusBoardMixin:
    """Mixed into Overlay; uses its state (self.desktop, self.cats, …)."""

    def _status_rect(self) -> QRect:
        """World-coords rect of the pinned status board — null when disabled.
        Without a placed position it defaults to bottom-left over the panel."""
        if not self.settings.status_board:
            return QRect()
        h = self._status_h()
        pos = self.settings.status_pos
        if pos is None:
            return QRect(int(self.desktop.floor_x0 + 40),
                         int(self.desktop.floor_y - h - 40), STATUS_W, h)
        return QRect(int(pos[0]), int(pos[1]), STATUS_W, h)

    def _status_rows_shown(self) -> list[tuple[str, str]]:
        return [(k, label) for k, label in ROW_LABELS
                if self.settings.status_rows.get(k, True)]

    def _status_h(self) -> int:
        """Board height for the rows the user enabled (Home tab)."""
        return 32 + ROW_H * len(self._status_rows_shown()) + 8

    def _status_sig(self) -> tuple:
        """Everything the status board shows (rounded) — repaint on change."""
        if not self.settings.status_board:
            return ()
        b = self.active.brain
        r = self._status_rect()
        return (tuple(round(v) for v in b.needs.values()), round(b.food_fill),
                round(b.litter_fill), len(b.litter_deposits),
                round(b.attachment_xp), b.attachment_level, self.active.cust.name,
                round(b.age, 1), r.x(), r.y(), r.height())
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
        values = dict(brain.needs)
        values["food_bowl"] = brain.food_fill
        values["litter_box"] = brain.litter_fill / 5 * 100
        rows = [(f"{label} ({len(brain.litter_deposits)})" if key == "litter_box"
                 else label, values[key]) for key, label in self._status_rows_shown()]
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
            ry += ROW_H
    def set_status_board(self, on: bool) -> None:
        """The pinned status board on the desktop level (P42) — painted on
        the FurnitureLayer behind windows, click-through."""
        self.settings.status_board = on
        self.refresh_status_board()

    def refresh_status_board(self) -> None:
        """Repaint after a settings change (rows, position, on/off)."""
        self._last_status_sig = ()     # force a repaint of the new state
        self._furn_update_all()
