"""Placement and arrange mode: the front window goes fullscreen and takes
input. Placing: the prop follows the cursor, a click drops it. Arranging:
click a placed piece to pick it up, Del removes the one under the cursor.
Right-click or Esc ends either mode."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt

from plasmacat.cat.render import lh, lw

from plasmacat.world.status_board import STATUS_W


class PlacementMixin:
    """Mixed into Overlay; uses its state (self.desktop, self.cats, …)."""

    def begin_move(self, kind: str, index: int | None = None) -> None:
        """Pick up a placed piece and drop it elsewhere (a shelf keeps its
        slot instead of becoming a new one). Cancel leaves it where it was."""
        self._move_index = index
        self.begin_placement(kind)

    def begin_placement(self, kind: str) -> None:
        """kind: 'ball' | 'plush' | 'food_bowl' | 'water_fountain' |
        'wall_shelf' | 'box' | 'status' | furniture kinds. The prop sticks to
        the cursor; left-click drops it, right-click or Esc cancels."""
        self._placing = kind
        self._place_since = self._time
        self._enter_input_mode()

    def begin_arrange(self) -> None:
        """Arrange the furniture in place: pick pieces up, delete them."""
        self._arranging = True
        self._placing = None
        self._place_since = self._time
        self._enter_input_mode()

    def _enter_input_mode(self) -> None:
        # plain title: no '@geometry' — the KWin script leaves a fullscreen
        # window alone while these modes need the whole screen (P37)
        self.setWindowTitle("plasmacat")
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)
        self.showFullScreen()
        self.activateWindow()
        self.raise_()
        self.setFocus()
        self.update()

    def _end_placement(self) -> None:
        self._placing = None
        self._arranging = False
        self._move_index = None
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
        self.showNormal()
        self._sync_window_geometry(force=True)  # back to the small window

    # -- arrange mode helpers ---------------------------------------------------

    def _prop_rect(self, kind: str, index: int | None) -> QRect:
        """World rect of a placed piece (for picking it up)."""
        b = self.cat.brain
        if kind == "wall_shelf":
            rects = self._shelf_rects()
            return rects[index] if index is not None and index < len(rects) else QRect()
        if kind == "wheel_stand":
            return self._wheel_rect()
        if kind == "box":
            return self._box_rect()
        attr = next(a for k, _l, a in self.FURNITURE if k == kind)
        x = getattr(b, attr)
        if x is None:
            return QRect()
        return self._bowl_rect(x, {"water_fountain": "fountain_0"}.get(kind, kind))

    def _prop_at(self, x: float, y: float) -> tuple[str, int | None] | None:
        """The topmost placed piece under (x, y) — shelves and small items
        win over the big furniture behind them."""
        hits = [(kind, idx) for kind, _label, idx in self.furniture_items()
                if self._prop_rect(kind, idx).contains(int(x), int(y))]
        if not hits:
            return None
        return min(hits, key=lambda h: self._prop_rect(*h).width()
                   * self._prop_rect(*h).height())

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        k = event.key()
        if not (self._placing or self._arranging):
            return
        if k == Qt.Key.Key_Escape:
            self._end_placement()
        elif k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self._arranging \
                and not self._placing:
            hit = self._prop_at(*self.desktop.cursor)
            if hit is not None and hit[0] not in self.BOWLS:
                self.remove_furniture(*hit)
                self.update()
    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if not (self._placing or self._arranging):
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._end_placement()
            return
        if self._arranging and not self._placing:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position()
                hit = self._prop_at(pos.x(), pos.y())
                if hit is not None:
                    self._move_index = hit[1]
                    self._placing = hit[0]    # carry it; the next click drops it
                    self.update()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        kind = self._placing
        if kind in ("ball", "plush"):
            toy = self.toys.spawn(kind, pos.x(), pos.y() - 15)
            if kind == "ball":
                toy.vy = -150.0  # little pop on drop
        elif kind == "status":
            # pinned status board (P42): free position, clamped on-screen
            gr = self._ghost_rect()
            gx = min(max(gr.x(), self.desktop.floor_x0),
                     self.desktop.floor_x1 - STATUS_W)
            gy = min(max(float(gr.y()), 0.0),
                     self.desktop.floor_y_at(gr.center().x()) - self._status_h())
            self.settings.status_pos = [gx, gy]
            self._furn_update_all()
        else:
            x = min(max(pos.x(), self.desktop.floor_x0 + 90), self.desktop.floor_x1 - 90)
            if kind == "food_bowl":
                self.cat.brain.food_x = x
            elif kind == "water_fountain":
                self.cat.brain.water_x = x
            elif kind == "wall_shelf":
                # fixed to the 'wall' at the dropped height — never falls
                y = min(max(pos.y(), 140.0), self.desktop.floor_y_at(pos.x()) - 80)
                idx = getattr(self, "_move_index", None)
                if idx is not None and 0 <= idx < len(self.cat.brain.shelves):
                    self.cat.brain.shelves[idx] = (x, y)
                else:
                    self.cat.brain.shelves.append((x, y))
                    del self.cat.brain.shelves[:-4]  # keep at most 4 shelves
                self._sync_furniture_platforms()
            elif kind == "box":
                self.cat.brain.box_x = x
                self._sync_furniture_platforms()
            elif kind == "scratch_post":
                self.cat.brain.scratch_x = x
            elif kind == "cat_bed":
                self.cat.brain.bed_x = x
            elif kind == "cat_grass":
                self.cat.brain.grass_x = x
                self.cat.brain.grass_charges = 3.0
            elif kind == "litter_0":
                self.cat.brain.litter_x = x
            elif kind == "cat_tree":
                self.cat.brain.tree_x = x
                self._sync_furniture_platforms()
            elif kind == "wheel_stand":
                self.cat.brain.wheel_x = x
                self._sync_furniture_platforms()
        self._end_placement()
    def _ghost_rect(self) -> QRect:
        if not self._placing:
            return QRect()
        cx, cy = self.desktop.cursor
        if self._placing == "status":  # the pinned status board (P42)
            h = self._status_h()
            return QRect(cx - STATUS_W // 2, cy - h // 2, STATUS_W, h)
        key = {"water_fountain": "fountain_0"}.get(self._placing, self._placing)
        pm = self._props[key]
        return QRect(cx - lw(pm) // 2, cy - lh(pm) // 2,
                     lw(pm), lh(pm))
