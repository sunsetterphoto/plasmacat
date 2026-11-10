"""Small, transparent, click-through overlay window: the game canvas (P37).

The window covers just the bounding box of the front-layer content (cat,
bubble, cat door, the front toys — resting floor toys live on the
FurnitureLayer since P42) instead of the whole screen — the fullscreen
translucent surface cost a native buffer copy per repaint (DECISIONS.md D17).
Wayland clients cannot position themselves, so the desired rect is encoded in
the window title ('plasmacat@x,y,w,h') and the KWin helper script applies it
(frameGeometry is read-write there). Placement mode temporarily goes
fullscreen (plain title: the script leaves the window alone).

Runs the simulation loop (QTimer ~60 fps), draws the cat (pixel-art sprite),
the toys and the cat's thought bubble, plays sound intents from the brain,
and repaints only dirty regions. Debug mode (--debug) draws platform top edges.
"""

from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QElapsedTimer, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QRegion
from PySide6.QtWidgets import QWidget

from plasmacat.bridge.desktop import DesktopState
from plasmacat.cat.household import Household
from plasmacat.cat.cat import Cat
from plasmacat.cat.interactions import CursorTracker, InteractionDetector
from plasmacat.cat.minigames import MouseHunt
from plasmacat.cat import sprites
from plasmacat.cat.render import (
    PROP_DETAIL, SpriteBank, art_pixel_device, lh, lw, prop_pixmap,
)
from plasmacat.cat.toys import ToyManager
from plasmacat.persist import Customization, Settings
from plasmacat.world.furniture_layer import FurnitureLayer
from plasmacat.world.placement import PlacementMixin
from plasmacat.world.status_board import STATUS_W, StatusBoardMixin
from plasmacat.world.window_policy import WIN_MIN_H, WIN_MIN_W, WindowPolicyMixin  # noqa: F401

FPS_MS = 16
MAX_CATS = 4  # P47: household size cap (each cat costs a brain + a sprite bank)

# every prop pixmap the layers draw (rebuilt per device pixel ratio)
PROP_NAMES = ("food_bowl", "food_bowl_empty",
                 "fountain_0", "fountain_1", "fountain_2",
                 "puke", "wall_shelf", "box", "box_front",
                 "cat_door_0", "cat_door_1", "cat_door_2",
                 "fish", "drop", "zzz", "heart",
                 "ball", "plush", "mouse", "lure", "laser_dot",
                 "scratch_post", "cat_bed",
                 "cat_grass", "litter_0", "litter_1", "litter_2",
                 "litter_poop", "litter_pee",
                 "cat_tree", "wheel_stand", "wheel_rim", "wheel_front")


DOOR_DUR = 0.9  # seconds for the cat-door transition flourish (P27)


