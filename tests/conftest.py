"""pytest setup: headless Qt and the src/ layout on sys.path."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# sprite tables are cached per test session, never in the user's ~/.cache
import tempfile  # noqa: E402
os.environ.setdefault("PLASMACAT_CACHE_DIR", tempfile.mkdtemp(prefix="plasmacat-test-"))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
