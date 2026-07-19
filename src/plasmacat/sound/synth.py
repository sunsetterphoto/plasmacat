"""Retro sound effects synthesized with numpy and written as WAV files.

8-bit-ish chiptune style: square/triangle waves, pitch glides, simple
envelopes. No Qt here (testable); the SoundPlayer lives in packs.py.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 22050  # sample rate: retro and small


def _t(dur: float) -> np.ndarray:
    return np.arange(int(SR * dur)) / SR


def _env(t: float | np.ndarray, attack: float, release: float, total: float) -> np.ndarray:
    t = np.asarray(t)
    e = np.minimum(1.0, t / max(attack, 1e-4))
    e *= np.minimum(1.0, np.maximum(0.0, (total - t) / max(release, 1e-4)))
    return e


def _square(freq: np.ndarray, duty: float = 0.5) -> np.ndarray:
    phase = np.cumsum(freq) / SR
    return np.where(phase % 1.0 < duty, 1.0, -1.0)


def _triangle(freq: np.ndarray) -> np.ndarray:
    phase = np.cumsum(freq) / SR
    return 2.0 * np.abs(2.0 * (phase % 1.0) - 1.0) - 1.0


def _crush(x: np.ndarray, levels: int = 24) -> np.ndarray:
    return np.round(x * levels) / levels


def _write(path: Path, x: np.ndarray) -> None:
    x = np.clip(x, -1.0, 1.0)
    pcm = (x * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------------
# Individual effects
# ---------------------------------------------------------------------------

def meow() -> np.ndarray:
    dur = 0.32
    t = _t(dur)
    glide = np.linspace(680, 380, len(t))
    vib = 1.0 + 0.03 * np.sin(2 * np.pi * 28 * t)
    x = _triangle(glide * vib) * _env(t, 0.02, 0.10, dur)
    return _crush(x) * 0.8


def mew() -> np.ndarray:
    dur = 0.15
    t = _t(dur)
    glide = np.linspace(850, 620, len(t))
    x = _triangle(glide) * _env(t, 0.01, 0.05, dur)
    return _crush(x) * 0.7


def chirp() -> np.ndarray:
    dur = 0.12
    t = _t(dur)
    glide = np.linspace(900, 1500, len(t))
    x = _square(glide, 0.35) * _env(t, 0.005, 0.04, dur)
    return _crush(x) * 0.5


def purr() -> np.ndarray:
    dur = 2.0
    t = _t(dur)
    am = 0.55 + 0.45 * np.sin(2 * np.pi * 22 * t)
    x = _square(np.full(len(t), 110.0), 0.4) * am
    # gentle fade at the very ends so it loops without clicks
    x *= _env(t, 0.05, 0.05, dur)
    return x * 0.35


def eat() -> np.ndarray:
    out = []
    for i, f in enumerate((500, 380, 300)):
        t = _t(0.07)
        blip = _triangle(np.full(len(t), f)) * _env(t, 0.005, 0.02, 0.07)
        noise = np.random.default_rng(i).uniform(-1, 1, len(t)) * 0.3
        out.append(_crush(blip + noise * _env(t, 0.005, 0.03, 0.07)))
        out.append(np.zeros(int(SR * 0.05)))
    return np.concatenate(out) * 0.7


def drink() -> np.ndarray:
    out = []
    for i in range(4):
        t = _t(0.05)
        noise = np.random.default_rng(10 + i).uniform(-1, 1, len(t))
        tick = noise * _env(t, 0.002, 0.03, 0.05)
        tone = _triangle(np.full(len(t), 900 + i * 120)) * 0.25
        out.append(_crush(tick + tone * _env(t, 0.002, 0.02, 0.05)))
        out.append(np.zeros(int(SR * 0.06)))
    return np.concatenate(out) * 0.6


def boing() -> np.ndarray:
    dur = 0.25
    t = _t(dur)
    wob = np.sin(2 * np.pi * 18 * t) * np.exp(-t * 12)
    freq = 300 + 250 * wob + np.linspace(0, 150, len(t))
    x = _square(freq, 0.4) * _env(t, 0.005, 0.08, dur)
    return _crush(x) * 0.5


def chime() -> np.ndarray:
    parts = []
    for f in (880, 1175, 1568):
        t = _t(0.09)
        parts.append(_square(np.full(len(t), float(f)), 0.5) * _env(t, 0.005, 0.04, 0.09))
    return _crush(np.concatenate(parts)) * 0.55


def scratch() -> np.ndarray:
    """Three fast claw rasps (filtered noise bursts)."""
    out = []
    for i in range(3):
        t = _t(0.07)
        noise = np.random.default_rng(30 + i).uniform(-1, 1, len(t))
        # crude lowpass: cumulative average to roughen the rasp
        kernel = np.ones(24) / 24
        rasp = np.convolve(noise, kernel, mode="same") * _env(t, 0.004, 0.03, 0.07)
        out.append(_crush(rasp * 2.5))
        out.append(np.zeros(int(SR * 0.08)))
    return np.concatenate(out) * 0.6


def puke() -> np.ndarray:
    """A sad little retch + splat: pitch-diving warble, then a noise blob."""
    dur = 0.55
    t = _t(dur)
    glide = np.linspace(520.0, 150.0, len(t))
    warble = _triangle(glide * (1.0 + 0.09 * np.sin(2 * np.pi * 9 * t)))
    n = np.random.default_rng(7).uniform(-1, 1, len(t))
    splat = np.convolve(n, np.ones(32) / 32, mode="same")
    splat *= np.clip(t * 8.0 - 2.8, 0.0, 1.0)  # the blob lands near the end
    x = warble * _env(t, 0.03, 0.20, dur) * 0.6 + splat * 0.4
    return _crush(x) * 0.7


EFFECTS = {
    "meow": meow,
    "mew": mew,
    "chirp": chirp,
    "purr": purr,
    "eat": eat,
    "drink": drink,
    "boing": boing,
    "chime": chime,
    "scratch": scratch,
    "puke": puke,
}


def build_pack(directory: Path) -> list[Path]:
    """Synthesize all effects into `directory` (skips existing files)."""
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, fn in EFFECTS.items():
        path = directory / f"{name}.wav"
        if not path.exists():
            _write(path, fn())
        written.append(path)
    return written
