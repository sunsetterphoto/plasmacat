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
from collections import deque

from plasmacat.bridge.desktop import DesktopState, Platform
from plasmacat.cat.household import Household
from plasmacat.cat.physics import CatBody, RUN_SPEED, WALK_SPEED

from plasmacat.cat.needs import (  # noqa: F401  (re-exported)
    NEED_DECAY,
    LITTER_CAPACITY,
    GRASS_FRENZY_S,
    FURNITURE_CAPTIONS,
    LEVEL_BACK_CAPTIONS,
    NEGLECT_EAT_S,
    LEVEL_DWELL_S,
    KEY_HOLD_S,
    AGE_MAX,
    AGE_STAGE_S,
    CARE_EMPTY_S,
    YOUNG_BAND,
    offline_aging,
    SLEEP_REGEN,
    HOP_COOLDOWN_S,
    HUNT_COOLDOWN_S,
    CATCH_RANGE,
    ATTACHMENT_LEVELS,
    FOODS,
    CATNIP_HIGH_S,
    circadian,
)
from plasmacat.cat.states import (  # noqa: F401
    BACK_COMMITTED,
    FRONT_COMMITTED,
    SOCIAL_CALM,
    HUNT_IMMUNE,
    RETURN_IMMUNE,
    STARTLE_IMMUNE,
)
from plasmacat.cat.behaviors import REGISTRY


