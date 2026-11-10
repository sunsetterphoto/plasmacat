from pathlib import Path

import pytest

from PySide6.QtMultimedia import QSoundEffect

from plasmacat.paths import data_file
from plasmacat.sound.player import SoundPlayer


def test_sound_fallback_on_error(qapp, monkeypatch):
    calls = []
    monkeypatch.setattr("plasmacat.sound.player.subprocess.Popen",
                        lambda args, **kw: calls.append(args))
    player = SoundPlayer(data_file("sounds"), volume=0.5)
    player._player_bin = "/usr/bin/pw-play"
    player._on_effect_status(QSoundEffect.Status.Error)
    player.play("drink")
    assert calls and calls[0][0] == "/usr/bin/pw-play"
    assert Path(calls[0][-1]).name == "drink.wav"
    assert "--volume=0.150" in calls[0]          # master 0.5 x drink gain 0.3


def test_effects_load_from_package(qapp):
    player = SoundPlayer(data_file("sounds"))
    assert {"meow", "purr", "eat"} <= set(player._effects)


def test_per_effect_gain_makes_drinking_quiet(qapp):
    from plasmacat.sound.player import GAIN
    player = SoundPlayer(data_file("sounds"), volume=0.8)
    assert GAIN["drink"] <= 0.35 and GAIN["bubble"] <= 0.5
    assert player._effects["drink"].volume() == pytest.approx(0.8 * GAIN["drink"], abs=0.01)
    player.set_volume(0.5)
    assert player._effects["drink"].volume() == pytest.approx(0.5 * GAIN["drink"], abs=0.01)


def test_bubble_sound_is_subtle():
    import math
    import struct
    import wave
    with wave.open(str(data_file("sounds/bubble.wav"))) as w:
        n = w.getnframes()
        assert 2.0 <= n / w.getframerate() <= 8.0
        raw = w.readframes(n)
        samples = struct.unpack("<%dh" % (len(raw) // 2), raw)
    rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768
    peak = max(abs(s) for s in samples) / 32768
    assert 20 * math.log10(rms) < -34      # a quiet bed, not a lapping cat
    assert 20 * math.log10(peak) < -12


def test_drinking_plays_bubbles_rarely():
    import random
    from plasmacat.bridge.desktop import DesktopState
    from plasmacat.cat.cat import Cat
    cat = Cat(400, 1080, rng=random.Random(3))
    cat.brain.state, cat.brain.state_left = "drinking", 60.0
    cat.brain.needs["thirst"] = 0.0
    played = []
    d = DesktopState(1920, 1080)
    for _ in range(int(20 * 60)):          # 20 s of drinking
        cat.brain.continue_state(1 / 60, cat.body, d) if hasattr(cat.brain, "continue_state") \
            else cat.brain._continue(1 / 60, cat.body, d)
        cat.brain.state_left = 60.0
        played += cat.brain.sounds
        cat.brain.sounds.clear()
    assert played.count("drink") <= 3      # an occasional lap, not every 1.4 s
    assert 3 <= played.count("bubble") <= 10


def test_spat_starts_with_a_hiss():
    import random
    from plasmacat.bridge.desktop import DesktopState
    from plasmacat.cat.behaviors.social import to_peer
    from plasmacat.cat.cat import Cat
    d = DesktopState(1920, 1080)
    a = Cat(600, 1080, rng=random.Random(1))
    b = Cat(660, 1080, rng=random.Random(2))
    a.brain.state, b.brain.state = "to_peer", "sit"
    a.brain._peer, a.brain._peer_intent = (b.body, b.brain), "fight"
    a.body.target_x = None
    to_peer(a.brain, 1 / 60, a.body, d)
    assert a.brain.state == "fight"
    assert "hiss" in a.brain.sounds + b.brain.sounds
