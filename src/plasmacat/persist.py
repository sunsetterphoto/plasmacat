"""Persistence: save/load game state as JSON, with offline need decay.

Save file: <AppDataLocation>/save.json (Linux: ~/.local/share/plasmacat/save.json).
No Qt here except nothing — pure json/dataclasses so it's testable.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

SAVE_VERSION = 2  # v2: cats[] list (P47 multi-cat); v1 single-cat keys migrate
MAX_OFFLINE_SECONDS = 4 * 3600  # decay while away is capped at 4 h worth


@dataclass
class Customization:
    name: str = "Minka"
    fur: tuple[int, int, int] = (230, 145, 60)      # 'f'
    fur_shade: tuple[int, int, int] | None = None   # 'F' (derived if None)
    belly: tuple[int, int, int] = (250, 220, 180)   # 'b'
    eye: tuple[int, int, int] = (90, 200, 90)       # 'e'
    pattern: str = "solid"                          # solid|tabby|tuxedo|spots|tortie
    collar: tuple[int, int, int] | None = None      # 'a' (None = no collar)
    sound_on: bool = True
    volume: float = 0.7
    sound_pack: str = "retro"                       # retro|natural
    status_window: bool = False                     # P42: pinned status board
    status_pos: list | None = None                  # [x, y] world coords (None
                                                    # = default: bottom-left)

    def derive_shade(self) -> tuple[int, int, int]:
        if self.fur_shade is not None:
            return self.fur_shade
        return tuple(int(c * 0.72) for c in self.fur)  # type: ignore[return-value]

    def to_palette(self) -> dict[str, tuple[int, int, int]]:
        from plasmacat.cat.sprites import DEFAULT_PALETTE

        pal = dict(DEFAULT_PALETTE)
        pal["f"] = self.fur
        pal["F"] = self.derive_shade()
        pal["b"] = self.belly
        pal["e"] = self.eye
        if self.collar is not None:
            pal["a"] = self.collar
        return pal

    def to_json(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_json(d: dict) -> "Customization":
        def rgb(v):
            return tuple(v) if v is not None else None

        return Customization(
            name=d.get("name", "Minka"),
            fur=rgb(d.get("fur")) or (230, 145, 60),
            fur_shade=rgb(d.get("fur_shade")),
            belly=rgb(d.get("belly")) or (250, 220, 180),
            eye=rgb(d.get("eye")) or (90, 200, 90),
            pattern=d.get("pattern", "solid"),
            collar=rgb(d.get("collar")),
            sound_on=d.get("sound_on", True),
            volume=d.get("volume", 0.7),
            sound_pack=d.get("sound_pack", "retro"),
            status_window=d.get("status_window", False),
            status_pos=(lambda v: [float(v[0]), float(v[1])]
                        if isinstance(v, (list, tuple)) and len(v) == 2
                        else None)(d.get("status_pos")),
        )


@dataclass
class CatState:
    """One cat's personal state (P47): look, needs, progress, lifecycle."""
    customization: Customization = field(default_factory=Customization)
    needs: dict[str, float] = field(default_factory=dict)
    attachment_xp: float = 0.0
    petted_strokes: int = 0
    age: float = 0.0                    # growth stage (float, 0..15)
    care: float = 0.5                   # attention reservoir 0..1
    fav_toy: str = ""                   # personality ('ball' | 'plush')


@dataclass
class GameState:
    cats: list[CatState] = field(default_factory=lambda: [CatState()])
    # the shared household (P47): one set of bowls/furniture for all cats
    toys: list[dict] = field(default_factory=list)  # [{kind, x, y}]
    food_type: str = "kibble"
    food_fill: float = 100.0
    water_fill: float = 100.0
    food_x: float | None = None
    water_x: float | None = None
    scratch_x: float | None = None
    bed_x: float | None = None
    grass_x: float | None = None
    grass_charges: float = 3.0
    litter_x: float | None = None
    litter_fill: float = 0.0
    litter_deposits: list[str] = field(default_factory=list)  # P40: poop/pee
    tree_x: float | None = None
    wheel_x: float | None = None
    box_x: float | None = None            # P25: cardboard box
    shelves: list[dict] = field(default_factory=list)  # P25: [{x, y}] wall shelves
    puke_spots: list[float] = field(default_factory=list)  # P25: messes to clean
    saved_at: float = 0.0

    @property
    def customization(self) -> Customization:
        """Compat: the primary cat's look (global settings live there too)."""
        return self.cats[0].customization


