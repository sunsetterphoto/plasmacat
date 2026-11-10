"""Needs, timing constants and the pure lifecycle math (aging, circadian rhythm)."""

from __future__ import annotations

import time

# Decay per real-time second (tuned for a desktop pet: noticeable in ~1-2 h).
NEED_DECAY = {
    "hunger": 100 / 5400.0,     # empty in 90 min
    "thirst": 100 / 4500.0,     # empty in 75 min
    "energy": 100 / 7200.0,     # empty in 2 h
    "play": 100 / 3600.0,       # empty in 60 min
    "affection": 100 / 10800.0, # empty in 3 h
    "bladder": 100 / 19800.0,   # ~5 litter trips/day: 2x poop, 3x pee
}

LITTER_CAPACITY = 5.0           # poop units; full box gets refused
GRASS_FRENZY_S = 20.0           # cat grass hyper mode
FURNITURE_CAPTIONS = ("Katzenbaum", "Kratzbaum", "Katzennest", "Regal",
                      "Karton")  # preferred spots
# platforms that count as the desktop (back) level: furniture + the wheel
LEVEL_BACK_CAPTIONS = FURNITURE_CAPTIONS + ("Laufrad",)
NEGLECT_EAT_S = 4500.0          # ~75 min without attention -> boredom eating
LEVEL_DWELL_S = 30.0            # after a level change she STAYS (user P28)
KEY_HOLD_S = 0.35               # P42: a direction key counts as 'held' this
                                # long (auto-repeat refreshes; no key-up events)

# -- aging / lifecycle (P47) ---------------------------------------------------
AGE_MAX = 15.0                  # growth stages 0 (kitten) .. 15 (very old)
AGE_STAGE_S = 8 * 3600.0        # base pace: one stage per 8 h of run time
CARE_EMPTY_S = 7200.0           # attention reservoir 1 -> 0 in 2 h
YOUNG_BAND = (3.0, 9.0)         # the 'young adult' band interaction stretches


def offline_aging(age: float, care: float, elapsed: float) -> tuple[float, float]:
    """Aging while the game was closed: nobody pets or plays, so the care
    reservoir drains and the clock runs at the uncared-for rate (the offline
    gain is capped at one full stage)."""
    elapsed = max(0.0, elapsed)
    care = max(0.0, care - elapsed / CARE_EMPTY_S)
    gained = min(elapsed / AGE_STAGE_S * 1.55, 1.0)
    return min(AGE_MAX, age + gained), care

SLEEP_REGEN = 100 / 900.0       # energy refills in 15 min of sleep
HOP_COOLDOWN_S = 25.0
HUNT_COOLDOWN_S = 12.0
CATCH_RANGE = 90.0              # pounce lands within this of the cursor = caught

ATTACHMENT_LEVELS = [
    (0, "Stray"),
    (100, "Acquaintance"),
    (300, "Friend"),
    (700, "Bonded"),
    (1500, "Inseparable"),
]

# Food shop: the cat likes foods differently (preference = hunger multiplier +
# affection bonus per meal). Catnip is… special.
FOODS = {
    "kibble": {"label": "Kibble", "hunger_mult": 1.0, "affection": 0.0, "thirst": 0.0},
    "tuna":   {"label": "Tuna", "hunger_mult": 1.4, "affection": 4.0, "thirst": 0.0},
    "milk":   {"label": "Milk", "hunger_mult": 0.8, "affection": 2.0, "thirst": 15.0},
    "catnip": {"label": "Catnip", "hunger_mult": 0.5, "affection": 8.0, "thirst": 0.0},
}
CATNIP_HIGH_S = 30.0


def circadian(hour: int | None = None) -> tuple[float, float]:
    """Cats are crepuscular (P26): most active at dawn/dusk, sleepy at night
    and midday. Returns (sleep multiplier, activity multiplier) for scoring."""
    h = time.localtime().tm_hour if hour is None else hour
    if 23 <= h or h < 5:
        return 2.2, 0.5    # deep night: sleepy
    if 5 <= h < 8:
        return 0.7, 1.4    # dawn zoomies
    if 8 <= h < 17:
        return 1.3, 0.9    # day naps
    if 17 <= h < 21:
        return 0.7, 1.4    # dusk playtime
    return 1.6, 0.7        # evening wind-down
