"""Home tab: furniture (place / move / remove each piece), food, cleaning,
and the pinned status board."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from plasmacat.cat.needs import FOODS
from plasmacat.persist import NEED_ROWS
from plasmacat.ui.tabs.common import hint, need_bar, reset_row, set_need

PLACEABLE = (("food_bowl", "Food bowl"), ("water_fountain", "Water fountain"),
             ("scratch_post", "Scratching post"), ("cat_bed", "Cat bed"),
             ("cat_grass", "Cat grass"), ("litter_0", "Litter box"),
             ("cat_tree", "Big cat tree"), ("wheel_stand", "Exercise wheel"),
             ("wall_shelf", "Wall shelf"), ("box", "Cardboard box"))
ROW_LABELS = {"hunger": "Food", "thirst": "Water", "energy": "Energy", "play": "Play",
              "affection": "Affection", "bladder": "Litter need",
              "food_bowl": "Food bowl", "litter_box": "Litter box"}


class HomeTab(QWidget):
    def __init__(self, ctl, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctl = ctl
        lay = QVBoxLayout(self)

        place = QGroupBox("Add furniture")
        pg = QGridLayout(place)
        self.place_combo = QComboBox()
        for kind, label in PLACEABLE:
            self.place_combo.addItem(label, kind)
        go = QPushButton("Place…")
        go.setToolTip("Click on the desktop to put it down (right-click or Esc cancels)")
        go.clicked.connect(lambda: ctl.place(self.place_combo.currentData()))
        pg.addWidget(self.place_combo, 0, 0)
        pg.addWidget(go, 0, 1)
        lay.addWidget(place)

        self.items_box = QGroupBox("Your furniture")
        self.items = QGridLayout(self.items_box)
        lay.addWidget(self.items_box)
        self.remove_buttons: dict = {}
        self._items_key = None

        food = QGroupBox("Food and cleaning")
        fg = QGridLayout(food)
        self.food_label = QLabel()
        self.food_bar = need_bar(0)
        refill = QPushButton("Refill bowl")
        refill.clicked.connect(ctl.refill_food)
        fg.addWidget(self.food_label, 0, 0)
        fg.addWidget(self.food_bar, 0, 1)
        fg.addWidget(refill, 0, 2)
        self.shop = QComboBox()
        for fid, f in FOODS.items():
            self.shop.addItem(f["label"], fid)
        buy = QPushButton("Buy")
        buy.setToolTip("Switch the bowl to this food (she likes some more than others)")
        buy.clicked.connect(lambda: ctl.buy_food(self.shop.currentData()))
        fg.addWidget(QLabel("Food shop"), 1, 0)
        fg.addWidget(self.shop, 1, 1)
        fg.addWidget(buy, 1, 2)
        self.litter_btn = QPushButton()
        self.litter_btn.clicked.connect(ctl.clean_litter)
        self.puke_btn = QPushButton()
        self.puke_btn.clicked.connect(ctl.clean_puke)
        fg.addWidget(self.litter_btn, 2, 0, 1, 2)
        fg.addWidget(self.puke_btn, 2, 2)
        lay.addWidget(food)

        board = QGroupBox("Status board on the desktop")
        bl = QVBoxLayout(board)
        top = QHBoxLayout()
        self.board_on = QCheckBox("Show")
        self.board_on.toggled.connect(lambda on: ctl.update_settings(status_board=on))
        pos = QPushButton("Position…")
        pos.clicked.connect(ctl.place_status_board)
        top.addWidget(self.board_on)
        top.addStretch(1)
        top.addWidget(pos)
        bl.addLayout(top)
        rows = QGridLayout()
        self.status_rows: dict[str, QCheckBox] = {}
        for i, key in enumerate(NEED_ROWS):
            cb = QCheckBox(ROW_LABELS[key])
            cb.toggled.connect(lambda on, k=key: ctl.set_flag("status_rows", k, on))
            self.status_rows[key] = cb
            rows.addWidget(cb, i // 4, i % 4)
        bl.addLayout(rows)
        bl.addWidget(hint("The board sits behind your windows and shows the cat nearest "
                          "your cursor."))
        row, self.reset_button = reset_row(self._reset)
        bl.addWidget(row)
        lay.addWidget(board)
        lay.addStretch(1)
        self.refresh()

    def _reset(self) -> None:
        self.ctl.reset_tab("home")
        self.refresh()

    def _rebuild_items(self) -> None:
        while self.items.count():
            w = self.items.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.remove_buttons = {}
        items = self.ctl.overlay.furniture_items()
        if not items:
            self.items.addWidget(QLabel("Nothing placed yet."), 0, 0)
        for r, (kind, label, index) in enumerate(items):
            self.items.addWidget(QLabel(label), r, 0)
            move = QPushButton("Move")
            move.setToolTip("Pick it up and click where it should go")
            move.clicked.connect(lambda _c=False, k=kind, i=index: self.ctl.overlay.begin_move(k, i))
            self.items.addWidget(move, r, 1)
            if kind not in self.ctl.overlay.BOWLS:
                rm = QPushButton("Remove")
                rm.clicked.connect(lambda _c=False, k=kind, i=index:
                                   self.ctl.remove_furniture(k, i))
                self.items.addWidget(rm, r, 2)
                self.remove_buttons[(kind, index)] = rm

    def refresh(self) -> None:
        key = tuple(self.ctl.overlay.furniture_items())
        if key != self._items_key:
            self._items_key = key
            self._rebuild_items()
        b = self.ctl.overlay.cat.brain
        self.food_label.setText(f"Bowl: {FOODS[b.food_type]['label']}")
        set_need(self.food_bar, b.food_fill)
        n = len(b.litter_deposits)
        self.litter_btn.setText(f"Clean litter box ({n})" if n else "Litter box is clean")
        self.litter_btn.setEnabled(n > 0)
        p = len(b.puke_spots)
        self.puke_btn.setText(f"Clean up vomit ({p})" if p else "No mess")
        self.puke_btn.setEnabled(p > 0)
        s = self.ctl.settings
        for w, val in [(self.board_on, s.status_board)] + \
                [(cb, s.status_rows.get(k, True)) for k, cb in self.status_rows.items()]:
            if w.isChecked() != val:
                w.blockSignals(True)
                w.setChecked(val)
                w.blockSignals(False)
