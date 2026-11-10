"""Runs the long headless behavior simulation (tests/sim_test.py) in its own
process — it pins the brain's clock module-globally, so it must not share an
interpreter with other tests."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_simulation_passes():
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run([sys.executable, str(ROOT / "tests" / "sim_test.py")],
                          capture_output=True, text=True, env=env, timeout=600)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    assert "SIM_TEST_OK" in proc.stdout
