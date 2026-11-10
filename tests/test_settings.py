import json

from plasmacat import persist
from plasmacat.persist import Settings


def test_settings_roundtrip(tmp_path):
    st = persist.GameState()
    st.settings.volume = 0.3
    st.settings.status_rows["play"] = False
    st.settings.notify["vomit"] = False
    st.settings.sound_groups["purr"] = False
    st.settings.pixel_size = "chunky"
    persist.save(tmp_path / "save.json", st)
    back = persist.load(tmp_path / "save.json")
    assert back.settings == st.settings


def test_settings_migrate_from_old_customization(tmp_path):
    old = {"version": 2, "cats": [{"customization": {
        "name": "Minka", "sound_on": False, "volume": 0.4,
        "status_window": True, "status_pos": [100, 200]}}]}
    (tmp_path / "save.json").write_text(json.dumps(old))
    st = persist.load(tmp_path / "save.json")
    s = st.settings
    assert (s.sound_on, s.volume, s.status_board, s.status_pos) == (False, 0.4, True, [100.0, 200.0])


def test_defaults_for_each_tab():
    d = Settings.defaults_for("sound")
    assert d["volume"] == 0.7 and d["sound_on"] is True and all(d["sound_groups"].values())
    assert set(Settings.defaults_for("home")) == {"status_board", "status_pos", "status_rows"}
    assert "pixel_size" in Settings.defaults_for("system")


def test_reset_tab_only_touches_that_tab():
    s = Settings(volume=0.1, pixel_size="fine")
    s.reset("sound")
    assert s.volume == 0.7 and s.pixel_size == "fine"


def test_unknown_keys_and_garbage_are_ignored():
    s = Settings.from_json({"volume": "loud", "status_rows": {"hunger": False, "bogus": 1},
                            "pixel_size": "giant", "foo": 1})
    assert s.volume == 0.7 and s.status_rows["hunger"] is False
    assert "bogus" not in s.status_rows and s.pixel_size == "normal"
