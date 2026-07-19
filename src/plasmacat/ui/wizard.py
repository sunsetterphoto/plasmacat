"""First-run setup wizard: customize the cat with a live animated preview.

Edits a Customization (name, fur, pattern, eyes, collar, sound) and shows the
result instantly as an animated walking cat. Pure Qt widgets.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QVBoxLayout,
)

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
    "None": None,
    "Red collar": (200, 60, 80),
    "Blue collar": (80, 120, 220),
    "Green collar": (80, 180, 110),
    "Purple collar": (160, 100, 200),
}
PATTERNS = ["solid", "tabby", "tuxedo", "spots", "tortie"]
PREVIEW_SCALE = 2


class SetupWizard(QDialog):
    def __init__(self, initial: Customization | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PlasmaCat — Set up your cat")
        self.cust = initial or Customization()
        self._frame = 0

        root = QHBoxLayout(self)

        # -- preview ---------------------------------------------------------
        self.preview = QLabel()
        self.preview.setFixedSize(64 * PREVIEW_SCALE, 48 * PREVIEW_SCALE)
        self.preview.setStyleSheet("background: #3c3c46; border-radius: 6px;")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)

        # -- controls --------------------------------------------------------
        right = QVBoxLayout()
        root.addLayout(right, 1)

        form = QGridLayout()
        right.addLayout(form)
        row = 0
        form.addWidget(QLabel("Name:"), row, 0)
        self.name_edit = QLineEdit(self.cust.name)
        self.name_edit.textChanged.connect(self._changed)
        form.addWidget(self.name_edit, row, 1)
        row += 1

        form.addWidget(QLabel("Fur:"), row, 0)
        fur_box = QHBoxLayout()
        for pname, rgb in FUR_PRESETS.items():
            btn = QPushButton()
            btn.setFixedSize(26, 26)
            btn.setToolTip(pname)
            btn.setStyleSheet(f"background: rgb({rgb[0]},{rgb[1]},{rgb[2]});"
                              "border: 1px solid #222; border-radius: 4px;")
            btn.clicked.connect(lambda checked, c=rgb: self._set_fur(c))
            fur_box.addWidget(btn)
        custom_fur = QPushButton("…")
        custom_fur.setFixedSize(26, 26)
        custom_fur.setToolTip("Custom color")
        custom_fur.clicked.connect(self._custom_fur)
        fur_box.addWidget(custom_fur)
        fur_box.addStretch(1)
        form.addLayout(fur_box, row, 1)
        row += 1

        form.addWidget(QLabel("Pattern:"), row, 0)
        self.pattern_combo = QComboBox()
        self.pattern_combo.addItems(PATTERNS)
        self.pattern_combo.setCurrentText(self.cust.pattern)
        self.pattern_combo.currentTextChanged.connect(self._changed)
        form.addWidget(self.pattern_combo, row, 1)
        row += 1

        form.addWidget(QLabel("Eyes:"), row, 0)
        self.eye_combo = QComboBox()
        self.eye_combo.addItems(list(EYE_PRESETS))
        self.eye_combo.currentTextChanged.connect(self._changed)
        form.addWidget(self.eye_combo, row, 1)
        row += 1

        form.addWidget(QLabel("Accessory:"), row, 0)
        self.collar_combo = QComboBox()
        self.collar_combo.addItems(list(COLLAR_PRESETS))
        self.collar_combo.currentTextChanged.connect(self._changed)
        form.addWidget(self.collar_combo, row, 1)
        row += 1

        snd_box = QGroupBox("Sound")
        snd_layout = QVBoxLayout(snd_box)
        self.sound_check = QCheckBox("Enable cat sounds")
        self.sound_check.setChecked(self.cust.sound_on)
        self.sound_check.toggled.connect(self._changed)
        snd_layout.addWidget(self.sound_check)
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("Volume"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(self.cust.volume * 100))
        self.volume_slider.valueChanged.connect(self._changed)
        vol_row.addWidget(self.volume_slider)
        snd_layout.addLayout(vol_row)
        right.addWidget(snd_box)
        right.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(125)  # 8 fps walk cycle
        self._refresh_preview()

    # -- slots ---------------------------------------------------------------

    def _set_fur(self, rgb: tuple[int, int, int]) -> None:
        self.cust.fur = rgb
        self.cust.fur_shade = None  # re-derive
        self._refresh_preview()

    def _custom_fur(self) -> None:
        c = QColorDialog.getColor(QColor(*self.cust.fur), self, "Fur color")
        if c.isValid():
            self._set_fur((c.red(), c.green(), c.blue()))

    def _changed(self, *_args) -> None:
        self.cust.name = self.name_edit.text().strip() or "Minka"
        self.cust.pattern = self.pattern_combo.currentText()
        self.cust.eye = EYE_PRESETS[self.eye_combo.currentText()]
        self.cust.collar = COLLAR_PRESETS[self.collar_combo.currentText()]
        self.cust.sound_on = self.sound_check.isChecked()
        self.cust.volume = self.volume_slider.value() / 100
        self._refresh_preview()

    def _advance(self) -> None:
        self._frame = (self._frame + 1) % 4
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        bank = SpriteBank(palette=self.cust.to_palette(), pattern=self.cust.pattern,
                          scale=PREVIEW_SCALE, accessory=self.cust.collar is not None)
        pm = bank.frame("walk", self._frame)
        acc = bank.accessory_frame("walk", self._frame)
        if acc is not None:
            pm = QPixmap(pm)
            with QPainter(pm) as p:
                p.drawPixmap(0, 0, acc)
        self.preview.setPixmap(pm)

    def result_customization(self) -> Customization:
        self._changed()  # make sure everything is applied
        return self.cust
