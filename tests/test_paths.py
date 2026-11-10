from pathlib import Path

from plasmacat import paths


def test_migrate_moves_catgame_save(tmp_path: Path):
    old = tmp_path / ".local/share/catgame"
    old.mkdir(parents=True)
    (old / "save.json").write_text('{"version": 2}')
    assert paths.migrate_legacy(tmp_path) is True
    new = tmp_path / ".local/share/plasmacat/save.json"
    assert new.read_text() == '{"version": 2}'
    assert not old.exists()


def test_migrate_noop_when_target_exists(tmp_path: Path):
    old = tmp_path / ".local/share/catgame"
    new = tmp_path / ".local/share/plasmacat"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    (old / "save.json").write_text("old")
    (new / "save.json").write_text("new")
    assert paths.migrate_legacy(tmp_path) is False
    assert (new / "save.json").read_text() == "new"
    assert (old / "save.json").exists()  # never touched


def test_migrate_noop_without_legacy(tmp_path: Path):
    assert paths.migrate_legacy(tmp_path) is False


def test_data_file_resolves_bridge_js():
    p = paths.data_file("kwin/bridge.js")
    assert p.is_file()
    assert "__CATGAME_IFACE__" in p.read_text() or "__PLASMACAT_IFACE__" in p.read_text()


def test_data_file_resolves_sounds_and_icons():
    assert paths.data_file("sounds/meow.wav").is_file()
    assert paths.data_file("icons/plasmacat-256.png").is_file()


def test_runtime_dir_under_xdg_runtime(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    d = paths.runtime_dir()
    assert d == tmp_path / "plasmacat"
    assert d.is_dir()
