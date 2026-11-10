"""The tray icon: a left click opens the Control Center; the menu holds only
the quick actions (everything else lives in the Control Center)."""

from __future__ import annotations

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from plasmacat.cat.render import SpriteBank


def mood_word(mood: float) -> str:
    return "happy" if mood >= 70 else "content" if mood >= 40 else "grumpy"


class Tray:
    def __init__(self, ctl, center, parent) -> None:
        self.ctl, self.center = ctl, center
        self.icon = QSystemTrayIcon(self._icon(), parent)
        self.icon.setToolTip("PlasmaCat")
        self.icon.activated.connect(self._activated)
        self.menu = QMenu()
        self.header = QAction("PlasmaCat", self.menu)
        self.header.setEnabled(False)
        self.menu.addAction(self.header)
        self.menu.addSeparator()
        self._add("Give treat", ctl.give_treat)
        toys = self.menu.addMenu("Toys")
        a = toys.addAction("Place a ball…")
        a.triggered.connect(lambda: ctl.place("ball"))
        a = toys.addAction("Place a plush mouse…")
        a.triggered.connect(lambda: ctl.place("plush"))
        self.string = toys.addAction("Wave a string")
        self.string.setCheckable(True)
        self.string.toggled.connect(ctl.toggle_string)
        self.laser = toys.addAction("Laser pointer")
        self.laser.setCheckable(True)
        self.laser.toggled.connect(ctl.toggle_laser)
        self.pause = self.menu.addAction("Pause cats")
        self.pause.setCheckable(True)
        self.pause.setToolTip("Hide all cats for a while (they keep their needs)")
        self.pause.toggled.connect(ctl.set_paused)
        self.sound = self.menu.addAction("Sound")
        self.sound.setCheckable(True)
        self.sound.toggled.connect(lambda on: ctl.update_settings(sound_on=on))
        self.menu.addSeparator()
        self._add("Control Center…", lambda: center.show_tab("cats"))
        self._add("Quit PlasmaCat", ctl.quit)
        self.menu.aboutToShow.connect(self.refresh)
        self.icon.setContextMenu(self.menu)
        ctl.changed.connect(self._update_icon)
        self._icon_key = None
        self.icon.show()

    def _add(self, text: str, slot) -> QAction:
        a = self.menu.addAction(text)
        a.triggered.connect(slot)
        return a

    def _icon(self) -> QIcon:
        cat = self.ctl.overlay.cat
        c = cat.cust
        bank = SpriteBank(c.to_palette(), c.pattern, device_px=1,
                          accessory=c.collar is not None, stage=cat.brain.stage)
        return QIcon(bank.frame("sit", 0))

    def _update_icon(self) -> None:
        cat = self.ctl.overlay.cat
        key = (cat.cust.fur, cat.cust.pattern, cat.cust.collar, cat.brain.stage)
        if key != self._icon_key:
            self._icon_key = key
            self.icon.setIcon(self._icon())

    def _activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:   # left click
            if self.center.isVisible():
                self.center.hide()
            else:
                self.center.show_tab("cats")

    def refresh(self) -> None:
        o = self.ctl.overlay
        cat = o.active
        names = f"{cat.cust.name} · {mood_word(cat.brain.mood)}"
        if len(o.cats) > 1:
            names += f"  ({len(o.cats)} cats)"
        self.header.setText(names)
        kinds = {t.kind for t in o.toys.toys}
        for action, on in ((self.string, "string" in kinds), (self.laser, "laser" in kinds),
                           (self.sound, self.ctl.settings.sound_on),
                           (self.pause, self.ctl.paused)):
            action.blockSignals(True)
            action.setChecked(on)
            action.blockSignals(False)
        self._update_icon()

    def notify(self, title: str, msg: str) -> None:
        self.icon.showMessage(title, msg, QSystemTrayIcon.MessageIcon.Information, 6000)
