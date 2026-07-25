"""PlasmaCat entry point.

Usage:
  python -m plasmacat.main [--debug] [--setup]   start the game
  python -m plasmacat.main --unload-bridge       unload a leftover KWin script and exit

First run (no save file) opens the customization wizard. State is saved to
~/.local/share/plasmacat/save.json every 30 s and on quit.
"""

from __future__ import annotations

import os
import random
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "kwin" / "plasmacat-bridge.js"
DESKTOP_FILE = ROOT / "plasmacat.desktop"


def _xdg_dir(location) -> Path:
    from PySide6.QtCore import QStandardPaths
    return Path(QStandardPaths.writableLocation(location))


def _autostart_path() -> Path:
    from PySide6.QtCore import QStandardPaths
    return _xdg_dir(QStandardPaths.StandardLocation.ConfigLocation) / \
        "autostart" / "plasmacat.desktop"


def autostart_enabled() -> bool:
    return _autostart_path().exists()


def set_autostart(enabled: bool) -> None:
    """Tray 'Start at login': install/remove the XDG autostart entry.
    Enabling also installs the app launcher (fixes the portal warning).
    The Exec line is rewritten to this checkout's run.sh, so the entries
    keep working after the project folder is moved."""
    from PySide6.QtCore import QStandardPaths
    if enabled:
        target = _autostart_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        _install_desktop_file(target)
        apps = _xdg_dir(QStandardPaths.StandardLocation.ApplicationsLocation) / \
            "plasmacat.desktop"
        if not apps.exists():
            apps.parent.mkdir(parents=True, exist_ok=True)
            _install_desktop_file(apps)
    else:
        _autostart_path().unlink(missing_ok=True)


def _install_desktop_file(target: Path) -> None:
    """Install our desktop file with Exec pointing at this checkout."""
    lines = DESKTOP_FILE.read_text(encoding="utf-8").splitlines()
    lines = [f"Exec={ROOT / 'run.sh'}" if line.startswith("Exec=") else line
             for line in lines]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _bar(value: float) -> str:
    filled = round(value / 100 * 8)
    return "█" * filled + "░" * (8 - filled)


