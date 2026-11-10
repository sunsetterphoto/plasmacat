"""System tab: start at login, pixel size, fullscreen behavior,
notifications, updates, starting over."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from plasmacat.persist import NOTIFY_KINDS
from plasmacat.ui.tabs.common import hint, reset_row

NOTIFY_LABELS = {"litter": "Litter box is full", "vomit": "A cat threw up",
                 "games": "Mini-game start and score"}


class SystemTab(QWidget):
    def __init__(self, ctl, save_path=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctl, self.save_path = ctl, save_path
        lay = QVBoxLayout(self)

        general = QGroupBox("General")
        form = QFormLayout(general)
        self.autostart = QCheckBox("Start PlasmaCat when I log in")
        self.autostart.toggled.connect(ctl.set_autostart)
        form.addRow(self.autostart)
        self.pixel_size = QComboBox()
        for key, label in (("fine", "Fine (small)"), ("normal", "Normal"),
                           ("chunky", "Chunky (big)")):
            self.pixel_size.addItem(label, key)
        self.pixel_size.currentIndexChanged.connect(
            lambda _i: ctl.update_settings(pixel_size=self.pixel_size.currentData()))
        form.addRow("Pixel size", self.pixel_size)
        self.fullscreen = QCheckBox("Hide the cats while a window is fullscreen")
        self.fullscreen.toggled.connect(lambda on: ctl.update_settings(hide_on_fullscreen=on))
        form.addRow(self.fullscreen)
        lay.addWidget(general)

        notes = QGroupBox("Notifications")
        nl = QVBoxLayout(notes)
        self.notify: dict[str, QCheckBox] = {}
        for k in NOTIFY_KINDS:
            cb = QCheckBox(NOTIFY_LABELS[k])
            cb.toggled.connect(lambda on, key=k: ctl.set_flag("notify", key, on))
            self.notify[k] = cb
            nl.addWidget(cb)
        lay.addWidget(notes)

        upd = QGroupBox("Updates")
        ul = QVBoxLayout(upd)
        self.auto_update = QCheckBox("Keep PlasmaCat up to date automatically")
        self.auto_update.toggled.connect(lambda on: ctl.update_settings(auto_update=on))
        ul.addWidget(self.auto_update)
        self.version = QLabel()
        ul.addWidget(self.version)
        lay.addWidget(upd)

        danger = QGroupBox("Start over")
        dl = QHBoxLayout(danger)
        dl.addWidget(hint("Rehomes all cats and clears the furniture, then starts fresh "
                          "with a kitten."), 1)
        reset = QPushButton("Start over…")
        reset.clicked.connect(self._start_over)
        dl.addWidget(reset)
        lay.addWidget(danger)
        row, self.reset_button = reset_row(self._reset)
        lay.addWidget(row)
        lay.addStretch(1)
        self.refresh()

    def _start_over(self) -> None:
        if self.save_path is None:
            return
        if QMessageBox.question(self, "Start over",
                                "Really start over? All cats and their progress are lost.") \
                == QMessageBox.StandardButton.Yes:
            self.ctl.reset_household(self.save_path)

    def _reset(self) -> None:
        self.ctl.reset_tab("system")
        self.refresh()

    def refresh(self) -> None:
        from importlib.metadata import PackageNotFoundError, version
        s = self.ctl.settings
        try:
            v = version("plasmacat")
        except PackageNotFoundError:
            from plasmacat import __version__ as v
        self.version.setText(f"Installed version: {v}")
        pairs = [(self.autostart, self.ctl.autostart_enabled()),
                 (self.fullscreen, s.hide_on_fullscreen),
                 (self.auto_update, s.auto_update)] + \
            [(cb, s.notify.get(k, True)) for k, cb in self.notify.items()]
        for w, val in pairs:
            if w.isChecked() != val:
                w.blockSignals(True)
                w.setChecked(val)
                w.blockSignals(False)
        idx = self.pixel_size.findData(s.pixel_size)
        if idx != self.pixel_size.currentIndex():
            self.pixel_size.blockSignals(True)
            self.pixel_size.setCurrentIndex(idx)
            self.pixel_size.blockSignals(False)
