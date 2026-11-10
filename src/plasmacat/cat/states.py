"""State sets: which brain states commit, calm or shield the cat."""

from __future__ import annotations

# states that COMMIT her to a level (P28). Everything else (sit, groom,
# loaf, watch, yawn, rituals, enjoy…) is level-neutral and never flips her:
# the level only changes on deliberate cross-world actions.
BACK_COMMITTED = frozenset({
    "eating", "drinking", "to_food", "to_water",
    "scratching", "to_scratch",
    "littering", "litter_cover", "to_litter", "litter_beg",
    "nibbling", "to_grass", "to_bed", "knead",
    "to_wheel", "to_wheel_air", "wheel_run",
    "to_box", "to_box_air", "box_hide",
})
FRONT_COMMITTED = frozenset({
    "wander", "chase", "hunt_stalk", "hunt_pounce", "to_toy", "pounce_toy",
    "follow", "to_gift", "carry_gift", "greet", "hop_walk", "zoomies", "to_toy_air", "to_toy_edge",
    "laser_chase", "laser_pounce", "user",
})

# P48: states in which a cat can be approached for a social interaction
SOCIAL_CALM = ("idle", "stand", "sit", "wander", "groom", "watch", "loaf")

# Reflex shields, nested on purpose: a returning human interrupts the
# least, a startle more, a hunt trigger the most.
# on_user_return: never greets out of these
RETURN_IMMUNE = frozenset({
    "air_down",
    "air_up",
    "chase_peer",
    "cuddle",
    "drinking",
    "eating",
    "fight",
    "flee_peer",
    "knead",
    "litter_cover",
    "littering",
    "nibbling",
    "scratching",
    "sleep",
    "sleep_belly",
    "user",
    "wheel_run",
})
# on_startle: additionally ignored
STARTLE_IMMUNE = RETURN_IMMUNE | frozenset({
    "carry_gift",
    "prep_jump",
    "retch",
    "supervise",
})
# on_hunt_trigger: additionally ignored
HUNT_IMMUNE = STARTLE_IMMUNE | frozenset({
    "beg",
    "box_hide",
    "land",
    "laser_chase",
    "laser_pounce",
    "stretch",
    "to_box",
    "to_box_air",
    "to_gift",
    "to_litter",
    "to_peer",
    "to_sleep_peer",
    "wiggle",
    "yawn",
    "zoomies",
})
