"""The Control Center: everything about your cats in one window, one tab per
category (Cats · Play · Home · Sound · System). Opened from the tray icon."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from plasmacat import paths
from plasmacat.ui.tabs.cats import CatsTab
from plasmacat.ui.tabs.home import HomeTab
from plasmacat.ui.tabs.play import PlayTab
from plasmacat.ui.tabs.sound import SoundTab
from plasmacat.ui.tabs.system import SystemTab


class ControlCenter(QWidget):
    TAB_ORDER = (("cats", "Cats"), ("play", "Play"), ("home", "Home"),
                 ("sound", "Sound"), ("system", "System"))

    def __init__(self, ctl, save_path=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctl = ctl
        self.setWindowTitle("PlasmaCat")
        self.setWindowIcon(QIcon(str(paths.data_file("icons/plasmacat-256.png"))))
        self.resize(620, 560)
        lay = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        lay.addWidget(self.tab_widget)
        self.tabs = {
            "cats": CatsTab(ctl, self), "play": PlayTab(ctl, self),
            "home": HomeTab(ctl, self), "sound": SoundTab(ctl, self),
            "system": SystemTab(ctl, save_path, self),
        }
        for key, label in self.TAB_ORDER:
            self.tab_widget.addTab(self.tabs[key], label)
        ctl.changed.connect(self.refresh)
        self._timer = QTimer(self)        # live needs while the window is open
        self._timer.timeout.connect(self.refresh)
        self._timer.start(1000)

    def show_tab(self, key: str = "cats") -> None:
        self.tab_widget.setCurrentWidget(self.tabs.get(key, self.tabs["cats"]))
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh(self) -> None:
        if not self.isVisible() and self.sender() is self._timer:
            return
        for tab in self.tabs.values():
            tab.refresh()
