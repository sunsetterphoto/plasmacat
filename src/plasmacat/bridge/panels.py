"""Refine the floor with Plasma's own panel settings.

KWin only shows a panel's frame. Whether the panel floats (its frame then
includes a float gap above and below the visible bar) and how thick the bar
is, only plasmashell knows — its scripting interface reports both. The
bridge sends each screen's bottom panels; the floor sits on the visible top:
  floating:  frame top + (frame height - thickness) / 2
  docked:    frame top
Panels that can't be matched keep the bridge's estimate.

Krema (a layer-shell dock, not a Plasma panel) is recognised by its window
class; its surface includes zoom headroom above the bar, so the visible bar
top is computed with Krema's own formula from ~/.config/kremarc.
"""

from __future__ import annotations

import json

QUERY = ("var o=[];panels().forEach(function(p){o.push({id:p.id,loc:p.location,"
         "floating:p.floating,height:p.height,hiding:p.hiding})});print(JSON.stringify(o));")
FLOAT_GAP = 8   # Plasma's floating margin above and below the bar


def query_plasma_panels() -> list[dict] | None:
    """Panel settings from plasmashell, or None if it can't be asked."""
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface
        iface = QDBusInterface("org.kde.plasmashell", "/PlasmaShell",
                               "org.kde.PlasmaShell", QDBusConnection.sessionBus())
        iface.setTimeout(500)
        reply = iface.call("evaluateScript", QUERY)
        args = reply.arguments()
        if not args:
            return None
        data = json.loads(str(args[0]).strip() or "null")
        return data if isinstance(data, list) else None
    except Exception:  # noqa: BLE001 — any failure just means "unknown"
        return None


def _match(panel: dict, plasma: list[dict]) -> tuple[dict, float] | None:
    """The Plasma panel behind a KWin dock frame and its visible top."""
    y, h = float(panel["y"]), float(panel["h"])
    for p in plasma:
        if p.get("loc") != "bottom" or not isinstance(p.get("height"), (int, float)):
            continue
        thick = float(p["height"])
        if p.get("floating") and abs(h - (thick + 2 * FLOAT_GAP)) <= 6:
            return p, y + (h - thick) / 2
        if not p.get("floating") and abs(h - thick) <= 4:
            return p, y
    return None


# -- Krema --------------------------------------------------------------------
# Krema 0.13 (src/utils/surfacegeometry.h, dockview.cpp): bar height =
# IconSize + 2 * s_padding (8) + floatingPadding (FloatingMargin if Floating).
# The surface's bottom edge is the screen edge; the bar sits at its bottom.
KREMA_PADDING = 8
KREMA_DEFAULTS = {"icon_size": 48, "floating": True, "floating_margin": 8}


def is_krema(panel: dict) -> bool:
    return "krema" in str(panel.get("cls", "")).lower()


def read_kremarc(path=None) -> dict:
    """Krema's dock geometry settings ([General] in kremarc), with Krema's defaults."""
    import configparser
    from pathlib import Path
    import os
    if path is None:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        path = Path(base) / "kremarc"
    out = dict(KREMA_DEFAULTS)
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    try:
        cp.read(path, encoding="utf-8")
    except (OSError, configparser.Error):
        return out
    if not cp.has_section("General"):
        return out
    g = cp["General"]
    try:
        out["icon_size"] = int(g.get("IconSize", out["icon_size"]))
        out["floating_margin"] = int(g.get("FloatingMargin", out["floating_margin"]))
    except ValueError:
        pass
    out["floating"] = g.get("Floating", "true").strip().lower() in ("true", "1", "yes")
    return out


def krema_bar_height(rc: dict) -> int:
    return (int(rc["icon_size"]) + 2 * KREMA_PADDING
            + (int(rc["floating_margin"]) if rc.get("floating") else 0))


def refine_floor(area: dict, plasma: list[dict] | None, krema: dict | None = None) -> float:
    """The floor y of one work area (absolute).

    Stable on purpose: a panel that only dodges windows keeps carrying the
    floor while it is hidden (otherwise cats and furniture would jump every
    time a window touches it); an auto-hide panel never carries it.
    A Krema dock carries the floor on its visible bar (also while it dodges);
    1 px edge surfaces (Krema's screen-edge probe) never carry it."""
    estimate = float(area["y"]) + float(area["h"])
    raw_bottom = float(area.get("raw_bottom", estimate))
    panels = [p for p in (area.get("panels") or []) if float(p.get("h", 0)) > 2]
    if not panels:
        return raw_bottom if area.get("panels") else estimate
    tops = []
    rest = []
    for panel in panels:
        if is_krema(panel):
            rc = krema if krema is not None else read_kremarc()
            tops.append(float(panel["y"]) + float(panel["h"]) - krema_bar_height(rc))
        else:
            rest.append(panel)
    if rest and not plasma:
        if not tops:
            return estimate
        # unknown panels next to a Krema dock: the bridge's estimate covers the visible ones
        unknown = estimate if any(not p.get("hidden") for p in rest) else raw_bottom
        return min([unknown] + tops)
    for panel in rest:
        m = _match(panel, plasma)
        if m is None:
            if panel.get("hidden"):
                continue          # unknown and invisible: not a floor
            return estimate       # unknown but visible: trust the bridge
        settings, top = m
        if settings.get("hiding") == "autohide":
            continue
        tops.append(top)
    return min([raw_bottom] + tops)


# -- docking the bottom panel while PlasmaCat runs -------------------------------

def _evaluate(script: str) -> str | None:
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface
        iface = QDBusInterface("org.kde.plasmashell", "/PlasmaShell",
                               "org.kde.PlasmaShell", QDBusConnection.sessionBus())
        iface.setTimeout(800)
        args = iface.call("evaluateScript", script).arguments()
        return str(args[0]) if args else None
    except Exception:  # noqa: BLE001
        return None


def set_plasma_floating(ids: list[int], floating: bool) -> None:
    wanted = json.dumps(sorted(int(i) for i in ids))
    _evaluate(f"var ids={wanted};panels().forEach(function(p){{"
              f"if(ids.indexOf(p.id)>=0){{p.floating={'true' if floating else 'false'};}}}});")


class PanelDock:
    """Docks floating bottom panels while PlasmaCat runs and gives them back
    afterwards. A docked panel has a straight, exact top edge: the cats and
    the furniture stand on it without a gap.

    Only panels WE docked are restored; their ids are kept in a state file,
    so a crash is repaired by the next start (or `--unload-bridge`)."""

    def __init__(self, state_file, query=None, set_floating=None) -> None:
        from pathlib import Path
        self.state_file = Path(state_file)
        self._query = query or query_plasma_panels
        self._set = set_floating or set_plasma_floating

    def _load(self) -> list[int]:
        try:
            data = json.loads(self.state_file.read_text())
            return [int(i) for i in data] if isinstance(data, list) else []
        except (OSError, ValueError, TypeError):
            return []

    def dock(self) -> list[int]:
        """Dock every floating bottom panel; returns the ids we hold."""
        panels = self._query()
        if not panels:
            return []
        ours = set(self._load())
        new = [int(p["id"]) for p in panels
               if p.get("loc") == "bottom" and p.get("floating") and "id" in p]
        if new:
            self._set(new, False)
        ours |= set(new)
        ours &= {int(p["id"]) for p in panels if "id" in p}   # panels that still exist
        if ours:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(sorted(ours)))
        return sorted(ours)

    def restore(self) -> list[int]:
        """Float the panels we docked again."""
        ours = self._load()
        if ours:
            self._set(ours, True)
        self.state_file.unlink(missing_ok=True)
        return sorted(ours)
