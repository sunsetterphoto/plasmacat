"""Small optional status window (P39): needs bars + care buttons.

Toggled from the tray ('Status window'), persisted in the customization.
The KWin bridge tags it keepAbove like every plasmacat window, so it stays
visible over other windows; its title matches neither the furniture prefix
nor the '@geometry' form, so the bridge leaves its position alone.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QVBoxLayout, QWidget)

NEEDS = (("hunger", "Food"), ("thirst", "Water"), ("energy", "Energy"),
         ("play", "Play"), ("affection", "Affection"), ("bladder", "Litter"))
BAR_H = 10
LABEL_W = 86


class StatusWindow(QWidget):
    def __init__(self, overlay) -> None:
        super().__init__()
        self.o = overlay
        self.setWindowTitle("PlasmaCat Status")
        self.setWindowFlags(Qt.WindowType.Tool)  # small utility window
        lay = QVBoxLayout(self)

        self.title = QLabel()
        font = self.title.font()
        font.setBold(True)
        self.title.setFont(font)
        lay.addWidget(self.title)

        self.bars: dict[str, QProgressBar] = {}
        for key, label in NEEDS:
            self._bar_row(lay, key, label)
        self._bar_row(lay, "food", "Food bowl")
        self._bar_row(lay, "litterbox", "Litter box")

        row = QHBoxLayout()
        self.btn_treat = QPushButton("Give treat")
        self.btn_food = QPushButton("Refill food")
        self.btn_litter = QPushButton("Clean litter")
        for b in (self.btn_treat, self.btn_food, self.btn_litter):
            row.addWidget(b)
        lay.addLayout(row)

        brain = overlay.cat.brain
        self.btn_treat.clicked.connect(brain.on_treat)
        self.btn_food.clicked.connect(brain.refill_food)
        self.btn_litter.clicked.connect(brain.clean_litter)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(1000)
        self.refresh()

    def _bar_row(self, lay: QVBoxLayout, key: str, label: str) -> QProgressBar:
        row = QHBoxLayout()
        lab = QLabel(label)
        lab.setMinimumWidth(LABEL_W)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        bar.setMaximumHeight(BAR_H)
        row.addWidget(lab)
        row.addWidget(bar)
        lay.addLayout(row)
        self.bars[key] = bar
        return bar

    def refresh(self) -> None:
        brain = self.o.cat.brain
        self.title.setText(f"{self.o.cust.name} — {brain.attachment_name} "
                           f"({int(brain.attachment_xp)} XP)")
        for key, _label in NEEDS:
            self.bars[key].setValue(int(brain.needs[key]))
        self.bars["food"].setValue(int(brain.food_fill))
        self.bars["litterbox"].setValue(int(brain.litter_fill / 5 * 100))
        self.btn_litter.setText(f"Clean litter ({len(brain.litter_deposits)})")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self.o.set_status_window(False)  # keeps tray action + save in sync
        super().closeEvent(event)
