"""PlasmaCat entry point.

Usage:
  python -m plasmacat.main [--debug] [--setup]   start the game
  python -m plasmacat.main --unload-bridge       unload a leftover KWin script and exit

First run (no save file) opens the customization wizard. State is saved to
~/.local/share/plasmacat/save.json every 30 s and on quit.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "kwin" / "plasmacat-bridge.js"


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

    from plasmacat.bridge.kwin import KWinBridge
    from plasmacat.cat.brain import NEED_DECAY
    from plasmacat.cat.render import SpriteBank
    from plasmacat.overlay import Overlay
    from plasmacat.persist import Customization, GameState
    from plasmacat.sound.packs import SoundPlayer
    from plasmacat.sound.synth import build_pack
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

    pack_dir = data_dir / "sounds" / "retro"
    build_pack(pack_dir)
    # natural pack ships in the repo (assets/) and is copied on first run
    import shutil as _shutil

    natural_src = ROOT / "assets" / "sounds" / "natural"
    natural_dst = data_dir / "sounds" / "natural"
    natural_dst.mkdir(parents=True, exist_ok=True)
    for f in natural_src.glob("*.*"):
        if not (natural_dst / f.name).exists():
            _shutil.copy2(f, natural_dst / f.name)
    player = SoundPlayer(data_dir / "sounds", pack=cust.sound_pack,
                         muted=not cust.sound_on, volume=cust.volume)

    overlay = Overlay(bridge, player=player, cust=cust, debug="--debug" in sys.argv)
    brain = overlay.cat.brain

    if state is not None:  # restore progress (with offline decay)
        restored = persist.offline_decay(state.needs, state.saved_at, NEED_DECAY)
        brain.needs.update(restored)
        brain.attachment_xp = state.attachment_xp
        brain.petted_strokes = state.petted_strokes
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
        brain.tree_x = state.tree_x
        brain.wheel_x = state.wheel_x
        brain.box_x = state.box_x
        brain.shelves = [(float(s.get("x", 400)), float(s.get("y", 300)))
                         for s in state.shelves]
        brain.puke_spots = list(state.puke_spots)
        if state.fav_toy in ("ball", "plush"):
            brain.fav_toy = state.fav_toy
        overlay._sync_furniture_platforms()
        for t in state.toys:
            if t.get("kind") in ("ball", "plush"):
                # clamp into the work area: older saves may hold positions from
                # broken builds (corner jams, the below-the-floor void bug)
                x = min(max(float(t.get("x", 400)), overlay.desktop.floor_x0 + 80),
                        overlay.desktop.floor_x1 - 80)
                y = min(max(float(t.get("y", overlay.desktop.floor_y)), 0.0),
                        overlay.desktop.floor_y)
                overlay.toys.spawn(t["kind"], x, y)

    # -- saving ---------------------------------------------------------------
    def collect_state() -> GameState:
        return GameState(
            customization=overlay.cust,
            needs=dict(brain.needs),
            attachment_xp=brain.attachment_xp,
            petted_strokes=brain.petted_strokes,
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
            tree_x=brain.tree_x,
            wheel_x=brain.wheel_x,
            box_x=brain.box_x,
            shelves=[{"x": sx, "y": sy} for sx, sy in brain.shelves],
            puke_spots=list(brain.puke_spots),
            fav_toy=brain.fav_toy,
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
                          accessory=c.collar is not None)
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
    treat_action.triggered.connect(brain.on_treat)
    menu.addAction(treat_action)

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
    clear_action = QAction("Clear toys", toys_menu)
    clear_action.triggered.connect(overlay.clear_toys)
    toys_menu.addAction(clear_action)

    bowls_menu = menu.addMenu("Bowls")
    for label, kind in (("Place food bowl…", "food_bowl"),
                        ("Place water fountain…", "water_fountain")):
        a = QAction(label, bowls_menu)
        a.triggered.connect(lambda checked, k=kind: overlay.begin_placement(k))
        bowls_menu.addAction(a)
    bowls_menu.addSeparator()
    refill_food_action = QAction("Refill food", bowls_menu)
    refill_food_action.triggered.connect(brain.refill_food)
    bowls_menu.addAction(refill_food_action)

    from plasmacat.cat.brain import FOODS
    shop_menu = menu.addMenu("Food shop")
    for fid, food in FOODS.items():
        a = QAction(f"Buy {food['label']}", shop_menu)
        a.triggered.connect(lambda checked, f=fid: brain.buy_food(f))
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
    clean_litter_action.triggered.connect(brain.clean_litter)
    furniture_menu.addAction(clean_litter_action)
    puke_action = QAction("Clean up vomit", furniture_menu)
    puke_action.triggered.connect(brain.clean_puke)
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

    pack_menu = sound_menu.addMenu("Sound pack")
    pack_actions: dict[str, QAction] = {}
    for pid, label in (("retro", "Retro (8-bit synth)"),
                       ("natural", "Natural (real cat)")):
        a = QAction(label, pack_menu)
        a.setCheckable(True)
        a.setChecked(player.pack == pid)
        pack_actions[pid] = a

        def set_sound_pack(checked: bool, p: str = pid) -> None:
            player.set_pack(p)
            overlay.cust.sound_pack = p
            for k, x in pack_actions.items():
                x.setChecked(k == p)

        a.triggered.connect(set_sound_pack)
        pack_menu.addAction(a)
    menu.addSeparator()

    customize_action = QAction("Customize…", menu)

    def open_wizard() -> None:
        wiz = SetupWizard(overlay.cust)
        if wiz.exec() == QDialog.DialogCode.Accepted:
            c = wiz.result_customization()
            overlay.set_customization(c)
            player.set_muted(not c.sound_on)
            player.set_volume(c.volume)
            tray.setIcon(tray_icon(c))
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
        status_action.setText(
            f"{overlay.cust.name} — {brain.attachment_name} ({int(brain.attachment_xp)} XP)")
        for need, action in need_actions.items():
            label = "Litter" if need == "bladder" else need.capitalize()
            action.setText(f"{label:<10} {_bar(brain.needs[need])}")
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
