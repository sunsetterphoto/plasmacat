"""PlasmaCat application: bootstrap, save/restore and lifecycle (see main.py
for the CLI).

First run (no save file) opens the appearance editor for your kitten. State
is saved to ~/.local/share/plasmacat/save.json every 30 s and on quit (an old
~/.local/share/catgame dir is migrated once at startup).
"""

from __future__ import annotations

import shutil
import time

from plasmacat import paths
from plasmacat.persist import CatState, GameState

SAVE_EVERY_MS = 30_000


def install_signal_handlers(app, on_quit) -> None:
    """SIGINT/SIGTERM (Ctrl+C, logout, systemd stop) quit through Qt's event
    loop so aboutToQuit runs: final save + KWin script unload. Python signal
    handlers only run while the interpreter executes bytecode, so a short
    timer keeps waking it up inside the Qt loop."""
    import signal

    from PySide6.QtCore import QTimer

    def _handler(signum, _frame):
        print(f"[app] signal {signum}: quitting")
        on_quit()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
    app._signal_pump = QTimer(app)  # keep a reference
    app._signal_pump.timeout.connect(lambda: None)
    app._signal_pump.start(200)


# -- save / restore -----------------------------------------------------------

HOUSEHOLD_FIELDS = ("food_type", "food_fill", "water_fill", "scratch_x", "bed_x",
                    "grass_x", "grass_charges", "litter_x", "litter_fill", "tree_x",
                    "wheel_x", "box_x")


def restore_state(overlay, state: GameState) -> None:
    """Put a loaded save back into the world (needs decay while away)."""
    from plasmacat import persist
    from plasmacat.cat.brain import NEED_DECAY, offline_aging

    elapsed = max(time.time() - state.saved_at, 0.0) if state.saved_at else 0.0
    for i, cs in enumerate(state.cats):
        cat = overlay.cat if i == 0 else overlay.add_cat(cs.customization, age=cs.age)
        b = cat.brain
        b.needs.update(persist.offline_decay(cs.needs, state.saved_at, NEED_DECAY))
        b.attachment_xp = cs.attachment_xp
        b.petted_strokes = cs.petted_strokes
        if cs.fav_toy in ("ball", "plush"):
            b.fav_toy = cs.fav_toy
        b.age, b.care = offline_aging(cs.age, cs.care, elapsed)
    brain = overlay.cat.brain   # the household is shared by all brains (P47)
    for f in HOUSEHOLD_FIELDS:
        setattr(brain, f, getattr(state, f))
    if state.food_x is not None:
        brain.food_x = state.food_x
    if state.water_x is not None:
        brain.water_x = state.water_x
    brain.litter_deposits = list(state.litter_deposits)
    brain.shelves = [(float(s.get("x", 400)), float(s.get("y", 300))) for s in state.shelves]
    brain.puke_spots = list(state.puke_spots)
    overlay._sync_furniture_platforms()
    for t in state.toys:
        if t.get("kind") in ("ball", "plush"):
            # clamp into the work area (old saves from broken builds)
            x = min(max(float(t.get("x", 400)), overlay.desktop.floor_x0 + 80),
                    overlay.desktop.floor_x1 - 80)
            fy = overlay.desktop.floor_y_at(x)
            y = min(max(float(t.get("y", fy)), 0.0), fy)
            overlay.toys.spawn(t["kind"], x, y)


def collect_state(overlay, settings) -> GameState:
    brain = overlay.cat.brain
    return GameState(
        cats=[CatState(customization=c.cust, needs=dict(c.brain.needs),
                       attachment_xp=c.brain.attachment_xp,
                       petted_strokes=c.brain.petted_strokes, age=c.brain.age,
                       care=c.brain.care, fav_toy=c.brain.fav_toy)
              for c in overlay.cats],
        toys=[{"kind": t.kind, "x": t.x, "y": t.y}
              for t in overlay.toys.toys if t.kind in ("ball", "plush")],
        food_x=brain.food_x, water_x=brain.water_x,
        litter_deposits=list(brain.litter_deposits),
        shelves=[{"x": sx, "y": sy} for sx, sy in brain.shelves],
        puke_spots=list(brain.puke_spots),
        settings=settings,
        **{f: getattr(brain, f) for f in HOUSEHOLD_FIELDS},
    )


# -- run ------------------------------------------------------------------------

