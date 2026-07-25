"""Cat brain: needs, mood, attachment, and a small utility-AI for behaviors.

Needs are 0-100 (100 = fully satisfied) and decay over time. Every few seconds
the brain scores candidate behaviors and commits to the best one for a while.
Pure python, no Qt; randomness is injectable for deterministic tests.

Attachment (XP + levels) grows through interaction: petting, rubbing, playing,
feeding (P5). Higher attachment unlocks cuddling and the tail snuggle.

Behaviors: wander, sit, groom, sleep, beg, hop-on-window (P3), chase, hunt,
cuddle, enjoy (P4), follow, bring gifts (P26). Linear sequences by _continue().
"""

from __future__ import annotations

import random
import time

from plasmacat.bridge.desktop import DesktopState, Platform
from plasmacat.cat.physics import CatBody, RUN_SPEED, WALK_SPEED

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
    "follow", "to_gift", "carry_gift", "greet", "hop_walk", "zoomies",
    "laser_chase", "laser_pounce", "user",
})

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


class Brain:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.needs: dict[str, float] = {
            "hunger": 80.0, "thirst": 80.0, "energy": 90.0,
            "play": 70.0, "affection": 50.0, "bladder": 85.0,
        }
        self.state = "idle"
        self.state_left = 0.0
        self.hop_target: Platform | None = None
        self.hop_cooldown = 0.0
        self.hunt_cooldown = 0.0
        self._startle_cd = 0.0
        self.wander_cooldown = 0.0          # set after a wall block (P19)
        self.hunt_target: tuple[float, float] | None = None
        self.petted_strokes = 0
        self.attachment_xp = 0.0
        self.log: list[str] = []
        # P5: bowls, treat flag, sound intent queue, thought bubble
        self.food_x: float | None = None
        self.water_x: float | None = None
        self.treat_pending = False
        self.toys = None                    # ToyManager, set by the overlay
        self._play_toy_target = None        # Toy being approached/pounced
        # P8d: bowl contents + food shop + catnip
        self.food_type = "kibble"
        self.food_fill = 100.0              # 0..100, drains while eating
        self.water_fill = 100.0
        self.catnip_high = 0.0              # seconds of hyper mode remaining
        # P9: placeable furniture
        self.scratch_x: float | None = None
        self.bed_x: float | None = None
        self.grass_x: float | None = None
        self.grass_charges = 3.0            # nibbles left; regrows over 10 min
        self._grass_regrow = 0.0
        self._sleep_mult = 1.0              # 1.5 while sleeping in the cat bed
        # P15: rituals & chains
        self._ritual: list[str] | None = None   # pre-sleep ritual steps left
        self._ritual_done = False
        self._chain_groom_sleep = False     # eating -> groom -> sleep chain
        self._post_sleep = 0.0              # seconds of extra attention-seeking
        self._was_sleeping = False
        self._lick_cycles = 0               # face-wash: paw licks remaining (P20)
        # P10: litter box + big cat tree
        self.litter_x: float | None = None
        self.litter_fill = 0.0              # poop units; user cleans at 5
        self.litter_deposits: list[str] = []  # P40: "poop"/"pee" per event
        self.tree_x: float | None = None
        # P11: exercise wheel
        self.wheel_x: float | None = None
        self.sounds: list[str] = []       # drained by the overlay each tick
        self.bubble: str | None = None    # thought-bubble icon name (props)
        self._purr_t = 0.0
        self._fx_t = 0.0
        # P24: empty-bowl visits cool down so the cat doesn't beg forever;
        # _wiggle_then holds the pounce that follows the butt wiggle
        self._food_beg_cd = 0.0
        self._water_beg_cd = 0.0
        self._wiggle_then: tuple[str, float, float] | None = None
        # P25: neglect -> boredom eating -> overeating -> vomit (real cats do
        # this; cat grass in excess also comes right back up)
        self._neglect_s = 0.0            # seconds since the last attention
        self._overate_s = 0.0            # time spent eating while full
        self._bored_eat = False          # this meal is boredom eating
        self._grass_recent = 0.0         # recently nibbled grass (stacking it)
        self.puke_spots: list[float] = []  # x positions of messes to clean up
        # P25 furniture: floating wall shelves + the cardboard box
        self.shelves: list[tuple[float, float]] = []
        self.box_x: float | None = None
        # P26: personality + movement polish
        self.fav_toy = "ball" if self.rng.random() < 0.5 else "plush"
        self._circ = (1.0, 1.0)          # circadian (sleep, activity) multipliers
        self._jump_then: tuple[float, float, str] | None = None  # after prep
        self._gift_toy = None            # plush being carried to the human
        # P28: the visibility level is a deliberate decision with a dwell
        # time, not a per-frame derivation (no more chaotic flip-flopping)
        self._level = "front"
        self._level_t = LEVEL_DWELL_S    # allow the first commit immediately
        # P34: laser pointer sessions
        self._laser_cd = 0.0             # cooldown after a chase session
        # P42: user control mode (WASD/arrows via KWin global shortcuts)
        self.user_control = False
        self.held: dict[str, float] = {}  # direction -> seconds still held
        self._user_jump = False           # jump edge queued by a key event

    def _is_sleep_state(self) -> bool:
        return self.state in ("sleep", "sleep_belly")

    def _laser(self):
        """The laser-pointer dot toy, if the user switched it on (P34)."""
        if not self.toys:
            return None
        return next((t for t in self.toys.toys if t.kind == "laser"), None)

    # -- needs & attachment ---------------------------------------------------

    def decay(self, dt: float) -> None:
        for k, rate in NEED_DECAY.items():
            if k == "energy" and self._is_sleep_state():
                self.needs[k] = min(100.0, self.needs[k] + SLEEP_REGEN * self._sleep_mult * dt)
            else:
                self.needs[k] = max(0.0, self.needs[k] - rate * dt)
        # cat grass regrows one charge per 10 minutes
        if self.grass_charges < 3.0:
            self._grass_regrow += dt
            if self._grass_regrow >= 600.0:
                self.grass_charges += 1.0
                self._grass_regrow = 0.0

    @property
    def mood(self) -> float:
        return sum(self.needs.values()) / len(self.needs)

    @property
    def attachment_level(self) -> int:
        lvl = 0
        for i, (xp_req, _name) in enumerate(ATTACHMENT_LEVELS):
            if self.attachment_xp >= xp_req:
                lvl = i
        return lvl

    @property
    def attachment_name(self) -> str:
        return ATTACHMENT_LEVELS[self.attachment_level][1]

    # -- visibility level (P28) -------------------------------------------------

    @property
    def level(self) -> str:
        """'front' (above the windows) or 'back' (desktop level, behind)."""
        return self._level

    def _committed_level(self, body: CatBody) -> str | None:
        """The level the current state commits her to — or None for neutral
        states, which keep whatever level she already has (anti flip-flop)."""
        plat = body.platform
        if plat is not None and plat.caption in LEVEL_BACK_CAPTIONS:
            return "back"  # furniture/wheel platforms are always desktop level
        if self.state in BACK_COMMITTED:
            return "back"
        if self.state in FRONT_COMMITTED:
            return "front"
        if self.state in ("sleep", "sleep_belly"):
            # lying down on the desktop = background level; on a window top
            # she stays on the window level
            if plat is not None and not plat.floor:
                return "front"
            return "back"
        if self.state in ("air_up", "prep_jump") and self.hop_target is not None:
            return "back" if self.hop_target.caption in LEVEL_BACK_CAPTIONS \
                else "front"
        return None

    def _redirect_to_level(self, body: CatBody, desktop: DesktopState) -> None:
        """A level-changing state slipped in mid-dwell: replace it with
        something suitable for the level she must stay on (P28)."""
        self._start(self._choose(desktop, body, force_level=True), body, desktop)

    def _force_level_ready(self) -> None:
        """User-initiated events override the dwell (her human calls, she
        comes): the next level change is allowed immediately."""
        self._level_t = max(self._level_t, LEVEL_DWELL_S)

    def add_xp(self, amount: float, reason: str) -> None:
        before = self.attachment_level
        self.attachment_xp += amount
        if self.attachment_level > before:
            self.log.append(f"ATTACHMENT UP -> {self.attachment_name} ({reason})")
            self.sounds.append("chime")

    def gain(self, need: str, amount: float) -> None:
        self.needs[need] = min(100.0, self.needs[need] + amount)

    # -- interaction events (called by the overlay via the detector) -----------

    def _meow(self) -> str:
        """A generic meow with variety (P17: avoids the same recording on loop)."""
        return "meow" if self.rng.random() < 0.6 else "meow2"

    def on_stroke(self, body: CatBody) -> None:
        """A petting stroke over the cat's body."""
        self._neglect_s = 0.0
        if self.mood < 30 and self.rng.random() < 0.5:
            # grumpy cat has no patience: walks off (no affection gained)
            plat = body.platform
            if plat is not None and self.state not in ("sleep", "eating", "drinking"):
                dest = min(max(body.x - body.facing * 180, plat.x0 + 90), plat.x1 - 90)
                body.walk_to(dest, WALK_SPEED)
                self.state = "annoyed"
                self.state_left = 4.0
                self.log.append("too grumpy for petting…")
                return
        self.petted_strokes += 1
        self.gain("affection", 1.5)
        self.add_xp(1.0, "petting")
        if self._is_sleep_state():
            self.state_left = 0.0          # wake up
            self.state = "idle"
        elif self.state in ("idle", "stand", "sit", "wander", "groom",
                            "cuddle_walk", "cuddle_rub", "watch", "loaf",
                            "toy_watch"):
            self.state = "enjoy"
            self.state_left = 1.6
            body.stop()

    def on_rub(self, body: CatBody) -> None:
        """Gentle cursor contact in the head zone."""
        self._neglect_s = 0.0
        self.gain("affection", 1.0)
        self.add_xp(1.5, "head rub")
        if self.state in ("idle", "stand", "sit", "wander", "groom", "enjoy",
                          "cuddle_walk", "cuddle_rub", "watch", "loaf",
                          "tailwrap"):
            self.state = "headrub"
            self.state_left = 1.8
            body.stop()

    def on_pat(self, body: CatBody, cursor: tuple[float, float]) -> None:
        """The cursor teases right in front of her face: reach out and pat it
        (P26 — the gentle paw bat every cat owner knows)."""
        if self.state in ("idle", "stand", "sit", "watch", "loaf", "wander",
                          "follow"):
            body.facing = 1 if cursor[0] >= body.x else -1
            self.state = "paw_bat"
            self.state_left = 0.7
            body.stop()
            self.gain("play", 1.0)

    def clear_toy_state(self) -> None:
        """'Clear toys' (tray): drop every behavior that targets a toy, so she
        doesn't pounce at air or 'catch' a deleted toy (P42)."""
        self._play_toy_target = None
        self._gift_toy = None
        if self._wiggle_then is not None and self._wiggle_then[0] in ("toy", "laser"):
            self._wiggle_then = None  # the wiggle branch lands on idle by itself
        if self.state in ("to_toy", "pounce_toy", "toy_watch", "to_gift",
                          "carry_gift", "laser_chase", "laser_pounce"):
            self.state = "idle"
            self.state_left = 0.0

    def set_user_control(self, on: bool) -> None:
        """Tray toggle (P42): the human drives the cat with WASD/arrows.
        The brain's autonomy is suspended while this is on."""
        self.user_control = on
        self.held.clear()
        self._user_jump = False
        self._force_level_ready()   # the human plays: she may come forward
        if not on:
            self.state = "idle"
            self.state_left = 0.0

    def on_key_event(self, name: str) -> None:
        """A global-shortcut activation from the KWin bridge. There are no
        key-up events on Wayland: a direction counts as held for KEY_HOLD_S
        (key auto-repeat keeps refreshing it), jump/stop are edge events."""
        if not self.user_control:
            return
        if name in ("left", "right"):
            self.held[name] = KEY_HOLD_S
        elif name == "jump":
            self._user_jump = True
        elif name == "stop":
            self.held.clear()

    def _user_tick(self, dt: float, body: CatBody, desktop: DesktopState) -> None:
        """Held keys -> run, jump edge -> forward hop. Needs/ambient keep
        running; _choose stays out of the way via the rolling state."""
        for k in list(self.held):
            self.held[k] -= dt
            if self.held[k] <= 0:
                del self.held[k]
        self.state = "user"
        self.state_left = 0.5
        direction = (1 if "right" in self.held else 0) \
            - (1 if "left" in self.held else 0)
        if direction != 0:
            body.facing = direction  # also aims the jump (pressed mid-run)
        if body.airborne:
            return
        if self._user_jump:
            self._user_jump = False
            body.jump_to(body.x + body.facing * 140, body.y - 80)
            return
        if direction != 0:
            body.walk_to(body.x + direction * 400, RUN_SPEED)
        elif body.target_x is not None:
            body.stop()

    def on_hunt_trigger(self, body: CatBody, cursor: tuple[float, float],
                        desktop: DesktopState) -> None:
        """Fast erratic cursor movement nearby: reflex pounce sequence."""
        if self.hunt_cooldown > 0 or body.airborne:
            return
        # never interrupt private business or committed sequences (P24):
        # a cat on the toilet / in the wheel / mid-meal does not pounce away
        if self.state in ("sleep", "sleep_belly", "beg", "air_up", "air_down",
                          "supervise", "eating", "drinking", "littering",
                          "litter_cover", "to_litter", "zoomies", "wheel_run",
                          "scratching", "nibbling", "knead", "yawn", "stretch",
                          "wiggle", "retch", "to_box", "to_box_air", "box_hide",
                          "to_gift", "carry_gift", "prep_jump", "land",
                          "laser_chase", "laser_pounce", "user"):
            return
        if self.needs["play"] < 15:
            return
        self._force_level_ready()  # the human teases: she may come forward now
        self.hunt_cooldown = HUNT_COOLDOWN_S
        self.hunt_target = cursor
        self.state = "hunt_stalk"
        self.state_left = 4.0
        body.stop()
        self.sounds.append("chirp")
        self.log.append("hunt!")

    def on_startle(self, body: CatBody, desktop: DesktopState) -> None:
        """Cursor rushed at the cat: hop back, mew, stay alert (P12b)."""
        if self._startle_cd > 0 or body.airborne:
            return
        if self.state in ("sleep", "sleep_belly", "eating", "drinking",
                          "littering", "litter_cover", "wheel_run",
                          "air_up", "air_down", "supervise", "scratching",
                          "nibbling", "knead", "retch", "carry_gift",
                          "prep_jump", "user"):
            return
        self._startle_cd = 10.0
        cx, _cy = desktop.cursor
        direction = -1.0 if cx > body.x else 1.0
        plat = body.platform or desktop.platform_below(body.x, body.y)
        tx = min(max(body.x + direction * 140, plat.x0 + 90), plat.x1 - 90)
        self.sounds.append("mew")
        self.log.append("startled!")
        if body.jump_to(tx, plat.y):
            self.state = "startle_air"
            self.state_left = 3.0
        else:
            self.state = "alert"
            self.state_left = 2.5

    def on_user_return(self, body: CatBody, desktop: DesktopState) -> None:
        """The human is back after being away: run to the cursor and greet
        (attachment-gated, P12b)."""
        if self.attachment_level < 1 or body.airborne:
            return
        if self.state in ("sleep", "sleep_belly", "eating", "drinking",
                          "littering", "litter_cover", "wheel_run",
                          "air_up", "air_down", "nibbling", "scratching",
                          "knead", "user"):
            return
        cx, _cy = desktop.cursor
        offset = 55 * (-1 if cx < body.x else 1)
        plat = desktop.platform_below(cx, desktop.screen_h)
        dest = min(max(cx + offset, plat.x0 + 90), plat.x1 - 90)
        body.walk_to(dest, RUN_SPEED)
        self._force_level_ready()  # the human is back: greet them up front
        self.state = "greet"
        self.state_left = 15.0
        self.sounds.append(self._meow())
        self.log.append("greeting the human!")

    # -- behavior selection -------------------------------------------------

    def _score(self, name: str, desktop: DesktopState) -> float:
        n = self.needs
        _sleep_m, _act_m = self._circ
        if name == "sleep":
            return 3.0 * (1 - n["energy"] / 100.0) ** 2 * _sleep_m
        if name == "beg":
            lack = max(1 - n["hunger"] / 100.0, 1 - n["thirst"] / 100.0)
            return 2.5 * lack ** 2 if lack > 0.45 else 0.0
        if name == "hop":
            has_windows = any(not p.floor for p in desktop.platforms)
            if not has_windows or self.hop_cooldown > 0:
                return 0.0
            return (0.35 + 0.4 * (n["play"] / 100.0)) * _act_m
        if name == "eat":
            if self.food_x is None:
                return 0.0
            if self.treat_pending:
                return 5.0
            if self.food_fill <= 0 and self._food_beg_cd > 0:
                return 0.0  # already begged recently: don't camp the empty bowl
            # a neglected cat eats from boredom (and overeats -> vomits)
            if (self.food_fill > 0 and self._neglect_s > NEGLECT_EAT_S
                    and 45 < n["hunger"] < 90):
                return 1.1
            lack = 1 - n["hunger"] / 100.0
            return 3.0 * lack ** 2 if lack > 0.4 else 0.0
        if name == "drink":
            if self.water_x is None:
                return 0.0
            lack = 1 - n["thirst"] / 100.0
            return 3.0 * lack ** 2 if lack > 0.4 else 0.0
        if name == "play_toy":
            if not self.toys or not self.toys.toys:
                return 0.0
            return (0.45 + 0.45 * (1 - n["play"] / 100.0)) * _act_m
        if name == "scratch":
            spots = [v for v in (self.scratch_x, self.tree_x) if v is not None]
            if not spots:
                return 0.0
            return 0.30 + 0.45 * (1 - n["play"] / 100.0)
        if name == "hide":
            if self.box_x is None:
                return 0.0
            return 0.22 + 0.12 * (1 - n["play"] / 100.0)
        if name == "nibble":
            if self.grass_x is None or self.grass_charges < 1:
                return 0.0
            return 0.18 + 0.10 * (n["affection"] / 100.0)
        if name == "litter":
            if self.litter_x is None or n["bladder"] > 35:
                return 0.0
            urgency = 1 - n["bladder"] / 100.0
            return 4.0 * urgency ** 2 + (2.0 if n["bladder"] < 20 else 0.0)
        if name == "exercise":
            if self.wheel_x is None or n["energy"] < 30:
                return 0.0
            return (0.32 + 0.40 * (1 - n["play"] / 100.0)) * _act_m
        if name == "chase":
            if not desktop.cursor_active:
                return 0.0
            s = 0.30 + 0.35 * (1 - n["play"] / 100.0)
            return (s + (0.3 if self.catnip_high > 0 else 0.0)) * _act_m
        if name == "cuddle":
            if not desktop.cursor_active or self.attachment_level < 1:
                return 0.0
            s = (0.10 + 0.25 * (1 - n["affection"] / 100.0)
                 + 0.10 * self.attachment_level)
            return s * (2.0 if self._post_sleep > 0 else 1.0)  # extra cuddly after sleep
        if name == "follow":
            # padding after the human at a respectful distance (P26)
            if not desktop.cursor_active or self.attachment_level < 2:
                return 0.0
            return 0.16 + 0.03 * self.attachment_level
        if name == "gift":
            # bringing 'prey' to the human: the ultimate cat compliment (P26)
            if not desktop.cursor_active or self.attachment_level < 3:
                return 0.0
            if not self.toys or not any(t.kind == "plush" for t in self.toys.toys):
                return 0.0
            return 0.12
        if name == "watch":
            if not desktop.cursor_active:
                return 0.0
            return 0.15 * _act_m
        if name == "laser_chase":
            # irresistible — but real needs still win, and she needs steam
            if not desktop.cursor_active or self._laser() is None:
                return 0.0
            if self._laser_cd > 0 or n["energy"] < 25 or n["play"] < 10:
                return 0.0
            return 0.85
        if name == "wander":
            if self.wander_cooldown > 0:
                return 0.0
            return 0.30 + 0.15 * (n["play"] / 100.0)
        if name == "groom":
            return 0.22
        if name == "sit":
            return 0.18
        if name == "loaf":
            # the contented tuck: only when she's comfortable and not sleepy
            if self.mood < 55 or n["energy"] < 25:
                return 0.0
            return 0.17
        return 0.0

    def _choose(self, desktop: DesktopState, body: CatBody,
                force_level: bool = False) -> str:
        self._circ = circadian()
        names = ["sleep", "beg", "hop", "chase", "cuddle", "eat", "drink",
                 "play_toy", "scratch", "nibble", "litter", "exercise", "watch",
                 "wander", "groom", "sit", "loaf", "hide", "follow", "gift",
                 "laser_chase"]
        if force_level or self._level_t < LEVEL_DWELL_S:
            # mid-dwell (or a forced redirect): only same-level + neutral
            # activities — she stays put and does something new there (P28)
            plat = body.platform
            on_furn = plat is not None and plat.caption in LEVEL_BACK_CAPTIONS
            on_window = plat is not None and not plat.floor and not on_furn
            if self._level == "back":
                drop = {"chase", "follow", "gift", "play_toy", "laser_chase"}
                if not on_furn:
                    drop.add("wander")
            else:
                drop = {"eat", "drink", "scratch", "nibble", "litter",
                        "exercise", "hide"}
                if not on_window:
                    drop.add("sleep")   # floor/furniture sleep = back level
            names = [n for n in names if n not in drop]
        scored = [(self._score(n, desktop) * self.rng.uniform(0.8, 1.2), n)
                  for n in names]
        scored.sort(reverse=True)
        return scored[0][1]

    # -- main tick -----------------------------------------------------------

    def tick(self, dt: float, body: CatBody, desktop: DesktopState) -> None:
        self.decay(dt)
        self.hop_cooldown = max(0.0, self.hop_cooldown - dt)
        self.hunt_cooldown = max(0.0, self.hunt_cooldown - dt)
        self._startle_cd = max(0.0, self._startle_cd - dt)
        self.wander_cooldown = max(0.0, self.wander_cooldown - dt)
        self.catnip_high = max(0.0, self.catnip_high - dt)
        self._post_sleep = max(0.0, self._post_sleep - dt)
        self._food_beg_cd = max(0.0, self._food_beg_cd - dt)
        self._water_beg_cd = max(0.0, self._water_beg_cd - dt)
        self._grass_recent = max(0.0, self._grass_recent - dt)
        self._laser_cd = max(0.0, self._laser_cd - dt)
        self._neglect_s += dt  # reset by any user attention (stroke/rub/treat)
        self.state_left -= dt
        # a window wall stopped the walk (set by physics): cool down instead
        # of instantly re-walking into the same wall (P19 fix, wired up in P24)
        if body.blocked:
            body.blocked = False
            self.wander_cooldown = 5.0
        # P28 level tracking: committed states may flip the level once the
        # 30 s dwell has passed; mid-dwell they get redirected to the
        # current level instead (no more chaotic door-hopping)
        self._level_t += dt
        want = self._committed_level(body)
        if want is not None and want != self._level:
            # user control is a user-initiated event: like _force_level_ready,
            # it overrides the dwell immediately (P42)
            if self._level_t >= LEVEL_DWELL_S or self.user_control:
                self._level = want
                self._level_t = 0.0
                self.log.append(f"level -> {want}")
            else:
                self._redirect_to_level(body, desktop)
        if self.user_control:
            # the human steers (P42): autonomy sleeps, needs/ambient run on
            self._user_tick(dt, body, desktop)
            self._ambient(dt)
            self._was_sleeping = self._is_sleep_state()
            return
        self._continue(dt, body, desktop)
        self._ambient(dt)
        if body.airborne or body.target_x is not None:
            self._was_sleeping = self._is_sleep_state()
            return
        if self.state_left > 0:
            self._was_sleeping = self._is_sleep_state()
            return
        if self._was_sleeping and self._is_sleep_state():
            self._apply_wake()
            # cats don't sprint out of bed: yawn, stretch, then face the day
            if self.rng.random() < 0.5:
                self.state = "yawn"
                self.state_left = self.rng.uniform(0.9, 1.4)
            else:
                self.state = "stretch"
                self.state_left = self.rng.uniform(1.2, 1.8)
            self._was_sleeping = False
            return
        self._start(self._choose(desktop, body), body, desktop)
        self._was_sleeping = self._is_sleep_state()

    def _ambient(self, dt: float) -> None:
        """Purring, periodic begging meows, and the thought bubble."""
        if self.state in ("enjoy", "headrub", "cuddle_rub", "tailwrap", "knead",
                          "sleep", "sleep_belly"):
            self._purr_t -= dt
            if self._purr_t <= 0:
                self.sounds.append("purr")
                self._purr_t = 2.2
        else:
            self._purr_t = 0.0
        if self.state == "beg":
            self._fx_t -= dt
            if self._fx_t <= 0:
                self.sounds.append("beg")
                self._fx_t = self.rng.uniform(2.5, 4.5)
            self.bubble = ("fish" if self.needs["hunger"] <= self.needs["thirst"]
                           else "drop")
        elif self.state in ("enjoy", "headrub", "cuddle_rub", "tailwrap"):
            self.bubble = "heart"
        elif self._is_sleep_state():
            self.bubble = "zzz"
        else:
            low = min(self.needs, key=lambda k: self.needs[k])
            if self.needs[low] < 35:
                self.bubble = {"hunger": "fish", "thirst": "drop",
                               "energy": "zzz"}.get(low)
            else:
                self.bubble = None

    def on_treat(self) -> None:
        """Tray 'Give treat': the cat will go eat soon and love you for it."""
        self._neglect_s = 0.0
        self.treat_pending = True
        self.log.append("treat offered!")

    # -- food shop / refills ---------------------------------------------------

    def buy_food(self, food: str) -> None:
        """Shop purchase: swaps the food type and refills the bowl."""
        if food not in FOODS:
            return
        self.food_type = food
        self.food_fill = 100.0
        self.sounds.append("chime")
        self.log.append(f"bought {FOODS[food]['label']}")

    def refill_food(self) -> None:
        self.food_fill = 100.0
        self.sounds.append("eat")
        self.log.append("food refilled")

    def refill_water(self) -> None:
        self.water_fill = 100.0
        self.sounds.append("drink")
        self.log.append("water refilled")

    def clean_litter(self) -> None:
        self.litter_fill = 0.0
        self.litter_deposits.clear()
        self.sounds.append("scratch")
        self.log.append("litter box cleaned")

    def clean_puke(self) -> None:
        """Tray cleanup: removes all vomit puddles."""
        if self.puke_spots:
            self.puke_spots.clear()
            self.sounds.append("scratch")
            self.log.append("vomit cleaned up")

    def _start_retch(self, reason: str) -> None:
        """Overeating / too much grass comes back up: retch, then a puddle
        on the floor the user has to clean (P25)."""
        self.state = "retch"
        self.state_left = 2.4
        self._fx_t = 0.0
        self.log.append(f"about to vomit ({reason})…")

    # -- behavior starts -----------------------------------------------------

    def _start(self, name: str, body: CatBody, desktop: DesktopState) -> None:
        self.state = name
        if name == "sleep":
            plat = body.platform
            if not self._ritual_done and self.rng.random() < 0.5:
                # the bedtime ritual: sit, scratch self, groom, then sleep
                self._ritual = ["ritual_sit", "ritual_scratch", "ritual_groom"]
                self._ritual_done = True
                self.state = self._ritual.pop(0)
                self.state_left = self._ritual_dur(self.state)
            elif plat is not None and plat.caption in FURNITURE_CAPTIONS:
                # already on the tree/post: nap right here, no walk to the bed
                self.state_left = self.rng.uniform(120, 7200)
            elif (self.bed_x is not None and abs(body.x - self.bed_x) > 60
                    and self.rng.random() < 0.4):
                body.walk_to(self.bed_x, WALK_SPEED)
                self.state = "to_bed"
                self.state_left = 30.0
            else:
                # cats nap where they are: floor spot, window top, anywhere
                self.state_left = self.rng.uniform(120, 7200)
                if (plat is not None and plat.floor
                        and self.attachment_level >= 3
                        and self.rng.random() < 0.3):
                    # deep trust: belly-up sleep (only where she feels safe)
                    self.state = "sleep_belly"
        elif name == "beg":
            self.state_left = self.rng.uniform(6, 10)
            self.sounds.append("beg")
            self.log.append(f"begging! needs={self._fmt_needs()}")
        elif name == "scratch":
            spots = [v for v in (self.scratch_x, self.tree_x) if v is not None]
            target = min(spots, key=lambda v: abs(v - body.x))
            body.walk_to(target - 40, WALK_SPEED)
            self.state = "to_scratch"
            self.state_left = 20.0
        elif name == "nibble":
            body.walk_to((self.grass_x or 400) - 35, WALK_SPEED)
            self.state = "to_grass"
            self.state_left = 20.0
        elif name == "litter":
            if self.litter_fill < LITTER_CAPACITY and self.needs["bladder"] < 30:
                # pre-poop zoomies: sprint across the desktop like crazy first
                self.state = "zoomies"
                self.state_left = self.rng.uniform(6, 10)
                self._fx_t = 0.0
            else:
                body.walk_to((self.litter_x or 500) - 30, WALK_SPEED)
                self.state = "to_litter"
                self.state_left = 20.0
        elif name == "exercise":
            body.walk_to((self.wheel_x or 600) - 80, RUN_SPEED)
            self.state = "to_wheel"
            self.state_left = 20.0
        elif name == "hide":
            # into the cardboard box: approach, hop in, lie in wait
            body.walk_to((self.box_x or 700) - 85, WALK_SPEED)
            self.state = "to_box"
            self.state_left = 20.0
        elif name == "watch":
            body.stop()
            self.state_left = self.rng.uniform(3, 6)
        elif name == "loaf":
            body.stop()
            self.state_left = self.rng.uniform(8, 30)
        elif name == "eat":
            self._bored_eat = (self._neglect_s > NEGLECT_EAT_S
                               and self.needs["hunger"] > 45)
            self._overate_s = 0.0
            body.walk_to((self.food_x or 100) - 35, WALK_SPEED)
            self.state = "to_food"
            self.state_left = 30.0
        elif name == "drink":
            body.walk_to((self.water_x or 190) - 35, WALK_SPEED)
            self.state = "to_water"
            self.state_left = 30.0
        elif name == "play_toy":
            toy = None
            if self.toys:
                # every cat has a favorite toy (persisted personality, P26)
                fav = [t for t in self.toys.toys if t.kind == self.fav_toy]
                pool = fav or self.toys.toys
                toy = min(pool, key=lambda t: (t.x - body.x) ** 2
                          + (t.y - body.y) ** 2) if pool else None
            if toy is None:
                self.state = "sit"
                self.state_left = 3.0
            else:
                self._play_toy_target = toy
                offset = 45 * (-1 if toy.x < body.x else 1)
                body.walk_to(toy.x + offset, RUN_SPEED)
                self.state = "to_toy"
                self.state_left = 15.0
        elif name == "hop":
            self._start_hop(body, desktop)
        elif name == "chase":
            self.state_left = self.rng.uniform(6, 10)
            self._chase_step(body, desktop)
        elif name == "follow":
            self.state_left = self.rng.uniform(6, 12)
            self._fx_t = 0.0
        elif name == "laser_chase":
            # the human waves the dot: come forward immediately (P34)
            self._force_level_ready()
            self.state_left = self.rng.uniform(20, 45)  # session length
            self.log.append("LASER!")
        elif name == "gift":
            toy = next((t for t in self.toys.toys if t.kind == "plush"), None)
            if toy is None:
                self.state = "sit"
                self.state_left = 2.0
            else:
                self._gift_toy = toy
                offset = 45 * (-1 if toy.x < body.x else 1)
                body.walk_to(toy.x + offset, WALK_SPEED)
                self.state = "to_gift"
                self.state_left = 20.0
        elif name == "cuddle":
            self._start_cuddle(body, desktop)
        elif name == "wander":
            plat = body.platform or desktop.platform_below(body.x, body.y)
            lo, hi = self._walk_range(plat)
            target = self.rng.uniform(lo, hi)
            speed = RUN_SPEED if (self.rng.random() < 0.25 or self.catnip_high > 0) \
                else WALK_SPEED
            body.walk_to(target, speed)
            self.state_left = 30.0  # safety cap; cleared on arrival in _continue
        else:  # sit, groom
            if name == "groom" and self.rng.random() < 0.4:
                # face wash instead: paw folds the ear, then 8 paw licks (P20)
                self.state = "ear_fold"
                self.state_left = self.rng.uniform(1.2, 1.8)
                self._lick_cycles = 8
            else:
                self.state_left = self.rng.uniform(5, 14)

    def _start_hop(self, body: CatBody, desktop: DesktopState) -> None:
        candidates = [p for p in desktop.platforms
                      if not p.floor and p is not body.platform and p.y < body.y - 40]
        if self._level_t < LEVEL_DWELL_S:
            # mid-dwell: only hop to platforms of the current level (P28)
            if self._level == "back":
                candidates = [p for p in candidates
                              if p.caption in LEVEL_BACK_CAPTIONS]
            else:
                candidates = [p for p in candidates
                              if p.caption not in LEVEL_BACK_CAPTIONS]
        if not candidates:
            self.state = "sit"
            self.state_left = 4.0
            self.hop_cooldown = HOP_COOLDOWN_S
            return
        # cats love their furniture: prefer tree/post platforms most of the time
        furniture = [p for p in candidates if p.caption in FURNITURE_CAPTIONS]
        pool = furniture if furniture and self.rng.random() < 0.7 else candidates
        self.hop_target = min(pool, key=lambda p: abs((p.x0 + p.x1) / 2 - body.x))
        center = (self.hop_target.x0 + self.hop_target.x1) / 2
        if abs(center - body.x) > 300:
            plat = body.platform or desktop.platforms[-1]
            dest = min(max(center, plat.x0 + 40), plat.x1 - 40)
            body.walk_to(dest, RUN_SPEED)
            self.state = "hop_walk"
            self.state_left = 15.0
        else:
            self._try_jump_up(body)

    def _try_jump_up(self, body: CatBody) -> None:
        assert self.hop_target is not None
        center = (self.hop_target.x0 + self.hop_target.x1) / 2
        # coil first: cats crouch briefly before they launch (P26)
        self._jump_then = (center, self.hop_target.y, "air_up")
        self.state = "prep_jump"
        self.state_left = 0.22

    def _ritual_dur(self, state: str) -> float:
        return {"ritual_sit": self.rng.uniform(2, 4),
                "ritual_scratch": self.rng.uniform(3, 5),
                "ritual_groom": self.rng.uniform(4, 8)}[state]

    def _apply_wake(self) -> None:
        """Waking up: playful and extra attention-seeking for a minute."""
        self._post_sleep = 60.0
        self._ritual_done = False
        self.needs["affection"] = max(0.0, self.needs["affection"] - 10)
        self.log.append("woke up refreshed, wants attention")

    def _walk_range(self, plat: Platform) -> tuple[float, float]:
        """Safe walk-target range inside a platform. On narrow platforms
        (e.g. the scratching-post top) targets outside the edge caused a
        jitter loop (walk off -> fall -> hop back -> repeat)."""
        lo, hi = plat.x0 + 90, plat.x1 - 90
        if lo > hi:
            lo = hi = (plat.x0 + plat.x1) / 2
        return lo, hi

    def _chase_step(self, body: CatBody, desktop: DesktopState) -> None:
        cx, _cy = desktop.cursor
        offset = 70 * (-1 if cx < body.x else 1)
        plat = desktop.platform_below(cx, desktop.screen_h)
        lo, hi = self._walk_range(plat)
        dest = min(max(cx + offset, lo), hi)
        # hysteresis: don't re-step for small corrections (anti flip-flop)
        if abs(dest - body.x) < 40:
            return
        speed = RUN_SPEED if abs(dest - body.x) > 250 else WALK_SPEED
        body.walk_to(dest, speed)

    def _start_cuddle(self, body: CatBody, desktop: DesktopState) -> None:
        cx, _cy = desktop.cursor
        offset = 55 * (-1 if cx < body.x else 1)
        plat = desktop.platform_below(cx, desktop.screen_h)
        lo, hi = self._walk_range(plat)
        dest = min(max(cx + offset, lo), hi)
        if abs(dest - body.x) > 30:
            body.walk_to(dest, WALK_SPEED)
        self.state = "cuddle_walk"
        self.state_left = 12.0

    # -- sequence continuation -------------------------------------------------

    def _continue(self, dt: float, body: CatBody, desktop: DesktopState) -> None:
        if self.state == "hop_walk":
            if body.target_x is None:
                if self.hop_target is not None:
                    self._try_jump_up(body)
                else:
                    self.state_left = 0.0
        elif self.state == "air_up":
            if not body.airborne:
                # absorb the landing first, then supervise (P26)
                self._land_then = "supervise"
                self.state = "land"
                self.state_left = 0.22
        elif self.state == "land":
            if self.state_left <= 0:
                if getattr(self, "_land_then", "idle") == "supervise":
                    self.state = "supervise"
                    self.state_left = self.rng.uniform(8, 18)
                else:
                    self.state = "idle"
                    self.state_left = 0.0
        elif self.state == "prep_jump":
            if self.state_left <= 0:
                nxt = self._jump_then
                self._jump_then = None
                if nxt is not None and body.jump_to(nxt[0], nxt[1]):
                    self.state = nxt[2]
                    self.state_left = 6.0
                    if nxt[2] == "air_up" and self.hop_target is not None:
                        self.log.append(f"hop onto {self.hop_target.caption!r}")
                else:
                    self.state = "sit"
                    self.state_left = 4.0
                    self.hop_cooldown = HOP_COOLDOWN_S
                    self.hop_target = None
        elif self.state == "supervise":
            if self.state_left <= 0:
                plat = body.platform
                if (plat is not None and plat.caption in FURNITURE_CAPTIONS
                        and self.needs["energy"] < 80 and self.rng.random() < 0.5):
                    # so comfy up here: nap on the furniture (user wish: she
                    # loves sleeping on the post/tree platforms)
                    self.state = "sleep"
                    self.state_left = self.rng.uniform(120, 7200)
                    self.log.append(f"napping on the {plat.caption}")
                else:
                    floor = next(p for p in desktop.platforms if p.floor)
                    hop_x = min(max(body.x + self.rng.uniform(-140, 140),
                                    floor.x0 + 70), floor.x1 - 70)
                    # short crouch, then the drop (resolved in prep_jump)
                    self._jump_then = (hop_x, floor.y, "air_down")
                    self.state = "prep_jump"
                    self.state_left = 0.18
        elif self.state == "air_down":
            if not body.airborne:
                self._land_then = "idle"
                self.state = "land"
                self.state_left = 0.22
        elif self.state == "wander":
            if body.target_x is None:
                self.state_left = 0.0
        elif self.state in ("sleep", "sleep_belly"):
            if body.airborne or self.needs["energy"] >= 99.0:
                self.state_left = 0.0  # the bed vanished or she is rested: wake
            self._sleep_mult = (1.5 if self.bed_x is not None
                                and abs(body.x - self.bed_x) < 60 else 1.0)
        elif self.state == "to_bed":
            if body.target_x is None:
                if self.rng.random() < 0.55:
                    # making biscuits before settling into the cushion
                    self.state = "knead"
                    self.state_left = self.rng.uniform(3.0, 5.0)
                else:
                    self.state = "sleep"
                    self.state_left = self.rng.uniform(120, 7200)
        elif self.state == "knead":
            if self.state_left <= 0:
                self.state = "sleep"
                self.state_left = self.rng.uniform(120, 7200)
        elif self.state == "yawn":
            if self.state_left <= 0:
                self.state = "stretch"
                self.state_left = self.rng.uniform(1.2, 1.8)
        elif self.state == "stretch":
            if self.state_left <= 0:
                self.state = "idle"
                self.state_left = 0.0
        elif self.state == "retch":
            self._fx_t -= dt
            if self._fx_t <= 0:
                self.sounds.append("puke")
                self._fx_t = 0.8
            if self.state_left <= 0:
                # the puddle lands on the floor below (gravity applies)
                floor = next(p for p in desktop.platforms if p.floor)
                px = min(max(body.x, floor.x0 + 40), floor.x1 - 40)
                self.puke_spots.append(px)
                del self.puke_spots[:-3]  # cap the mess
                self.needs["hunger"] = 55.0   # ...and she feels better
                self.needs["affection"] = max(0.0, self.needs["affection"] - 3)
                self.log.append("vomited — the floor needs cleaning")
                self.state = "idle"
                self.state_left = 0.0
        elif self.state == "to_box":
            if body.target_x is None:
                box_plat = next((p for p in desktop.platforms
                                 if p.caption == "Karton"), None)
                if box_plat is not None and body.jump_to(
                        (box_plat.x0 + box_plat.x1) / 2, box_plat.y):
                    self.state = "to_box_air"
                    self.state_left = 4.0
                else:
                    self.state = "idle"
                    self.state_left = 0.0
        elif self.state == "to_box_air":
            if not body.airborne:
                self.state = "box_hide"
                self.state_left = self.rng.uniform(8, 30)
                self.log.append("hiding in the box")
        elif self.state == "box_hide":
            self.gain("play", 1.5 * dt)
            cx, _cy = desktop.cursor
            body.facing = 1 if cx >= body.x else -1
            if (desktop.cursor_active and abs(cx - body.x) < 350
                    and self.rng.random() < 0.5 * dt):
                # AMBUSH: burst out of the box at the 'prey'
                plat = desktop.platform_below(cx, desktop.screen_h)
                tx = min(max(cx, plat.x0 + 90), plat.x1 - 90)
                self._wiggle_then = ("hunt", tx, plat.y)
                self.state = "wiggle"
                self.state_left = 0.5
            elif self.state_left <= 0:
                floor = next(p for p in desktop.platforms if p.floor)
                hop_x = min(max(body.x + self.rng.uniform(-160, 160),
                                floor.x0 + 70), floor.x1 - 70)
                if body.jump_to(hop_x, floor.y):
                    self.state = "air_down"
                    self.state_left = 4.0
                else:
                    self.state = "idle"
        elif self.state == "to_scratch":
            if body.target_x is None:
                body.facing = 1 if (self.scratch_x or 0) > body.x else -1
                self.state = "scratching"
                self.state_left = 4.0
                self._fx_t = 0.0
        elif self.state == "scratching":
            self.gain("play", 5.0 * dt)
            self._fx_t -= dt
            if self._fx_t <= 0:
                self.sounds.append("scratch")
                self._fx_t = 1.0
            if self.state_left <= 0:
                self.add_xp(2.0, "scratching post")
                self.state = "idle"
        elif self.state == "to_grass":
            if body.target_x is None:
                body.facing = 1 if (self.grass_x or 0) > body.x else -1
                self.state = "nibbling"
                self.state_left = 2.5
                self._fx_t = 0.0
        elif self.state == "nibbling":
            self._fx_t -= dt
            if self._fx_t <= 0:
                self.sounds.append("eat")
                self._fx_t = 1.0
            if self.state_left <= 0:
                self.grass_charges = max(0.0, self.grass_charges - 1)
                self.gain("affection", 3)
                self.gain("hunger", 3)
                self.add_xp(3.0, "cat grass")
                # too much grass (or grass on a neglected stomach) comes back
                # up — real cats do exactly this (P25)
                chance = 0.10
                if self._grass_recent > 0:
                    chance += 0.40
                if self._neglect_s > NEGLECT_EAT_S:
                    chance += 0.30
                self._grass_recent = 120.0
                if self.rng.random() < chance:
                    self._start_retch("too much cat grass")
                else:
                    # grass really winds her up: proper frenzy after nibbling
                    self.catnip_high = GRASS_FRENZY_S
                    self.needs["play"] = 100.0
                    self.sounds.append("boing")
                    self.log.append("cat grass FRENZY!")
                    self.state = "idle"
        elif self.state == "to_litter":
            if body.target_x is None:
                if self.litter_fill >= LITTER_CAPACITY:
                    # dirty box: refuses, complains loudly
                    self.state = "litter_beg"
                    self.state_left = 5.0
                    self._fx_t = 0.0
                else:
                    body.facing = 1 if (self.litter_x or 0) > body.x else -1
                    self.state = "littering"
                    self.state_left = 3.0
                    self._fx_t = 0.0
        elif self.state == "littering":
            # quiet squat; the effect lands when the covering is done
            if self.state_left <= 0:
                # a real cat always covers the evidence afterwards
                self.state = "litter_cover"
                self.state_left = 1.6
                self._fx_t = 0.0
        elif self.state == "litter_cover":
            self._fx_t -= dt
            if self._fx_t <= 0:
                self.sounds.append("scratch")  # scraping litter over the pile
                self._fx_t = 0.7
            if self.state_left <= 0:
                self.needs["bladder"] = 100.0
                poop = self.rng.random() < 0.4  # ~2 poop / 3 pee per full box
                self.litter_fill += 1.0 if poop else 0.5
                self.litter_deposits.append("poop" if poop else "pee")
                self.add_xp(0.5, "litter box")
                self.log.append(f"litter used ({self.litter_deposits[-1]}, "
                                f"fill {self.litter_fill:.1f})")
                self.state = "idle"
        elif self.state == "litter_beg":
            self._fx_t -= dt
            if self._fx_t <= 0:
                self.sounds.append("beg")
                self._fx_t = 1.5
            if self.state_left <= 0:
                self.state = "idle"
        elif self.state == "to_wheel":
            if body.target_x is None:
                wheel_plat = next((p for p in desktop.platforms
                                   if p.caption == "Laufrad"), None)
                if wheel_plat is not None and body.jump_to(wheel_plat.x0 + 60,
                                                           wheel_plat.y):
                    self.state = "to_wheel_air"
                    self.state_left = 4.0
                else:
                    self.state = "idle"
                    self.state_left = 0.0
        elif self.state == "to_wheel_air":
            if not body.airborne:
                self.state = "wheel_run"
                self.state_left = self.rng.uniform(20, 240)
                self._fx_t = 0.0
                self.log.append("exercise wheel!")
        elif self.state == "wheel_run":
            self.gain("play", 6.0 * dt)
            self.needs["energy"] = max(0.0, self.needs["energy"] - 2.5 * dt)  # workout!
            self._fx_t -= dt
            if self._fx_t <= 0:
                self.sounds.append("chirp" if self.rng.random() < 0.5 else "boing")
                self._fx_t = 1.5
            if self.state_left <= 0 or self.needs["energy"] < 15 or self.needs["play"] >= 98:
                # hop out — far enough to clear the wheel's platform span,
                # or she lands right back on the track (P46)
                tx = body.x + body.facing * 110
                plat = desktop.platform_below(tx, body.y)
                if body.jump_to(tx, plat.y):
                    self.state = "air_down"
                    self.state_left = 4.0
                    self.add_xp(3.0, "exercise wheel")
                else:
                    self.state = "idle"
        elif self.state == "startle_air":
            if not body.airborne:
                self.state = "alert"
                self.state_left = 2.5
        elif self.state == "alert":
            body.facing = 1 if desktop.cursor[0] > body.x else -1
            if self.state_left <= 0:
                self.state = "idle"
        elif self.state == "greet":
            if body.target_x is None:
                self.state = "headrub"
                self.state_left = 2.5
                self.gain("affection", 4)
                self.add_xp(2.0, "welcome back")
        elif self.state == "annoyed":
            if body.target_x is None:
                self.state = "idle"
                self.state_left = 0.0
        elif self.state == "watch":
            body.facing = 1 if desktop.cursor[0] > body.x else -1
            # excited chattering at fast-moving 'prey' (P26)
            if desktop.cursor_speed > 250 and self.rng.random() < 0.4 * dt:
                self.sounds.append("chirp")
            if self.state_left <= 0:
                self.state = "idle"
        elif self.state == "groom":
            if self.state_left <= 0 and self._chain_groom_sleep:
                # after eating: groom, then (often) sleep — the classic chain
                self._chain_groom_sleep = False
                if self.rng.random() < 0.5:
                    self._start("sleep", body, desktop)
                else:
                    self.state = "idle"
        elif self.state == "ear_fold":
            if self.state_left <= 0:
                self.state = "lick_paw"     # ...then 8 cycles of paw licking
                self.state_left = self._lick_cycles * 0.4  # 2.5 cycles/s
        elif self.state == "lick_paw":
            if self.state_left <= 0:
                self._lick_cycles = 0
                self.state = "idle"
        elif self.state in ("ritual_sit", "ritual_scratch", "ritual_groom"):
            if self.state_left <= 0:
                nxt = self._ritual.pop(0) if self._ritual else None
                if nxt is None:
                    self._ritual = None
                    self._start("sleep", body, desktop)  # ritual complete
                else:
                    self.state = nxt
                    self.state_left = self._ritual_dur(nxt)
        elif self.state == "zoomies":
            self._fx_t -= dt
            if self._fx_t <= 0:
                self._fx_t = self.rng.uniform(0.5, 1.0)
                floor = next(p for p in desktop.platforms if p.floor)
                wins = [p for p in desktop.platforms
                        if not p.floor and p.caption not in FURNITURE_CAPTIONS]
                if self.rng.random() < 0.25 and wins:
                    tgt = self.rng.choice(wins)
                    body.jump_to((tgt.x0 + tgt.x1) / 2, tgt.y)  # sprint up a window
                else:
                    lo, hi = self._walk_range(floor)
                    body.walk_to(self.rng.uniform(lo, hi), RUN_SPEED)
            if self.state_left <= 0:
                body.walk_to((self.litter_x or 500) - 30, RUN_SPEED)
                self.state = "to_litter"
                self.state_left = 20.0
        elif self.state == "to_food":
            if body.target_x is None:
                body.facing = 1 if (self.food_x or 0) > body.x else -1  # face the bowl
                self.state = "eating"
                self.state_left = self.rng.uniform(20, 300)
                self._fx_t = 0.0
        elif self.state == "eating":
            if self.food_fill > 0:
                food = FOODS[self.food_type]
                self.gain("hunger", 1.0 * food["hunger_mult"] * dt)
                if food["thirst"]:
                    self.gain("thirst", food["thirst"] * dt / 5.0)
                self.food_fill = max(0.0, self.food_fill - 1.0 * dt)
                self._fx_t -= dt
                if self._fx_t <= 0:
                    self.sounds.append("eat")
                    self._fx_t = 1.2
                if self.needs["hunger"] >= 99.0 and not self._bored_eat:
                    self.state_left = min(self.state_left, 0.5)  # full: wrap up
                if self._bored_eat:
                    self.state_left = min(self.state_left, 22.0)  # joyless meal
                    if self.needs["hunger"] >= 97.0:
                        self._overate_s += dt  # munching past full: this ends badly
            else:
                # empty bowl: a few pitiful meows, then she gives up for a
                # while instead of camping there for minutes (P24)
                self.state_left = min(self.state_left, 3.5)
                self._fx_t -= dt
                if self._fx_t <= 0:
                    self.sounds.append("beg")
                    self._fx_t = 1.8
            if self.state_left <= 0:
                if self.food_fill <= 0:
                    self._food_beg_cd = 60.0
                food = FOODS[self.food_type]
                if self.food_fill > 0:
                    self.gain("hunger", 10)
                    self.gain("affection", food["affection"])
                    self.add_xp(2.0, "meal")
                    if self.food_type == "catnip" and self.catnip_high <= 0:
                        self.catnip_high = CATNIP_HIGH_S
                        self.needs["play"] = 100.0
                        self.add_xp(8.0, "catnip!")
                        self.sounds.append("boing")
                        self.log.append("CATNIP FRENZY!")
                if self.treat_pending:
                    self.treat_pending = False
                    self.gain("affection", 6)
                    self.add_xp(5.0, "treat")
                if self._overate_s > 5.0:
                    # kept munching past full from sheer boredom — and now
                    self._bored_eat = False
                    self._start_retch("boredom eating")
                elif self.rng.random() < 0.6:
                    # after eating: groom, then (often) sleep
                    self.state = "groom"
                    self.state_left = self.rng.uniform(4, 10)
                    self._chain_groom_sleep = True
                else:
                    self.state = "idle"
        elif self.state == "to_water":
            if body.target_x is None:
                body.facing = 1 if (self.water_x or 0) > body.x else -1  # face the bowl
                self.state = "drinking"
                self.state_left = self.rng.uniform(20, 120)
                self._fx_t = 0.0
        elif self.state == "drinking":
            # the fountain never runs dry (P25): nothing to drain or beg for
            self.gain("thirst", 1.5 * dt)
            self._fx_t -= dt
            if self._fx_t <= 0:
                self.sounds.append("drink")
                self._fx_t = 1.4
            if self.needs["thirst"] >= 99.0:
                self.state_left = min(self.state_left, 0.5)  # had enough
            if self.state_left <= 0:
                self.gain("thirst", 10)
                self.state = "idle"
        elif self.state == "to_toy":
            toy = self._play_toy_target
            if toy is None or (self.toys is not None
                               and toy not in self.toys.toys):
                # gone mid-approach ('Clear toys'): drop it, don't pounce air
                self._play_toy_target = None
                self.state = "idle"
                self.state_left = 0.0
            elif body.target_x is None:
                if toy.kind == "ball":
                    # batting happens via proximity (ToyManager); watch it roll
                    self.state = "toy_watch"
                    self.state_left = self.rng.uniform(10, 1200)
                    self._fx_t = 0.0
                else:
                    plat = desktop.platform_below(toy.x, toy.y)
                    # the butt wiggle telegraphs the pounce (classic cat)
                    self._wiggle_then = ("toy", toy.x, plat.y)
                    self.state = "wiggle"
                    self.state_left = 0.6
        elif self.state == "wiggle":
            if self._wiggle_then is not None:
                body.facing = 1 if self._wiggle_then[1] >= body.x else -1
            if self.state_left <= 0:
                nxt = self._wiggle_then
                self._wiggle_then = None
                if nxt is None:
                    self.state = "idle"
                    self.state_left = 0.0
                elif body.jump_to(nxt[1], nxt[2]):
                    self.state = ("hunt_pounce" if nxt[0] == "hunt"
                                  else "laser_pounce" if nxt[0] == "laser"
                                  else "pounce_toy")
                    self.state_left = 4.0
                else:
                    self.state = "idle" if nxt[0] == "hunt" else "sit"
                    self.state_left = 0.0 if nxt[0] == "hunt" else 2.0
        elif self.state == "toy_watch":
            if not self.toys or not self.toys.toys:
                self.state = "idle"
                self.state_left = 0.0
            else:
                # a real cat follows the ball it batted (bat -> chase -> bat)
                self._fx_t -= dt
                if self._fx_t <= 0:
                    self._fx_t = 1.0
                    t = self.toys.nearest(body.x, body.y)
                    if t is not None and abs(t.x - body.x) > 80:
                        off = 45 * (-1 if t.x < body.x else 1)
                        spd = RUN_SPEED if abs(t.x - body.x) > 250 else WALK_SPEED
                        body.walk_to(t.x + off, spd)
            if self.state_left <= 0 or self.needs["play"] >= 95:
                body.stop()
                self.state = "idle"
        elif self.state == "pounce_toy":
            if not body.airborne:
                toy = self._play_toy_target
                self._play_toy_target = None
                caught = (toy is not None
                          and (self.toys is None or toy in self.toys.toys)
                          and ((toy.x - body.x) ** 2 + (toy.y - body.y) ** 2) ** 0.5 < 70)
                if caught:
                    self.gain("play", 14)
                    self.add_xp(3.0, f"caught {toy.kind}")
                    self.sounds.append("boing")
                    self.log.append(f"caught the {toy.kind}!")
                    if toy.kind == "plush" and self.rng.random() < 0.4:
                        toy.x = min(max(body.x + self.rng.uniform(-400, 400),
                                        desktop.floor_x0 + 30),
                                    desktop.floor_x1 - 30)
                        toy.vy = -250  # 'escapes' with a hop
                        self.log.append("the plush mouse 'escaped'!")
                    elif toy.kind == "string":
                        toy.interactions += 1
                        toy.vy -= 350
                        toy.vx += self.rng.uniform(-150, 150)
                    self.state = "enjoy"
                    self.state_left = 2.0
                else:
                    self.state = "sit"
                    self.state_left = 1.5
        elif self.state == "chase":
            self.gain("play", 1.2 * dt)
            if body.target_x is None and self.state_left > 0:
                self._chase_step(body, desktop)
            if not desktop.cursor_active or self.state_left <= 0:
                body.stop()
                self.state_left = 0.0
        elif self.state == "follow":
            # padding after the human at a polite 130-170 px distance (P26)
            cx, _cy = desktop.cursor
            dist = cx - body.x
            self._fx_t -= dt
            if self._fx_t <= 0:
                self._fx_t = 0.7
                if abs(dist) > 170:
                    plat = desktop.platform_below(cx, desktop.screen_h)
                    lo, hi = self._walk_range(plat)
                    dest = min(max(cx - (1 if dist > 0 else -1) * 150, lo), hi)
                    body.walk_to(dest, WALK_SPEED)
                elif abs(dist) < 110:
                    body.stop()  # close enough: just watch them
            if body.target_x is None:
                body.facing = 1 if dist > 0 else -1
            if not desktop.cursor_active or self.state_left <= 0:
                body.stop()
                self.state = "sit"
                self.state_left = 2.0
        elif self.state == "laser_chase":
            laser = self._laser()
            if laser is None or not desktop.cursor_active:
                body.stop()
                self.state = "idle"
                self.state_left = 0.0
            elif self.needs["energy"] < 25:
                # out of steam: she gives up on the uncatchable dot (P34)
                body.stop()
                self.state = "sit"
                self.state_left = 3.0
                self._laser_cd = 60.0
                self.log.append("too tired for the laser")
            else:
                # chasing the dot is a workout
                self.needs["energy"] = max(0.0, self.needs["energy"] - 2.0 * dt)
                self.gain("play", 3.0 * dt)
                dist = abs(laser.x - body.x)
                body.facing = 1 if laser.x >= body.x else -1
                if body.target_x is None:
                    plat = desktop.platform_below(laser.x, desktop.screen_h)
                    if dist < 55:
                        # in striking range: wiggle, then pounce on the dot
                        tx = min(max(laser.x, plat.x0 + 90), plat.x1 - 90)
                        self._wiggle_then = ("laser", tx, plat.y)
                        self.state = "wiggle"
                        self.state_left = 0.5
                    else:
                        lo, hi = self._walk_range(plat)
                        off = 70 * (-1 if laser.x < body.x else 1)
                        spd = RUN_SPEED if dist > 150 else WALK_SPEED
                        body.walk_to(min(max(laser.x + off, lo), hi), spd)
                if self.state_left <= 0:
                    body.stop()
                    self.state = "idle"
                    self.state_left = 0.0
                    self._laser_cd = 45.0   # she needs a break from the dot
        elif self.state == "laser_pounce":
            if not body.airborne:
                laser = self._laser()
                caught = laser is not None and abs(laser.x - body.x) < 60
                if caught:
                    # GOT IT — well, almost: the dot blinks out and reappears
                    laser.escape()
                    self.gain("play", 10)
                    self.gain("affection", 1)
                    self.add_xp(2.0, "caught the dot")
                    self.sounds.append("boing")
                    self.log.append("caught the laser dot!")
                self.state = "laser_chase"
                self.state_left = self.rng.uniform(8, 15)
        elif self.state == "to_gift":
            if self._gift_toy is None or self._gift_toy not in self.toys.toys:
                self._gift_toy = None
                self.state = "idle"
                self.state_left = 0.0
            elif body.target_x is None:
                # picked it up: the plush rides at her mouth now
                self._gift_toy.carried = True
                self.state = "carry_gift"
                self.state_left = 25.0
                self._fx_t = 0.0
        elif self.state == "carry_gift":
            toy = self._gift_toy
            if toy is None or not getattr(toy, "carried", False) \
                    or toy not in self.toys.toys:
                self._gift_toy = None
                self.state = "idle"
                self.state_left = 0.0
            else:
                cx, _cy = desktop.cursor
                self._fx_t -= dt
                if self._fx_t <= 0:
                    self._fx_t = 1.5
                    plat = desktop.platform_below(cx, desktop.screen_h)
                    lo, hi = self._walk_range(plat)
                    offset = 60 * (-1 if cx < body.x else 1)
                    body.walk_to(min(max(cx + offset, lo), hi), WALK_SPEED)
                if body.target_x is None and abs(cx - body.x) < 100:
                    # presented! drops it at your feet, so proud
                    toy.carried = False
                    toy.vy = -120.0
                    toy.vx = body.facing * 60.0
                    self._gift_toy = None
                    self.sounds.append(self._meow())
                    self.gain("affection", 6)
                    self.add_xp(6.0, "gift for you")
                    self.log.append("brought you a gift!")
                    self.state = "enjoy"
                    self.state_left = 2.5
                elif self.state_left <= 0:
                    toy.carried = False
                    self._gift_toy = None
                    self.state = "idle"
        elif self.state == "hunt_stalk":
            if self.hunt_target is not None:
                tx, ty = self.hunt_target
                body.facing = 1 if tx > body.x else -1
                dist = abs(tx - body.x)
                if not desktop.cursor_active or self.state_left <= 0:
                    self.state = "idle"
                    self.state_left = 0.0
                elif dist < 260 or desktop.cursor_speed < 150:
                    plat = desktop.platform_below(tx, desktop.screen_h)
                    if plat.floor:
                        tx = min(max(tx, plat.x0 + 90), plat.x1 - 90)
                    # butt wiggle first, then the pounce (resolved in "wiggle")
                    self._wiggle_then = ("hunt", tx, plat.y)
                    self.state = "wiggle"
                    self.state_left = 0.7
        elif self.state == "hunt_pounce":
            if not body.airborne:
                cx, _cy = desktop.cursor
                if abs(cx - body.x) < CATCH_RANGE:
                    self.gain("play", 18)
                    self.gain("affection", 4)
                    self.add_xp(5.0, "catch")
                    self.log.append("caught the 'prey'!")
                    self.state = "enjoy"
                    self.state_left = 2.5
                else:
                    self.state = "sit"
                    self.state_left = 1.5
        elif self.state == "cuddle_walk":
            if body.target_x is None:
                cx, _cy = desktop.cursor
                if abs(cx - body.x) < 140:
                    self.state = "cuddle_rub"
                    self.state_left = self.rng.uniform(2.5, 4.0)
                else:
                    self.state_left = 0.0
                    self.state = "idle"
        elif self.state == "cuddle_rub":
            self.gain("affection", 2.0 * dt)
            if self.state_left <= 0:
                if self.attachment_level >= 2 and self.rng.random() < 0.6:
                    self.state = "tailwrap"
                    self.state_left = 3.5
                else:
                    self.state = "idle"
                    self.state_left = 0.0
        elif self.state == "tailwrap":
            self.gain("affection", 2.5 * dt)
            if self.state_left <= 0:
                self.state = "idle"

    def _fmt_needs(self) -> str:
        return " ".join(f"{k}={v:.0f}" for k, v in self.needs.items())
