"""The shared home all cats live in: bowls, furniture, consumables."""

from __future__ import annotations


class Household:
    """The shared home all cats live in (P47): bowl/furniture positions and
    consumables (food fill, litter fill, grass charges, puke spots). Every
    Brain forwards these attributes here, so all cats drink from the same
    fountain and share one litter box."""

    def __init__(self, private: bool = False) -> None:
        # private: owned by a single Brain that ticks it (tests, lone cats);
        # a shared home is ticked once per frame by the overlay
        self.private = private
        self.food_x: float | None = None
        self.water_x: float | None = None
        self.food_type = "kibble"
        self.food_fill = 100.0              # 0..100, drains while eating
        self.water_fill = 100.0
        self.scratch_x: float | None = None
        self.bed_x: float | None = None
        self.grass_x: float | None = None
        self.grass_charges = 3.0            # nibbles left; regrows over 10 min
        self._grass_regrow = 0.0
        self.litter_x: float | None = None
        self.litter_fill = 0.0              # poop units; user cleans at 5
        self.litter_deposits: list[str] = []  # P40: "poop"/"pee" per event
        self.tree_x: float | None = None
        self.wheel_x: float | None = None
        self.shelves: list[tuple[float, float]] = []
        self.box_x: float | None = None
        self.puke_spots: list[float] = []   # x positions of messes to clean up

    def tick(self, dt: float) -> None:
        """Advance the home's own timers (call once per frame, not per cat):
        cat grass regrows one charge per 10 minutes."""
        if self.grass_charges < 3.0:
            self._grass_regrow += dt
            if self._grass_regrow >= 600.0:
                self.grass_charges += 1.0
                self._grass_regrow = 0.0
