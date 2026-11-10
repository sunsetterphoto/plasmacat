"""The real Overlay ticks headless (fake bridge) in normal and debug mode."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r'''
import sys
from PySide6.QtWidgets import QApplication
app = QApplication([])
from plasmacat.bridge.kwin import FakeBridge
from plasmacat.world.overlay import Overlay
for debug in (False, True):
    b = FakeBridge()
    ov = Overlay(b, debug=debug)
    b.start()
    ov._on_cursor(500, 500)
    for i in range(120):
        ov._on_cursor(500 + i * 3, 500)
        ov._clock.restart()
        import time; time.sleep(0.002)
        ov._dbg_t = 5.0   # force the once-per-second debug report
        ov._tick()
print("OVERLAY_SMOKE_OK")
'''


def test_overlay_ticks_in_normal_and_debug_mode():
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True,
                          text=True, env=env, timeout=120)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-3000:]
    assert "Traceback" not in out, out[-3000:]
    assert "OVERLAY_SMOKE_OK" in proc.stdout
