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


class SoundPlayer:
    def __init__(self, sounds_dir: Path, muted: bool = False,
                 volume: float = 0.7) -> None:
        self.sounds_dir = sounds_dir
        self.muted = muted
        self.volume = volume
        self._effects: dict[str, QSoundEffect] = {}
        self._last: dict[str, float] = {}
        self._qt_ok = True
        self._player_bin = shutil.which("pw-play") or shutil.which("paplay")
        for wav in sorted(self.sounds_dir.glob("*.wav")):
            self._load(wav.stem, wav, self.volume)

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

    def play(self, name: str, cooldown: float = 0.4) -> None:
        if self.muted:
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
                subprocess.Popen(
                    [self._player_bin, str(wav)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def set_muted(self, muted: bool) -> None:
        self.muted = muted

    def set_volume(self, volume: float) -> None:
        self.volume = volume
        for eff in self._effects.values():
            eff.setVolume(volume)
