"""PlasmaCat entry point.

Usage:
  python -m plasmacat.main [--debug] [--setup] [--control]   start the game
  python -m plasmacat.main --unload-bridge                   unload a leftover KWin script
  python -m plasmacat.main --help
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__.strip())
        return 0
    from plasmacat.app import run
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