class Brain:
    def __init__(self, rng: random.Random | None = None,
                 household: Household | None = None) -> None:
        self.rng = rng or random.Random()
        # the shared home (P47): bowls, furniture and consumables live on the
        # Household; this brain's same-named attributes forward there (see the
        # property wiring at the bottom of the class). A brain constructed
        # without one gets a private household (tests, single-cat runs).
        self.household = household or Household(private=True)
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
        self.log: deque[str] = deque(maxlen=200)  # debug trail, bounded
        # P47 lifecycle: age in growth stages (float, 0..15) and the care
        # reservoir (0..1) that interaction refills and time drains
        self.age = 6.0                      # adult default; kittens start at 0
        self.care = 0.5
        # P5: treat flag, sound intent queue, thought bubble
        self.treat_pending = False
        self.toys = None                    # ToyManager, set by the overlay
        self._play_toy_target = None        # Toy being approached/pounced
        # P8d: catnip
        self.catnip_high = 0.0              # seconds of hyper mode remaining
        self._sleep_mult = 1.0              # 1.5 while sleeping in the cat bed
        # P15: rituals & chains
        self._ritual: list[str] | None = None   # pre-sleep ritual steps left
        self._ritual_done = False
        self._chain_groom_sleep = False     # eating -> groom -> sleep chain
        self._post_sleep = 0.0              # seconds of extra attention-seeking
        self._was_sleeping = False
        self._lick_cycles = 0               # face-wash: paw licks remaining (P20)
        # P11: exercise wheel
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
        # P26: personality + movement polish
        self.fav_toy = "ball" if self.rng.random() < 0.5 else "plush"
        self._circ = (1.0, 1.0)          # circadian (sleep, activity) multipliers
        self._jump_then: tuple[float, float, str] | None = None  # after prep
        self._gift_toy = None            # plush being carried to the human
        self._land_then = "idle"         # state after landing (supervise drop)
        self._lap_t = 0.0                # drinking: time to the next lap sound
        self._toy_hops = 0               # level changes left while fetching a toy
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
        # P48: cat-cat social life. `peers` are the other cats in the home as
        # (body, brain) tuples, wired by the overlay whenever cats are added.
        self.peers: list[tuple[CatBody, "Brain"]] = []
        self._social_cd = self.rng.uniform(15, 60)  # first contact comes early
        self._peer: tuple[CatBody, "Brain"] | None = None
        self._peer_intent = "cuddle"
        self._chase_t = 0.0

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
        # a shared home is ticked once per frame by the overlay; a private
        # one (tests, a lone brain) advances with its only cat
        if self.household.private:
            self.household.tick(dt)

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

    # -- lifecycle (P47) -------------------------------------------------------

    @property
    def stage(self) -> int:
        """Growth stage 0..15: drives sprite proportions and behavior."""
        return min(max(int(self.age), 0), int(AGE_MAX))

    @property
    def life_stage(self) -> str:
        s = self.stage
        if s <= 2:
            return "kitten"
        if s <= 5:
            return "junior"
        if s <= 10:
            return "adult"
        if s <= 13:
            return "senior"
        return "old"

    @property
    def speed_mult(self) -> float:
        """Kittens toddle, seniors shuffle: walk/run speed by stage."""
        s = self.stage
        if s <= 5:
            return 0.78 + 0.044 * s      # 0.78 -> 1.0
        if s <= 10:
            return 1.0
        return 1.0 - 0.06 * (s - 10)     # 0.70 at 15

    def _aging_rate(self) -> float:
        """Growth stages per second. Food + sleep cycles set the base (a
        well-fed, well-rested cat ages slowest); interaction stretches the
        young-adult band; neglect speeds the whole clock up."""
        health = (self.needs["hunger"] + self.needs["energy"]) / 200.0
        rate = (1.55 - 0.85 * health) / AGE_STAGE_S
        if self.care < 0.25:
            rate *= 1.4                  # a neglected cat ages faster
        if YOUNG_BAND[0] <= self.age <= YOUNG_BAND[1]:
            rate *= 1.0 - 0.55 * self.care  # loved cats stay young longer
        return rate

    def _care(self, amount: float) -> None:
        """Refill the attention reservoir (called by every interaction)."""
        self.care = min(1.0, self.care + amount)

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
        self._care(0.10)
        if self.mood < 30 and self.rng.random() < 0.5:
            # grumpy cat has no patience: walks off (no affection gained)
            plat = body.platform
            if plat is not None and self.state not in ("sleep", "eating", "drinking"):
                # _walk_range: on narrow furniture tops (e.g. the 57 px post
                # top) the old x0+90/x1-90 clamp inverts and points OFF the
                # platform — she would walk off the edge and fall
                lo, hi = self._walk_range(plat)
                dest = min(max(body.x - body.facing * 180, lo), hi)
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
        self._care(0.08)
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
            self._care(0.03)

    def clear_toy_state(self) -> None:
        """'Clear toys' (tray): drop every behavior that targets a toy, so she
        doesn't pounce at air or 'catch' a deleted toy (P42)."""
        self._play_toy_target = None
        self._gift_toy = None
        if self._wiggle_then is not None and self._wiggle_then[0] in ("toy", "laser"):
            self._wiggle_then = None  # the wiggle branch lands on idle by itself
        if self.state in ("to_toy", "to_toy_air", "to_toy_edge", "pounce_toy", "toy_watch", "to_gift",
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
        if self.hunt_cooldown > 0 or body.airborne or not desktop.cursor_active:
            return
        # never interrupt private business or committed sequences (P24):
        # a cat on the toilet / in the wheel / mid-meal does not pounce away
        if self.state in HUNT_IMMUNE:
            return
        if self.needs["play"] < 15:
            return
        self._force_level_ready()  # the human teases: she may come forward now
        self._care(0.04)
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
        if self.state in STARTLE_IMMUNE:
            return
        self._startle_cd = 10.0
        cx, _cy = desktop.cursor
        direction = -1.0 if cx > body.x else 1.0
        plat = body.platform or desktop.platform_below(body.x, body.y)
        # _walk_range: narrow furniture tops — see the grumpy walk-off above
        lo, hi = self._walk_range(plat)
        tx = min(max(body.x + direction * 140, lo), hi)
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
        if self.state in RETURN_IMMUNE:
            return
        cx, _cy = desktop.cursor
        offset = 55 * (-1 if cx < body.x else 1)
        plat = desktop.floor_under(cx)
        dest = min(max(cx + offset, plat.x0 + 90), plat.x1 - 90)
        body.walk_to(dest, RUN_SPEED)
        self._force_level_ready()  # the human is back: greet them up front
        self.state = "greet"
        self.state_left = 15.0
        self.sounds.append(self._meow())
        self.log.append("greeting the human!")

    # -- behavior selection -------------------------------------------------

    def _score(self, name: str, desktop: DesktopState,
               body: CatBody | None = None) -> float:
        n = self.needs
        _sleep_m, _act_m = self._circ
        stage = self.stage
        # P47 life-stage temperament: kittens are hyper and nap a lot,
        # seniors slow down and lose interest in workouts
        if name == "sleep":
            stage_m = 1.25 if stage <= 2 else \
                (1.0 + 0.07 * (stage - 10) if stage > 10 else 1.0)
            return 3.0 * (1 - n["energy"] / 100.0) ** 2 * _sleep_m * stage_m
        if name == "beg":
            lack = max(1 - n["hunger"] / 100.0, 1 - n["thirst"] / 100.0)
            return 2.5 * lack ** 2 if lack > 0.45 else 0.0
        if name == "hop":
            has_windows = any(not p.floor for p in desktop.platforms)
            if not has_windows or self.hop_cooldown > 0:
                return 0.0
            if stage >= 12:
                return 0.0  # too old for window acrobatics
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
            stage_m = 1.3 if stage <= 2 else (0.55 if stage >= 11 else 1.0)
            return (0.45 + 0.45 * (1 - n["play"] / 100.0)) * _act_m * stage_m
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
            if stage <= 2 or stage >= 11:
                return 0.0  # too small / too old for the exercise wheel
            return (0.32 + 0.40 * (1 - n["play"] / 100.0)) * _act_m
        if name == "chase":
            if not desktop.cursor_active:
                return 0.0
            s = 0.30 + 0.35 * (1 - n["play"] / 100.0)
            stage_m = 1.2 if stage <= 2 else (0.5 if stage >= 11 else 1.0)
            return (s + (0.3 if self.catnip_high > 0 else 0.0)) * _act_m * stage_m
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
            if stage >= 12:
                return 0.0  # the old lady has seen enough dots
            return 0.85
        if name == "wander":
            if self.wander_cooldown > 0:
                return 0.0
            stage_m = 1.15 if stage <= 2 else (0.6 if stage >= 11 else 1.0)
            return (0.30 + 0.15 * (n["play"] / 100.0)) * stage_m
        if name == "social":
            # P48: hanging out with the other cat — playful kittens most,
            # dignified seniors least
            if body is None or self._social_cd > 0 \
                    or self._social_peer(body) is None:
                return 0.0
            s = (0.35 + 0.25 * (1 - n["play"] / 100.0)
                 + 0.15 * (1 - n["affection"] / 100.0))
            return s * (1.4 if stage <= 2 else 0.6 if stage >= 11 else 1.0)
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
                 "laser_chase", "social"]
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
        scored = [(self._score(n, desktop, body) * self.rng.uniform(0.8, 1.2), n)
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
        self._social_cd = max(0.0, self._social_cd - dt)  # P48
        self._neglect_s += dt  # reset by any user attention (stroke/rub/treat)
        # P47 lifecycle: the care reservoir drains with time; the aging clock
        # advances at the care/health-dependent rate
        self.care = max(0.0, self.care - dt / CARE_EMPTY_S)
        self.age = min(AGE_MAX, self.age + self._aging_rate() * dt)
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
                          "sleep", "sleep_belly", "cuddle"):
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
        elif self.state in ("enjoy", "headrub", "cuddle_rub", "tailwrap", "cuddle"):
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
        self._care(0.20)
        self.treat_pending = True
        self.log.append("treat offered!")

    # -- food shop / refills ---------------------------------------------------

    def buy_food(self, food: str) -> None:
        """Shop purchase: swaps the food type and refills the bowl."""
        if food not in FOODS:
            return
        self.food_type = food
        self.food_fill = 100.0
        self._care(0.10)
        self.sounds.append("chime")
        self.log.append(f"bought {FOODS[food]['label']}")

    def refill_food(self) -> None:
        self.food_fill = 100.0
        self._care(0.12)
        self.sounds.append("eat")
        self.log.append("food refilled")

    def refill_water(self) -> None:
        self.water_fill = 100.0
        self.sounds.append("bubble")
        self.log.append("water refilled")

    def clean_litter(self) -> None:
        self.litter_fill = 0.0
        self.litter_deposits.clear()
        self._care(0.08)
        self.sounds.append("scratch")
        self.log.append("litter box cleaned")

    def clean_puke(self) -> None:
        """Tray cleanup: removes all vomit puddles."""
        if self.puke_spots:
            self.puke_spots.clear()
            self._care(0.06)
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
            # P48: cats mostly sleep in similar spots — a peer already
            # snoozing on the same floor is the best place in the house
            if plat is not None and plat.floor and self.rng.random() < 0.5:
                sleepy = [(pb, pr) for pb, pr in self.peers
                          if pr.state in ("sleep", "sleep_belly", "cuddle")
                          and pb.platform is plat and abs(pb.x - body.x) > 40]
                if sleepy:
                    pb, pr = min(sleepy, key=lambda p: abs(p[0].x - body.x))
                    lo, hi = self._walk_range(plat)
                    side = self.rng.choice((-1.0, 1.0))
                    dest = min(max(pb.x + side * self.rng.uniform(60, 110), lo), hi)
                    if abs(dest - body.x) > 30:
                        body.walk_to(dest, WALK_SPEED)
                        self.state = "to_sleep_peer"
                        self.state_left = 30.0
                        self._peer = (pb, pr)
                        return
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
            if self.litter_fill < LITTER_CAPACITY and self.needs["bladder"] < 30 \
                    and self.stage < 11:
                # pre-poop zoomies: sprint across the desktop like crazy first
                # (seniors skip the theatrics and just go)
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
                # the laser dot is its own game (laser_chase), never a "toy"
                playable = [t for t in self.toys.toys if t.kind != "laser"]
                fav = [t for t in playable if t.kind == self.fav_toy]
                pool = fav or playable
                toy = min(pool, key=lambda t: (t.x - body.x) ** 2
                          + (t.y - body.y) ** 2) if pool else None
            if toy is None:
                self.state = "sit"
                self.state_left = 3.0
            else:
                self._play_toy_target = toy
                self._approach_toy(body, desktop, toy)
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
            toy = next((t for t in self.toys.toys if t.kind == "plush"
                        and not t.carried and not self._claimed_by_other(t)), None)
            if toy is None:
                self.state = "sit"
                self.state_left = 2.0
            else:
                toy.claim = self
                self._gift_toy = toy
                offset = 45 * (-1 if toy.x < body.x else 1)
                body.walk_to(toy.x + offset, WALK_SPEED)
                self.state = "to_gift"
                self.state_left = 20.0
        elif name == "cuddle":
            self._start_cuddle(body, desktop)
        elif name == "social":
            self._start_social(body, desktop)
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

    def _floor_target(self, desktop: DesktopState, anchor_x: float,
                      target_x: float) -> float:
        """target_x clamped into the safe walk range of the floor under
        anchor_x (the cat's own screen, P38)."""
        lo, hi = self._walk_range(desktop.floor_under(anchor_x))
        return min(max(target_x, lo), hi)

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
        dest = self._floor_target(desktop, cx, cx + offset)
        # hysteresis: don't re-step for small corrections (anti flip-flop)
        if abs(dest - body.x) < 40:
            return
        speed = RUN_SPEED if abs(dest - body.x) > 250 else WALK_SPEED
        body.walk_to(dest, speed)

    def _start_cuddle(self, body: CatBody, desktop: DesktopState) -> None:
        cx, _cy = desktop.cursor
        offset = 55 * (-1 if cx < body.x else 1)
        dest = self._floor_target(desktop, cx, cx + offset)
        if abs(dest - body.x) > 30:
            body.walk_to(dest, WALK_SPEED)
        self.state = "cuddle_walk"
        self.state_left = 12.0

    # -- cat-cat social life (P48) ----------------------------------------------

    def _social_peer(self, body: CatBody) -> tuple[CatBody, "Brain"] | None:
        """The nearest other cat that is up for company: on the SAME floor
        (social walks don't cross platforms), in a calm state, and not being
        steered by the human right now."""
        plat = body.platform
        if plat is None or not plat.floor:
            return None
        best: tuple[CatBody, "Brain"] | None = None
        best_d = 1e9
        for pb, pr in self.peers:
            if pr.user_control or pr.state not in SOCIAL_CALM:
                continue
            if pb.platform is not plat:
                continue
            d = abs(pb.x - body.x)
            if d < best_d:
                best, best_d = (pb, pr), d
        return best

    def _start_social(self, body: CatBody, desktop: DesktopState) -> None:
        """Pick a peer and an intent — cuddle, chase, or (rarely) a spat —
        and walk over. The paired states are entered on arrival."""
        peer = self._social_peer(body)
        if peer is None:
            self.state = "sit"
            self.state_left = 3.0
            return
        fight_p = 0.12 if self.mood < 45 else 0.03
        chase_p = 0.55 if self.stage <= 2 else 0.35
        r = self.rng.random()
        if r < fight_p:
            intent = "fight"
        elif r < fight_p + chase_p:
            intent = "chase"
        else:
            intent = "cuddle"
        if self.stage >= 11 and intent == "chase" and self.rng.random() < 0.6:
            intent = "cuddle"  # the old lady prefers a quiet snuggle
        pb, _pr = peer
        self._peer = peer
        self._peer_intent = intent
        self._chase_t = 0.0
        offset = 40 * (-1 if pb.x < body.x else 1)
        body.walk_to(pb.x + offset, RUN_SPEED if intent == "chase" else WALK_SPEED)
        self.state = "to_peer"
        self.state_left = 15.0
        self.log.append(f"seeking the other cat ({intent})")

    # -- sequence continuation -------------------------------------------------

    def _continue(self, dt: float, body: CatBody, desktop: DesktopState) -> None:
        """Advance the current state (handlers live in cat/behaviors)."""
        handler = REGISTRY.get(self.state)
        if handler is not None:
            handler(self, dt, body, desktop)

    TOY_LEVEL_TOLERANCE = 60.0   # px between her feet and a toy "on her level"

    def toy_on_my_level(self, body: CatBody, toy) -> bool:
        """Resting toys must lie on her level; a string dangles from the
        cursor and is played from wherever she stands below it."""
        if toy.kind in ("string", "laser"):
            return True
        return abs(toy.y - body.y) <= self.TOY_LEVEL_TOLERANCE

    def _approach_toy(self, body: CatBody, desktop: DesktopState, toy,
                      hops_left: int = 2) -> None:
        """Go to a toy: walk if it lies on her level, otherwise jump to the
        toy's level first. She never 'plays' with a toy from another level
        (a plush on the floor while she sits up on a window)."""
        offset = 45 * (-1 if toy.x < body.x else 1)
        if self.toy_on_my_level(body, toy):
            plat = body.platform or desktop.platform_below(body.x, body.y)
            lo, hi = self._walk_range(plat)
            body.walk_to(min(max(toy.x + offset, lo), hi), RUN_SPEED)
            self.state = "to_toy"
            self.state_left = 15.0
            return
        if hops_left <= 0:
            self._play_toy_target = None
            self.state = "sit"
            self.state_left = 2.0
            return
        plat = desktop.platform_below(toy.x, toy.y - 5)
        tx = min(max(toy.x + offset, plat.x0 + 20), plat.x1 - 20)
        cur = body.platform
        if cur is not None and plat.y > cur.y and cur.x0 - 30 < tx < cur.x1 + 30:
            # the toy lies below her own perch: she cannot drop through it,
            # so she jumps off past the nearer edge and walks over below
            left, right = cur.x0 - 60, cur.x1 + 60
            options = [x for x in (left, right) if plat.x0 + 20 <= x <= plat.x1 - 20]
            if options:
                tx = min(options, key=lambda x: abs(x - toy.x))
        if cur is not None and abs(tx - body.x) > 220:
            # too far for one jump: walk to the near end of her perch first
            edge = min(max(tx, cur.x0 + 15), cur.x1 - 15)
            if abs(edge - body.x) > 20:
                self._toy_hops = hops_left
                body.walk_to(edge, RUN_SPEED)
                self.state = "to_toy_edge"
                self.state_left = 12.0
                return
        self._toy_hops = hops_left - 1
        self._jump_then = (tx, plat.y, "to_toy_air")
        self.state = "prep_jump"       # short crouch, then the jump
        self.state_left = 0.18

    def _claimed_by_other(self, toy) -> bool:
        """Another cat is already fetching this plush as her gift."""
        other = getattr(toy, "claim", None)
        return other is not None and other is not self and other._gift_toy is toy

    def _fmt_needs(self) -> str:
        return " ".join(f"{k}={v:.0f}" for k, v in self.needs.items())


def _household_forward(name: str):
    """Build a property that forwards a brain attribute to the Household
    (P47): existing code keeps reading/writing brain.food_x & friends, but
    every cat in the home shares the same underlying values."""
    return property(lambda self: getattr(self.household, name),
                    lambda self, value: setattr(self.household, name, value))


for _forwarded in ("food_x", "water_x", "food_type", "food_fill", "water_fill",
                   "scratch_x", "bed_x", "grass_x", "grass_charges",
                   "litter_x", "litter_fill", "litter_deposits",
                   "tree_x", "wheel_x", "shelves", "box_x", "puke_spots"):
    setattr(Brain, _forwarded, _household_forward(_forwarded))
del _forwarded
