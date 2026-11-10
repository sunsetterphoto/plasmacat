"""Filesystem locations: packaged data, XDG state/runtime dirs, legacy migration.

Everything PlasmaCat ships (KWin script, sounds, icons) lives inside the
package under ``plasmacat/data`` and is resolved with importlib.resources, so
the app works the same from a checkout, an install dir or a wheel. Nothing is
ever written into the package: the rendered KWin script goes to
``$XDG_RUNTIME_DIR/plasmacat`` and the save game to ``$XDG_DATA_HOME/plasmacat``.
"""

from __future__ import annotations

import os
import shutil
from importlib import resources
from pathlib import Path

APP = "plasmacat"
LEGACY_APP = "catgame"  # data dir name before the PlasmaCat rename (P33)


def data_file(rel: str) -> Path:
    """Absolute path of a file shipped in plasmacat/data (e.g. 'kwin/bridge.js')."""
    return Path(str(resources.files("plasmacat").joinpath("data", rel)))


def _data_home(home: Path | None = None) -> Path:
    if home is None:
        env = os.environ.get("XDG_DATA_HOME")
        if env:
            return Path(env)
        home = Path.home()
    return home / ".local" / "share"


def state_dir() -> Path:
    """Save game + per-user state (~/.local/share/plasmacat)."""
    d = _data_home() / APP
    d.mkdir(parents=True, exist_ok=True)
    return d


def runtime_dir() -> Path:
    """Per-session scratch (the rendered KWin script): $XDG_RUNTIME_DIR/plasmacat."""
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/{APP}-{os.getuid()}"
    d = Path(base) / APP
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def migrate_legacy(home: Path | None = None) -> bool:
    """Move the pre-rename data dir (catgame/) to plasmacat/ once.
    Never overwrites: if plasmacat/ already exists, nothing happens."""
    base = _data_home(home)
    old, new = base / LEGACY_APP, base / APP
    if not old.is_dir() or new.exists():
        return False
    shutil.move(str(old), str(new))
    return True
