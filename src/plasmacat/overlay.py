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

from PySide6.QtCore import QElapsedTimer, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from plasmacat.bridge.desktop import DesktopState
from plasmacat.cat.brain import Household
from plasmacat.cat.cat import Cat
from plasmacat.cat.interactions import InteractionDetector
from plasmacat.cat.minigames import MouseHunt
from plasmacat.cat.render import SpriteBank, prop_pixmap
from plasmacat.cat.toys import ToyManager
from plasmacat.persist import Customization

SCALE_MIN = 2
FPS_MS = 16
MAX_CATS = 4  # P47: household size cap (each cat costs a brain + a sprite bank)

# P37 small-window policy (see module docstring)
WIN_MIN_W = 240
WIN_MIN_H = 180
WIN_MARGIN = 24         # breathing room around the content bbox
WIN_SHRINK_DELAY = 5.0  # seconds of small content before the window shrinks
WIN_SHRINK_FRAC = 0.6   # … to below this fraction of the window size

# P42 pinned status board (painted on the FurnitureLayer, display-only)
STATUS_W = 250
STATUS_H = 32 + 8 * 17 + 8  # title + 8 bar rows + bottom margin


class FurnitureLayer(QWidget):
    """Desktop-level layer rendered BEHIND all windows (keepBelow, tagged by
    the bridge via its window title): bowls and static furniture. One instance
    per screen (P38), each showing the world slice of its screen. Repainted
    only when its content changes."""

    def __init__(self, overlay: "Overlay", screen, parent=None) -> None:
        super().__init__(parent)
        self.o = overlay
        self._ox = screen.geometry().x()   # the screen's world position (P38)
        self._oy = screen.geometry().y()
        self.setWindowTitle("plasmacat-furniture")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.winId()  # realize so windowHandle() exists for setScreen
        if self.windowHandle() is not None:
            self.windowHandle().setScreen(screen)
        self.showFullScreen()

    def refresh(self) -> None:
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        o = self.o
        p = QPainter(self)
        # P30: an exception mid-paint leaves Qt's painter active and wedges
        # the Wayland backing store (observed: SIGSEGV in finalizeBackBuffer
        # after the out-of-world toy OverflowErrors). finally: always end it.
        try:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(event.rect(), QColor(0, 0, 0, 0))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            # everything below is drawn in world coordinates, translated by
            # this screen's world position (P38)
            p.translate(-self._ox, -self._oy)
            region = event.rect().translated(self._ox, self._oy)
            # 1. static furniture (bowls, post, tree, bed, grass, litter, box…)
            for name, x in ((n, fx) for fx, n in o._floor_props()):
                br = o._bowl_rect(x, name)
                if region.intersects(br):
                    p.drawPixmap(br.x(), br.y(), o._props[name])
            # 1b. floating wall shelves (P25): fixed to the 'wall', any height
            for sr in o._shelf_rects():
                if region.intersects(sr):
                    p.drawPixmap(sr.x(), sr.y(), o._props["wall_shelf"])
            # 1c. litter deposits (P40): every poop/pee visible in the tray
            for dr, kind in o._litter_deposit_rects():
                if region.intersects(dr):
                    pm = o._props["litter_poop" if kind == "poop" else "litter_pee"]
                    p.drawPixmap(dr.x(), dr.y(), pm)
            # 1d. floor toys (ball/plush/…): desktop level like the furniture
            # they rest on. Only cursor tools + carried toys stay front (P42).
            for toy in o.toys.toys:
                if o._toy_front(toy):
                    continue
                if not (math.isfinite(toy.x) and math.isfinite(toy.y)) \
                        or abs(toy.x) > 10000 or abs(toy.y) > 10000:
                    continue
                pm = o._props[toy.kind]
                tr = QRect(int(toy.x) - pm.width() // 2,
                           int(toy.y) - pm.height(), pm.width(), pm.height())
                if region.intersects(tr):
                    p.drawPixmap(tr.x(), tr.y(), pm)
            # 2. exercise wheel: static stand, then rim rotating around the axle —
            #    the full illusion lives on THIS layer (P23)
            if o.cat.brain.wheel_x is not None:
                wr = o._wheel_rect()
                if region.intersects(wr):
                    cxm = wr.x() + 32 * o.prop_scale   # rim center (canvas 32,34)
                    cym = wr.y() + 34 * o.prop_scale
                    p.drawPixmap(wr.x(), wr.y(), o._props["wheel_stand"])
                    p.save()
                    p.translate(cxm, cym)
                    # clockwise (positive in Qt's y-down space): the bottom
                    # surface moves left, matching the right-facing runner
                    # (was counterclockwise = visibly backwards, P46)
                    p.rotate(o._wheel_angle)
                    p.translate(-cxm, -cym)
                    p.drawPixmap(wr.x(), wr.y(), o._props["wheel_rim"])
                    p.restore()
            # 3. the cats that have "stepped back" to this level (P47: loop)
            for cat in o.cats:
                if o.cat_layer(cat) != "back":
                    continue
                frame, acc, cr, br_b, bubble = o.current_cat(cat)
                p.drawPixmap(cr.x(), cr.y(), frame)
                if acc is not None:
                    p.drawPixmap(cr.x(), cr.y(), acc)
                if bubble:
                    p.drawPixmap(br_b.x(), br_b.y(), o._props[bubble])
            # 4. wheel front arc / box front wall over the cat (inside illusion)
            if o.cat.brain.wheel_x is not None:
                wr = o._wheel_rect()
                if region.intersects(wr):
                    p.drawPixmap(wr.x(), wr.y(), o._props["wheel_front"])
            if o.cat.brain.box_x is not None:
                br2 = o._box_rect()
                if region.intersects(br2):
                    p.drawPixmap(br2.x(), br2.y(), o._props["box_front"])
            # 6. the pinned status board (P42): display-only panel
            sr = o._status_rect()
            if not sr.isNull() and region.intersects(sr):
                o._paint_status(p)
        except Exception as exc:
            print(f"[paint] furniture layer error: {exc!r}")
        finally:
            p.end()


