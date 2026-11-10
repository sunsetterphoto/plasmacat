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


def dispose(*widgets) -> None:
    """Really destroy Qt widgets now: closing alone leaves them alive until
    interpreter exit, where PySide6 tears them down after the QApplication
    and segfaults."""
    from PySide6.QtCore import QCoreApplication, QEvent
    for w in widgets:
        w.close()
        w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture(scope="session")
def qapp():
    import gc

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    dispose(*QApplication.topLevelWidgets())
    gc.collect()
