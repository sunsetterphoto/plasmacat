#!/usr/bin/env bash
# PlasmaCat launcher. Usage:
#   ./run.sh                     start the game
#   ./run.sh --unload-bridge     remove a leftover KWin helper script (after a crash)
# Uses the system PySide6 (Fedora: python3-pyside6); a local .venv wins if present.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
if ! "$PY" -c "import PySide6.QtDBus, PySide6.QtMultimedia" 2>/dev/null; then
  echo "PlasmaCat needs PySide6. On Fedora: sudo dnf install python3-pyside6" >&2
  exit 1
fi
exec env PYTHONPATH=src PYTHONUNBUFFERED=1 "$PY" -m plasmacat.main "$@"
