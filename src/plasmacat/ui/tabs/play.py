"""Play tab: toys, the laser pointer, control mode, mini-games."""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QGroupBox, QPushButton, QVBoxLayout, QWidget

from plasmacat.ui.tabs.common import hint


class PlayTab(QWidget):
    def __init__(self, ctl, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctl = ctl
        lay = QVBoxLayout(self)

        toys = QGroupBox("Toys")
        g = QGridLayout(toys)
        for i, (text, kind, tip) in enumerate((
                ("Place a ball", "ball", "Click on the desktop to drop it — she bats it around"),
                ("Place a plush mouse", "plush", "Her favorite prey; trusted cats bring it to you"))):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, k=kind: ctl.place(k))
            g.addWidget(b, 0, i)
        self.string = QPushButton("Wave a string")
        self.string.setCheckable(True)
        self.string.setToolTip("A string dangles from your cursor")
        self.string.toggled.connect(ctl.toggle_string)
        self.laser = QPushButton("Laser pointer")
        self.laser.setCheckable(True)
        self.laser.setToolTip("A red dot follows your cursor — she never quite catches it")
        self.laser.toggled.connect(ctl.toggle_laser)
        g.addWidget(self.string, 1, 0)
        g.addWidget(self.laser, 1, 1)
        clear = QPushButton("Clear all toys")
        clear.clicked.connect(self._clear)
        g.addWidget(clear, 2, 0, 1, 2)
        lay.addWidget(toys)

        games = QGroupBox("Games")
        gl = QVBoxLayout(games)
        hunt = QPushButton("Mouse hunt (60 s)")
        hunt.setToolTip("Up to 8 mice scurry around — catch them!")
        hunt.clicked.connect(ctl.start_hunt)
        gl.addWidget(hunt)
        self.control = QPushButton("Steer the cat yourself")
        self.control.setCheckable(True)
        self.control.toggled.connect(ctl.set_control)
        gl.addWidget(self.control)
        gl.addWidget(hint("While steering: A/D or ←/→ walk, W/↑/Space jumps, S/↓ stops. "
                          "These keys are only grabbed while this is on."))
        lay.addWidget(games)
        lay.addStretch(1)

    def _clear(self) -> None:
        for b in (self.string, self.laser):
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)
        self.ctl.clear_toys()

    def refresh(self) -> None:
        self.control.blockSignals(True)
        self.control.setChecked(self.ctl.overlay._control_on)
        self.control.blockSignals(False)
