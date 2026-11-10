"""install.sh / uninstall.sh in a throw-away HOME against a local repo."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run(cmd, env, cwd=None):
    return subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True, timeout=120)


@pytest.fixture
def env(tmp_path):
    origin = tmp_path / "origin"
    subprocess.run(["git", "clone", "-q", "--no-local", str(ROOT), str(origin)], check=True)
    g = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
         "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(tmp_path), "PATH": os.environ["PATH"]}
    subprocess.run(["git", "-C", str(origin), "tag", "-f", "v9.0.0"], check=True, env=g)
    home = tmp_path / "home"
    home.mkdir()
    return dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home / ".local/share"),
                XDG_CONFIG_HOME=str(home / ".config"), XDG_STATE_HOME=str(home / ".local/state"),
                PLASMACAT_REPO=str(origin), PLASMACAT_SANDBOX="1",
                XDG_SESSION_TYPE="wayland")


def test_install_release_then_uninstall_keeps_save(env):
    home = Path(env["HOME"])
    res = run(["bash", str(ROOT / "install.sh")], env)
    assert res.returncode == 0, res.stdout + res.stderr
    app = home / ".local/share/plasmacat/app"
    assert (app / "run.sh").exists()
    tag = subprocess.run(["git", "-C", str(app), "describe", "--tags"], capture_output=True,
                         text=True).stdout.strip()
    assert tag == "v9.0.0"
    desktop = (home / ".local/share/applications/plasmacat.desktop").read_text()
    assert f"Exec={app}/run.sh" in desktop
    assert (home / ".local/share/icons/hicolor/64x64/apps/plasmacat.png").exists()
    # run it again: idempotent update in place
    assert run(["bash", str(ROOT / "install.sh")], env).returncode == 0
    save = home / ".local/share/plasmacat/save.json"
    save.write_text("{}")
    res = run(["bash", str(ROOT / "uninstall.sh")], env)
    assert res.returncode == 0, res.stderr
    assert not app.exists() and save.exists()
    assert not (home / ".local/share/applications/plasmacat.desktop").exists()


def test_dev_install_links_the_checkout(env):
    home = Path(env["HOME"])
    res = run(["bash", str(ROOT / "install.sh"), "--dev"], env)
    assert res.returncode == 0, res.stdout + res.stderr
    app = home / ".local/share/plasmacat/app"
    assert app.is_symlink() and app.resolve() == ROOT.resolve()
    run(["bash", str(ROOT / "uninstall.sh"), "--purge"], env)
    assert not app.exists() and ROOT.exists()       # the checkout itself is untouched
