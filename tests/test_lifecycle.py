"""The app must save and unload its KWin script on SIGTERM (logout) and
SIGINT (Ctrl+C). Runs the real app headless with the test-only fake bridge."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _seed_save(data_home: Path) -> Path:
    d = data_home / "plasmacat"
    d.mkdir(parents=True)
    save = d / "save.json"
    save.write_text(json.dumps({"version": 2, "cats": [{"age": 3.0}],
                                "saved_at": 1000.0}))
    return save


def _run_and_signal(tmp_path: Path, sig: int) -> tuple[subprocess.CompletedProcess, Path, float]:
    data_home = tmp_path / "data"
    save = _seed_save(data_home)
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), QT_QPA_PLATFORM="offscreen",
               XDG_DATA_HOME=str(data_home), XDG_CONFIG_HOME=str(tmp_path / "cfg"),
               XDG_RUNTIME_DIR=str(tmp_path / "run"), PLASMACAT_FAKE_BRIDGE="1",
               PYTHONUNBUFFERED="1")
    (tmp_path / "run").mkdir()
    start = time.time()
    proc = subprocess.Popen([sys.executable, "-m", "plasmacat.main"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines = []
    deadline = time.time() + 60
    while time.time() < deadline:          # wait until the event loop runs
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line)
        if "[app] ready" in line:
            break
    time.sleep(0.5)
    proc.send_signal(sig)
    rest, _ = proc.communicate(timeout=15)
    out = "".join(lines) + rest
    return subprocess.CompletedProcess(proc.args, proc.returncode, out, ""), save, start


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT], ids=["sigterm", "sigint"])
def test_signal_saves_and_unloads(tmp_path, sig):
    res, save, start = _run_and_signal(tmp_path, sig)
    assert res.returncode == 0, res.stdout[-3000:]
    assert "bridge unloaded" in res.stdout
    assert json.loads(save.read_text())["saved_at"] >= start
    assert "Traceback" not in res.stdout
