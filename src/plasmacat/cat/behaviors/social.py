"""Cat-to-cat life: approach, cuddle, spats, chases, co-sleeping.

State handlers moved verbatim out of Brain._continue: each takes the
brain as `self` so the bodies read exactly like the methods they were.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from plasmacat.cat.physics import RUN_SPEED, WALK_SPEED
from plasmacat.cat.states import SOCIAL_CALM

if TYPE_CHECKING:
    from plasmacat.bridge.desktop import DesktopState
    from plasmacat.cat.brain import Brain
    from plasmacat.cat.physics import CatBody


def to_peer(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    peer = self._peer
    if peer is None or peer[1].state not in SOCIAL_CALM + ("to_peer",):
        # she wandered off or got busy: no hard feelings
        self._peer = None
        self.state = "sit"
        self.state_left = 2.0
    elif body.target_x is None:
        pb, pr = peer
        intent = self._peer_intent
        dur = self.rng.uniform(6, 10)
        self._social_cd = self.rng.uniform(90, 200)
        pr._social_cd = max(pr._social_cd, self.rng.uniform(60, 150))
        if intent == "cuddle":
            body.stop()
            pb.stop()
            body.facing = 1 if pb.x >= body.x else -1
            pb.facing = -body.facing
            self.state = "cuddle"
            self.state_left = dur
            pr.state = "cuddle"
            pr.state_left = dur + 0.5
            self.add_xp(1.5, "cuddling")
            pr.add_xp(1.5, "cuddling")
            self.sounds.append("purr")
            self.log.append("cuddling with the other cat")
            self._peer = None
        elif intent == "fight":
            body.stop()
            pb.stop()
            body.facing = 1 if pb.x >= body.x else -1
            pb.facing = -body.facing
            self.state = "fight"
            self.state_left = self.rng.uniform(2.5, 4.0)
            pr.state = "fight"
            pr.state_left = self.state_left + self.rng.uniform(-0.5, 0.5)
            self._fx_t = 0.0
            pr._fx_t = 0.4
            self.sounds.append("meow2")
            self.log.append("a proper cat spat!")
            self._peer = None
        else:  # chase — she runs, I follow
            self.state = "chase_peer"
            self.state_left = dur
            self._peer = (pb, pr)
            self._chase_t = 0.0
            pr.state = "flee_peer"
            pr.state_left = dur
            pr._peer = (body, self)
            self.sounds.append("chirp")
            self.log.append("chasing the other cat!")
    elif self.state_left <= 0:
        self._peer = None
        self.state = "sit"
        self.state_left = 2.0


def cuddle(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    self.gain("affection", 1.5 * dt)
    if self.state_left <= 0:
        self.state = "idle"
        self.state_left = 0.0


def fight(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    self._fx_t -= dt
    if self._fx_t <= 0:
        self.sounds.append("meow2" if self.rng.random() < 0.6 else "mew")
        self._fx_t = self.rng.uniform(0.6, 1.3)
    if self.state_left <= 0:
        # every spat ends with one stalking off offended
        if self.rng.random() < 0.5:
            plat = body.platform
            if plat is not None:
                lo, hi = self._walk_range(plat)
                body.walk_to(min(max(body.x - body.facing * 180, lo), hi),
                             WALK_SPEED)
            self.state = "annoyed"
            self.state_left = 4.0
        else:
            self.state = "idle"
            self.state_left = 0.0


def chase_peer(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    peer = self._peer
    if peer is None or peer[1].state != "flee_peer":
        self._peer = None
        self.state = "idle"
        self.state_left = 0.0
    else:
        pb, pr = peer
        self._chase_t += dt
        self.gain("play", 2.0 * dt)
        plat = body.platform
        if body.target_x is None and plat is not None:
            lo, hi = self._walk_range(plat)
            body.walk_to(min(max(pb.x, lo), hi), RUN_SPEED)
        if self._chase_t > 1.5 and abs(pb.x - body.x) < 45 \
                and abs(pb.y - body.y) < 40:
            # caught! half the time the roles flip (that's the game)
            if self.rng.random() < 0.5 and self.stage <= 5:
                pr.state = "chase_peer"
                pr.state_left = self.rng.uniform(5, 9)
                pr._peer = (body, self)
                self.state = "flee_peer"
                self.state_left = pr.state_left
                self._peer = (pb, pr)
                self.sounds.append("chirp")
            else:
                self.gain("play", 6)
                pr.gain("play", 6)
                self.add_xp(1.0, "cat chase")
                pr.add_xp(1.0, "cat chase")
                self.sounds.append("boing")
                self.state = "sit"
                self.state_left = 2.0
                pr.state = "sit"
                pr.state_left = 2.0
                pr._peer = None
                self._peer = None
        elif self.state_left <= 0:
            if peer[1].state == "flee_peer":
                peer[1].state = "idle"
                peer[1].state_left = 0.0
                peer[1]._peer = None
            self._peer = None
            self.state = "idle"
            self.state_left = 0.0


def flee_peer(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    peer = self._peer
    if peer is None or peer[1].state != "chase_peer":
        self._peer = None
        self.state = "idle"
        self.state_left = 0.0
    else:
        pb, _pr = peer
        self.gain("play", 2.0 * dt)
        plat = body.platform
        if body.target_x is None and plat is not None:
            lo, hi = self._walk_range(plat)
            away = -1.0 if pb.x >= body.x else 1.0
            body.walk_to(min(max(body.x + away * 320, lo), hi), RUN_SPEED)
        if self.state_left <= 0:
            # tired of running: turn and face the pursuer
            self._peer = None
            self.state = "sit"
            self.state_left = 2.0


def to_sleep_peer(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.target_x is None or self.state_left <= 0:
        peer = self._peer
        self._peer = None
        if peer is not None:
            body.facing = 1 if peer[0].x >= body.x else -1  # face her
        self.state = "sleep"
        self.state_left = self.rng.uniform(120, 7200)
        self.log.append("joined the other cat for a nap")


STATES = {
    "to_peer": to_peer,
    "cuddle": cuddle,
    "fight": fight,
    "chase_peer": chase_peer,
    "flee_peer": flee_peer,
    "to_sleep_peer": to_sleep_peer,
}
