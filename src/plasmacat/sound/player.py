"""Sound playback: real cat recordings with mute/volume and per-effect
cooldowns. The WAVs ship in plasmacat/data/sounds (see ATTRIBUTION.md there)
and are played in place — nothing is copied to the user's data dir.

Primary backend: QtMultimedia QSoundEffect. Fallback: `pw-play`/`paplay`
subprocess (if the Qt backend reports an error on this system).
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect


# Per-effect gain on top of the master volume. The recordings differ a lot in
# loudness (measured mean: purr/eat -15 dB, drink -18 dB, chime -28 dB); the
# fountain bubbles are meant to be barely noticeable.
GAIN: dict[str, float] = {
    "purr": 0.45, "eat": 0.45, "drink": 0.3, "bubble": 0.5,
    "beg": 0.6, "mew": 0.7, "puke": 0.7, "meow": 0.85, "meow2": 0.85,
    "hiss": 0.7,
}


# Effects by group (Sound tab: each group can be switched off)
GROUP_OF: dict[str, str] = {
    "meow": "voice", "meow2": "voice", "mew": "voice", "beg": "voice",
    "chirp": "voice", "hiss": "voice", "purr": "purr",
    "eat": "eating", "drink": "eating", "bubble": "eating",
    "boing": "play", "scratch": "play", "chime": "alerts", "puke": "alerts",
}


class SoundPlayer:
    def __init__(self, sounds_dir: Path, muted: bool = False,
                 volume: float = 0.7) -> None:
        self.sounds_dir = sounds_dir
        self.muted = muted
        self.volume = volume
        self._effects: dict[str, QSoundEffect] = {}
        self._last: dict[str, float] = {}
        self._groups_off: set[str] = set()
        self._qt_ok = True
        self._player_bin = shutil.which("pw-play") or shutil.which("paplay")
        for wav in sorted(self.sounds_dir.glob("*.wav")):
            self._load(wav.stem, wav, self.volume * GAIN.get(wav.stem, 1.0))

    def _load(self, name: str, wav: Path, volume: float) -> None:
        eff = QSoundEffect()
        # loading is asynchronous: an Error only shows up later, so watch it
        eff.statusChanged.connect(lambda e=eff: self._on_effect_status(e.status()))
        eff.setSource(QUrl.fromLocalFile(str(wav)))
        eff.setVolume(volume)
        self._effects[name] = eff

    def _on_effect_status(self, status) -> None:
        """A QtMultimedia backend that cannot play our WAVs switches the
        whole player to the pw-play/paplay fallback."""
        if status == QSoundEffect.Status.Error and self._qt_ok:
            self._qt_ok = False
            print("[sound] QtMultimedia failed — falling back to",
                  self._player_bin or "silence")

    def set_group_enabled(self, group: str, on: bool) -> None:
        (self._groups_off.discard if on else self._groups_off.add)(group)

    def play(self, name: str, cooldown: float = 0.4) -> None:
        if self.muted or GROUP_OF.get(name) in self._groups_off:
            return
        now = time.monotonic()
        if now - self._last.get(name, 0.0) < cooldown:
            return
        self._last[name] = now
        if self._qt_ok and name in self._effects:
            self._effects[name].play()
        elif self._player_bin:
            wav = self.sounds_dir / f"{name}.wav"
            if wav.exists():
                vol = self.volume * GAIN.get(name, 1.0)
                if self._player_bin.endswith("paplay"):
                    flag = f"--volume={int(vol * 65536)}"
                else:
                    flag = f"--volume={vol:.3f}"
                subprocess.Popen(
                    [self._player_bin, flag, str(wav)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def set_muted(self, muted: bool) -> None:
        self.muted = muted

    def set_volume(self, volume: float) -> None:
        self.volume = volume
        for name, eff in self._effects.items():
            eff.setVolume(volume * GAIN.get(name, 1.0))
