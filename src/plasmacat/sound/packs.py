"""Sound playback: sound packs (retro synth / natural recordings), mute/volume,
per-effect cooldowns.

The 'natural' pack overrides the retro pack for the effects it contains
(meow, mew, purr — real recordings, see assets/sounds/natural/ATTRIBUTION.md);
all other effects fall back to the synthesized retro versions.

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


# Aliases so behavior-specific names work in packs that lack them
# (retro synth pack has no 'beg'/'meow2' recordings).
SOUND_ALIASES = {"beg": "meow", "meow2": "meow"}


class SoundPlayer:
    def __init__(self, sounds_root: Path, pack: str = "retro",
                 muted: bool = False, volume: float = 0.7) -> None:
        self.sounds_root = sounds_root
        self.muted = muted
        self.volume = volume
        self._effects: dict[str, QSoundEffect] = {}
        self._last: dict[str, float] = {}
        self._qt_ok = True
        self._player_bin = shutil.which("pw-play") or shutil.which("paplay")
        self.set_pack(pack)

    def _load(self, name: str, wav: Path, volume: float) -> None:
        eff = QSoundEffect()
        eff.setSource(QUrl.fromLocalFile(str(wav)))
        eff.setVolume(volume)
        self._effects[name] = eff

    def set_pack(self, pack: str) -> None:
        self.pack = pack
        self._effects.clear()
        retro = self.sounds_root / "retro"
        for wav in sorted(retro.glob("*.wav")):
            self._load(wav.stem, wav, self.volume)
        if pack == "natural":
            natural = self.sounds_root / "natural"
            for wav in sorted(natural.glob("*.wav")):
                self._load(wav.stem, wav, self.volume)  # overrides retro
        if self._effects:
            first = next(iter(self._effects.values()))
            self._qt_ok = first.status() != QSoundEffect.Status.Error

    def play(self, name: str, cooldown: float = 0.4) -> None:
        if self.muted:
            return
        now = time.monotonic()
        if now - self._last.get(name, 0.0) < cooldown:
            return
        self._last[name] = now
        eff_name = name if name in self._effects else SOUND_ALIASES.get(name, name)
        if self._qt_ok and eff_name in self._effects:
            self._effects[eff_name].play()
        elif self._player_bin:
            wav = self.sounds_root / self.pack / f"{name}.wav"
            if not wav.exists():
                wav = self.sounds_root / self.pack / f"{SOUND_ALIASES.get(name, name)}.wav"
            if not wav.exists():
                wav = self.sounds_root / "retro" / f"{SOUND_ALIASES.get(name, name)}.wav"
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
