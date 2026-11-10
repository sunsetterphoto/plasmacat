"""AppController: every user action in one place.

The tray menu and the Control Center both call these methods, so an action
behaves the same wherever it is triggered, and settings changes are applied
to the overlay and the sound player immediately.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QStandardPaths, Signal

from plasmacat import paths
from plasmacat.persist import Settings

ROOT = Path(__file__).resolve().parents[2]   # checkout root (run.sh lives here)
MAX_CATS = 4


def _autostart_path() -> Path:
    base = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.ConfigLocation))
    return base / "autostart" / "plasmacat.desktop"


def launcher_exec() -> str:
    """What the desktop entries run: the stable install path if PlasmaCat
    was installed with install.sh, else this checkout's run.sh."""
    installed = Path.home() / ".local/share/plasmacat/app/run.sh"
    return str(installed if installed.exists() else ROOT / "run.sh")


def install_desktop_file(target: Path) -> None:
    lines = paths.data_file("plasmacat.desktop").read_text(encoding="utf-8").splitlines()
    lines = [f"Exec={launcher_exec()}" if ln.startswith("Exec=") else ln for ln in lines]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


class AppController(QObject):
    changed = Signal()          # something the UIs show has changed

    def __init__(self, overlay, player, bridge, settings: Settings,
                 save: Callable[[], None], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.overlay = overlay
        self.player = player
        self.bridge = bridge
        self.settings = settings
        self._save = save
        self.quit_requested: Callable[[], None] | None = None
        self.show_control_center: Callable[[str], None] | None = None
        self.apply_settings()

    # -- persistence --------------------------------------------------------------

    def save_now(self) -> None:
        self._save()

    # -- settings -------------------------------------------------------------------

    def apply_settings(self) -> None:
        """Push every setting to the overlay and the sound player."""
        s = self.settings
        if self.player is not None:
            self.player.set_muted(not s.sound_on)
            self.player.set_volume(s.volume)
            for group, on in s.sound_groups.items():
                self.player.set_group_enabled(group, on)
        if self.overlay.pixel_size != s.pixel_size:
            self.overlay.set_pixel_size(s.pixel_size)
        self.overlay.refresh_status_board()
        self.changed.emit()

    def update_settings(self, **values) -> None:
        for k, v in values.items():
            setattr(self.settings, k, v)
        self.apply_settings()

    def set_flag(self, field: str, key: str, on: bool) -> None:
        """One switch inside a per-entry dict (sound groups, status rows…)."""
        getattr(self.settings, field)[key] = on
        self.apply_settings()

    def reset_tab(self, tab: str) -> None:
        self.settings.reset(tab)
        self.apply_settings()

    # -- cats ---------------------------------------------------------------------

    @property
    def cats(self) -> list:
        return self.overlay.cats

    def give_treat(self, cat=None) -> None:
        (cat or self.overlay.active).brain.on_treat()
        self.changed.emit()

    def customize(self, cat, parent=None) -> bool:
        from plasmacat.ui.appearance_editor import AppearanceDialog
        result = AppearanceDialog(cat.cust, stage=cat.brain.stage,
                                  title=f"PlasmaCat — {cat.cust.name}",
                                  parent=parent).customization()
        if result is None:
            return False
        self.overlay.set_customization(result, cat)
        self.save_now()
        self.changed.emit()
        return True

    def can_add_kitten(self) -> bool:
        return len(self.cats) < MAX_CATS

    def add_kitten(self, parent=None) -> bool:
        from plasmacat.ui.appearance_editor import (
            KITTEN_NAMES, AppearanceDialog, random_customization)
        if not self.can_add_kitten():
            return False
        used = {c.cust.name for c in self.cats}
        name = next((n for n in KITTEN_NAMES if n not in used), "Kitty")
        result = AppearanceDialog(random_customization(name), stage=0,
                                  title="PlasmaCat — A new kitten!",
                                  parent=parent).customization()
        if result is None:
            return False
        self.overlay.add_kitten(result)
        self.save_now()
        self.changed.emit()
        return True

    def remove_cat(self, cat) -> bool:
        ok = self.overlay.remove_cat(cat)
        if ok:
            self.save_now()
            self.changed.emit()
        return ok

    # -- play ---------------------------------------------------------------------

    def place(self, kind: str) -> None:
        self.overlay.begin_placement(kind)

    def toggle_string(self, on: bool) -> None:
        self.overlay.toggle_string(on)

    def toggle_laser(self, on: bool) -> None:
        self.overlay.toggle_laser(on)

    def set_control(self, on: bool) -> None:
        self.overlay.set_user_control(on)
        self.changed.emit()

    def start_hunt(self) -> None:
        self.overlay.start_mouse_hunt()

    def clear_toys(self) -> None:
        self.overlay.clear_toys()
        self.changed.emit()

    @property
    def paused(self) -> bool:
        return "pause" in self.overlay._hidden

    def set_paused(self, on: bool) -> None:
        self.overlay.set_hidden("pause", on)
        self.changed.emit()

    # -- home ---------------------------------------------------------------------

    def remove_furniture(self, kind: str, index: int | None = None) -> None:
        self.overlay.remove_furniture(kind, index)
        self.save_now()
        self.changed.emit()

    def refill_food(self) -> None:
        self.overlay.active.brain.refill_food()
        self.changed.emit()

    def buy_food(self, food_id: str) -> None:
        self.overlay.active.brain.buy_food(food_id)
        self.changed.emit()

    def clean_litter(self) -> None:
        self.overlay.active.brain.clean_litter()
        self.changed.emit()

    def clean_puke(self) -> None:
        self.overlay.active.brain.clean_puke()
        self.changed.emit()

    def place_status_board(self) -> None:
        if not self.settings.status_board:
            self.update_settings(status_board=True)
        self.overlay.begin_placement("status")

    # -- system ---------------------------------------------------------------------

    def autostart_enabled(self) -> bool:
        return _autostart_path().exists()

    def set_autostart(self, on: bool) -> None:
        """XDG autostart entry (and the app launcher, so the portal knows us)."""
        if on:
            install_desktop_file(_autostart_path())
            apps = Path(QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.ApplicationsLocation)) / "plasmacat.desktop"
            if not apps.exists():
                install_desktop_file(apps)
        else:
            _autostart_path().unlink(missing_ok=True)
        self.changed.emit()

    def reset_household(self, save_path: Path) -> None:
        """Start over: delete the save and restart into the first-run flow."""
        save_path.unlink(missing_ok=True)
        self.bridge.stop()   # clean handover to the new process (P29)
        os.execvpe(sys.executable, [sys.executable, "-m", "plasmacat.main"], os.environ)

    def quit(self) -> None:
        if self.quit_requested is not None:
            self.quit_requested()

