"""Art quality guards for the procedural sprites (finer grid, shading,
organic patterns, curved tail, attached whiskers, blink frames)."""
import time

from plasmacat.cat import sprites
from plasmacat.cat.patterns import apply_pattern
from plasmacat.cat.render import sprite_rgba

O = sprites.DEFAULT_PALETTE["o"]
F = sprites.DEFAULT_PALETTE["f"]


def _frame(state="stand", i=0):
    return sprites.SPRITES[state][i]


def test_grid_is_detail_times_pose_space():
    assert sprites.DETAIL == 2
    assert (sprites.GRID_W, sprites.GRID_H) == (sprites.CANVAS_W * 2, sprites.CANVAS_H * 2)
    sprites.validate()


def test_outline_is_one_cell_thin_on_the_back():
    fr = _frame()
    x = 29 * sprites.DETAIL                       # through the middle of the back
    col = [fr[y][x] for y in range(sprites.GRID_H)]
    top = next(y for y, ch in enumerate(col) if ch != ".")
    assert col[top] == "o" and col[top + 1] not in ".o"


def test_selective_outline_and_rim_light():
    fr = _frame()
    w, h, px = sprite_rgba(fr, sprites.DEFAULT_PALETTE)
    x = 29 * sprites.DETAIL
    col = [px[y * w + x] for y in range(h)]
    top = next(y for y, p in enumerate(col) if p[3])
    assert col[top][:3] != O                       # soft outline on the lit top side
    assert sum(col[top + 1][:3]) > sum(F)          # rim light right below it
    bottom = max(y for y, p in enumerate(col) if p[3])
    assert col[bottom][:3] == O                    # hard outline underneath


def test_tail_is_curved():
    fr = _frame()
    # tail = fur/outline cells left of the body, above the back line
    pts = [(x, y) for y in range(0, 30 * 2) for x in range(0, 14 * 2) if fr[y][x] != "."]
    ys = sorted({y for _, y in pts})
    centers = [(sum(x for x, yy in pts if yy == y) / sum(1 for _, yy in pts if yy == y), y)
               for y in ys]
    (x0, y0), (x1, y1) = centers[0], centers[-1]
    dev = max(abs((x - x0) - (x1 - x0) * (y - y0) / max(y1 - y0, 1)) for x, y in centers)
    assert dev > 1.5


def test_whiskers_attach_to_the_muzzle():
    fr = _frame()
    whisk = {(x, y) for y in range(sprites.GRID_H) for x in range(sprites.GRID_W)
             if fr[y][x] == "w" and x > 52 * 2}
    assert whisk
    attached = any(fr[y + dy][x + dx] not in ".w"
                   for x, y in whisk for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                   if 0 <= x + dx < sprites.GRID_W and 0 <= y + dy < sprites.GRID_H)
    assert attached


def test_blink_frames_exist():
    for state in ("stand_blink", "sit_blink", "loaf_blink"):
        assert state in sprites.SPRITES


def _patch_count(frame, ch="F"):
    cells = {(x, y) for y, row in enumerate(frame) for x, c in enumerate(row) if c == ch}
    seen, n = set(), 0
    for c in cells:
        if c in seen:
            continue
        n += 1
        stack = [c]
        while stack:
            x, y = stack.pop()
            if (x, y) in seen or (x, y) not in cells:
                continue
            seen.add((x, y))
            stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return n


def test_tortie_is_not_a_checkerboard():
    t = apply_pattern(_frame(), "tortie")
    rows_with_change = sum(1 for row in t if "F" in row)
    # organic patches: transitions do not all fall on a coarse 10-cell lattice
    xs = {x for row in t for x in range(1, len(row)) if (row[x] == "F") != (row[x - 1] == "F")}
    assert rows_with_change > 10
    assert len({x % 10 for x in xs}) >= 6


def test_tabby_stripes_follow_the_body():
    t = apply_pattern(_frame(), "tabby")
    assert _patch_count(t) >= 4


def test_spots_are_round_patches():
    t = apply_pattern(_frame(), "spots")
    assert _patch_count(t) >= 5


def test_stage_build_stays_reasonable():
    t0 = time.perf_counter()
    sprites.sprites_for(2)
    assert time.perf_counter() - t0 < 8.0      # cold build (slow CI headroom)


def test_stage_tables_come_from_the_disk_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("PLASMACAT_CACHE_DIR", str(tmp_path))
    sprites._SPRITES_BY_STAGE.pop(3, None)
    sprites._ACCESSORIES_BY_STAGE.pop(3, None)
    cold = sprites.sprites_for(3)
    assert list(tmp_path.glob("*.json.gz"))
    sprites._SPRITES_BY_STAGE.pop(3, None)
    sprites._ACCESSORIES_BY_STAGE.pop(3, None)
    t0 = time.perf_counter()
    warm = sprites.sprites_for(3)
    assert time.perf_counter() - t0 < 0.5
    assert warm == cold
    assert sprites.accessories_for(3)


def test_blink_uses_closed_eye_frames():
    from plasmacat.world.overlay import Overlay
    keys = {}
    for state in ("stand", "sit", "loaf"):
        class C:
            anim_state = state
            blink_active = True
            class brain:
                mood = 90
        keys[state] = Overlay._anim_key(None, C)
    assert keys == {"stand": "stand_blink", "sit": "sit_blink", "loaf": "loaf_blink"}
