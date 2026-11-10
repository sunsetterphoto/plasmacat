"""Resting: sleep, the pre-sleep ritual, grooming, stretching.

State handlers moved verbatim out of Brain._continue: each takes the
brain as `self` so the bodies read exactly like the methods they were.
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from plasmacat.bridge.desktop import DesktopState
    from plasmacat.cat.brain import Brain
    from plasmacat.cat.physics import CatBody


def sleep(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.airborne or self.needs["energy"] >= 99.0:
        self.state_left = 0.0  # the bed vanished or she is rested: wake
    self._sleep_mult = (1.5 if self.bed_x is not None
                        and abs(body.x - self.bed_x) < 60 else 1.0)


def to_bed(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if body.target_x is None:
        if self.rng.random() < 0.55:
            # making biscuits before settling into the cushion
            self.state = "knead"
            self.state_left = self.rng.uniform(3.0, 5.0)
        else:
            self.state = "sleep"
            self.state_left = self.rng.uniform(120, 7200)


def knead(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if self.state_left <= 0:
        self.state = "sleep"
        self.state_left = self.rng.uniform(120, 7200)


def yawn(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if self.state_left <= 0:
        self.state = "stretch"
        self.state_left = self.rng.uniform(1.2, 1.8)


def stretch(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if self.state_left <= 0:
        self.state = "idle"
        self.state_left = 0.0


def groom(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if self.state_left <= 0 and self._chain_groom_sleep:
        # after eating: groom, then (often) sleep — the classic chain
        self._chain_groom_sleep = False
        if self.rng.random() < 0.5:
            self._start("sleep", body, desktop)
        else:
            self.state = "idle"


def ear_fold(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if self.state_left <= 0:
        self.state = "lick_paw"     # ...then 8 cycles of paw licking
        self.state_left = self._lick_cycles * 0.4  # 2.5 cycles/s


def lick_paw(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if self.state_left <= 0:
        self._lick_cycles = 0
        self.state = "idle"


def ritual_sit(self: Brain, dt: float, body: CatBody, desktop: DesktopState) -> None:
    if self.state_left <= 0:
        nxt = self._ritual.pop(0) if self._ritual else None
        if nxt is None:
            self._ritual = None
            self._start("sleep", body, desktop)  # ritual complete
        else:
            self.state = nxt
            self.state_left = self._ritual_dur(nxt)


STATES = {
    "sleep": sleep,
    "sleep_belly": sleep,
    "to_bed": to_bed,
    "knead": knead,
    "yawn": yawn,
    "stretch": stretch,
    "groom": groom,
    "ear_fold": ear_fold,
    "lick_paw": lick_paw,
    "ritual_sit": ritual_sit,
    "ritual_scratch": ritual_sit,
    "ritual_groom": ritual_sit,
}
