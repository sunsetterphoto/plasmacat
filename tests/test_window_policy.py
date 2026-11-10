"""Small-window policy (P37): runs tests/window_geo_test.py in its own process
(it builds a full Overlay with a fake bridge)."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_window_geometry_policy():
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run([sys.executable, str(ROOT / "tests" / "window_geo_test.py")],
                          capture_output=True, text=True, env=env, timeout=300)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    assert "WINDOW_GEO_OK" in proc.stdout
