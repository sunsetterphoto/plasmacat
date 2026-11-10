"""Appearance editor: name, fur, coat pattern, eyes and collar with a live,
animated preview. Used by the first-run flow, 'Add kitten' and the Cats tab.

The editor always works on a COPY of the customization: Cancel leaves the
cat untouched.
"""

from __future__ import annotations

import copy
import random

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from plasmacat.cat import sprites
from plasmacat.cat.patterns import PATTERNS
from plasmacat.cat.render import SpriteBank
from plasmacat.persist import Customization

FUR_PRESETS = {
    "Orange": (230, 145, 60),
    "Grey": (160, 160, 170),
    "Black": (60, 60, 70),
    "White": (235, 230, 225),
    "Brown": (140, 90, 55),
    "Cream": (225, 210, 190),
}
EYE_PRESETS = {
    "Green": (90, 200, 90),
    "Gold": (240, 200, 80),
    "Blue": (100, 160, 240),
    "Copper": (220, 140, 60),
}
COLLAR_PRESETS = {
    "No collar": None,
    "Red collar": (200, 60, 80),
    "Blue collar": (80, 120, 220),
    "Green collar": (80, 180, 110),
    "Purple collar": (160, 100, 200),
}
PATTERN_LABELS = {"solid": "Solid", "tabby": "Tabby (stripes)", "tuxedo": "Tuxedo",
                  "spots": "Spotted", "tortie": "Tortoiseshell"}
PREVIEW_CELL = 2          # logical px per sprite grid cell in the preview
KITTEN_NAMES = ("Findus", "Luna", "Balu", "Kiki", "Mogli", "Nala", "Felix", "Minka")


def random_customization(name: str = "Kitty", rng: random.Random | None = None) -> Customization:
    rng = rng or random.Random()
    return Customization(
        name=name,
        fur=rng.choice(list(FUR_PRESETS.values())),
        eye=rng.choice(list(EYE_PRESETS.values())),
        pattern=rng.choice(PATTERNS),
        collar=rng.choice(list(COLLAR_PRESETS.values())),
    )


