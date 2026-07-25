"""Sound playback: the natural pack (real recordings, mute/volume,
per-effect cooldowns).

All effects are real cat recordings (see assets/sounds/natural/ATTRIBUTION.md);
the synthesized 8-bit pack was removed in P49.

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
    def __init__(self, sounds_root: Path, muted: bool = False,
                 volume: float = 0.7) -> None:
        self.sounds_root = sounds_root
        self.muted = muted
        self.volume = volume
        self._effects: dict[str, QSoundEffect] = {}
        self._last: dict[str, float] = {}
        self._qt_ok = True
        self._player_bin = shutil.which("pw-play") or shutil.which("paplay")
        natural = self.sounds_root / "natural"
        for wav in sorted(natural.glob("*.wav")):
            self._load(wav.stem, wav, self.volume)
        if self._effects:
            first = next(iter(self._effects.values()))
            self._qt_ok = first.status() != QSoundEffect.Status.Error

    def _load(self, name: str, wav: Path, volume: float) -> None:
        eff = QSoundEffect()
        eff.setSource(QUrl.fromLocalFile(str(wav)))
        eff.setVolume(volume)
        self._effects[name] = eff

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
            wav = self.sounds_root / "natural" / f"{name}.wav"
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
