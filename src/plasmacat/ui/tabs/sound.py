"""Sound tab: on/off, volume, each sound group separately."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from plasmacat.persist import SOUND_GROUPS
from plasmacat.ui.tabs.common import reset_row

GROUP_LABELS = {"voice": "Meows, chirps and hisses", "purr": "Purring",
                "eating": "Eating, drinking, fountain", "play": "Toys and scratching",
                "alerts": "Chimes and accidents"}
GROUP_SAMPLE = {"voice": "meow", "purr": "purr", "eating": "bubble",
                "play": "boing", "alerts": "chime"}


class SoundTab(QWidget):
    def __init__(self, ctl, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctl = ctl
        lay = QVBoxLayout(self)
        self.enabled = QCheckBox("Cat sounds")
        self.enabled.toggled.connect(lambda on: ctl.update_settings(sound_on=on))
        lay.addWidget(self.enabled)
        row = QHBoxLayout()
        row.addWidget(QLabel("Volume"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.valueChanged.connect(lambda v: ctl.update_settings(volume=v / 100))
        row.addWidget(self.volume, 1)
        lay.addLayout(row)

        box = QGroupBox("What you hear")
        bl = QVBoxLayout(box)
        self.groups: dict[str, QCheckBox] = {}
        for g in SOUND_GROUPS:
            line = QHBoxLayout()
            cb = QCheckBox(GROUP_LABELS[g])
            cb.toggled.connect(lambda on, k=g: ctl.set_flag("sound_groups", k, on))
            self.groups[g] = cb
            line.addWidget(cb, 1)
            test = QPushButton("▶")
            test.setFixedWidth(32)
            test.setToolTip("Play a sample")
            test.setAccessibleName(f"Play a sample: {GROUP_LABELS[g]}")
            test.clicked.connect(lambda _c=False, k=g: self._sample(k))
            line.addWidget(test)
            bl.addLayout(line)
        lay.addWidget(box)
        row, self.reset_button = reset_row(self._reset)
        lay.addWidget(row)
        lay.addStretch(1)
        self.refresh()

    def _sample(self, group: str) -> None:
        p = self.ctl.player
        if p is not None:
            p.play(GROUP_SAMPLE[group], cooldown=0.0)

    def _reset(self) -> None:
        self.ctl.reset_tab("sound")
        self.refresh()

    def refresh(self) -> None:
        s = self.ctl.settings
        for w, setter, val in ((self.enabled, self.enabled.setChecked, s.sound_on),
                               (self.volume, self.volume.setValue, round(s.volume * 100))):
            w.blockSignals(True)
            setter(val)
            w.blockSignals(False)
        for g, cb in self.groups.items():
            cb.blockSignals(True)
            cb.setChecked(s.sound_groups.get(g, True))
            cb.blockSignals(False)
