#!/usr/bin/env python3
"""Generate the fountain's gentle bubbling (src/plasmacat/data/sounds/bubble.wav).

Physically modeled, not a chiptune: every air bubble rings as a damped sine
whose pitch rises slightly as it detaches (Minnaert resonance, after van den
Doel's bubble model); small bubbles ring high and short. A faint band-passed
trickle sits underneath. The result is normalized to a quiet level on
purpose — the fountain should be barely noticeable.

Usage: python3 tools/make_bubbles.py [out.wav]   (deterministic, seed 7)
"""

from __future__ import annotations

import math
import random
import struct
import sys
import wave
from pathlib import Path

RATE = 44100
SECONDS = 4.0
TARGET_RMS_DB = -40.0   # quiet bed
SEED = 7


def bubbles(n: int, rng: random.Random) -> list[float]:
    out = [0.0] * n
    t = 0.05
    while t < SECONDS - 0.1:
        t += rng.expovariate(5.0)                      # ~5 bubbles per second
        for _ in range(1 + (rng.random() < 0.25)):     # sometimes a pair
            f0 = rng.uniform(650.0, 2300.0)            # small bubbles: high pitch
            tau = rng.uniform(0.006, 0.018)            # and a short ring
            rise = rng.uniform(4.0, 9.0)               # pitch rise per second (rel.)
            amp = rng.uniform(0.25, 1.0) * (900.0 / f0) ** 0.5
            start = int((t + rng.uniform(0.0, 0.02)) * RATE)
            phase = 0.0
            for i in range(int(tau * 6 * RATE)):
                k = start + i
                if k >= n:
                    break
                dt = i / RATE
                phase += 2 * math.pi * f0 * (1 + rise * dt) / RATE
                env = math.exp(-dt / tau) * math.sin(min(1.0, i / 130.0) * math.pi / 2) ** 2  # 3 ms soft attack: no click
                out[k] += amp * env * math.sin(phase)
    return out


def trickle(n: int, rng: random.Random) -> list[float]:
    """Band-passed noise (~1-4 kHz) with a slow wobble: running water."""
    out, lp, hp_prev, hp = [0.0] * n, 0.0, 0.0, 0.0
    a_lp = 1 - math.exp(-2 * math.pi * 4000 / RATE)
    a_hp = math.exp(-2 * math.pi * 1000 / RATE)
    for i in range(n):
        x = rng.uniform(-1, 1)
        lp += a_lp * (x - lp)
        hp = a_hp * (hp + lp - hp_prev)
        hp_prev = lp
        wobble = 0.6 + 0.4 * math.sin(2 * math.pi * 0.7 * i / RATE)
        out[i] = hp * wobble * 0.08
    return out


def main() -> None:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(__file__).resolve().parents[1] / "src/plasmacat/data/sounds/bubble.wav"
    rng = random.Random(SEED)
    n = int(SECONDS * RATE)
    mix = [b + w for b, w in zip(bubbles(n, rng), trickle(n, rng))]
    fade = int(0.35 * RATE)
    for i in range(fade):
        g = i / fade
        mix[i] *= g
        mix[n - 1 - i] *= g
    rms = math.sqrt(sum(s * s for s in mix) / n) or 1.0
    gain = 10 ** (TARGET_RMS_DB / 20) / rms
    pcm = struct.pack("<%dh" % n, *(max(-32767, min(32767, int(s * gain * 32767))) for s in mix))
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    print("wrote", out_path)


if __name__ == "__main__":
    main()