def run(argv: list[str]) -> int:
    from PySide6.QtCore import QCoreApplication, QTimer
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtWidgets import QApplication

    if "--unload-bridge" in argv:
        QCoreApplication(argv)  # needed for the DBus connection
        from plasmacat.bridge.kwin import unload_bridge
        from plasmacat.bridge.panels import PanelDock
        unload_bridge()
        restored = PanelDock(paths.state_dir() / "panels-docked.json").restore()
        print("bridge unload requested" + (f"; panels restored: {restored}" if restored else ""))
        return 0

    app = QApplication(argv)
    app.setQuitOnLastWindowClosed(False)  # tray app
    QCoreApplication.setApplicationName("plasmacat")
    QGuiApplication.setDesktopFileName("plasmacat")  # app_id -> KWin resourceClass
    app.setWindowIcon(QIcon(str(paths.data_file("icons/plasmacat-256.png"))))

    from plasmacat import persist
    from plasmacat.bridge.kwin import FakeBridge, activate_running_instance, make_bridge
    from plasmacat.bridge.panels import PanelDock
    from plasmacat.controller import AppController
    from plasmacat.sound.player import SoundPlayer
    from plasmacat.ui.control_center import ControlCenter
    from plasmacat.ui.first_run import first_run
    from plasmacat.ui.tray import Tray
    from plasmacat.world.overlay import Overlay

    if paths.migrate_legacy():
        print("[persist] migrated ~/.local/share/catgame -> plasmacat")
    data_dir = paths.state_dir()
    shutil.rmtree(data_dir / "sounds", ignore_errors=True)  # old sound copies (<0.2)
    save_path = data_dir / "save.json"

    bridge = make_bridge(str(paths.data_file("kwin/bridge.js")))
    if not bridge.start():
        if bridge.error == "running":
            activate_running_instance()
            print("PlasmaCat is already running — brought it to the front.")
            return 0
        print("Could not start PlasmaCat: KWin refused the helper script. "
              "Try: ./run.sh --unload-bridge")
        return 1
    bridge.start_watchdog(app)  # reloads the script if Plasma/KWin restarts

    # (after the bridge: a second launch must find the running instance,
    # not open a second first-run dialog)
    state = persist.load(save_path)
    settings = state.settings if state else persist.Settings()
    fresh = state is None
    cust = state.customization if state else None
    if fresh or "--setup" in argv:
        cust = first_run(cust) or cust or persist.Customization()

    player = SoundPlayer(paths.data_file("sounds"),
                         muted=not settings.sound_on, volume=settings.volume)
    overlay = Overlay(bridge, player=player, cust=cust, settings=settings,
                      debug="--debug" in argv)
    if state is not None:
        restore_state(overlay, state)
        if "--setup" in argv:
            overlay.set_customization(cust, overlay.cat)
    else:
        overlay.cat.brain.age = 0.0  # a fresh game: you raise her from a kitten

    def save_now() -> None:
        persist.save(save_path, collect_state(overlay, settings))

    ctl = AppController(overlay=overlay, player=player, bridge=bridge,
                        settings=settings, save=save_now)
    if not isinstance(bridge, FakeBridge):       # never touch a panel in tests
        ctl.panel_dock = PanelDock(data_dir / "panels-docked.json")
        ctl.apply_settings()
    center = ControlCenter(ctl, save_path=save_path)
    ctl.show_control_center = center.show_tab
    ctl.quit_requested = app.quit
    tray = Tray(ctl, center, app)
    overlay.notify = tray.notify
    ctl.watch_updates()
    tray.icon.messageClicked.connect(ctl.notification_clicked)
    if ctl.is_installed_copy() and settings.auto_update:   # also check at startup
        QTimer.singleShot(20_000, lambda: ctl.check_updates_now(lambda _m: None,
                                                                manual=False))
    bridge.activateRequested.connect(lambda: center.show_tab("cats"))
    if "--control" in argv:   # dev shortcut: start in control mode
        ctl.set_control(True)
    if fresh:
        QTimer.singleShot(600, lambda: center.show_tab("home"))

    save_timer = QTimer(app)
    save_timer.timeout.connect(save_now)
    save_timer.start(SAVE_EVERY_MS)

    def shutdown() -> None:
        try:
            save_now()
        finally:
            ctl.shutdown()       # undock panels
            bridge.stop()

    app.aboutToQuit.connect(shutdown)
    install_signal_handlers(app, app.quit)
    QTimer.singleShot(0, lambda: print("[app] ready", flush=True))
    return app.exec()
