"""Placement mode: the front window goes fullscreen, the prop follows the cursor, a click drops it."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt

from plasmacat.cat.render import lh, lw

from plasmacat.world.status_board import STATUS_H, STATUS_W


class PlacementMixin:
    """Mixed into Overlay; uses its state (self.desktop, self.cats, …)."""

    def begin_placement(self, kind: str) -> None:
        """kind: 'ball' | 'plush' | 'food_bowl' | 'water_fountain' |
        'wall_shelf' | 'box' | 'status' | furniture kinds. The prop sticks to
        the cursor; left-click drops it, right-click cancels."""
        self._placing = kind
        self._place_since = self._time
        # plain title: no '@geometry' — the KWin script leaves a fullscreen
        # window alone while placement mode needs the whole screen (P37)
        self.setWindowTitle("plasmacat")
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)
        self.showFullScreen()
        self.activateWindow()
        self.raise_()
    def _end_placement(self) -> None:
        self._placing = None
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
        self.showNormal()
        self._sync_window_geometry(force=True)  # back to the small window
    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if not self._placing:
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._end_placement()
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
                     self.desktop.floor_y_at(gr.center().x()) - STATUS_H)
            self.cust.status_pos = [gx, gy]
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
            return QRect(cx - STATUS_W // 2, cy - STATUS_H // 2,
                         STATUS_W, STATUS_H)
        key = {"water_fountain": "fountain_0"}.get(self._placing, self._placing)
        pm = self._props[key]
        return QRect(cx - lw(pm) // 2, cy - lh(pm) // 2,
                     lw(pm), lh(pm))
