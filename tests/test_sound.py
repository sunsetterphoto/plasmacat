from pathlib import Path

from PySide6.QtMultimedia import QSoundEffect

from plasmacat.paths import data_file
from plasmacat.sound.player import SoundPlayer


def test_sound_fallback_on_error(qapp, monkeypatch):
    calls = []
    monkeypatch.setattr("plasmacat.sound.player.subprocess.Popen",
                        lambda args, **kw: calls.append(args))
    player = SoundPlayer(data_file("sounds"))
    player._player_bin = "/usr/bin/pw-play"
    player._on_effect_status(QSoundEffect.Status.Error)
    player.play("meow")
    assert calls and calls[0][0] == "/usr/bin/pw-play"
    assert Path(calls[0][1]).name == "meow.wav"


def test_effects_load_from_package(qapp):
    player = SoundPlayer(data_file("sounds"))
    assert {"meow", "purr", "eat"} <= set(player._effects)
