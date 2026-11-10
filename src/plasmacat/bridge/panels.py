"""Refine the floor with Plasma's own panel settings.

KWin only shows a panel's frame. Whether the panel floats (its frame then
includes a float gap above and below the visible bar) and how thick the bar
is, only plasmashell knows — its scripting interface reports both. The
bridge sends each screen's bottom panels; the floor sits on the visible top:
  floating:  frame top + (frame height - thickness) / 2
  docked:    frame top
Panels that can't be matched keep the bridge's estimate.
"""

from __future__ import annotations

import json

QUERY = ("var o=[];panels().forEach(function(p){o.push({loc:p.location,"
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


def _visible_top(panel: dict, plasma: list[dict]) -> float | None:
    y, h = float(panel["y"]), float(panel["h"])
    for p in plasma:
        if p.get("loc") != "bottom" or not isinstance(p.get("height"), (int, float)):
            continue
        thick = float(p["height"])
        if p.get("floating") and abs(h - (thick + 2 * FLOAT_GAP)) <= 6:
            return y + (h - thick) / 2
        if not p.get("floating") and abs(h - thick) <= 4:
            return y
    return None


def refine_floor(area: dict, plasma: list[dict] | None) -> float:
    """The floor y of one work area (absolute)."""
    estimate = float(area["y"]) + float(area["h"])
    panels = area.get("panels") or []
    if not plasma or not panels:
        return estimate
    tops = [_visible_top(p, plasma) for p in panels]
    if any(t is None for t in tops):
        return estimate
    return min([float(area.get("raw_bottom", estimate))] + tops)
