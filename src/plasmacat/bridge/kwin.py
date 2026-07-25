"""Bridge to KWin: loads the helper KWin script and hosts the DBus service it calls.

The KWin script (kwin/plasmacat-bridge.js) pushes data to us via callDBus:
  SetCursor("x,y")       -> cursorChanged(int, int)     (~30 Hz while moving)
  SetWindows("[...]")    -> windowsChanged(list[dict])  (on any window change)
  SetWorkAreas("[...]")  -> workAreasChanged(list[dict]) (one work area per screen, P38)
  SetWorkArea("{...}")   -> workAreaChanged(dict)       (legacy single-area form)
  OverlayTagged("...")   -> overlayTagged(str)          (our overlay got keepAbove etc.)
  KeyEvent("left")       -> keyEvent(str)               (P42 control-mode shortcuts)
All DBus arguments are single strings (DECISIONS.md D3).

IMPORTANT (DECISIONS.md D10): the DBus interface name QtDBus auto-generates for a
Python QObject is NONDETERMINISTIC (seen: 'local.py.main.BridgeService',
'local.plasmacat.BridgeService'). We therefore introspect ourselves at startup and
inject the discovered name into the JS template (__CATGAME_IFACE__ placeholder),
writing the concrete script to kwin/plasmacat-bridge.runtime.js.
"""

from __future__ import annotations

import json
import re

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface

SCRIPT_PLUGIN = "plasmacat-bridge"
SERVICE = "org.plasmacat.Bridge"
OBJPATH = "/Bridge"
IFACE_PLACEHOLDER = "__CATGAME_IFACE__"
CONTROL_PLACEHOLDER = "__CONTROL_MODE__"  # P42: control-mode key shortcuts