class Overlay(WindowPolicyMixin, PlacementMixin, StatusBoardMixin, QWidget):
    def __init__(self, bridge, player=None, cust: Customization | None = None,
                 settings: Settings | None = None, debug: bool = False,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("plasmacat")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        screen = QGuiApplication.primaryScreen().geometry()
        self.desktop = DesktopState(screen.width(), screen.height())
        if debug:
            scr = QGuiApplication.primaryScreen()
            print(f"[dbg] Qt screen geometry={screen.width()}x{screen.height()} "
                  f"dpr={scr.devicePixelRatio()} virtual={scr.virtualGeometry().getRect()}")
        # pixel-exact sizes (render.art_pixel_device): wide screens get 1.5x
        # bigger art; the real sizes are set by _apply_dpr() below and again
        # whenever the window's device pixel ratio changes
        self.pixel_size = "normal"
        self._size_factor = 1.5 if screen.width() >= 2550 else 1.0
        self._dpr = 0.0
        self.device_px = self.prop_device_px = 1
        self.scale = self.prop_scale = 1.0   # logical px per art pixel
        self._props: dict = {}
        self.cust = cust or Customization()
        self.settings = settings or Settings()
        self.player = player
        self.debug = debug
        self.toys = ToyManager(rng=random.Random())
        # P47 multi-cat: every cat shares one Household (bowls, furniture,
        # litter — brains forward there), but has its own look, banks, brain
        self.household = Household()
        self.cats: list[Cat] = []
        self._banks: dict[Cat, tuple[SpriteBank, SpriteBank, int]] = {}
        self._doors: dict[Cat, tuple[float, float, float, str]] = {}
        self._prev_back: dict[Cat, bool] = {}
        self._prev_brain_state: dict[Cat, str] = {}
        self._active: Cat | None = None  # the cat the cursor is 'with'
        self._control_on = False         # P42 control-mode toggle state
        self._apply_dpr(self.devicePixelRatioF())
        primary = self.add_cat(self.cust, age=6.0)
        primary.brain.food_x = self.desktop.floor_x0 + 110.0
        primary.brain.water_x = self.desktop.floor_x0 + 200.0

        self._wheel_angle = 0.0
        self._time = 0.0
        self._dbg_t = 0.0
        self._placing: str | None = None      # placement mode: prop follows cursor
        self._arranging = False               # arrange mode: pick pieces up
        self._move_index: int | None = None
        self._fullscreen_active = False
        self._place_since = 0.0
        self._inactive_since: float | None = None
        self._last_sig: tuple = ()
        self._last_furn_sig: tuple = ()
        self._last_fountain_frame = -1
        self._prev_puke_count = 0
        self._last_back_toy_sig: tuple = ()  # P42: floor toys on the back layer
        self._last_back_sig: tuple = ()      # P49: back-layer repaint gating
        self._furn_move_ticks = 0            # P32 flush cadence, back layer
        self._prev_furn_moving = False
        self._move_ticks = 0               # P32 full-flush cadence
        self._prev_moving = False
        self._win_x = 0                    # P37: window's world position
        self._win_y = 0                    # (applied by KWin, not by us)
        self._shrink_since: float | None = None
        self._last_status_sig: tuple = ()  # P42: pinned status board
        self._hunt: MouseHunt | None = None  # P42: mouse-hunt session
        self.notify = None  # optional callback(title, msg) set by the app
        self._hidden: set[str] = set()   # reasons to hide all windows
        self.last_notify_kind: str | None = None
        self.context_requested = None    # callback(thing, global_pos, widget)
        self._bridge = bridge
        self.furniture_layers = [FurnitureLayer(self, s)
                                 for s in QGuiApplication.screens()]
        QGuiApplication.instance().screenAdded.connect(self._screens_changed)
        QGuiApplication.instance().screenRemoved.connect(self._screens_changed)

        bridge.cursorChanged.connect(self._on_cursor)
        bridge.windowsChanged.connect(self.desktop.set_windows)
        bridge.workAreasChanged.connect(self._on_work_areas)
        bridge.keyEvent.connect(self._on_key_event)  # P42 control mode
        if hasattr(bridge, "fullscreenChanged"):
            bridge.fullscreenChanged.connect(self._on_fullscreen)

        # ONE CursorTracker (fed here, D13); one InteractionDetector per cat
        # sharing it, so each cat keeps its own stroke/rub accumulators
        self._tracker = CursorTracker()
        self._detectors: dict[int, InteractionDetector] = {}

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer.start(FPS_MS)

        self.resize(WIN_MIN_W * 2, WIN_MIN_H * 2)
        self.show()
        self._sync_window_geometry(force=True)

    # -- cats (P47 multi-cat) --------------------------------------------------

    @property
    def cat(self) -> Cat:
        """The primary cat (compat alias for cats[0]; the household state is
        shared, so furniture access via her brain hits every cat's world)."""
        return self.cats[0]

    @property
    def active(self) -> Cat:
        """The cat the user is currently 'with' (nearest the cursor): target
        of the status board, treats, customization and control mode."""
        if self._active is None or self._active not in self.cats:
            self._active = self.cats[0]
        return self._active

    def add_cat(self, cust: Customization, age: float = 0.0,
                x: float | None = None) -> Cat:
        if x is None:
            x = self.desktop.screen_w * 0.5
        cat = Cat(x, self.desktop.floor_y_at(x), rng=random.Random(),
                  cust=cust, household=self.household)
        cat.brain.age = age
        cat.brain.toys = self.toys
        self.cats.append(cat)
        # P48: the cats know each other (cuddle, chase, spats, co-sleeping)
        for c in self.cats:
            c.brain.peers = [(o.body, o.brain) for o in self.cats if o is not c]
        br, bl = self._make_banks(cust, cat.brain.stage)
        self._banks[cat] = (br, bl, cat.brain.stage)
        return cat

    def remove_cat(self, cat: Cat) -> bool:
        """Remove a cat from the household (never the last one)."""
        if cat not in self.cats or len(self.cats) <= 1:
            return False
        self.cats.remove(cat)
        for d in (self._banks, self._doors, self._prev_back, self._prev_brain_state):
            d.pop(cat, None)
        for c in self.cats:
            c.brain.peers = [(o.body, o.brain) for o in self.cats if o is not c]
        if self._active is cat:
            self._active = None
        self.cust = self.cats[0].cust
        self.update()
        self._furn_update_all()
        return True

    def _on_fullscreen(self, on: bool) -> None:
        """A fullscreen window is active (video, game): step aside."""
        self._fullscreen_active = on
        self.set_hidden("fullscreen", on and self.settings.hide_on_fullscreen)

    # -- clicks: right-click menus, petting -------------------------------------

    def _toy_rect(self, toy) -> QRect:
        pm = self._props.get(toy.kind)
        if pm is None:
            return QRect()
        return QRect(int(toy.x) - lw(pm) // 2 - 4, int(toy.y) - lh(pm) - 4,
                     lw(pm) + 8, lh(pm) + 8)

    def _puke_rects(self) -> list[QRect]:
        return [self._bowl_rect(px, "puke") for px in self.cat.brain.puke_spots]

    def thing_at(self, x: float, y: float):
        """What is under a world point: ('cat', cat) | ('toy', toy) |
        ('puke', index) | ('prop', kind, index) | ('status',) | None."""
        pt = QPoint(int(x), int(y))
        for cat in self.cats:
            if self._cat_rect(cat).contains(pt):
                return ("cat", cat)
        for toy in self.toys.toys:
            if toy.kind in ("ball", "plush") and self._toy_rect(toy).contains(pt):
                return ("toy", toy)
        for i, r in enumerate(self._puke_rects()):
            if r.adjusted(-4, -8, 4, 4).contains(pt):
                return ("puke", i)
        hit = self._prop_at(x, y)
        if hit is not None:
            return ("prop", hit[0], hit[1])
        if self._status_rect().contains(pt):
            return ("status",)
        return None

    def interactive_rects(self, layer: str) -> list[QRect]:
        """World rects that take mouse input on a layer; everything else
        stays click-through. 'front' = the cat window, 'back' = furniture."""
        if layer == "front":
            return [self._cat_rect(c) for c in self.cats if self.cat_layer(c) != "back"]
        rects = [self._cat_rect(c) for c in self.cats if self.cat_layer(c) == "back"]
        rects += [self._prop_rect(k, i) for k, _l, i in self.furniture_items()]
        rects += [self._toy_rect(t) for t in self.toys.toys if t.kind in ("ball", "plush")]
        rects += self._puke_rects()
        if not self._status_rect().isNull():
            rects.append(self._status_rect())
        return [r for r in rects if not r.isNull()]

    def update_input_masks(self, force: bool = False) -> None:
        """Wayland input regions: clicks reach us only over cats and things;
        while placing or arranging, the front window takes the whole screen."""
        nowhere = QRegion(QRect(-9, -9, 1, 1))
        if self._placing or self._arranging:
            front = QRegion()                       # no mask = everything
        else:
            ox, oy = self._origin()
            front = QRegion()
            for r in self.interactive_rects("front"):
                front += r.translated(-ox, -oy)
            if front.isEmpty():
                front = nowhere
        back_rects = self.interactive_rects("back")
        masks = [(self, front)]
        for layer in self.furniture_layers:
            reg = QRegion()
            for r in back_rects:
                reg += r.translated(-layer._ox, -layer._oy)
            reg = reg.intersected(QRegion(layer.rect()))
            masks.append((layer, nowhere if reg.isEmpty() else reg))
        key = tuple((id(w), tuple((r.x(), r.y(), r.width(), r.height()) for r in reg))
                    for w, reg in masks)
        if not force and key == getattr(self, "_mask_key", None):
            return
        self._mask_key = key
        for w, reg in masks:
            handle = w.windowHandle()
            if handle is not None:
                handle.setMask(reg)
                w.update()      # the region is committed with the next frame

    def handle_click(self, x: float, y: float, button, global_pos, widget) -> None:
        """A click on a cat or a thing (world coords). Right: its menu.
        Left on a cat: a pet."""
        thing = self.thing_at(x, y)
        if thing is None:
            return
        if button == Qt.MouseButton.RightButton:
            if self.context_requested is not None:
                self.context_requested(thing, global_pos, widget)
        elif button == Qt.MouseButton.LeftButton and thing[0] == "cat":
            thing[1].brain.on_stroke(thing[1].body)

    def set_hidden(self, reason: str, on: bool) -> None:
        """Hide every PlasmaCat window while any reason holds ('pause' from
        the tray, 'fullscreen' while a fullscreen window is active). The
        simulation keeps running, so needs go on as usual."""
        hidden_before = bool(self._hidden)
        (self._hidden.add if on else self._hidden.discard)(reason)
        if bool(self._hidden) == hidden_before:
            return
        if self.debug:
            print(f"[dbg] hidden -> {sorted(self._hidden) or 'visible'}")
        windows = [self] + list(self.furniture_layers)
        for w in windows:
            w.setVisible(not self._hidden)
        if not self._hidden:
            self._sync_window_geometry(force=True)
            self._furn_update_all()

    @property
    def hidden(self) -> bool:
        return bool(self._hidden)

    def _notify(self, kind: str, title: str, msg: str) -> None:
        """A desktop notification, if the user wants this kind (System tab).
        Hidden cats (pause, fullscreen) only let the update offer through.
        The kind of the last one shown decides what a click on it does."""
        if self._hidden and kind != "update":
            return
        if self.notify is not None and self.settings.notify.get(kind, True):
            self.last_notify_kind = kind
            self.notify(title, msg)

    # -- furniture management (Control Center → Home) ---------------------------

    FURNITURE = (("food_bowl", "Food bowl", "food_x"),
                 ("water_fountain", "Water fountain", "water_x"),
                 ("scratch_post", "Scratching post", "scratch_x"),
                 ("cat_bed", "Cat bed", "bed_x"),
                 ("cat_grass", "Cat grass", "grass_x"),
                 ("litter_0", "Litter box", "litter_x"),
                 ("cat_tree", "Big cat tree", "tree_x"),
                 ("wheel_stand", "Exercise wheel", "wheel_x"),
                 ("box", "Cardboard box", "box_x"))
    BOWLS = ("food_bowl", "water_fountain")   # movable, never removed

    def furniture_items(self) -> list[tuple[str, str, int | None]]:
        """Every placed piece: (kind, label, shelf index or None)."""
        b = self.cat.brain
        items = [(kind, label, None) for kind, label, attr in self.FURNITURE
                 if getattr(b, attr) is not None]
        items += [("wall_shelf", f"Wall shelf {i + 1}", i) for i in range(len(b.shelves))]
        return items

    def remove_furniture(self, kind: str, index: int | None = None) -> None:
        b = self.cat.brain
        if kind == "wall_shelf":
            if index is not None and 0 <= index < len(b.shelves):
                del b.shelves[index]
        elif kind not in self.BOWLS:
            attr = next(a for k, _l, a in self.FURNITURE if k == kind)
            setattr(b, attr, None)
        self._sync_furniture_platforms()
        self._furn_update_all()

    def add_kitten(self, cust: Customization) -> Cat | None:
        """Tray 'Add kitten': a new stage-0 cat near the cursor."""
        if len(self.cats) >= MAX_CATS:
            return None
        cx, _cy = self.desktop.cursor
        x = min(max(float(cx), self.desktop.floor_x0 + 120),
                self.desktop.floor_x1 - 120)
        kitten = self.add_cat(cust, age=0.0, x=x)
        kitten.brain.sounds.append("mew")
        return kitten

    def _banks_for(self, cat: Cat) -> tuple[SpriteBank, SpriteBank]:
        """The cat's sprite banks, rebuilt when she grows into a new stage
        (the stage drives the sprite proportions, P47)."""
        br, bl, st = self._banks[cat]
        if st != cat.brain.stage:
            br, bl = self._make_banks(cat.cust, cat.brain.stage)
            self._banks[cat] = (br, bl, cat.brain.stage)
        return br, bl

    def _update_active(self) -> None:
        """Track which cat the cursor is with (80 px hysteresis against
        flickering). Control mode follows: you steer the cat you point at."""
        cx, cy = self.desktop.cursor

        def dist(c: Cat) -> float:
            return abs(c.body.x - cx) + 0.5 * abs(c.body.y - cy)

        best = min(self.cats, key=dist)
        if self._active is None:
            self._active = best
        elif best is not self._active and dist(self._active) - dist(best) > 80:
            self._active = best
        for c in self.cats:
            want = self._control_on and c is self._active
            if c.brain.user_control != want:
                c.brain.set_user_control(want)

    # -- customization ---------------------------------------------------------

    def _make_banks(self, cust: Customization,
                    stage: int = 6) -> tuple[SpriteBank, SpriteBank]:
        kwargs = dict(palette=cust.to_palette(), pattern=cust.pattern,
                      device_px=self.device_px, dpr=self._dpr,
                      accessory=cust.collar is not None, stage=stage)
        return (SpriteBank(facing="right", **kwargs),
                SpriteBank(facing="left", **kwargs))

    def _apply_dpr(self, dpr: float) -> None:
        """(Re)build every pixmap for this device pixel ratio so each art
        pixel is a whole number of device pixels (no compositor resampling)."""
        dpr = dpr or 1.0
        if abs(dpr - self._dpr) < 1e-3 and self._props:
            return
        self._dpr = dpr
        # one cell size for everything: cat grid cells and prop cells are
        # the same size, so 1 prop pixel (PROP_DETAIL cells) = 1.5 old cat
        # pixels (DETAIL cells) exactly, as the furniture art was designed
        self.device_px = art_pixel_device(dpr, self.pixel_size, self._size_factor)
        self.prop_device_px = self.device_px
        self.scale = sprites.DETAIL * self.device_px / dpr       # per pose pixel
        self.prop_scale = PROP_DETAIL * self.device_px / dpr     # per prop pixel
        self._props = {name: prop_pixmap(name, self.prop_device_px, dpr)
                       for name in PROP_NAMES}
        for cat in self.cats:
            br, bl = self._make_banks(cat.cust, cat.brain.stage)
            self._banks[cat] = (br, bl, cat.brain.stage)
        if self.cats:
            self._sync_furniture_platforms()
        for layer in getattr(self, "furniture_layers", []):
            layer.refresh()
        self.update()

    def set_pixel_size(self, preference: str) -> None:
        """'fine' | 'normal' | 'chunky' (System tab)."""
        self.pixel_size = preference
        self._dpr = 0.0  # force a rebuild
        self._apply_dpr(self.devicePixelRatioF())

    def set_customization(self, cust: Customization, cat: Cat | None = None) -> None:
        """Re-skin a cat live (default: the cat at the cursor)."""
        cat = cat or self.active
        cat.cust = cust
        if cat is self.cats[0]:
            self.cust = cust
        br, bl = self._make_banks(cust, cat.brain.stage)
        self._banks[cat] = (br, bl, cat.brain.stage)
        self.update()

    def _on_work_areas(self, areas: list[dict]) -> None:
        # refine each floor with Plasma's panel settings (bridge/panels.py)
        if any(a.get("panels") for a in areas):
            from plasmacat.bridge.panels import query_plasma_panels, refine_floor
            plasma = query_plasma_panels()
            areas = [dict(a, h=round(refine_floor(a, plasma) - a["y"])) for a in areas]
        self.desktop.set_work_areas(areas)
        if self.debug:
            print(f"[dbg] work areas -> {areas}")
        # keep the bowls inside the area — but do NOT yank user-placed bowls
        # back to the corner: a floating panel docking/undocking (P43) fires
        # this often, and only the floor height changes then
        for attr, default_off in (("food_x", 110.0), ("water_x", 200.0)):
            x = getattr(self.cat.brain, attr)
            inside = x is not None \
                and self.desktop.floor_x0 + 80 <= x <= self.desktop.floor_x1 - 80
            if not inside:
                setattr(self.cat.brain, attr,
                        self.desktop.floor_x0 + default_off)
        # floor_y may have moved (panel resized/floats/Plasma restart): the
        # furniture platforms must follow or the cat floats beside the
        # bed/wheel (P24)
        self._sync_furniture_platforms()
        # a placed status board must not end up under a grown panel (P42)
        if self.settings.status_pos is not None:
            px, py = self.settings.status_pos
            sx = min(max(px, self.desktop.floor_x0),
                     self.desktop.floor_x1 - STATUS_W)
            sy = min(max(py, 0.0),
                     self.desktop.floor_y_at(px + STATUS_W / 2) - self._status_h())
            if [sx, sy] != self.settings.status_pos:
                self.settings.status_pos = [sx, sy]
                self._furn_update(self._status_rect())

    def _screens_changed(self, _screen) -> None:
        """A monitor was (un)plugged: rebuild the furniture layers so each
        screen has exactly one (P38). The bridge sends the new work areas."""
        for layer in self.furniture_layers:
            layer.hide()
            layer.deleteLater()
        self.furniture_layers = [FurnitureLayer(self, s)
                                 for s in QGuiApplication.screens()]
        self._furn_update_all()

    def _furn_update(self, world_rect: QRect) -> None:
        """Repaint a world-coords region on every furniture layer it touches."""
        for layer in self.furniture_layers:
            cov = QRect(layer._ox, layer._oy, layer.width(), layer.height())
            if cov.intersects(world_rect):
                layer.update(world_rect.translated(-layer._ox, -layer._oy))

    def _furn_update_all(self) -> None:
        for layer in self.furniture_layers:
            layer.update()

    # -- layer logic (P18) ------------------------------------------------------

    def on_back_layer(self, cat: Cat) -> bool:
        """The visibility level is a deliberate brain decision with a 30 s
        dwell (P28): calm states are level-neutral, only committed
        cross-world actions flip it. The overlay just follows brain.level."""
        return cat.brain.level == "back"

    # -- cat door between the levels (P27) -------------------------------------

    def _door_phase(self, cat: Cat) -> float:
        """0..1 while the cat-door animation runs, else -1."""
        d = self._doors.get(cat)
        if d is None:
            return -1.0
        ph = (self._time - d[2]) / DOOR_DUR
        return ph if ph < 1.0 else -1.0

    def _desktop_covered(self, cat: Cat) -> bool:
        """P50/P51: the cat door plays only when the crossing is hidden by a
        (near-)MAXIMIZED window — that's when stepping forward/back is a
        real vanishing/emerging act. Floating windows don't count: she can
        hop onto those, but the level flip stays seamless, no door wanted.
        The bridge reports no maximized flag, so 'maximized' is inferred
        from the geometry: the window must span its work area (±8 px)."""
        cr = self._cat_rect(cat)
        cx, cy = cr.center().x(), cr.center().y()
        for w in self.desktop.windows:
            if not (w["x"] <= cx <= w["x"] + w["w"]
                    and w["y"] <= cy <= w["y"] + w["h"]):
                continue
            for ax, ay, aw, ah in self.desktop.work_areas:
                if w["x"] <= ax + 8 and w["y"] <= ay + 8 \
                        and w["x"] + w["w"] >= ax + aw - 8 \
                        and w["y"] + w["h"] >= ay + ah - 8:
                    return True  # a (near-)maximized window hides her here
        return False

    def cat_layer(self, cat: Cat) -> str | None:
        """Which layer draws the cat this frame — or None while she passes
        through the door. The logical layer flips instantly (on_back_layer);
        the door makes the crossing visible: old side -> inside -> new side."""
        back = self.on_back_layer(cat)
        ph = self._door_phase(cat)
        if ph < 0:
            return "back" if back else "front"
        if 0.25 <= ph < 0.65:
            return None  # inside the door
        d = self._doors[cat]
        if ph < 0.25:
            return "front" if d[3] == "in" else "back"  # old side
        return "back" if back else "front"                       # new side

    def current_cat(self, cat: Cat):
        """The cat's current frame + accessory + rects, for the layer that
        draws her this tick."""
        bank_r, bank_l = self._banks_for(cat)
        bank = bank_r if cat.body.facing >= 0 else bank_l
        key = self._anim_key(cat)
        idx = cat.frame % bank.frame_count(key)
        return (bank.frame(key, idx), bank.accessory_frame(key, idx),
                self._cat_rect(cat), self._bubble_rect(cat), cat.brain.bubble)

    # -- geometry -------------------------------------------------------------

    def _anim_key(self, cat: Cat) -> str:
        """Animation state + blink + mood-dependent tail variant (P12a/P8g)."""
        state = cat.anim_state
        if cat.blink_active and state in ("stand", "sit", "loaf"):
            return state + "_blink"     # same pose, eyes closed
        if state in ("stand", "walk"):
            mood = cat.brain.mood
            if mood < 40:
                return state + ":low"   # grumpy: tail low
            if mood < 70:
                return state + ":mid"   # neutral: tail horizontal
        return state                    # content/happy: tail up (default)

    def _cat_rect(self, cat: Cat) -> QRect:
        bank_r, _bank_l = self._banks_for(cat)
        pm = bank_r.frame(self._anim_key(cat), 0)
        return QRect(int(cat.body.x) - lw(pm) // 2,
                     int(cat.body.y) - lh(pm), lw(pm), lh(pm))

    def _bubble_rect(self, cat: Cat) -> QRect:
        if not cat.brain.bubble:
            return QRect()
        pm = self._props[cat.brain.bubble]
        cr = self._cat_rect(cat)
        bob = int(2.5 * math.sin(self._time * 3.0))
        return QRect(cr.center().x() - lw(pm) // 2,
                     cr.top() - lh(pm) - 6 + bob, lw(pm), lh(pm))

    def _bowl_rect(self, x: float, name: str) -> QRect:
        pm = self._props[name]
        return QRect(int(x) - lw(pm) // 2,
                     int(self.desktop.floor_y_at(x)) - lh(pm),
                     lw(pm), lh(pm))

    def _floor_props(self) -> list[tuple[float, str]]:
        """All static floor items: bowls (fill-aware) + P9/P25 furniture."""
        brain = self.cat.brain
        out: list[tuple[float, str]] = []
        if brain.food_x is not None:
            out.append((brain.food_x,
                        "food_bowl" if brain.food_fill > 25 else "food_bowl_empty"))
        if brain.water_x is not None:
            # the perpetual fountain (P25): animated, never runs dry
            out.append((brain.water_x,
                        f"fountain_{int(self._time * 2.5) % 3}"))
        for px in brain.puke_spots:
            out.append((px, "puke"))
        if brain.scratch_x is not None:
            out.append((brain.scratch_x, "scratch_post"))
        if brain.bed_x is not None:
            out.append((brain.bed_x, "cat_bed"))
        if brain.grass_x is not None:
            out.append((brain.grass_x, "cat_grass"))
        if brain.litter_x is not None:
            # always the clean base tray: every deposit is drawn on top as
            # its own visible pile (P40), not via coarse fill-level variants
            out.append((brain.litter_x, "litter_0"))
        if brain.tree_x is not None:
            out.append((brain.tree_x, "cat_tree"))
        if brain.box_x is not None:
            out.append((brain.box_x, "box"))
        return out

    def _wheel_rect(self) -> QRect:
        pm = self._props["wheel_stand"]
        return QRect(int(self.cat.brain.wheel_x) - lw(pm) // 2,
                     int(self.desktop.floor_y_at(self.cat.brain.wheel_x)) - lh(pm),
                     lw(pm), lh(pm))

    def _box_rect(self) -> QRect:
        pm = self._props["box"]
        return QRect(int(self.cat.brain.box_x) - lw(pm) // 2,
                     int(self.desktop.floor_y_at(self.cat.brain.box_x)) - lh(pm),
                     lw(pm), lh(pm))

    def _shelf_rects(self) -> list[QRect]:
        """Screen rects of the floating wall shelves (P25)."""
        pm = self._props["wall_shelf"]
        return [QRect(int(x) - lw(pm) // 2, int(y), lw(pm), lh(pm))
                for x, y in self.cat.brain.shelves]

    def _fountain_rect(self) -> QRect:
        if self.cat.brain.water_x is None:
            return QRect()
        return self._bowl_rect(self.cat.brain.water_x, "fountain_0")

    def _litter_deposit_rects(self) -> list[tuple[QRect, str]]:
        """Each poop/pee as a visible pile in the tray (P40), deterministically
        scattered so existing piles never jump around between events."""
        brain = self.cat.brain
        if brain.litter_x is None:
            return []
        br = self._bowl_rect(brain.litter_x, "litter_0")
        out: list[tuple[QRect, str]] = []
        for i, kind in enumerate(brain.litter_deposits):
            pm = self._props["litter_poop" if kind == "poop" else "litter_pee"]
            ox = ((i * 23) % 57) - 28          # -28..+28 across the tray
            oy = 10 + ((i * 7) % 8)            # slight depth variation
            out.append((QRect(br.center().x() + ox - lw(pm) // 2,
                              br.bottom() - oy - lh(pm),
                              lw(pm), lh(pm)), kind))
        return out

    def _door_rect(self, cat: Cat) -> QRect:
        d = self._doors.get(cat)
        if d is None:
            return QRect()
        pm = self._props["cat_door_0"]
        return QRect(int(d[0]) - lw(pm) // 2,
                     int(d[1]) - lh(pm), lw(pm), lh(pm))

    @staticmethod
    def _toy_front(toy) -> bool:
        """Layer rule (P42): cursor tools (string, laser) and carried toys
        are front-overlay content; resting floor toys (ball, plush, …) live
        on the desktop (back) level together with the furniture they lie on."""
        return toy.kind in ("string", "laser") or getattr(toy, "carried", False)

    def _toy_rects(self, layer: str | None = None) -> list[QRect]:
        rects = []
        for toy in self.toys.toys:
            if layer == "front" and not self._toy_front(toy):
                continue
            if layer == "back" and self._toy_front(toy):
                continue
            # a runaway/out-of-world toy must never kill the tick (P25)
            if not (math.isfinite(toy.x) and math.isfinite(toy.y)):
                continue
            if abs(toy.x) > 10000 or abs(toy.y) > 10000:
                continue
            if toy.kind == "laser" and not toy.visible:
                continue  # the dot blinked out after being caught (P34)
            pm = self._props["lure" if toy.kind == "string"
                             else "laser_dot" if toy.kind == "laser"
                             else toy.kind]
            if toy.kind in ("string", "laser"):  # center-aligned
                rects.append(QRect(int(toy.x) - lw(pm) // 2,
                                   int(toy.y) - lh(pm) // 2,
                                   lw(pm), lh(pm)))
            else:
                rects.append(QRect(int(toy.x) - lw(pm) // 2,
                                   int(toy.y) - lh(pm),
                                   lw(pm), lh(pm)))
            if toy.kind == "string":
                ax, ay = toy.anchor
                rects.append(QRect(int(min(ax, toy.x)) - 4, int(min(ay, toy.y)) - 4,
                                   int(abs(ax - toy.x)) + 8, int(abs(ay - toy.y)) + 8))
        return rects

    # -- simulation ---------------------------------------------------------

    def _on_cursor(self, x: int, y: int) -> None:
        self.desktop.set_cursor(x, y)
        self._tracker.add(x, y)

    def _layer_regions(self) -> tuple[QRect, QRect]:
        """World rects covered by front-layer and back-layer content (cats,
        bubbles, cat doors, toys, the placement ghost). Layer-specific: a
        far-away floor toy must not stretch the front window's dirty region."""
        front = self._ghost_rect()
        back = QRect()
        for cat in self.cats:
            r = self._cat_rect(cat).united(self._bubble_rect(cat)) \
                .united(self._door_rect(cat))
            if self.cat_layer(cat) == "back":
                back = back.united(r)
            else:
                front = front.united(r)
        for r in self._toy_rects("front"):
            front = front.united(r)
        for r in self._toy_rects("back"):
            back = back.united(r)
        return front, back

    def _tick(self) -> None:
        dt = min(self._clock.restart() / 1000.0, 0.1)
        if dt <= 0.0:
            return  # zero-length frame (same-millisecond reentry): nothing to do
        self._time += dt
        # the front window may have moved to a screen with another scale
        self._apply_dpr(self.devicePixelRatioF())
        old_front, old_back = self._layer_regions()

        if (self._placing or self._arranging) and self._time - self._place_since > 60.0:
            self._end_placement()  # auto-cancel dangling placement
        if any(c.brain.state == "wheel_run" for c in self.cats):
            self._wheel_angle = (self._wheel_angle + 200.0 * dt) % 360.0

        self.desktop.cursor_active = self._tracker.idle_for() < 2.0
        self.desktop.cursor_speed = self._tracker.speed(time.monotonic())
        # greeting when the human returns after >60 s away
        if self.desktop.cursor_active:
            if self._inactive_since is not None:
                if self._time - self._inactive_since > 60.0:
                    for cat in self.cats:
                        cat.brain.on_user_return(cat.body, self.desktop)
                self._inactive_since = None
        elif self._inactive_since is None:
            self._inactive_since = self._time
        self._update_active()
        # interactions: every cat has its own detector on the shared tracker
        cx, cy = self.desktop.cursor
        live = {id(c) for c in self.cats}
        for key in [k for k in self._detectors if k not in live]:
            del self._detectors[key]  # a removed cat
        for cat in ([] if self._hidden else self.cats):   # hidden: no reactions
            det = self._detectors.setdefault(
                id(cat), InteractionDetector(self._tracker))
            rect = self._cat_rect(cat)
            events = det.tick(
                dt, (rect.x(), rect.y(), rect.width(), rect.height()),
                self.desktop.cursor)
            for ev in events:
                if self.debug:
                    print(f"[interact] {ev} speed={self.desktop.cursor_speed:.0f} "
                          f"state={cat.brain.state}")
                if ev == "stroke":
                    cat.brain.on_stroke(cat.body)
                elif ev == "rub":
                    cat.brain.on_rub(cat.body)
                elif ev == "hunt":
                    cat.brain.on_hunt_trigger(cat.body, self.desktop.cursor,
                                              self.desktop)
                elif ev == "startle":
                    cat.brain.on_startle(cat.body, self.desktop)
                elif ev == "pat":
                    cat.brain.on_pat(cat.body, self.desktop.cursor)

        self.household.tick(dt)   # shared timers advance once, not per cat
        for cat in self.cats:
            cat.tick(dt, self.desktop)
        fx_sounds: list[str] = []  # toy/hunt intents, not tied to one brain
        self.toys.tick(dt, self.desktop, self.cats, fx_sounds)
        if self._hunt is not None:  # P42 mini-game session
            self._hunt.tick(dt, self.desktop, self.cats, self.toys, fx_sounds)
            if not self._hunt.active:
                self._notify("games", "Mouse hunt",
                             f"Time! Your cats caught {self._hunt.score} "
                             f"{'mouse' if self._hunt.score == 1 else 'mice'}.")
                self._hunt = None
                self._furn_update_all()  # the leftover mice scurry off

        # adaptive frame rate: 30 fps while anything moves, 15 fps when the
        # cat idles (P12c — the fullscreen Wayland surface copy is the cost
        # driver; pixel animations run at 8-12 fps anyway)
        interval = 33 if self._is_active() else 66
        if self._timer.interval() != interval:
            self._timer.setInterval(interval)
            if self.debug:
                print(f"[perf] interval -> {interval} ms")

        if self.debug:
            self._dbg_t += dt
            if self._dbg_t >= 1.0:
                self._dbg_t = 0.0
                r = self._cat_rect(self.cat)
                inside = (r.x() <= cx <= r.x() + r.width()
                          and r.y() <= cy <= r.y() + r.height())
                print(f"[dbg] cursor=({cx},{cy}) cat=({r.x()},{r.y()},{r.width()},"
                      f"{r.height()}) inside={inside} "
                      f"speed={self.desktop.cursor_speed:.0f} "
                      f"cats={len(self.cats)} "
                      f"catworld=({self.cat.body.x:.0f},{self.cat.body.y:.0f})")

        if self.player and not self._hidden:   # hidden cats are silent
            for cat in self.cats:
                for sound in cat.brain.sounds:
                    self.player.play(sound)
            for sound in fx_sounds:
                self.player.play(sound)
        for cat in self.cats:
            cat.brain.sounds.clear()

        # only repaint when something visible actually changed (P12c)
        sig = self._signature()
        furn_sig = (self.cat.brain.food_fill > 25,
                    round(self.cat.brain.litter_fill),
                    len(self.cat.brain.litter_deposits),
                    len(self.cat.brain.puke_spots),
                    self.cat.brain.food_x, self.cat.brain.water_x,
                    self.cat.brain.scratch_x, self.cat.brain.bed_x,
                    self.cat.brain.grass_x, self.cat.brain.litter_x,
                    self.cat.brain.tree_x, self.cat.brain.wheel_x,
                    self.cat.brain.box_x, tuple(self.cat.brain.shelves))
        if furn_sig != self._last_furn_sig:
            self._last_furn_sig = furn_sig
            self._furn_update_all()
        # the fountain ripples on its own cheap repaint schedule (P25):
        # only its small region, not the whole back layer
        if self.cat.brain.water_x is not None:
            fframe = int(self._time * 2.5) % 3
            if fframe != self._last_fountain_frame:
                self._last_fountain_frame = fframe
                self._furn_update(self._fountain_rect())
        # the pinned status board (P42) repaints only its own region
        status_sig = self._status_sig()
        if status_sig != self._last_status_sig:
            self._last_status_sig = status_sig
            self._furn_update(self._status_rect())
        # user notifications (P25): full litter box / vomit on the floor
        for cat in self.cats:
            st = cat.brain.state
            if st == "litter_beg" \
                    and self._prev_brain_state.get(cat) != "litter_beg":
                self._notify("litter", "PlasmaCat", f"{cat.cust.name}: the litter "
                             "box is full — please clean it!")
        if len(self.cat.brain.puke_spots) > self._prev_puke_count:
            self._notify("vomit", "PlasmaCat", "A cat vomited on the floor — "
                         "clean it up (Control Center → Home)!")
        self._prev_brain_state = {c: c.brain.state for c in self.cats}
        self._prev_puke_count = len(self.cat.brain.puke_spots)
        new_front, new_back = self._layer_regions()
        moving = any(c.body.airborne or c.body.target_x is not None
                     for c in self.cats)
        if sig != self._last_sig:
            self._last_sig = sig
            if self._placing:
                self.update()  # ghost + hint cover the whole screen area anyway
            # P32: KWin drops partial shm damage for this translucent window
            # at fractional scaling (measured: trail fragments at the sprite's
            # top rows; a full repaint clears them). While the cat moves, force
            # a full repaint every 3rd tick (~0.1 s trails = invisible motion
            # blur) and once when she stops; cheap region updates otherwise.
            self._move_ticks = self._move_ticks + 1 if moving else 0
            if (moving and self._move_ticks % 3 == 0) \
                    or (not moving and self._prev_moving):
                self.update()
            else:
                ox, oy = self._origin()
                self.update(old_front.united(new_front).adjusted(6, 6, 6, 6)
                            .translated(-ox, -oy))
            self._prev_moving = moving
        # the cats move between layers: keep the back layer in sync, and let
        # them pass through the cat door (P27) whenever the level flips —
        # but only where a window actually covers the crossing point (P50):
        # on visible desktop the flip is seamless, so the door is pointless
        for cat in self.cats:
            back = self.on_back_layer(cat)
            if back != self._prev_back.get(cat, False):
                if self._desktop_covered(cat):
                    self._doors[cat] = (cat.body.x, cat.body.y, self._time,
                                        "in" if back else "out")
            self._prev_back[cat] = back
        for cat in list(self._doors):
            if self._time - self._doors[cat][2] >= DOOR_DUR:
                del self._doors[cat]
        any_back = any(self.on_back_layer(c) for c in self.cats)
        # floor toys on the back layer (P42): their motion repaints there too
        back_toy_sig = tuple((t.kind, round(t.x), round(t.y))
                             for t in self.toys.toys if not self._toy_front(t))
        back_toys_changed = back_toy_sig != self._last_back_toy_sig
        self._last_back_toy_sig = back_toy_sig
        back_toy_moving = any(not self._toy_front(t)
                              and (abs(t.vx) > 1 or abs(t.vy) > 1)
                              for t in self.toys.toys)
        # P49 back-layer gating: repaint ONLY when back content actually
        # changed. Before, any back-level cat (even a perfectly still one)
        # repainted her region every tick, and breath frames / the bobbing
        # zzz bubble kept rewriting the same slice — at fractional scaling
        # KWin drops partial damage (P32), which showed up as the furniture
        # under a sleeping cat visibly "trembling".
        back_sig = tuple(
            (self._anim_key(c), c.frame, int(c.body.x), int(c.body.y),
             c.body.facing, c.brain.bubble,
             int(2.5 * math.sin(self._time * 3.0)) if c.brain.bubble else 0)
            for c in self.cats if self.cat_layer(c) != "front")
        back_changed = back_sig != self._last_back_sig
        self._last_back_sig = back_sig
        furn_moving = ((moving and any_back) or back_toy_moving or back_changed)
        self._furn_move_ticks = self._furn_move_ticks + 1 if furn_moving else 0
        if back_changed or back_toys_changed or self._doors:
            if (furn_moving and self._furn_move_ticks % 3 == 0) \
                    or (not furn_moving and self._prev_furn_moving):
                self._furn_update_all()  # P32 full flush on the back layer
            else:
                self._furn_update(old_back.united(new_back).adjusted(6, 6, 6, 6))
        self._prev_furn_moving = furn_moving
        # the exercise wheel spins on THIS layer: repaint its rect every tick
        # while she runs (P46) — the ring is symmetric, only the red marker
        # shows the angle, and it lives OUTSIDE the cat's repaint region, so
        # region updates never showed the rotation
        if any(c.brain.state == "wheel_run" for c in self.cats) \
                and self.cat.brain.wheel_x is not None:
            self._furn_update(self._wheel_rect())
        self._sync_window_geometry()
        self.update_input_masks()
        if self.debug:
            self.update()  # platform lines may change anytime

    # -- furniture platforms -----------------------------------------------------

    def _sync_furniture_platforms(self) -> None:
        """Furniture contributes jumpable platforms (props.FURNITURE_SURFACES):
        cat-tree levels, the scratching-post top, the bed cushion, the
        wheel's inner track, the box floor — plus the wall shelves."""
        from plasmacat.bridge.desktop import Platform
        from plasmacat.world.props import furniture_surfaces

        b = self.cat.brain
        plats = []
        for kind, x in (("cat_tree", b.tree_x), ("scratch_post", b.scratch_x),
                        ("cat_bed", b.bed_x), ("wheel_stand", b.wheel_x),
                        ("box", b.box_x)):
            if x is not None:
                plats += [Platform(x0, x1, y, label) for x0, x1, y, label in
                          furniture_surfaces(kind, x, self.desktop.floor_y_at(x),
                                             self.prop_scale)]
        for sx, sy in self.cat.brain.shelves:
            # floating wall shelves: fixed at their placed height (P25)
            plats.append(Platform(sx - 60, sx + 60, sy, "Regal"))
        self.desktop.set_extra_platforms(plats)


    # -- user control mode (P42) -------------------------------------------------

    def _on_key_event(self, name: str) -> None:
        self.active.brain.on_key_event(name)

    def set_user_control(self, on: bool) -> None:
        """Tray toggle: WASD/arrows drive the ACTIVE cat (the one nearest the
        cursor, P47). The bridge registers the global shortcuts only while
        the mode is on (they grab keys system-wide — no shortcuts, no
        steering)."""
        self._control_on = on
        self._update_active()  # the user_control flags follow the active cat
        self._bridge.set_control_mode(on)

    # -- mini-games (P42) ---------------------------------------------------------

    def start_mouse_hunt(self) -> None:
        """Tray 'Games → Mouse hunt': 60 s of mice, catch up to 8."""
        from plasmacat.cat.minigames import MouseHunt
        if self._hunt is not None:
            return  # a hunt is already running
        self._hunt = MouseHunt(rng=random.Random())
        self._notify("games", "Mouse hunt", "Mice are loose! Catch 8 in 60 seconds.")

    # -- toys (called from the tray menu) --------------------------------------

    def toggle_string(self, on: bool) -> None:
        if on:
            cx, cy = self.desktop.cursor
            self.toys.spawn("string", float(cx), float(cy + 150))
        else:
            self.toys.remove("string")
            self.update()  # removal happens outside the tick: repaint now,
                           # or the last frame lingers in the buffer (P42)

    def toggle_laser(self, on: bool) -> None:
        """Tray toggle: the laser-pointer dot at the cursor (P34)."""
        if on:
            cx, cy = self.desktop.cursor
            self.toys.spawn("laser", float(cx), float(cy))
            self.active.brain.sounds.append("chirp")  # get her attention
        else:
            self.toys.remove("laser")
            for cat in self.cats:
                if cat.brain.state in ("laser_chase", "laser_pounce"):
                    cat.brain.state = "idle"
                    cat.brain.state_left = 0.0
            self.update()  # see toggle_string

    def clear_toys(self) -> None:
        """Tray 'Clear toys': drop every toy on BOTH layers and repaint —
        removals outside the tick never covered the toy's last drawn region
        and left ghost pixels in the translucent buffers (P42). Also drops
        toy-targeting brain states and syncs the tray checkmarks."""
        self.toys.toys.clear()
        for cat in self.cats:
            cat.brain.clear_toy_state()
        self._hunt = None  # an active mouse hunt ends with its mice (P42)
        for act in (getattr(self, "_string_action", None),
                    getattr(self, "_laser_action", None)):
            if act is not None and act.isChecked():
                act.setChecked(False)  # keep the tray toggles in sync
        self.update()
        self._furn_update_all()

    def _signature(self) -> tuple:
        """Everything that can change what's on screen. Repaint only on change."""
        per_cat = []
        for c in self.cats:
            per_cat.append((
                self._anim_key(c), c.frame, int(c.body.x), int(c.body.y),
                c.body.facing, c.brain.bubble, c.blink_active,
                self.cat_layer(c), c.brain.stage,
                # the bubble's bob phase: missing this caused stale streaks
                int(2.5 * math.sin(self._time * 3.0)) if c.brain.bubble else 0,
            ))
        return (
            tuple(per_cat), self._placing, self._arranging,
            # only FRONT toys: floor toys on the back layer have their own
            # back_toy_sig and must not repaint this window (P42). Carried
            # flips + laser blink (visible) change the pixels without
            # moving, so they are part of the signature too.
            tuple((t.kind, round(t.x), round(t.y), bool(getattr(t, "carried", False)),
                   getattr(t, "visible", True))
                  for t in self.toys.toys if self._toy_front(t)),
            round(self._wheel_angle), self.cat.brain.wheel_x,
            # the cat door animation frames (P27)
            tuple(int(self._door_phase(c) * 5) if self._door_phase(c) >= 0 else -1
                  for c in self._doors),
        )

    def _is_active(self) -> bool:
        if self._placing or self._arranging or self._doors:
            return True  # placement + door flaps must animate smoothly (P27)
        for cat in self.cats:
            b = cat.body
            if b.airborne or b.target_x is not None or cat.blink_active:
                return True
            if cat.brain.user_control:
                return True  # P42: steering must stay at 30 fps
            if cat.anim_state in ("walk", "run", "jump", "scratch", "wiggle",
                                  "tail_lash", "knead", "cover", "drink",
                                  "stretch", "yawn", "retch"):
                return True
            if cat.brain.state in ("wheel_run", "hunt_pounce", "hunt_stalk",
                                   "scratching", "startle_air"):
                return True
        if any(abs(t.vx) > 1 or abs(t.vy) > 1 for t in self.toys.toys):
            return True
        # interactions near a cat stay responsive even when she idles
        cx, cy = self.desktop.cursor
        near = any(abs(cx - c.body.x) < 300 and abs(cy - c.body.y) < 300
                   for c in self.cats)
        return near and self.desktop.cursor_active

    # -- drawing ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        p = QPainter(self)
        # P30: never leave Qt's painter active after an exception — a wedged
        # backing store segfaults in the Wayland flush (see FurnitureLayer)
        try:
            region = event.rect()
            # Explicitly clear the dirty region ourselves: Qt's pre-paint clear of
            # translucent widgets leaves subpixel residue at the trailing edge on
            # this setup (fractional scaling), which showed up as a "tail trail".
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(region, QColor(0, 0, 0, 0))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            # P37: the window shows only a slice of the world — everything
            # below is drawn in world coordinates, translated by the window's
            # world position ((0,0) while fullscreen in placement mode)
            ox, oy = self._origin()
            p.translate(-ox, -oy)
            if self.debug:
                p.setPen(QPen(QColor(0, 255, 0, 160), 2))
                for plat in self.desktop.platforms:
                    p.drawLine(int(plat.x0), int(plat.y), int(plat.x1), int(plat.y))
            # (exercise wheel lives entirely on the FurnitureLayer since P23)
            # cats (only the front-level ones; the FurnitureLayer draws the
            # ones that have stepped back to the furniture level)
            for cat in self.cats:
                if self.cat_layer(cat) != "front":
                    continue
                frame, acc, cr, br, bubble = self.current_cat(cat)
                p.drawPixmap(cr.x(), cr.y(), frame)
                if acc is not None:
                    p.drawPixmap(cr.x(), cr.y(), acc)
                # thought bubble (front level only; the back level draws it
                # with the cat)
                if bubble:
                    p.drawPixmap(br.x(), br.y(), self._props[bubble])
            # (wheel front arc is drawn on the FurnitureLayer with the wheel)
            # toys — only the front layer's share (string/laser/carried, P42);
            # resting floor toys are drawn by the FurnitureLayer behind windows
            for toy in self.toys.toys:
                if not self._toy_front(toy):
                    continue
                if not (math.isfinite(toy.x) and math.isfinite(toy.y)) \
                        or abs(toy.x) > 10000 or abs(toy.y) > 10000:
                    continue  # out-of-world toy: never crash the paint (P25)
                if toy.kind == "laser" and not toy.visible:
                    continue  # dot blinked out after a catch (P34)
                if toy.kind == "string":
                    ax, ay = toy.anchor
                    p.setPen(QPen(QColor(240, 210, 90, 220), 2))
                    p.drawLine(int(ax), int(ay), int(toy.x), int(toy.y))
                    pm = self._props["lure"]
                    p.drawPixmap(int(toy.x) - lw(pm) // 2,
                                 int(toy.y) - lh(pm) // 2, pm)
                elif toy.kind == "laser":
                    pm = self._props["laser_dot"]
                    p.drawPixmap(int(toy.x) - lw(pm) // 2,
                                 int(toy.y) - lh(pm) // 2, pm)
                else:
                    pm = self._props[toy.kind]
                    p.drawPixmap(int(toy.x) - lw(pm) // 2,
                                 int(toy.y) - lh(pm), pm)
            # thought bubbles are drawn with their cats above (front level)
            # the cat doors (P27): a flapping portal at the crossing point
            for cat, d in self._doors.items():
                ph = self._door_phase(cat)
                if ph < 0:
                    continue
                frame = ("cat_door_0", "cat_door_1", "cat_door_2",
                         "cat_door_2", "cat_door_1")[min(int(ph * 5), 4)]
                pm = self._props[frame]
                p.drawPixmap(int(d[0]) - lw(pm) // 2, int(d[1]) - lh(pm), pm)
            # placement ghost + hint
            if self._arranging and not self._placing:
                hit = self._prop_at(*self.desktop.cursor)
                if hit is not None:      # highlight what a click would pick up
                    p.setPen(QPen(QColor(120, 200, 255), 2, Qt.PenStyle.DashLine))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(self._prop_rect(*hit).adjusted(-4, -4, 4, 4))
            if self._placing:
                gr = self._ghost_rect()
                p.setOpacity(0.65)
                if self._placing == "status":  # no pixmap: panel outline
                    p.fillRect(gr, QColor(20, 20, 26, 205))
                else:
                    key = {"water_fountain": "fountain_0"}.get(self._placing,
                                                               self._placing)
                    p.drawPixmap(gr.x(), gr.y(), self._props[key])
                p.setOpacity(1.0)
            if self._placing or self._arranging:
                hint = ("Click to put it down  ·  Right-click or Esc cancels"
                        if self._placing else
                        "Click a piece to move it  ·  Del removes the one under the "
                        "cursor  ·  Right-click or Esc: done")
                fm = p.fontMetrics()
                tw = fm.horizontalAdvance(hint)
                hx = (self.width() - tw) // 2
                p.fillRect(hx - 12, 34, tw + 24, 26, QColor(20, 20, 26, 200))
                p.setPen(QColor(240, 240, 240))
                p.drawText(hx, 52, hint)
        except Exception as exc:
            print(f"[paint] overlay error: {exc!r}")
        finally:
            p.end()