class AppearanceEditor(QWidget):
    changed = Signal()

    def __init__(self, initial: Customization | None = None, stage: int = 6,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cust = copy.deepcopy(initial or Customization())
        self.stage = stage
        self._frame = 0

        root = QHBoxLayout(self)
        self.preview = QLabel()
        self.preview.setFixedSize(sprites.GRID_W * PREVIEW_CELL + 16,
                                  sprites.GRID_H * PREVIEW_CELL + 16)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background: #3a3c48; border-radius: 8px;")
        root.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)

        form = QFormLayout()
        root.addLayout(form, 1)
        self.name_edit = QLineEdit(self.cust.name)
        self.name_edit.setMaxLength(24)
        self.name_edit.textChanged.connect(self._changed)
        form.addRow("Name", self.name_edit)

        fur_row = QHBoxLayout()
        for label, rgb in FUR_PRESETS.items():
            btn = QPushButton()
            btn.setFixedSize(26, 26)
            btn.setToolTip(label)
            btn.setAccessibleName(f"{label} fur")
            btn.setStyleSheet(f"background: rgb{rgb}; border: 1px solid #222; border-radius: 13px;")
            btn.clicked.connect(lambda _c=False, c=rgb: self._set_fur(c))
            fur_row.addWidget(btn)
        custom = QPushButton("…")
        custom.setFixedSize(26, 26)
        custom.setToolTip("Pick any fur color")
        custom.clicked.connect(self._custom_fur)
        fur_row.addWidget(custom)
        fur_row.addStretch(1)
        form.addRow("Fur", fur_row)

        self.pattern_combo = QComboBox()
        for key in PATTERNS:
            self.pattern_combo.addItem(PATTERN_LABELS.get(key, key), key)
        self.pattern_combo.setCurrentIndex(max(0, self.pattern_combo.findData(self.cust.pattern)))
        self.pattern_combo.currentIndexChanged.connect(self._changed)
        form.addRow("Coat", self.pattern_combo)

        self.eye_combo = self._preset_combo(EYE_PRESETS, self.cust.eye)
        form.addRow("Eyes", self.eye_combo)
        self.collar_combo = self._preset_combo(COLLAR_PRESETS, self.cust.collar)
        form.addRow("Collar", self.collar_combo)

        surprise = QPushButton("Surprise me")
        surprise.setToolTip("A random look (keeps the name)")
        surprise.clicked.connect(self._randomize)
        form.addRow("", surprise)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(140)
        self._refresh_preview()

    def _preset_combo(self, presets: dict, current) -> QComboBox:
        combo = QComboBox()
        for label, value in presets.items():
            combo.addItem(label, value)
        idx = next((i for i, v in enumerate(presets.values())
                    if (tuple(v) if v else v) == (tuple(current) if current else current)), -1)
        if idx < 0:                       # a custom value from an older save
            combo.addItem("Custom", current)
            idx = combo.count() - 1
        combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(self._changed)
        return combo

    # -- edits ------------------------------------------------------------------

    def _set_fur(self, rgb: tuple[int, int, int]) -> None:
        self.cust.fur = tuple(rgb)
        self.cust.fur_shade = None  # re-derived from the fur
        self._refresh_preview()
        self.changed.emit()

    def _custom_fur(self) -> None:
        c = QColorDialog.getColor(QColor(*self.cust.fur), self, "Fur color")
        if c.isValid():
            self._set_fur((c.red(), c.green(), c.blue()))

    def _randomize(self) -> None:
        r = random_customization(self.cust.name)
        self.cust.fur, self.cust.fur_shade = r.fur, None
        for combo, value in ((self.pattern_combo, r.pattern), (self.eye_combo, r.eye),
                             (self.collar_combo, r.collar)):
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0, combo.findData(value)))
            combo.blockSignals(False)
        self._changed()

    def _changed(self, *_args) -> None:
        self.cust.name = self.name_edit.text().strip() or "Minka"
        self.cust.pattern = self.pattern_combo.currentData()
        eye = self.eye_combo.currentData()
        self.cust.eye = tuple(eye) if eye else self.cust.eye
        collar = self.collar_combo.currentData()
        self.cust.collar = tuple(collar) if collar else None
        self._refresh_preview()
        self.changed.emit()

    # -- preview ----------------------------------------------------------------

    def _advance(self) -> None:
        self._frame = (self._frame + 1) % 4
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        dpr = self.devicePixelRatioF() or 1.0
        bank = SpriteBank(palette=self.cust.to_palette(), pattern=self.cust.pattern,
                          device_px=max(1, round(PREVIEW_CELL * dpr)), dpr=dpr,
                          accessory=self.cust.collar is not None, stage=self.stage)
        pm = QPixmap(bank.frame("walk", self._frame))
        acc = bank.accessory_frame("walk", self._frame)
        if acc is not None:
            with QPainter(pm) as p:
                p.drawPixmap(0, 0, acc)
        self.preview.setPixmap(pm)

    def result(self) -> Customization:
        self._changed()
        return copy.deepcopy(self.cust)


class AppearanceDialog(QDialog):
    """Modal wrapper: OK returns the edited copy, Cancel returns None."""

    def __init__(self, initial: Customization | None = None, stage: int = 6,
                 title: str = "PlasmaCat — Appearance", intro: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        if intro:
            lbl = QLabel(intro)
            lbl.setWordWrap(True)
            lay.addWidget(lbl)
        self.editor = AppearanceEditor(initial, stage=stage, parent=self)
        lay.addWidget(self.editor)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def customization(self) -> Customization | None:
        """Run the dialog; the edited copy on OK, None on Cancel."""
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.editor.result()
        return None
