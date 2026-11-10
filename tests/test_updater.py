"""Release updater: fast-forwards an install checkout to the newest v* tag."""
import json
import subprocess
from pathlib import Path

import pytest

from plasmacat import updater


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                        "HOME": str(cwd), "PATH": "/usr/bin:/bin"})


@pytest.fixture
def repos(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    (origin / "f.txt").write_text("1")
    git(origin, "add", ".")
    git(origin, "commit", "-qm", "one")
    git(origin, "tag", "v0.2.0")
    app = tmp_path / "app"
    git(tmp_path, "clone", "-q", str(origin), str(app))
    (origin / "f.txt").write_text("2")
    git(origin, "commit", "-qam", "two")
    git(origin, "tag", "v0.2.1")
    (origin / "f.txt").write_text("3")
    git(origin, "commit", "-qam", "unreleased work")   # not tagged: never installed
    return origin, app


def test_check_only_offers_the_new_release(repos):
    _origin, app = repos
    st = updater.check(app)
    assert st.available == "v0.2.1" and not st.updated
    assert (app / "f.txt").read_text() == "1"                 # nothing installed yet
    assert json.loads((app / ".available").read_text())["version"] == "v0.2.1"


def test_apply_installs_the_newest_release(repos):
    _origin, app = repos
    st = updater.check(app, apply=True)
    assert st.updated and st.current == "v0.2.1"
    assert (app / "f.txt").read_text() == "2"                 # never the untagged work
    assert json.loads((app / ".updated").read_text())["version"] == "v0.2.1"
    assert not (app / ".available").exists()


def test_check_is_quiet_when_current(repos):
    _origin, app = repos
    updater.check(app, apply=True)
    st = updater.check(app)
    assert not st.updated and st.available is None and st.current == "v0.2.1"


def test_check_refuses_dirty_tree(repos):
    _origin, app = repos
    (app / "f.txt").write_text("local edit")
    st = updater.check(app, apply=True)
    assert not st.updated and "local changes" in st.message
    assert (app / "f.txt").read_text() == "local edit"


def test_disabled_in_settings_skips(repos, tmp_path):
    _origin, app = repos
    save = tmp_path / "save.json"
    save.write_text(json.dumps({"settings": {"auto_update": False}}))
    st = updater.check(app, save_path=save)
    assert not st.updated and "disabled" in st.message
    assert (app / "f.txt").read_text() == "1"


def test_not_a_git_checkout(tmp_path):
    st = updater.check(tmp_path)
    assert not st.updated and "not a git checkout" in st.message
