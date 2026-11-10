"""Release updater for an installed PlasmaCat (install.sh → ~/.local/share/plasmacat/app).

Check, offer, then install — the user decides:
  python3 -m plasmacat.updater [APP_DIR]          check GitHub for a newer
        release tag (vX.Y.Z); if there is one, write <app>/.available — the
        running app offers it ("PlasmaCat vX is available — click to update")
  python3 -m plasmacat.updater --manual [APP_DIR] the same check, even when
        automatic checks are switched off ('Check now')
  python3 -m plasmacat.updater --apply [APP_DIR]  fast-forward to the newest
        release (never to untagged work, never over local changes) and write
        <app>/.updated; the app restarts itself

The daily systemd user timer only checks. Honors the "Check for updates"
switch in the settings (save.json).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


@dataclass
class UpdateStatus:
    current: str | None
    latest: str | None
    updated: bool
    message: str
    available: str | None = None   # a newer release, offered but not installed


def _git(app: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(app), *args], check=True,
                          capture_output=True, text=True, timeout=120).stdout.strip()


def _auto_update_enabled(save_path: Path | None) -> bool:
    if save_path is None or not save_path.exists():
        return True
    try:
        return bool(json.loads(save_path.read_text()).get("settings", {})
                    .get("auto_update", True))
    except (OSError, ValueError):
        return True


def _version_key(tag: str) -> tuple[int, int, int]:
    m = TAG_RE.match(tag)
    return (int(m[1]), int(m[2]), int(m[3])) if m else (-1, -1, -1)


def current_version(app: Path) -> str | None:
    try:
        return _git(app, "describe", "--tags", "--abbrev=0", "--match", "v*")
    except (subprocess.CalledProcessError, OSError):
        return None


def check(app: Path, save_path: Path | None = None, apply: bool = False,
          manual: bool = False) -> UpdateStatus:
    app = Path(app)
    if not (app / ".git").exists():
        return UpdateStatus(None, None, False, f"{app} is not a git checkout")
    if not (apply or manual) and not _auto_update_enabled(save_path):
        return UpdateStatus(current_version(app), None, False,
                            "automatic updates are disabled in the settings")
    try:
        if _git(app, "status", "--porcelain", "--untracked-files=no"):
            return UpdateStatus(current_version(app), None, False,
                                "local changes in the install dir — not touching it")
        _git(app, "fetch", "--quiet", "--tags", "origin")
        tags = [t for t in _git(app, "tag", "--list", "v*").split() if TAG_RE.match(t)]
        if not tags:
            return UpdateStatus(current_version(app), None, False, "no releases found")
        latest = max(tags, key=_version_key)
        head = _git(app, "rev-parse", "HEAD")
        target = _git(app, "rev-list", "-n", "1", latest)
        if head == target or _git(app, "merge-base", head, target) == target:
            (app / ".available").unlink(missing_ok=True)
            return UpdateStatus(latest, latest, False, "already up to date")
        if not apply:
            (app / ".available").write_text(json.dumps({"version": latest,
                                                        "at": time.time()}))
            return UpdateStatus(current_version(app), latest, False,
                                f"{latest} is available", available=latest)
        _git(app, "merge", "--ff-only", "--quiet", target)
    except subprocess.CalledProcessError as exc:
        return UpdateStatus(current_version(app), None, False,
                            f"update failed: {exc.stderr.strip() or exc}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return UpdateStatus(current_version(app), None, False, f"update failed: {exc}")
    (app / ".available").unlink(missing_ok=True)
    (app / ".updated").write_text(json.dumps({"version": latest, "at": time.time()}))
    return UpdateStatus(latest, latest, True, f"updated to {latest}")


def main(argv: list[str] | None = None) -> int:
    from plasmacat.paths import state_dir
    argv = list(sys.argv[1:] if argv is None else argv)
    apply, manual = "--apply" in argv, "--manual" in argv
    rest = [a for a in argv if a not in ("--apply", "--manual")]
    app = Path(rest[0]) if rest else Path(__file__).resolve().parents[2]
    st = check(app, save_path=state_dir() / "save.json", apply=apply, manual=manual)
    print(f"[plasmacat-update] {st.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
