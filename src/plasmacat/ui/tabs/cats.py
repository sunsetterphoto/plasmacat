"""Cats tab: one card per cat — look, life stage, bond, needs, care."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from plasmacat.cat.render import SpriteBank
from plasmacat.ui.tabs.common import hint, need_bar, set_need

NEEDS = (("hunger", "Food"), ("thirst", "Water"), ("energy", "Energy"),
         ("play", "Play"), ("affection", "Affection"), ("bladder", "Litter"))


class CatCard(QGroupBox):
    def __init__(self, ctl, cat, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctl, self.cat = ctl, cat
        lay = QHBoxLayout(self)
        self.portrait = QLabel()
        self.portrait.setFixedSize(140, 108)
        self.portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.portrait.setStyleSheet("background: #3a3c48; border-radius: 8px;")
        lay.addWidget(self.portrait)

        mid = QVBoxLayout()
        self.title = QLabel()
        self.title.setStyleSheet("font-weight: bold; font-size: 12pt;")
        self.subtitle = QLabel()
        mid.addWidget(self.title)
        mid.addWidget(self.subtitle)
        grid = QGridLayout()
        self.bars = {}
        for i, (key, label) in enumerate(NEEDS):
            grid.addWidget(QLabel(label), i // 2, (i % 2) * 2)
            self.bars[key] = need_bar(cat.brain.needs.get(key, 0))
            grid.addWidget(self.bars[key], i // 2, (i % 2) * 2 + 1)
        mid.addLayout(grid)
        lay.addLayout(mid, 1)

        btns = QVBoxLayout()
        for text, slot, tip in (
                ("Give treat", lambda: ctl.give_treat(self.cat), "A little snack — she loves it"),
                ("Appearance…", lambda: ctl.customize(self.cat, self), "Name, fur, coat, eyes, collar"),
                ("Remove…", self._remove, "Rehome this cat")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            btns.addWidget(b)
        self.remove_btn = btns.itemAt(2).widget()
        btns.addStretch(1)
        lay.addLayout(btns)
        self._portrait_key = None
        self.refresh()

    def _remove(self) -> None:
        ok = QMessageBox.question(
            self, "Remove cat",
            f"Rehome {self.cat.cust.name}? Her progress is lost.") == QMessageBox.StandardButton.Yes
        if ok:
            self.ctl.remove_cat(self.cat)

    def refresh(self) -> None:
        b, c = self.cat.brain, self.cat.cust
        self.title.setText(c.name)
        self.subtitle.setText(f"{b.life_stage} · {b.attachment_name} ({int(b.attachment_xp)} XP)")
        for key, bar in self.bars.items():
            set_need(bar, b.needs.get(key, 0))
        self.remove_btn.setEnabled(len(self.ctl.cats) > 1)
        key = (c.fur, c.pattern, c.eye, c.collar, b.stage)
        if key != self._portrait_key:     # portraits only re-render on change
            self._portrait_key = key
            dpr = self.devicePixelRatioF() or 1.0
            bank = SpriteBank(c.to_palette(), c.pattern, device_px=max(1, round(dpr)),
                              dpr=dpr, accessory=c.collar is not None, stage=b.stage)
            self.portrait.setPixmap(bank.frame("sit", 0))


class CatsTab(QWidget):
    def __init__(self, ctl, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctl = ctl
        outer = QVBoxLayout(self)
        outer.addWidget(hint("Pet a cat by moving the cursor slowly over her, or click "
                             "her. Right-click a cat — or her bowl, toys and furniture — "
                             "for the things you can do with it."))
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.inner = QWidget()
        self.list = QVBoxLayout(self.inner)
        self.list.addStretch(1)
        self.area.setWidget(self.inner)
        outer.addWidget(self.area, 1)
        self.add_btn = QPushButton("Add a kitten…")
        self.add_btn.clicked.connect(lambda: ctl.add_kitten(self))
        outer.addWidget(self.add_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.cards: list[CatCard] = []
        self.refresh()

    def refresh(self) -> None:
        if [c.cat for c in self.cards] != list(self.ctl.cats):
            for card in self.cards:
                card.setParent(None)
                card.deleteLater()
            self.cards = [CatCard(self.ctl, cat, self.inner) for cat in self.ctl.cats]
            for i, card in enumerate(self.cards):
                self.list.insertWidget(i, card)
        for card in self.cards:
            card.refresh()
        self.add_btn.setEnabled(self.ctl.can_add_kitten())
        self.add_btn.setToolTip("" if self.ctl.can_add_kitten()
                                else "The home is full — four cats are enough!")
