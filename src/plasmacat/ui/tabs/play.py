"""Play tab: toys, the laser pointer, control mode, mini-games."""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QGroupBox, QPushButton, QVBoxLayout, QWidget

from plasmacat.ui.tabs.common import hint, tile


class PlayTab(QWidget):
    def __init__(self, ctl, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctl = ctl
        lay = QVBoxLayout(self)

        toys = QGroupBox("Toys")
        g = QGridLayout(toys)
        self.tiles: dict = {}
        for i, (text, kind, tip) in enumerate((
                ("Ball", "ball", "Click on the desktop to drop it — she bats it around"),
                ("Plush mouse", "plush", "Her favorite prey; trusted cats bring it to you"))):
            b = tile(text, kind, tip)
            b.clicked.connect(lambda _c=False, k=kind: ctl.place(k))
            self.tiles[kind] = b
            g.addWidget(b, 0, i)
        self.string = tile("String", "lure", "A string dangles from your cursor", checkable=True)
        self.string.toggled.connect(ctl.toggle_string)
        self.laser = tile("Laser pointer", "laser_dot",
                          "A red dot follows your cursor — she chases and pounces it",
                          checkable=True)
        self.laser.toggled.connect(ctl.toggle_laser)
        self.tiles["string"], self.tiles["laser"] = self.string, self.laser
        g.addWidget(self.string, 0, 2)
        g.addWidget(self.laser, 0, 3)
        clear = QPushButton("Put all toys away")
        clear.clicked.connect(self._clear)
        g.addWidget(clear, 1, 0, 1, 4)
        g.addWidget(hint("Tip: right-click a toy on the desktop to toss it or put it away."),
                    2, 0, 1, 4)
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
        kinds = {t.kind for t in self.ctl.overlay.toys.toys}
        for b, on in ((self.control, self.ctl.overlay._control_on),
                      (self.string, "string" in kinds), (self.laser, "laser" in kinds)):
            if b.isChecked() != on:
                b.blockSignals(True)
                b.setChecked(on)
                b.blockSignals(False)