def main() -> int:
    from PySide6.QtCore import QCoreApplication, QStandardPaths, QTimer
    from PySide6.QtGui import QAction, QGuiApplication, QIcon
    from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QSystemTrayIcon

    if "--unload-bridge" in sys.argv:
        app = QCoreApplication(sys.argv)  # needed for the DBus connection
        from plasmacat.bridge.kwin import unload_bridge

        unload_bridge()
        print("bridge unload requested")
        return 0

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tray app: no normal windows
    # NOTE: the data dir stays 'catgame' (~/.local/share/catgame) so existing
    # saves survive the PlasmaCat rename (P33)
    QCoreApplication.setApplicationName("catgame")
    QGuiApplication.setDesktopFileName("plasmacat")  # app_id -> KWin resourceClass
    _icon_png = ROOT / "assets" / "icons" / "plasmacat-256.png"
    if _icon_png.exists():  # repo checkout (pip installs fall back to theme)
        app.setWindowIcon(QIcon(str(_icon_png)))

    from plasmacat.bridge.kwin import KWinBridge
    from plasmacat.cat.brain import NEED_DECAY, offline_aging
    from plasmacat.cat.render import SpriteBank
    from plasmacat.overlay import Overlay
    from plasmacat.persist import CatState, Customization, GameState
    from plasmacat.sound.packs import SoundPlayer
    from plasmacat.ui.wizard import SetupWizard
    from plasmacat import persist

    data_dir = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation))
    save_path = data_dir / "save.json"

    # -- load state / first-run wizard ----------------------------------------
    state = persist.load(save_path)
    cust = state.customization if state else Customization()
    if state is None or "--setup" in sys.argv:
        wiz = SetupWizard(cust)
        if wiz.exec() == QDialog.DialogCode.Accepted:
            cust = wiz.result_customization()

    bridge = KWinBridge(str(SCRIPT_PATH))
    if not bridge.start():
        print("Could not start PlasmaCat: another instance is running or KWin "
              "refused the helper script. Try: ./run.sh --unload-bridge")
        return 1
    bridge.start_watchdog(app)  # reloads the script if Plasma/KWin restarts

    # the natural pack (real recordings, P49) ships in the repo (assets/)
    # and is copied to the data dir on first run
    natural_src = ROOT / "assets" / "sounds" / "natural"
    natural_dst = data_dir / "sounds" / "natural"
    natural_dst.mkdir(parents=True, exist_ok=True)
    for f in natural_src.glob("*.*"):
        if not (natural_dst / f.name).exists():
            shutil.copy2(f, natural_dst / f.name)
    player = SoundPlayer(data_dir / "sounds",
                         muted=not cust.sound_on, volume=cust.volume)

    overlay = Overlay(bridge, player=player, cust=cust, debug="--debug" in sys.argv)
    brain = overlay.cat.brain  # primary brain; furniture state is shared (P47)

    if state is not None:  # restore progress (with offline decay)
        elapsed = max(time.time() - state.saved_at, 0.0) if state.saved_at else 0.0
        for i, cs in enumerate(state.cats):
            cat = overlay.cat if i == 0 \
                else overlay.add_cat(cs.customization, age=cs.age)
            b = cat.brain
            b.needs.update(persist.offline_decay(cs.needs, state.saved_at,
                                                 NEED_DECAY))
            b.attachment_xp = cs.attachment_xp
            b.petted_strokes = cs.petted_strokes
            if cs.fav_toy in ("ball", "plush"):
                b.fav_toy = cs.fav_toy
            # the clock ticked while the game was closed (neglect pace, P47)
            b.age, b.care = offline_aging(cs.age, cs.care, elapsed)
        brain.food_type = state.food_type
        brain.food_fill = state.food_fill
        brain.water_fill = state.water_fill
        if state.food_x is not None:
            brain.food_x = state.food_x
        if state.water_x is not None:
            brain.water_x = state.water_x
        brain.scratch_x = state.scratch_x
        brain.bed_x = state.bed_x
        brain.grass_x = state.grass_x
        brain.grass_charges = state.grass_charges
        brain.litter_x = state.litter_x
        brain.litter_fill = state.litter_fill
        brain.litter_deposits = list(state.litter_deposits)
        brain.tree_x = state.tree_x
        brain.wheel_x = state.wheel_x
        brain.box_x = state.box_x
        brain.shelves = [(float(s.get("x", 400)), float(s.get("y", 300)))
                         for s in state.shelves]
        brain.puke_spots = list(state.puke_spots)
        overlay._sync_furniture_platforms()
        for t in state.toys:
            if t.get("kind") in ("ball", "plush"):
                # clamp into the work area: older saves may hold positions from
                # broken builds (corner jams, the below-the-floor void bug)
                x = min(max(float(t.get("x", 400)), overlay.desktop.floor_x0 + 80),
                        overlay.desktop.floor_x1 - 80)
                fy = overlay.desktop.floor_y_at(x)  # the toy's own screen (P38)
                y = min(max(float(t.get("y", fy)), 0.0), fy)
                overlay.toys.spawn(t["kind"], x, y)
    else:
        brain.age = 0.0  # a fresh game: you raise her from a kitten (P47)

    # -- saving ---------------------------------------------------------------
    def collect_state() -> GameState:
        return GameState(
            cats=[CatState(customization=c.cust,
                           needs=dict(c.brain.needs),
                           attachment_xp=c.brain.attachment_xp,
                           petted_strokes=c.brain.petted_strokes,
                           age=c.brain.age,
                           care=c.brain.care,
                           fav_toy=c.brain.fav_toy)
                  for c in overlay.cats],
            toys=[{"kind": t.kind, "x": t.x, "y": t.y}
                  for t in overlay.toys.toys if t.kind in ("ball", "plush")],
            food_type=brain.food_type,
            food_fill=brain.food_fill,
            water_fill=brain.water_fill,
            food_x=brain.food_x,
            water_x=brain.water_x,
            scratch_x=brain.scratch_x,
            bed_x=brain.bed_x,
            grass_x=brain.grass_x,
            grass_charges=brain.grass_charges,
            litter_x=brain.litter_x,
            litter_fill=brain.litter_fill,
            litter_deposits=list(brain.litter_deposits),
            tree_x=brain.tree_x,
            wheel_x=brain.wheel_x,
            box_x=brain.box_x,
            shelves=[{"x": sx, "y": sy} for sx, sy in brain.shelves],
            puke_spots=list(brain.puke_spots),
        )

    def save_now() -> None:
        persist.save(save_path, collect_state())

    save_timer = QTimer(app)
    save_timer.timeout.connect(save_now)
    save_timer.start(30_000)
    app.aboutToQuit.connect(save_now)

    # -- tray -----------------------------------------------------------------
    def tray_icon(c: Customization) -> QIcon:
        bank = SpriteBank(palette=c.to_palette(), pattern=c.pattern, scale=1,
                          accessory=c.collar is not None,
                          stage=overlay.cat.brain.stage)
        return QIcon(bank.frame("sit", 0))

    tray = QSystemTrayIcon(tray_icon(cust), app)
    menu = QMenu()

    status_action = QAction("PlasmaCat", menu)
    status_action.setEnabled(False)
    menu.addAction(status_action)
    need_actions: dict[str, QAction] = {}
    for need in ("hunger", "thirst", "energy", "play", "affection", "bladder"):
        a = QAction("", menu)
        a.setEnabled(False)
        menu.addAction(a)
        need_actions[need] = a
    fill_actions: dict[str, QAction] = {}
    for key in ("food_fill", "water_fill", "litter_fill"):
        a = QAction("", menu)
        a.setEnabled(False)
        menu.addAction(a)
        fill_actions[key] = a
    menu.addSeparator()

    treat_action = QAction("Give treat", menu)
    treat_action.triggered.connect(lambda: overlay.active.brain.on_treat())
    menu.addAction(treat_action)

    status_win_action = QAction("Status widget", menu)
    status_win_action.setCheckable(True)
    status_win_action.setChecked(cust.status_window)
    status_win_action.toggled.connect(overlay.set_status_window)
    menu.addAction(status_win_action)
    overlay._status_action = status_win_action
    if cust.status_window:
        overlay.set_status_window(True)
    status_pos_action = QAction("Position status widget…", menu)

    def place_status() -> None:
        if not overlay.cust.status_window:
            overlay.set_status_window(True)  # placing implies pinning it
        overlay.begin_placement("status")

    status_pos_action.triggered.connect(place_status)
    menu.addAction(status_pos_action)

    control_action = QAction("Control cat (WASD/arrows)", menu)
    control_action.setCheckable(True)
    control_action.toggled.connect(overlay.set_user_control)
    menu.addAction(control_action)
    if "--control" in sys.argv:  # dev shortcut: start in control mode
        control_action.setChecked(True)

    toys_menu = menu.addMenu("Toys")
    for label, kind in (("Place ball…", "ball"),
                        ("Place plush mouse…", "plush")):
        a = QAction(label, toys_menu)
        a.triggered.connect(lambda checked, k=kind: overlay.begin_placement(k))
        toys_menu.addAction(a)
    string_action = QAction("Wave string", toys_menu)
    string_action.setCheckable(True)
    string_action.toggled.connect(overlay.toggle_string)
    toys_menu.addAction(string_action)
    overlay._string_action = string_action  # synced by 'Clear toys' (P42)
    laser_action = QAction("Laser pointer", toys_menu)
    laser_action.setCheckable(True)
    laser_action.toggled.connect(overlay.toggle_laser)
    toys_menu.addAction(laser_action)
    overlay._laser_action = laser_action
    clear_action = QAction("Clear toys", toys_menu)
    clear_action.triggered.connect(overlay.clear_toys)
    toys_menu.addAction(clear_action)

    games_menu = menu.addMenu("Games")
    hunt_action = QAction("Mouse hunt (60 s)", games_menu)
    hunt_action.triggered.connect(lambda: overlay.start_mouse_hunt())
    games_menu.addAction(hunt_action)

    bowls_menu = menu.addMenu("Bowls")
    for label, kind in (("Place food bowl…", "food_bowl"),
                        ("Place water fountain…", "water_fountain")):
        a = QAction(label, bowls_menu)
        a.triggered.connect(lambda checked, k=kind: overlay.begin_placement(k))
        bowls_menu.addAction(a)
    bowls_menu.addSeparator()
    refill_food_action = QAction("Refill food", bowls_menu)
    refill_food_action.triggered.connect(lambda: overlay.active.brain.refill_food())
    bowls_menu.addAction(refill_food_action)

    from plasmacat.cat.brain import FOODS
    shop_menu = menu.addMenu("Food shop")
    for fid, food in FOODS.items():
        a = QAction(f"Buy {food['label']}", shop_menu)
        a.triggered.connect(lambda checked, f=fid: overlay.active.brain.buy_food(f))
        shop_menu.addAction(a)

    furniture_menu = menu.addMenu("Furniture")
    for label, kind in (("Place scratching post…", "scratch_post"),
                        ("Place cat bed…", "cat_bed"),
                        ("Place cat grass…", "cat_grass"),
                        ("Place litter box…", "litter_0"),
                        ("Place big cat tree…", "cat_tree"),
                        ("Place exercise wheel…", "wheel_stand"),
                        ("Place wall shelf…", "wall_shelf"),
                        ("Place cardboard box…", "box")):
        a = QAction(label, furniture_menu)
        a.triggered.connect(lambda checked, k=kind: overlay.begin_placement(k))
        furniture_menu.addAction(a)
    furniture_menu.addSeparator()
    clean_litter_action = QAction("Clean litter box", furniture_menu)
    clean_litter_action.triggered.connect(lambda: overlay.active.brain.clean_litter())
    furniture_menu.addAction(clean_litter_action)
    puke_action = QAction("Clean up vomit", furniture_menu)
    puke_action.triggered.connect(lambda: overlay.active.brain.clean_puke())
    furniture_menu.addAction(puke_action)
    remove_furniture_action = QAction("Remove furniture", furniture_menu)

    def clear_furniture() -> None:
        brain.scratch_x = None
        brain.bed_x = None
        brain.grass_x = None
        brain.litter_x = None
        brain.tree_x = None
        brain.wheel_x = None
        brain.box_x = None
        brain.shelves.clear()
        overlay._sync_furniture_platforms()

    remove_furniture_action.triggered.connect(clear_furniture)
    furniture_menu.addAction(remove_furniture_action)

    sound_menu = menu.addMenu("Sound")
    enable_action = QAction("Enabled", sound_menu)
    enable_action.setCheckable(True)
    enable_action.setChecked(not player.muted)
    enable_action.toggled.connect(lambda on: (player.set_muted(not on),
                                              setattr(overlay.cust, "sound_on", on)))
    sound_menu.addAction(enable_action)

    volume_menu = sound_menu.addMenu("Volume")
    for pct in (25, 50, 75, 100):
        a = QAction(f"{pct}%", volume_menu)
        a.setCheckable(True)
        a.setChecked(pct == round(player.volume * 100))

        def set_vol(checked: bool, v: int = pct) -> None:
            player.set_volume(v / 100)
            overlay.cust.volume = v / 100
            for x in volume_menu.actions():
                x.setChecked(x.text() == f"{v}%")

        a.triggered.connect(set_vol)
        volume_menu.addAction(a)
    menu.addSeparator()

    add_kitten_action = QAction("Add kitten…", menu)

    KITTEN_NAMES = ("Findus", "Luna", "Balu", "Kiki", "Mogli", "Nala", "Felix")

    def add_kitten() -> None:
        from plasmacat.overlay import MAX_CATS
        if len(overlay.cats) >= MAX_CATS:
            overlay.notify and overlay.notify(
                "PlasmaCat", f"The home is full — {MAX_CATS} cats are enough!")
            return
        used = {c.cust.name for c in overlay.cats}
        name = next((n for n in KITTEN_NAMES if n not in used), "Kitty")
        from plasmacat.ui.wizard import FUR_PRESETS, PATTERNS
        proto = Customization(name=name,
                              fur=random.choice(list(FUR_PRESETS.values())),
                              pattern=random.choice(PATTERNS))
        wiz = SetupWizard(proto)
        wiz.setWindowTitle("PlasmaCat — A new kitten!")
        if wiz.exec() == QDialog.DialogCode.Accepted:
            overlay.add_kitten(wiz.result_customization())
            save_now()

    add_kitten_action.triggered.connect(add_kitten)
    menu.addAction(add_kitten_action)

    customize_action = QAction("Customize…", menu)

    def open_wizard() -> None:
        wiz = SetupWizard(overlay.active.cust)  # edits the cat at the cursor
        if wiz.exec() == QDialog.DialogCode.Accepted:
            c = wiz.result_customization()
            c.status_window = overlay.cust.status_window  # keep the P39 toggle
            overlay.set_customization(c)
            # sound is global: mirror it onto the primary cust (saved there)
            overlay.cust.sound_on = c.sound_on
            overlay.cust.volume = c.volume
            player.set_muted(not c.sound_on)
            player.set_volume(c.volume)
            tray.setIcon(tray_icon(overlay.cust))
            save_now()

    customize_action.triggered.connect(open_wizard)
    menu.addAction(customize_action)

    reset_action = QAction("Reset cat…", menu)

    def reset_cat() -> None:
        answer = QMessageBox.question(
            None, "Reset cat",
            "Really reset? Your cat's attachment and progress will be lost.")
        if answer == QMessageBox.StandardButton.Yes:
            save_path.unlink(missing_ok=True)
            # clean handover: unload the KWin script before the restart,
            # otherwise the new instance races its own predecessor (P29)
            bridge.stop()
            # restart the process; the new run shows the setup wizard
            os.execvpe(sys.executable, [sys.executable, "-m", "plasmacat.main"],
                       os.environ)

    reset_action.triggered.connect(reset_cat)
    menu.addAction(reset_action)

    login_action = QAction("Start at login", menu)
    login_action.setCheckable(True)
    login_action.setChecked(autostart_enabled())
    login_action.toggled.connect(set_autostart)
    menu.addAction(login_action)
    menu.addSeparator()

    quit_action = QAction("Quit PlasmaCat", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.setToolTip("PlasmaCat")
    tray.show()
    # desktop notifications (P25): full litter box, vomit to clean up
    overlay.notify = lambda title, msg: tray.showMessage(
        title, msg, QSystemTrayIcon.MessageIcon.Information, 6000)

    def refresh_status() -> None:
        ab = overlay.active.brain  # the cat at the cursor (P47)
        header = (f"{overlay.active.cust.name} — {ab.life_stage} — "
                  f"{ab.attachment_name} ({int(ab.attachment_xp)} XP)")
        if len(overlay.cats) > 1:
            header += f"   ·   {len(overlay.cats)} cats"
        status_action.setText(header)
        for need, action in need_actions.items():
            label = "Litter" if need == "bladder" else need.capitalize()
            action.setText(f"{label:<10} {_bar(ab.needs[need])}")
        fill_actions["food_fill"].setText(
            f"{FOODS[brain.food_type]['label']:<10} {_bar(brain.food_fill)}")
        fill_actions["water_fill"].setText("Fountain  ∞")
        fill_actions["litter_fill"].setText(
            f"Litterbox {_bar(brain.litter_fill / 5 * 100)}")
        puke_action.setText(f"Clean up vomit ({len(brain.puke_spots)})")

    status_timer = QTimer(app)
    status_timer.timeout.connect(refresh_status)
    status_timer.start(2000)
    refresh_status()

    exit_code = app.exec()
    bridge.stop()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