DOOR_DUR = 0.9  # seconds for the cat-door transition flourish (P27)


class Overlay(QWidget):
    def __init__(self, bridge, player=None, cust: Customization | None = None,
                 debug: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("plasmacat")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        screen = QGuiApplication.primaryScreen().geometry()
        self.desktop = DesktopState(screen.width(), screen.height())
        if debug:
            scr = QGuiApplication.primaryScreen()
            print(f"[dbg] Qt screen geometry={screen.width()}x{screen.height()} "
                  f"dpr={scr.devicePixelRatio()} virtual={scr.virtualGeometry().getRect()}")
        # pixel size adapts to screen width (2x at 1920px, 3x at 2560px);
        # sprite canvas is 64x48, so scale 2 == 128x96 px cat
        self.scale = max(SCALE_MIN, min(3, screen.width() // 850))
        self.prop_scale = max(3, self.scale - 1)
        self.cust = cust or Customization()
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
        primary = self.add_cat(self.cust, age=6.0)
        primary.brain.food_x = self.desktop.floor_x0 + 110.0
        primary.brain.water_x = self.desktop.floor_x0 + 200.0

        self._props = {
            name: prop_pixmap(name, self.prop_scale)
            for name in ("food_bowl", "food_bowl_empty",
                         "fountain_0", "fountain_1", "fountain_2",
                         "puke", "wall_shelf", "box", "box_front",
                         "cat_door_0", "cat_door_1", "cat_door_2",
                         "fish", "drop", "zzz", "heart",
                         "ball", "plush", "mouse", "lure", "laser_dot",
                         "scratch_post", "cat_bed",
                         "cat_grass", "litter_0", "litter_1", "litter_2",
                         "litter_poop", "litter_pee",
                         "cat_tree", "wheel_stand", "wheel_rim", "wheel_front")
        }
        self._wheel_angle = 0.0
        self._time = 0.0
        self._dbg_t = 0.0
        self._placing: str | None = None      # placement mode: prop follows cursor
        self._place_since = 0.0
        self._inactive_since: float | None = None
        self._last_sig: tuple = ()
        self._last_furn_sig: tuple = ()
        self._last_fountain_frame = -1
        self._prev_puke_count = 0
        self._last_back_toy_sig: tuple = ()  # P42: floor toys on the back layer
        self._furn_move_ticks = 0            # P32 flush cadence, back layer
        self._prev_furn_moving = False
        self._move_ticks = 0               # P32 full-flush cadence
        self._prev_moving = False
        self._win_x = 0                    # P37: window's world position
        self._win_y = 0                    # (applied by KWin, not by us)
        self._shrink_since: float | None = None
        self._last_status_sig: tuple = ()  # P42: pinned status board
        self._hunt: MouseHunt | None = None  # P42: mouse-hunt session
        self.notify = None  # optional callback(title, msg) set by the tray
        self._bridge = bridge
        self.furniture_layers = [FurnitureLayer(self, s)
                                 for s in QGuiApplication.screens()]
        QGuiApplication.instance().screenAdded.connect(self._screens_changed)
        QGuiApplication.instance().screenRemoved.connect(self._screens_changed)

        bridge.cursorChanged.connect(self._on_cursor)
        bridge.windowsChanged.connect(self.desktop.set_windows)
        bridge.workAreaChanged.connect(self._on_work_area)
        bridge.workAreasChanged.connect(self._on_work_areas)
        bridge.keyEvent.connect(self._on_key_event)  # P42 control mode

        # NOTE: the detector owns the single CursorTracker — feed it, not a copy.
        self._detector = InteractionDetector()

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
        br, bl = self._make_banks(cust, self.scale, cat.brain.stage)
        self._banks[cat] = (br, bl, cat.brain.stage)
        return cat

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
            br, bl = self._make_banks(cat.cust, self.scale, cat.brain.stage)
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

    @staticmethod
    def _make_banks(cust: Customization, scale: int = SCALE_MIN,
                    stage: int = 6) -> tuple[SpriteBank, SpriteBank]:
        kwargs = dict(palette=cust.to_palette(), pattern=cust.pattern, scale=scale,
                      accessory=cust.collar is not None, stage=stage)
        return (SpriteBank(facing="right", **kwargs),
                SpriteBank(facing="left", **kwargs))

    def set_customization(self, cust: Customization) -> None:
        """Re-skin the ACTIVE cat live (from the tray 'Customize...' action)."""
        cat = self.active
        cat.cust = cust
        if cat is self.cats[0]:
            self.cust = cust
        br, bl = self._make_banks(cust, self.scale, cat.brain.stage)
        self._banks[cat] = (br, bl, cat.brain.stage)
        self.update()

    def _on_work_area(self, d: dict) -> None:
        self._on_work_areas([d])

    def _on_work_areas(self, areas: list[dict]) -> None:
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
        if self.cust.status_pos is not None:
            px, py = self.cust.status_pos
            sx = min(max(px, self.desktop.floor_x0),
                     self.desktop.floor_x1 - STATUS_W)
            sy = min(max(py, 0.0),
                     self.desktop.floor_y_at(px + STATUS_W / 2) - STATUS_H)
            if [sx, sy] != self.cust.status_pos:
                self.cust.status_pos = [sx, sy]
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
        if cat.blink_active:
            if state == "stand":
                return "enjoy"          # same pose, eyes closed
            if state == "sit":
                return "sit_blink"
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
        return QRect(int(cat.body.x) - pm.width() // 2,
                     int(cat.body.y) - pm.height(), pm.width(), pm.height())

    def _bubble_rect(self, cat: Cat) -> QRect:
        if not cat.brain.bubble:
            return QRect()
        pm = self._props[cat.brain.bubble]
        cr = self._cat_rect(cat)
        bob = int(2.5 * math.sin(self._time * 3.0))
        return QRect(cr.center().x() - pm.width() // 2,
                     cr.top() - pm.height() - 6 + bob, pm.width(), pm.height())

    def _bowl_rect(self, x: float, name: str) -> QRect:
        pm = self._props[name]
        return QRect(int(x) - pm.width() // 2,
                     int(self.desktop.floor_y_at(x)) - pm.height(),
                     pm.width(), pm.height())

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
        return QRect(int(self.cat.brain.wheel_x) - pm.width() // 2,
                     int(self.desktop.floor_y_at(self.cat.brain.wheel_x)) - pm.height(),
                     pm.width(), pm.height())

    def _box_rect(self) -> QRect:
        pm = self._props["box"]
        return QRect(int(self.cat.brain.box_x) - pm.width() // 2,
                     int(self.desktop.floor_y_at(self.cat.brain.box_x)) - pm.height(),
                     pm.width(), pm.height())

    def _shelf_rects(self) -> list[QRect]:
        """Screen rects of the floating wall shelves (P25)."""
        pm = self._props["wall_shelf"]
        return [QRect(int(x) - pm.width() // 2, int(y), pm.width(), pm.height())
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
            out.append((QRect(br.center().x() + ox - pm.width() // 2,
                              br.bottom() - oy - pm.height(),
                              pm.width(), pm.height()), kind))
        return out

    def _door_rect(self, cat: Cat) -> QRect:
        d = self._doors.get(cat)
        if d is None:
            return QRect()
        pm = self._props["cat_door_0"]
        return QRect(int(d[0]) - pm.width() // 2,
                     int(d[1]) - pm.height(), pm.width(), pm.height())

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
                rects.append(QRect(int(toy.x) - pm.width() // 2,
                                   int(toy.y) - pm.height() // 2,
                                   pm.width(), pm.height()))
            else:
                rects.append(QRect(int(toy.x) - pm.width() // 2,
                                   int(toy.y) - pm.height(),
                                   pm.width(), pm.height()))
            if toy.kind == "string":
                ax, ay = toy.anchor
                rects.append(QRect(int(min(ax, toy.x)) - 4, int(min(ay, toy.y)) - 4,
                                   int(abs(ax - toy.x)) + 8, int(abs(ay - toy.y)) + 8))
        return rects

    # -- small window geometry (P37) ----------------------------------------

    def _origin(self) -> tuple[int, int]:
        """World coords of the window's top-left corner. (0,0) while
        fullscreen (placement mode): the buffer then maps 1:1 to the world."""
        if self.isFullScreen():
            return (0, 0)
        return (self._win_x, self._win_y)

    def _front_bounds(self) -> QRect:
        """World-coords bounding rect of everything the front layer draws:
        the front-level cats, their bubbles, cat doors and the front toys
        (string/laser/carried — floor toys live on the back layer since P42),
        margin, minimum size."""
        r = QRect()
        for cat in self.cats:
            if self.cat_layer(cat) == "front":
                r = r.united(self._cat_rect(cat)).united(self._bubble_rect(cat))
            # doors are always front-window content, even mid-crossing (P27)
            r = r.united(self._door_rect(cat))
        for tr in self._toy_rects("front"):  # only front-layer content (P42)
            r = r.united(tr)
        if r.isNull():
            # every cat is on the back level: no front content — stay put
            return QRect(self._win_x, self._win_y, self.width(), self.height())
        r = r.adjusted(-WIN_MARGIN, -WIN_MARGIN, WIN_MARGIN, WIN_MARGIN)
        if r.width() < WIN_MIN_W:
            r.moveLeft(r.center().x() - WIN_MIN_W // 2)
            r.setWidth(WIN_MIN_W)
        if r.height() < WIN_MIN_H:
            r.moveTop(r.center().y() - WIN_MIN_H // 2)
            r.setHeight(WIN_MIN_H)
        return r

    def _sync_window_geometry(self, force: bool = False) -> None:
        """Keep the small front window covering all front-layer content.
        Wayland clients cannot self-position: the desired rect goes into the
        window title and the KWin script applies it (frameGeometry)."""
        if self._placing or self.isFullScreen():
            return
        need = self._front_bounds()
        cur = QRect(self._win_x, self._win_y, self.width(), self.height())
        new = QRect(cur)
        if force:
            new = need
        elif not cur.contains(need):
            if need.width() > cur.width() or need.height() > cur.height():
                # content bigger than the window (rare): grow + recenter
                new = QRect(0, 0, max(cur.width(), need.width()),
                            max(cur.height(), need.height()))
                new.moveCenter(need.center())
            else:
                # follow with the SMALLEST move that keeps the content inside
                # (P44): recentering used to snap the window by hundreds of
                # px, and since KWin applies the new position a frame later,
                # the cat visibly jumped while walking
                if need.left() < cur.left():
                    new.moveLeft(need.left())
                if need.right() > cur.right():
                    new.moveRight(need.right())
                if need.top() < cur.top():
                    new.moveTop(need.top())
                if need.bottom() > cur.bottom():
                    new.moveBottom(need.bottom())
        else:
            small = (need.width() < cur.width() * WIN_SHRINK_FRAC
                     and need.height() < cur.height() * WIN_SHRINK_FRAC)
            if small:
                if self._shrink_since is None:
                    self._shrink_since = self._time
                elif self._time - self._shrink_since >= WIN_SHRINK_DELAY:
                    new = need
            else:
                self._shrink_since = None
        vg = QRect()
        for s in QGuiApplication.screens():
            vg = vg.united(s.geometry())
        if new.width() >= vg.width() or new.height() >= vg.height():
            new = QRect(vg)
        else:
            new.moveLeft(min(max(new.x(), vg.x()),
                             vg.x() + vg.width() - new.width()))
            new.moveTop(min(max(new.y(), vg.y()),
                            vg.y() + vg.height() - new.height()))
        if new == cur:
            return
        self._shrink_since = None
        self._win_x, self._win_y = new.x(), new.y()
        if new.size() != self.size():
            self.resize(new.size())
        self.setWindowTitle(
            f"plasmacat@{new.x()},{new.y()},{new.width()},{new.height()}")
        self.update()  # content moved relative to the window

    # -- simulation ---------------------------------------------------------

    def _on_cursor(self, x: int, y: int) -> None:
        self.desktop.set_cursor(x, y)
        self._detector.tracker.add(x, y)

    def _tick(self) -> None:
        dt = min(self._clock.restart() / 1000.0, 0.1)
        if dt <= 0.0:
            return  # zero-length frame (same-millisecond reentry): nothing to do
        self._time += dt
        # layer-specific regions (P42): a far-away floor toy must not stretch
        # the front window's dirty region into a giant bounding box
        old_front = self._ghost_rect()
        old_back = QRect()
        for cat in self.cats:
            r = self._cat_rect(cat).united(self._bubble_rect(cat)) \
                .united(self._door_rect(cat))
            if self.cat_layer(cat) == "back":
                old_back = old_back.united(r)
            else:
                old_front = old_front.united(r)
        for r in self._toy_rects("front"):
            old_front = old_front.united(r)
        for r in self._toy_rects("back"):
            old_back = old_back.united(r)

        if self._placing and self._time - self._place_since > 30.0:
            self._end_placement()  # auto-cancel dangling placement
        if any(c.brain.state == "wheel_run" for c in self.cats):
            self._wheel_angle = (self._wheel_angle + 200.0 * dt) % 360.0

        self.desktop.cursor_active = self._detector.tracker.idle_for() < 2.0
        self.desktop.cursor_speed = self._detector.tracker.speed()
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
        # interactions (P47): the cat UNDER the cursor is ticked first with
        # the real dt, so its stroke/rub accumulators advance; the others
        # only watch for teasing (shared detector state must not double-tick)
        cx, cy = self.desktop.cursor
        ordered = sorted(
            self.cats,
            key=lambda c: 0 if self._cat_rect(c).contains(cx, cy) else 1)
        for i, cat in enumerate(ordered):
            rect = self._cat_rect(cat)
            events = self._detector.tick(
                dt if i == 0 else 0.0,
                (rect.x(), rect.y(), rect.width(), rect.height()),
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

        for cat in self.cats:
            cat.tick(dt, self.desktop)
        fx_sounds: list[str] = []  # toy/hunt intents, not tied to one brain
        self.toys.tick(dt, self.desktop, self.cats, fx_sounds)
        if self._hunt is not None:  # P42 mini-game session
            self._hunt.tick(dt, self.desktop, self.cats, self.toys, fx_sounds)
            if not self._hunt.active:
                if self.notify is not None:
                    self.notify("Mouse hunt",
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

        if self.player:
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
        if self.notify is not None:
            for cat in self.cats:
                st = cat.brain.state
                if st == "litter_beg" \
                        and self._prev_brain_state.get(cat) != "litter_beg":
                    self.notify("PlasmaCat", f"{cat.cust.name}: the litter box "
                                           "is full — please clean it!")
            if len(self.cat.brain.puke_spots) > self._prev_puke_count:
                self.notify("PlasmaCat", "A cat vomited on the floor — "
                                       "clean it up (tray menu)!")
        self._prev_brain_state = {c: c.brain.state for c in self.cats}
        self._prev_puke_count = len(self.cat.brain.puke_spots)
        new_front = self._ghost_rect()
        new_back = QRect()
        for cat in self.cats:
            r = self._cat_rect(cat).united(self._bubble_rect(cat)) \
                .united(self._door_rect(cat))
            if self.cat_layer(cat) == "back":
                new_back = new_back.united(r)
            else:
                new_front = new_front.united(r)
        for r in self._toy_rects("front"):
            new_front = new_front.united(r)
        for r in self._toy_rects("back"):
            new_back = new_back.united(r)
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
        # them pass through the cat door (P27) whenever the level flips
        for cat in self.cats:
            back = self.on_back_layer(cat)
            if back != self._prev_back.get(cat, False):
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
        furn_moving = (moving and any_back) or back_toy_moving
        self._furn_move_ticks = self._furn_move_ticks + 1 if furn_moving else 0
        if any_back or self._doors or back_toys_changed:
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
        if self.debug:
            self.update()  # platform lines may change anytime

    # -- placement mode (click-to-place: verified working on Wayland, D2) -------

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

    def _sync_furniture_platforms(self) -> None:
        """Furniture contributes jumpable platforms: two cat-tree levels
        (matching props._cat_tree at scale 3) + the exercise wheel's inner
        track (props._wheel_stand, track at canvas row 58)."""
        from plasmacat.bridge.desktop import Platform

        plats = []
        if self.cat.brain.tree_x is not None:
            x = self.cat.brain.tree_x
            fy = self.desktop.floor_y_at(x)
            plats += [
                Platform(x - 54, x + 42, fy - 108, "Katzenbaum"),
                Platform(x - 24, x + 66, fy - 192, "Katzenbaum"),
            ]
        if self.cat.brain.scratch_x is not None:
            x = self.cat.brain.scratch_x
            fy = self.desktop.floor_y_at(x)
            # wide top platform of the scratching post (canvas cols 2-21)
            plats.append(Platform(x - 30, x + 27, fy - 192, "Kratzbaum"))
        if self.cat.brain.bed_x is not None:
            x = self.cat.brain.bed_x
            fy = self.desktop.floor_y_at(x)
            # the cushion IS a surface: the cat lies IN the bed, not next to it
            plats.append(Platform(x - 55, x + 55, fy - 27, "Katzennest"))
        if self.cat.brain.wheel_x is not None:
            x = self.cat.brain.wheel_x
            fy = self.desktop.floor_y_at(x)
            # the wheel's inner track: her feet touch the rim's inner bottom
            # (canvas row 60 = fy-36 at scale 3; was fy-42, she floated — P46)
            plats.append(Platform(x - 60, x + 60, fy - 36, "Laufrad"))
        if self.cat.brain.box_x is not None:
            x = self.cat.brain.box_x
            fy = self.desktop.floor_y_at(x)
            # the box's inner floor: the cat sits IN the cardboard box
            plats.append(Platform(x - 55, x + 55, fy - 30, "Karton"))
        for sx, sy in self.cat.brain.shelves:
            # floating wall shelves: fixed at their placed height (P25)
            plats.append(Platform(sx - 60, sx + 60, sy, "Regal"))
        self.desktop.set_extra_platforms(plats)

    def _ghost_rect(self) -> QRect:
        if not self._placing:
            return QRect()
        cx, cy = self.desktop.cursor
        if self._placing == "status":  # the pinned status board (P42)
            return QRect(cx - STATUS_W // 2, cy - STATUS_H // 2,
                         STATUS_W, STATUS_H)
        key = {"water_fountain": "fountain_0"}.get(self._placing, self._placing)
        pm = self._props[key]
        return QRect(cx - pm.width() // 2, cy - pm.height() // 2,
                     pm.width(), pm.height())

    # -- pinned status board (P42) ----------------------------------------------

    def _status_rect(self) -> QRect:
        """World-coords rect of the pinned status board — null when disabled.
        Without a placed position it defaults to bottom-left over the panel."""
        if not self.cust.status_window:
            return QRect()
        pos = self.cust.status_pos
        if pos is None:
            return QRect(int(self.desktop.floor_x0 + 40),
                         int(self.desktop.floor_y - STATUS_H - 40),
                         STATUS_W, STATUS_H)
        return QRect(int(pos[0]), int(pos[1]), STATUS_W, STATUS_H)

    def _status_sig(self) -> tuple:
        """Everything the status board shows (rounded) — repaint on change."""
        if not self.cust.status_window:
            return ()
        b = self.active.brain
        r = self._status_rect()
        return (tuple(round(v) for v in b.needs.values()), round(b.food_fill),
                round(b.litter_fill), len(b.litter_deposits),
                round(b.attachment_xp), b.attachment_level, self.active.cust.name,
                round(b.age, 1), r.x(), r.y())

    def _paint_status(self, p: QPainter) -> None:
        """Draw the board (world coords; the painter is already translated).
        Pure QPainter, display-only: the FurnitureLayer is click-through, so
        the care actions (treat/refill/clean) stay in the tray menu. Shows
        the ACTIVE cat (nearest the cursor, P47)."""
        brain = self.active.brain
        sr = self._status_rect()
        x, y = sr.x(), sr.y()
        p.setPen(QPen(QColor(80, 80, 96, 220), 1))
        p.setBrush(QColor(20, 20, 26, 205))
        p.drawRoundedRect(sr, 8.0, 8.0)
        font = p.font()
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(240, 240, 240))
        p.drawText(x + 12, y + 20,
                   f"{self.active.cust.name} — {brain.life_stage} — "
                   f"{brain.attachment_name} ({int(brain.attachment_xp)} XP)")
        font.setBold(False)
        p.setFont(font)
        rows = [(label, brain.needs[key]) for key, label in
                (("hunger", "Food"), ("thirst", "Water"), ("energy", "Energy"),
                 ("play", "Play"), ("affection", "Affection"),
                 ("bladder", "Litter"))]
        rows.append(("Food bowl", brain.food_fill))
        rows.append((f"Litter box ({len(brain.litter_deposits)})",
                     brain.litter_fill / 5 * 100))
        ry = y + 32
        for label, value in rows:
            p.setPen(QColor(200, 200, 210))
            p.drawText(x + 12, ry + 9, label)
            bx = x + 112
            bw = STATUS_W - 112 - 12
            v = min(max(value, 0.0), 100.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(60, 60, 72, 220))
            p.drawRoundedRect(bx, ry, bw, 10, 4.0, 4.0)
            if v > 0:
                p.setBrush(QColor(90, 200, 90) if v > 50
                           else QColor(230, 180, 60) if v > 25
                           else QColor(220, 80, 70))
                p.drawRoundedRect(bx, ry, max(4, int(bw * v / 100)), 10, 4.0, 4.0)
            ry += 17

    def set_status_window(self, on: bool) -> None:
        """Tray toggle: the pinned status board on the desktop level (P42) —
        painted on the FurnitureLayer behind windows, click-through. (Was a
        real tool window in P39; it could be minimized and get lost.)"""
        self.cust.status_window = on
        self._last_status_sig = ()     # force a repaint of the new state
        self._furn_update_all()
        act = getattr(self, "_status_action", None)
        if act is not None and act.isChecked() != on:
            act.setChecked(on)

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
        if self.notify is not None:
            self.notify("Mouse hunt", "Mice are loose! Catch 8 in 60 seconds.")

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
            tuple(per_cat), self._placing,
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
        if self._placing or self._doors:
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
                    p.drawPixmap(int(toy.x) - pm.width() // 2,
                                 int(toy.y) - pm.height() // 2, pm)
                elif toy.kind == "laser":
                    pm = self._props["laser_dot"]
                    p.drawPixmap(int(toy.x) - pm.width() // 2,
                                 int(toy.y) - pm.height() // 2, pm)
                else:
                    pm = self._props[toy.kind]
                    p.drawPixmap(int(toy.x) - pm.width() // 2,
                                 int(toy.y) - pm.height(), pm)
            # thought bubbles are drawn with their cats above (front level)
            # the cat doors (P27): a flapping portal at the crossing point
            for cat, d in self._doors.items():
                ph = self._door_phase(cat)
                if ph < 0:
                    continue
                frame = ("cat_door_0", "cat_door_1", "cat_door_2",
                         "cat_door_2", "cat_door_1")[min(int(ph * 5), 4)]
                pm = self._props[frame]
                p.drawPixmap(int(d[0]) - pm.width() // 2, int(d[1]) - pm.height(), pm)
            # placement ghost + hint
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
                hint = "Left-click to place — right-click to cancel"
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