def save(path: Path, state: GameState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state.saved_at = time.time()
    payload = {
        "version": SAVE_VERSION,
        "cats": [{
            "customization": c.customization.to_json(),
            "needs": c.needs,
            "attachment_xp": c.attachment_xp,
            "petted_strokes": c.petted_strokes,
            "age": c.age,
            "care": c.care,
            "fav_toy": c.fav_toy,
        } for c in state.cats],
        "toys": state.toys,
        "food_type": state.food_type,
        "food_fill": state.food_fill,
        "water_fill": state.water_fill,
        "food_x": state.food_x,
        "water_x": state.water_x,
        "scratch_x": state.scratch_x,
        "bed_x": state.bed_x,
        "grass_x": state.grass_x,
        "grass_charges": state.grass_charges,
        "litter_x": state.litter_x,
        "litter_fill": state.litter_fill,
        "litter_deposits": state.litter_deposits,
        "tree_x": state.tree_x,
        "wheel_x": state.wheel_x,
        "box_x": state.box_x,
        "shelves": state.shelves,
        "puke_spots": state.puke_spots,
        "saved_at": state.saved_at,
    }
    path.write_text(json.dumps(payload, indent=2))


def _cat_from_json(c: dict) -> CatState:
    return CatState(
        customization=Customization.from_json(c.get("customization", {})),
        needs={k: float(v) for k, v in c.get("needs", {}).items()},
        attachment_xp=float(c.get("attachment_xp", 0.0)),
        petted_strokes=int(c.get("petted_strokes", 0)),
        age=float(c.get("age", 6.0)),
        care=float(c.get("care", 0.5)),
        fav_toy=c.get("fav_toy", ""),
    )


def load(path: Path) -> GameState | None:
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    cats_raw = d.get("cats")
    if isinstance(cats_raw, list) and cats_raw:
        cats = [_cat_from_json(c) for c in cats_raw if isinstance(c, dict)] \
            or [CatState()]
    else:
        # legacy v1 save (single cat at the top level, P47 migration):
        # the veteran cat keeps her grown-up body (stage 6, not a kitten)
        cats = [CatState(
            customization=Customization.from_json(d.get("customization", {})),
            needs={k: float(v) for k, v in d.get("needs", {}).items()},
            attachment_xp=float(d.get("attachment_xp", 0.0)),
            petted_strokes=int(d.get("petted_strokes", 0)),
            age=6.0,
            care=0.5,
            fav_toy=d.get("fav_toy", ""),
        )]
    state = GameState(
        cats=cats,
        toys=[t for t in d.get("toys", []) if isinstance(t, dict)],
        food_type=d.get("food_type", "kibble"),
        food_fill=float(d.get("food_fill", 100.0)),
        water_fill=float(d.get("water_fill", 100.0)),
        food_x=d.get("food_x"),
        water_x=d.get("water_x"),
        scratch_x=d.get("scratch_x"),
        bed_x=d.get("bed_x"),
        grass_x=d.get("grass_x"),
        grass_charges=float(d.get("grass_charges", 3.0)),
        litter_x=d.get("litter_x"),
        litter_fill=float(d.get("litter_fill", 0.0)),
        litter_deposits=[x for x in d.get("litter_deposits", [])
                         if x in ("poop", "pee")],
        tree_x=d.get("tree_x"),
        wheel_x=d.get("wheel_x"),
        box_x=d.get("box_x"),
        shelves=[s for s in d.get("shelves", []) if isinstance(s, dict)],
        puke_spots=[float(x) for x in d.get("puke_spots", [])],
        saved_at=float(d.get("saved_at", 0.0)),
    )
    return state


def offline_decay(needs: dict[str, float], saved_at: float,
                  decay: dict[str, float], now: float | None = None) -> dict[str, float]:
    """Apply need decay for the time the game was closed (capped)."""
    now = time.time() if now is None else now
    elapsed = min(max(now - saved_at, 0.0), MAX_OFFLINE_SECONDS)
    out = dict(needs)
    for k, rate in decay.items():
        if k in out:
            out[k] = max(0.0, out[k] - rate * elapsed)
    return out
