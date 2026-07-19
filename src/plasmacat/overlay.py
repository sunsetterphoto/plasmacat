"""Fullscreen, transparent, click-through overlay: the game canvas.

Runs the simulation loop (QTimer ~60 fps), draws the cat (pixel-art sprite),
the food/water bowls and the cat's thought bubble, plays sound intents from
the brain, and repaints only dirty regions. Debug mode (--debug) draws
platform top edges.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QElapsedTimer, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from plasmacat.bridge.desktop import DesktopState
from plasmacat.cat.cat import Cat
from plasmacat.cat.interactions import InteractionDetector
from plasmacat.cat.render import SpriteBank, prop_pixmap
from plasmacat.cat.toys import ToyManager
from plasmacat.persist import Customization

SCALE_MIN = 2
FPS_MS = 16


class FurnitureLayer(QWidget):
    """Desktop-level layer rendered BEHIND all windows (keepBelow, tagged by
    the bridge via its window title): bowls and static furniture. Repainted
    only when its content changes."""

    def __init__(self, overlay: "Overlay", parent=None) -> None:
        super().__init__(parent)
        self.o = overlay
        self.setWindowTitle("plasmacat-furniture")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
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
            # 1. static furniture (bowls, post, tree, bed, grass, litter, box…)
            for name, x in ((n, fx) for fx, n in o._floor_props()):
                br = o._bowl_rect(x, name)
                if event.rect().intersects(br):
                    p.drawPixmap(br.x(), br.y(), o._props[name])
            # 1b. floating wall shelves (P25): fixed to the 'wall', any height
            for sr in o._shelf_rects():
                if event.rect().intersects(sr):
                    p.drawPixmap(sr.x(), sr.y(), o._props["wall_shelf"])
            # 2. exercise wheel: static stand, then rim rotating around the axle —
            #    the full illusion lives on THIS layer (P23)
            if o.cat.brain.wheel_x is not None:
                wr = o._wheel_rect()
                if event.rect().intersects(wr):
                    cxm = wr.x() + 32 * o.prop_scale   # rim center (canvas 32,34)
                    cym = wr.y() + 34 * o.prop_scale
                    p.drawPixmap(wr.x(), wr.y(), o._props["wheel_stand"])
                    p.save()
                    p.translate(cxm, cym)
                    p.rotate(-o._wheel_angle)
                    p.translate(-cxm, -cym)
                    p.drawPixmap(wr.x(), wr.y(), o._props["wheel_rim"])
                    p.restore()
            # 3. the cat herself, when she has "stepped back" to this level
            if o.cat_layer() == "back":
                frame, acc, cr, br_b, bubble = o.current_cat()
                p.drawPixmap(cr.x(), cr.y(), frame)
                if acc is not None:
                    p.drawPixmap(cr.x(), cr.y(), acc)
                if bubble:
                    p.drawPixmap(br_b.x(), br_b.y(), o._props[bubble])
            # 4. wheel front arc / box front wall over the cat (inside illusion)
            if o.cat.brain.wheel_x is not None:
                wr = o._wheel_rect()
                if event.rect().intersects(wr):
                    p.drawPixmap(wr.x(), wr.y(), o._props["wheel_front"])
            if o.cat.brain.box_x is not None:
                br2 = o._box_rect()
                if event.rect().intersects(br2):
                    p.drawPixmap(br2.x(), br2.y(), o._props["box_front"])
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
        self.cat = Cat(self.desktop.screen_w * 0.5, self.desktop.floor_y,
                       rng=random.Random())
        self.cat.brain.food_x = self.desktop.floor_x0 + 110.0
        self.cat.brain.water_x = self.desktop.floor_x0 + 200.0
        self.cust = cust or Customization()
        self.bank_right, self.bank_left = self._make_banks(self.cust)
        self.player = player
        self.debug = debug
        self.toys = ToyManager(rng=random.Random())
        self.cat.brain.toys = self.toys

        self._props = {
            name: prop_pixmap(name, self.prop_scale)
            for name in ("food_bowl", "food_bowl_empty",
                         "fountain_0", "fountain_1", "fountain_2",
                         "puke", "wall_shelf", "box", "box_front",
                         "cat_door_0", "cat_door_1", "cat_door_2",
                         "fish", "drop", "zzz", "heart",
                         "ball", "plush", "lure", "scratch_post", "cat_bed",
                         "cat_grass", "litter_0", "litter_1", "litter_2",
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
        self._prev_back = False
        self._prev_brain_state = ""
        self._prev_puke_count = 0
        self._door: tuple[float, float, float, str] | None = None  # P27
        self._move_ticks = 0               # P32 full-flush cadence
        self._prev_moving = False
        self.notify = None  # optional callback(title, msg) set by the tray
        self.furniture_layer = FurnitureLayer(self)

        bridge.cursorChanged.connect(self._on_cursor)
        bridge.windowsChanged.connect(self.desktop.set_windows)
        bridge.workAreaChanged.connect(self._on_work_area)

        # NOTE: the detector owns the single CursorTracker — feed it, not a copy.
        self._detector = InteractionDetector()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer.start(FPS_MS)

        self.showFullScreen()

    # -- customization ---------------------------------------------------------

    @staticmethod
    def _make_banks(cust: Customization, scale: int = SCALE_MIN) -> tuple[SpriteBank, SpriteBank]:
        kwargs = dict(palette=cust.to_palette(), pattern=cust.pattern, scale=scale,
                      accessory=cust.collar is not None)
        return (SpriteBank(facing="right", **kwargs),
                SpriteBank(facing="left", **kwargs))

    def set_customization(self, cust: Customization) -> None:
        """Re-skin the cat live (from the tray 'Customize...' action)."""
        self.cust = cust
        self.bank_right, self.bank_left = self._make_banks(cust, self.scale)
        self.update()

    def _on_work_area(self, d: dict) -> None:
        self.desktop.set_work_area(d)
        if self.debug:
            print(f"[dbg] work area -> {d}")
        # keep the bowls anchored to the work-area corner
        self.cat.brain.food_x = self.desktop.floor_x0 + 110.0
        self.cat.brain.water_x = self.desktop.floor_x0 + 200.0
        # floor_y may have moved (panel resized/Plasma restart): the furniture
        # platforms must follow or the cat floats beside the bed/wheel (P24)
        self._sync_furniture_platforms()

    # -- layer logic (P18) ------------------------------------------------------

    def on_back_layer(self) -> bool:
        """The visibility level is a deliberate brain decision with a 30 s
        dwell (P28): calm states are level-neutral, only committed
        cross-world actions flip it. The overlay just follows brain.level."""
        return self.cat.brain.level == "back"

    # -- cat door between the levels (P27) -------------------------------------

    def _door_phase(self) -> float:
        """0..1 while the cat-door animation runs, else -1."""
        if self._door is None:
            return -1.0
        ph = (self._time - self._door[2]) / DOOR_DUR
        return ph if ph < 1.0 else -1.0

    def cat_layer(self) -> str | None:
        """Which layer draws the cat this frame — or None while she passes
        through the door. The logical layer flips instantly (on_back_layer);
        the door makes the crossing visible: old side -> inside -> new side."""
        back = self.on_back_layer()
        ph = self._door_phase()
        if ph < 0:
            return "back" if back else "front"
        if 0.25 <= ph < 0.65:
            return None  # inside the door
        if ph < 0.25:
            return "front" if self._door[3] == "in" else "back"  # old side
        return "back" if back else "front"                       # new side

    def current_cat(self):
        """The cat's current frame + accessory + rects, for the layer that
        draws her this tick."""
        bank = self.bank_right if self.cat.body.facing >= 0 else self.bank_left
        key = self._anim_key()
        idx = self.cat.frame % bank.frame_count(key)
        return (bank.frame(key, idx), bank.accessory_frame(key, idx),
                self._cat_rect(), self._bubble_rect(), self.cat.brain.bubble)

    # -- geometry -------------------------------------------------------------

    def _anim_key(self) -> str:
        """Animation state + blink + mood-dependent tail variant (P12a/P8g)."""
        state = self.cat.anim_state
        if self.cat.blink_active:
            if state == "stand":
                return "enjoy"          # same pose, eyes closed
            if state == "sit":
                return "sit_blink"
        if state in ("stand", "walk"):
            mood = self.cat.brain.mood
            if mood < 40:
                return state + ":low"   # grumpy: tail low
            if mood < 70:
                return state + ":mid"   # neutral: tail horizontal
        return state                    # content/happy: tail up (default)

    def _cat_rect(self) -> QRect:
        pm = self.bank_right.frame(self._anim_key(), 0)
        return QRect(int(self.cat.body.x) - pm.width() // 2,
                     int(self.cat.body.y) - pm.height(), pm.width(), pm.height())

    def _bubble_rect(self) -> QRect:
        if not self.cat.brain.bubble:
            return QRect()
        pm = self._props[self.cat.brain.bubble]
        cr = self._cat_rect()
        bob = int(2.5 * math.sin(self._time * 3.0))
        return QRect(cr.center().x() - pm.width() // 2,
                     cr.top() - pm.height() - 6 + bob, pm.width(), pm.height())

    def _bowl_rect(self, x: float, name: str) -> QRect:
        pm = self._props[name]
        return QRect(int(x) - pm.width() // 2, int(self.desktop.floor_y) - pm.height(),
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
            variant = ("litter_0" if brain.litter_fill < 2
                       else "litter_1" if brain.litter_fill < 4 else "litter_2")
            out.append((brain.litter_x, variant))
        if brain.tree_x is not None:
            out.append((brain.tree_x, "cat_tree"))
        if brain.box_x is not None:
            out.append((brain.box_x, "box"))
        return out

    def _wheel_rect(self) -> QRect:
        pm = self._props["wheel_stand"]
        return QRect(int(self.cat.brain.wheel_x) - pm.width() // 2,
                     int(self.desktop.floor_y) - pm.height(), pm.width(), pm.height())

    def _box_rect(self) -> QRect:
        pm = self._props["box"]
        return QRect(int(self.cat.brain.box_x) - pm.width() // 2,
                     int(self.desktop.floor_y) - pm.height(), pm.width(), pm.height())

    def _shelf_rects(self) -> list[QRect]:
        """Screen rects of the floating wall shelves (P25)."""
        pm = self._props["wall_shelf"]
        return [QRect(int(x) - pm.width() // 2, int(y), pm.width(), pm.height())
                for x, y in self.cat.brain.shelves]

    def _fountain_rect(self) -> QRect:
        if self.cat.brain.water_x is None:
            return QRect()
        return self._bowl_rect(self.cat.brain.water_x, "fountain_0")

    def _door_rect(self) -> QRect:
        if self._door is None:
            return QRect()
        pm = self._props["cat_door_0"]
        return QRect(int(self._door[0]) - pm.width() // 2,
                     int(self._door[1]) - pm.height(), pm.width(), pm.height())

    def _toy_rects(self) -> list[QRect]:
        rects = []
        for toy in self.toys.toys:
            # a runaway/out-of-world toy must never kill the tick (P25)
            if not (math.isfinite(toy.x) and math.isfinite(toy.y)):
                continue
            if abs(toy.x) > 10000 or abs(toy.y) > 10000:
                continue
            pm = self._props["lure" if toy.kind == "string" else toy.kind]
            if toy.kind == "string":
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

    # -- simulation ---------------------------------------------------------

    def _on_cursor(self, x: int, y: int) -> None:
        self.desktop.set_cursor(x, y)
        self._detector.tracker.add(x, y)

    def _tick(self) -> None:
        dt = min(self._clock.restart() / 1000.0, 0.1)
        if dt <= 0.0:
            return  # zero-length frame (same-millisecond reentry): nothing to do
        self._time += dt
        old = self._cat_rect().united(self._bubble_rect()).united(self._ghost_rect())
        old = old.united(self._door_rect())
        for r in self._toy_rects():
            old = old.united(r)

        if self._placing and self._time - self._place_since > 30.0:
            self._end_placement()  # auto-cancel dangling placement
        if self.cat.brain.state == "wheel_run":
            self._wheel_angle = (self._wheel_angle + 200.0 * dt) % 360.0

        self.desktop.cursor_active = self._detector.tracker.idle_for() < 2.0
        self.desktop.cursor_speed = self._detector.tracker.speed()
        # greeting when the human returns after >60 s away
        if self.desktop.cursor_active:
            if self._inactive_since is not None:
                if self._time - self._inactive_since > 60.0:
                    self.cat.brain.on_user_return(self.cat.body, self.desktop)
                self._inactive_since = None
        elif self._inactive_since is None:
            self._inactive_since = self._time
        rect = self._cat_rect()
        events = self._detector.tick(
            dt, (rect.x(), rect.y(), rect.width(), rect.height()), self.desktop.cursor)
        for ev in events:
            if self.debug:
                print(f"[interact] {ev} speed={self.desktop.cursor_speed:.0f} "
                      f"state={self.cat.brain.state}")
            if ev == "stroke":
                self.cat.brain.on_stroke(self.cat.body)
            elif ev == "rub":
                self.cat.brain.on_rub(self.cat.body)
            elif ev == "hunt":
                self.cat.brain.on_hunt_trigger(self.cat.body, self.desktop.cursor,
                                               self.desktop)
            elif ev == "startle":
                self.cat.brain.on_startle(self.cat.body, self.desktop)
            elif ev == "pat":
                self.cat.brain.on_pat(self.cat.body, self.desktop.cursor)

        self.cat.tick(dt, self.desktop)
        self.toys.tick(dt, self.desktop, self.cat, self.cat.brain.sounds)

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
                cx, cy = self.desktop.cursor
                r = self._cat_rect()
                inside = (r.x() <= cx <= r.x() + r.width()
                          and r.y() <= cy <= r.y() + r.height())
                print(f"[dbg] cursor=({cx},{cy}) cat=({r.x()},{r.y()},{r.width()},"
                      f"{r.height()}) inside={inside} "
                      f"speed={self.desktop.cursor_speed:.0f} "
                      f"catworld=({self.cat.body.x:.0f},{self.cat.body.y:.0f})")

        if self.player:
            for sound in self.cat.brain.sounds:
                self.player.play(sound)
        self.cat.brain.sounds.clear()

        # only repaint when something visible actually changed (P12c)
        sig = self._signature()
        furn_sig = (self.cat.brain.food_fill > 25,
                    round(self.cat.brain.litter_fill),
                    len(self.cat.brain.puke_spots),
                    self.cat.brain.food_x, self.cat.brain.water_x,
                    self.cat.brain.scratch_x, self.cat.brain.bed_x,
                    self.cat.brain.grass_x, self.cat.brain.litter_x,
                    self.cat.brain.tree_x, self.cat.brain.wheel_x,
                    self.cat.brain.box_x, tuple(self.cat.brain.shelves))
        if furn_sig != self._last_furn_sig:
            self._last_furn_sig = furn_sig
            self.furniture_layer.refresh()
        # the fountain ripples on its own cheap repaint schedule (P25):
        # only its small region, not the whole back layer
        if self.cat.brain.water_x is not None:
            fframe = int(self._time * 2.5) % 3
            if fframe != self._last_fountain_frame:
                self._last_fountain_frame = fframe
                self.furniture_layer.update(self._fountain_rect())
        # user notifications (P25): full litter box / vomit on the floor
        if self.notify is not None:
            st = self.cat.brain.state
            if st == "litter_beg" and self._prev_brain_state != "litter_beg":
                self.notify("PlasmaCat", "The litter box is full — please clean it!")
            if len(self.cat.brain.puke_spots) > self._prev_puke_count:
                self.notify("PlasmaCat", "Your cat vomited on the floor — "
                                       "clean it up (tray menu)!")
        self._prev_brain_state = self.cat.brain.state
        self._prev_puke_count = len(self.cat.brain.puke_spots)
        new = self._cat_rect().united(self._bubble_rect()).united(self._ghost_rect())
        new = new.united(self._door_rect())
        for r in self._toy_rects():
            new = new.united(r)
        moving = self.cat.body.airborne or self.cat.body.target_x is not None
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
                self.update(old.united(new).adjusted(6, 6, 6, 6))
            self._prev_moving = moving
        # the cat moves between layers: keep the back layer in sync, and let
        # her pass through the cat door (P27) whenever the level flips
        back = self.on_back_layer()
        if back != self._prev_back:
            self._door = (self.cat.body.x, self.cat.body.y, self._time,
                          "in" if back else "out")
        if self._door is not None and self._time - self._door[2] >= DOOR_DUR:
            self._door = None
        if back or back != self._prev_back or self._door is not None:
            if moving and self._move_ticks % 3 == 0:
                self.furniture_layer.update()  # P32 full flush on the back layer
            else:
                self.furniture_layer.update(old.united(new).adjusted(6, 6, 6, 6))
        self._prev_back = back
        if self.debug:
            self.update()  # platform lines may change anytime

    # -- placement mode (click-to-place: verified working on Wayland, D2) -------

    def begin_placement(self, kind: str) -> None:
        """kind: 'ball' | 'plush' | 'food_bowl' | 'water_fountain' |
        'wall_shelf' | 'box' | furniture kinds. The prop sticks to the
        cursor; left-click drops it, right-click cancels."""
        self._placing = kind
        self._place_since = self._time
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)
        self.showFullScreen()
        self.activateWindow()
        self.raise_()

    def _end_placement(self) -> None:
        self._placing = None
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
        self.showFullScreen()

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
        else:
            x = min(max(pos.x(), self.desktop.floor_x0 + 90), self.desktop.floor_x1 - 90)
            if kind == "food_bowl":
                self.cat.brain.food_x = x
            elif kind == "water_fountain":
                self.cat.brain.water_x = x
            elif kind == "wall_shelf":
                # fixed to the 'wall' at the dropped height — never falls
                y = min(max(pos.y(), 140.0), self.desktop.floor_y - 80)
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
            fy = self.desktop.floor_y
            plats += [
                Platform(x - 54, x + 42, fy - 108, "Katzenbaum"),
                Platform(x - 24, x + 66, fy - 192, "Katzenbaum"),
            ]
        if self.cat.brain.scratch_x is not None:
            x = self.cat.brain.scratch_x
            fy = self.desktop.floor_y
            # wide top platform of the scratching post (canvas cols 2-21)
            plats.append(Platform(x - 30, x + 27, fy - 192, "Kratzbaum"))
        if self.cat.brain.bed_x is not None:
            x = self.cat.brain.bed_x
            fy = self.desktop.floor_y
            # the cushion IS a surface: the cat lies IN the bed, not next to it
            plats.append(Platform(x - 55, x + 55, fy - 27, "Katzennest"))
        if self.cat.brain.wheel_x is not None:
            x = self.cat.brain.wheel_x
            fy = self.desktop.floor_y
            plats.append(Platform(x - 60, x + 60, fy - 42, "Laufrad"))
        if self.cat.brain.box_x is not None:
            x = self.cat.brain.box_x
            fy = self.desktop.floor_y
            # the box's inner floor: the cat sits IN the cardboard box
            plats.append(Platform(x - 55, x + 55, fy - 30, "Karton"))
        for sx, sy in self.cat.brain.shelves:
            # floating wall shelves: fixed at their placed height (P25)
            plats.append(Platform(sx - 60, sx + 60, sy, "Regal"))
        self.desktop.set_extra_platforms(plats)

    def _ghost_rect(self) -> QRect:
        if not self._placing:
            return QRect()
        key = {"water_fountain": "fountain_0"}.get(self._placing, self._placing)
        pm = self._props[key]
        cx, cy = self.desktop.cursor
        return QRect(cx - pm.width() // 2, cy - pm.height() // 2,
                     pm.width(), pm.height())

    # -- toys (called from the tray menu) --------------------------------------

    def toggle_string(self, on: bool) -> None:
        if on:
            cx, cy = self.desktop.cursor
            self.toys.spawn("string", float(cx), float(cy + 150))
        else:
            self.toys.remove("string")

    def clear_toys(self) -> None:
        self.toys.toys.clear()

    def _signature(self) -> tuple:
        """Everything that can change what's on screen. Repaint only on change."""
        c = self.cat
        ph = self._door_phase()
        return (
            self._anim_key(), c.frame, int(c.body.x), int(c.body.y), c.body.facing,
            c.brain.bubble, c.blink_active, self._placing, self.cat_layer(),
            tuple((t.kind, round(t.x), round(t.y)) for t in self.toys.toys),
            round(self._wheel_angle), c.brain.wheel_x,
            # the bubble's bob phase: missing this caused stale-bubble streaks
            int(2.5 * math.sin(self._time * 3.0)) if c.brain.bubble else 0,
            # the cat door animation frame (P27)
            int(ph * 5) if ph >= 0 else -1,
        )

    def _is_active(self) -> bool:
        b = self.cat.body
        if b.airborne or b.target_x is not None or self._placing or self.cat.blink_active:
            return True
        if self._door is not None:
            return True  # the flap must animate smoothly (P27)
        if self.cat.anim_state in ("walk", "run", "jump", "scratch", "wiggle",
                                   "tail_lash", "knead", "cover", "drink",
                                   "stretch", "yawn", "retch"):
            return True
        if self.cat.brain.state in ("wheel_run", "hunt_pounce", "hunt_stalk",
                                    "scratching", "startle_air"):
            return True
        if any(abs(t.vx) > 1 or abs(t.vy) > 1 for t in self.toys.toys):
            return True
        # interactions near the cat stay responsive even when it idles
        cx, cy = self.desktop.cursor
        near = abs(cx - b.x) < 300 and abs(cy - b.y) < 300
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
            if self.debug:
                p.setPen(QPen(QColor(0, 255, 0, 160), 2))
                for plat in self.desktop.platforms:
                    p.drawLine(int(plat.x0), int(plat.y), int(plat.x1), int(plat.y))
            # (exercise wheel lives entirely on the FurnitureLayer since P23)
            # cat (only when she's on the front level; the FurnitureLayer draws
            # her when she has stepped back to the furniture level)
            if self.cat_layer() == "front":
                bank = self.bank_right if self.cat.body.facing >= 0 else self.bank_left
                key = self._anim_key()
                frame_idx = self.cat.frame % bank.frame_count(key)
                frame = bank.frame(key, frame_idx)
                cr = self._cat_rect()
                p.drawPixmap(cr.x(), cr.y(), frame)
                acc = bank.accessory_frame(key, frame_idx)
                if acc is not None:
                    p.drawPixmap(cr.x(), cr.y(), acc)
            # (wheel front arc is drawn on the FurnitureLayer with the wheel)
            # toys (ball/plush are drawn bottom-aligned: contact point = sprite
            # bottom, like the cat's feet; the string lure stays center-aligned)
            for toy in self.toys.toys:
                if not (math.isfinite(toy.x) and math.isfinite(toy.y)) \
                        or abs(toy.x) > 10000 or abs(toy.y) > 10000:
                    continue  # out-of-world toy: never crash the paint (P25)
                if toy.kind == "string":
                    ax, ay = toy.anchor
                    p.setPen(QPen(QColor(240, 210, 90, 220), 2))
                    p.drawLine(int(ax), int(ay), int(toy.x), int(toy.y))
                    pm = self._props["lure"]
                    p.drawPixmap(int(toy.x) - pm.width() // 2,
                                 int(toy.y) - pm.height() // 2, pm)
                else:
                    pm = self._props[toy.kind]
                    p.drawPixmap(int(toy.x) - pm.width() // 2,
                                 int(toy.y) - pm.height(), pm)
            # thought bubble (front level only; back level draws it with the cat)
            if self.cat.brain.bubble and self.cat_layer() == "front":
                br = self._bubble_rect()
                p.drawPixmap(br.x(), br.y(), self._props[self.cat.brain.bubble])
            # the cat door (P27): a flapping portal at the level-crossing point
            ph = self._door_phase()
            if ph >= 0 and self._door is not None:
                dx, dy = self._door[0], self._door[1]
                frame = ("cat_door_0", "cat_door_1", "cat_door_2",
                         "cat_door_2", "cat_door_1")[min(int(ph * 5), 4)]
                pm = self._props[frame]
                p.drawPixmap(int(dx) - pm.width() // 2, int(dy) - pm.height(), pm)
            # placement ghost + hint
            if self._placing:
                gr = self._ghost_rect()
                p.setOpacity(0.65)
                key = {"water_fountain": "fountain_0"}.get(self._placing, self._placing)
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
