#!/usr/bin/env bash
# PlasmaCat launcher. Usage:
#   ./run.sh                     start the game
#   ./run.sh --unload-bridge     remove a leftover KWin helper script (after a crash)
set -euo pipefail
cd "$(dirname "$0")"
exec env PYTHONPATH=src .venv/bin/python -m plasmacat.main "$@"