class BridgeService(QObject):
    """DBus-facing object. Slot names become DBus methods under the
    auto-generated interface 'BridgeService' (must match IFACE in the JS)."""

    cursorChanged = Signal(int, int)
    windowsChanged = Signal(list)
    workAreaChanged = Signal(dict)
    workAreasChanged = Signal(list)
    overlayTagged = Signal(str)
    keyEvent = Signal(str)  # P42: control-mode key from a KWin shortcut

    @Slot(str)
    def SetCursor(self, csv: str) -> None:
        try:
            xs, ys = csv.split(",")
            self.cursorChanged.emit(int(xs), int(ys))
        except ValueError:
            pass

    @Slot(str)
    def SetWindows(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return
        if isinstance(data, list):
            self.windowsChanged.emit(data)

    @Slot(str)
    def SetWorkArea(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return
        if isinstance(data, dict) and {"x", "y", "w", "h"} <= data.keys():
            self.workAreaChanged.emit(data)

    @Slot(str)
    def SetWorkAreas(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return
        if isinstance(data, list) and data and all(
                isinstance(a, dict) and {"x", "y", "w", "h"} <= a.keys()
                for a in data):
            self.workAreasChanged.emit(data)

    @Slot(str)
    def OverlayTagged(self, caption: str) -> None:
        self.overlayTagged.emit(caption)

    @Slot(str)
    def KeyEvent(self, payload: str) -> None:
        self.keyEvent.emit(payload)


class KWinBridge(QObject):
    """Owns the DBus service and the lifecycle of the KWin helper script."""

    def __init__(self, script_path: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.script_path = script_path
        self.service = BridgeService(self)
        self.cursorChanged = self.service.cursorChanged
        self.windowsChanged = self.service.windowsChanged
        self.workAreaChanged = self.service.workAreaChanged
        self.workAreasChanged = self.service.workAreasChanged
        self.overlayTagged = self.service.overlayTagged
        self.keyEvent = self.service.keyEvent  # P42
        self._scripting = QDBusInterface(
            "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting"
        )
        self._loaded = False
        self._control_mode = False  # P42: script rendered WITH key shortcuts?

    def start(self) -> bool:
        """Register the DBus service and load the KWin script.

        Returns False if another PlasmaCat instance already holds the service.
        """
        from PySide6.QtCore import QThread

        bus = QDBusConnection.sessionBus()
        # brief retries: after an exec-restart (Reset cat) our own
        # predecessor's bus name can linger for a few hundred ms (P29)
        registered = False
        for _ in range(5):
            if bus.registerService(SERVICE):
                registered = True
                break
            QThread.msleep(300)
        if not registered:
            return False
        bus.registerObject(
            OBJPATH, self.service, QDBusConnection.RegisterOption.ExportAllSlots
        )
        script = self._render_script(bus)
        if script is None:
            return False
        self._loaded = self._load_script(script)
        return self._loaded

    def _load_script(self, script: str) -> bool:
        """loadScript + start() with retries (slow KWin right after login,
        P36). loadScript only registers the script; start() actually runs it
        (D9)."""
        from PySide6.QtCore import QThread

        reply = None
        args: list = []
        for _attempt in range(3):
            reply = self._scripting.call("loadScript", script, SCRIPT_PLUGIN)
            if reply.arguments() and int(reply.arguments()[0]) < 0:
                # A leftover script with our name (e.g. after a crash) blocks loading.
                self._scripting.call("unloadScript", SCRIPT_PLUGIN)
                reply = self._scripting.call("loadScript", script, SCRIPT_PLUGIN)
            args = reply.arguments()
            if args and int(args[0]) >= 0:
                break
            # KWin may still be initializing (autostart right after login, P36)
            QThread.msleep(500)
        ok = bool(args) and int(args[0]) >= 0
        if ok:
            self._scripting.call("start")
        else:
            print("[bridge] ERROR: KWin refused to load the script:",
                  reply.errorMessage())
        return ok

    def _reload(self) -> None:
        """Unload + re-render + load the helper script (keeps the DBus
        service registration — only the compositor side is replaced)."""
        script = self._render_script(QDBusConnection.sessionBus())
        if script is None:
            return
        self._scripting.call("unloadScript", SCRIPT_PLUGIN)
        self._loaded = self._load_script(script)

    def set_control_mode(self, on: bool) -> None:
        """P42: re-render the helper script WITH/WITHOUT the global key
        shortcuts and reload it. The shortcuts grab WASD/arrows system-wide,
        so they must only exist while the user steers the cat."""
        if on == self._control_mode:
            return
        self._control_mode = on
        if self._loaded:
            self._reload()

    def _render_script(self, bus: QDBusConnection) -> str | None:
        """Fill __CATGAME_IFACE__ in the JS template with the interface name
        discovered by introspecting our own freshly-registered object.
        Retries: right after a previous instance dies, the bus name can briefly
        route to the corpse."""
        from PySide6.QtCore import QThread

        intro = QDBusInterface(SERVICE, OBJPATH,
                               "org.freedesktop.DBus.Introspectable", bus)
        iface = None
        for attempt in range(5):
            reply = intro.call("Introspect")
            xml = str(reply.arguments()[0]) if reply.arguments() else ""
            match = re.search(r'name="([^"]*BridgeService)"', xml)
            if match:
                iface = match.group(1)
                break
            err = intro.lastError()
            print(f"[bridge] introspect attempt {attempt + 1} failed: "
                  f"{err.message() if err.isValid() else 'no match'}")
            if attempt == 4:
                print("[bridge] XML was:", xml[:300])
            QThread.msleep(300)
        if iface is None:
            print("[bridge] ERROR: could not discover our DBus interface name")
            return None
        template = self.script_path
        try:
            src = open(template, encoding="utf-8").read()
        except OSError as exc:
            print("[bridge] ERROR: cannot read script template:", exc)
            return None
        if IFACE_PLACEHOLDER not in src:
            print("[bridge] ERROR: template has no iface placeholder")
            return None
        if CONTROL_PLACEHOLDER not in src:
            print("[bridge] ERROR: template has no control-mode placeholder")
            return None
        runtime = template.replace(".js", ".runtime.js")
        with open(runtime, "w", encoding="utf-8") as fh:
            fh.write(src.replace(IFACE_PLACEHOLDER, iface)
                     .replace(CONTROL_PLACEHOLDER,
                              "true" if self._control_mode else "false"))
        print(f"[bridge] DBus interface: {iface}")
        return runtime

    def stop(self) -> None:
        if self._loaded:
            self._scripting.call("unloadScript", SCRIPT_PLUGIN)
            self._loaded = False

    def start_watchdog(self, parent: QObject) -> None:
        """Reload the bridge script if KWin/Plasma restarts (the script dies
        with the compositor and all tags/data streams stop). Checks every 10 s."""
        from PySide6.QtCore import QTimer

        self._watchdog = QTimer(parent)
        self._watchdog.timeout.connect(self._check_alive)
        self._watchdog.start(10_000)

    def _check_alive(self) -> None:
        reply = self._scripting.call("isScriptLoaded", SCRIPT_PLUGIN)
        loaded = bool(reply.arguments() and reply.arguments()[0])
        if not loaded:
            print("[bridge] KWin restarted or script lost — reloading")
            self._reload()  # keeps service registration + control mode


def unload_bridge() -> None:
    """Standalone helper: unload a leftover script (e.g. after a crash).
    Also cleans up the legacy pre-rename 'catgame-bridge' if present."""
    scripting = QDBusInterface("org.kde.KWin", "/Scripting",
                               "org.kde.kwin.Scripting")
    scripting.call("unloadScript", SCRIPT_PLUGIN)
    scripting.call("unloadScript", "catgame-bridge")  # legacy name (pre-P33)
