"""Cat body: movement, jumping and landing on platforms. Pure python, no Qt.

Coordinates are screen pixels; y is the cat's FEET (sprite bottom). Gravity
pulls +y (down). Platforms come from bridge.desktop.DesktopState.
"""

from __future__ import annotations

from plasmacat.bridge.desktop import DesktopState, Platform

GRAVITY = 2200.0          # px/s^2
WALK_SPEED = 90.0
RUN_SPEED = 230.0
JUMP_VY = -1800.0         # initial upward velocity (arcade-strong: ~735 px max)
MAX_VX_AIR = 380.0        # horizontal air speed clamp
EDGE_MARGIN = 10.0        # how close to a platform edge the cat dares go
ACCEL = 800.0             # px/s^2 — she speeds up visibly, not instantly (P26)
DECEL = 1000.0            # px/s^2 — and brakes before the target, no overshoot
MIN_SPEED = 25.0          # crawl while braking


class CatBody:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.airborne = False
        self.facing = 1                    # 1 = right, -1 = left
        self.blocked = False               # set when a wall stopped the walk (P19)
        self.platform: Platform | None = None
        self.target_x: float | None = None  # walk destination
        self.speed = WALK_SPEED
        self.cur_speed = 0.0               # current ground speed (accel/brake)

    # -- intents -----------------------------------------------------------

    def walk_to(self, x: float, speed: float = WALK_SPEED) -> None:
        # ignore micro-targets (< 15 px): they only cause flip-flopping (P19)
        if abs(x - self.x) < 15.0:
            self.stop()
            return
        self.target_x = x
        self.speed = speed

    def stop(self) -> None:
        self.target_x = None
        self.vx = 0.0
        self.cur_speed = 0.0

    def jump_to(self, x: float, y: float) -> bool:
        """Ballistic hop to point (x, y). Impulse is scaled to the height
        difference (gentle hop for downward jumps). Returns False if unreachable."""
        if self.airborne:
            return False
        dy = y - self.y
        if dy < 0:  # upward: use just enough impulse (+ margin), capped by JUMP_VY
            vy = -((2 * GRAVITY * -dy) ** 0.5) - 60.0
            if vy < JUMP_VY:
                return False  # too high to reach
        elif dy < 1.0 and abs(x - self.x) > 30.0:
            # same-level hop (startle jump, long pounce): pick an arc whose
            # flight time keeps vx under the cap — the fixed -350 impulse only
            # covers ~120 px and silently failed anything farther (P24)
            t = abs(x - self.x) / (MAX_VX_AIR * 0.85)
            vy = -0.5 * GRAVITY * t
            if vy < JUMP_VY:
                return False  # too far even for a stretched long-jump
        else:       # downward: small hop, gravity does the rest
            vy = -350.0
        t = (-vy + (vy * vy + 2 * GRAVITY * dy) ** 0.5) / GRAVITY
        if t <= 0.01:
            return False
        vx = (x - self.x) / t
        if abs(vx) > MAX_VX_AIR:
            return False
        self.vx = vx
        self.vy = vy
        self.airborne = True
        self.platform = None
        self.target_x = None
        self.facing = 1 if vx >= 0 else -1
        return True

    def _wall_ahead(self, x_next: float, desktop: DesktopState) -> float | None:
        """A foreground window's side edge blocking the walk (P16: a window
        in front is a wall). Returns the blocking side x, or None."""
        body_top = self.y - 96.0
        direction = 1 if x_next > self.x else -1
        for w in desktop._windows:
            if not (w["y"] < self.y - 10 and w["y"] + w["h"] > body_top + 10):
                continue  # no vertical overlap with the cat's body
            if (self.platform is not None and not self.platform.floor
                    and abs(self.platform.y - w["y"]) < 2.0):
                continue  # the window the cat stands on is not a wall
            if direction > 0:
                side = float(w["x"])
                if self.x < side <= x_next:
                    return side
            else:
                side = float(w["x"] + w["w"])
                if x_next <= side < self.x:
                    return side
        return None

    # -- simulation --------------------------------------------------------

    def tick(self, dt: float, desktop: DesktopState) -> None:
        if self.airborne:
            self.x += self.vx * dt
            old_y = self.y
            self.y += self.vy * dt
            self.vy += GRAVITY * dt
            # keep the whole sprite on screen, with a visible gap (the cat
            # turns around before it presses into the screen edge)
            self.x = min(max(self.x, desktop.floor_x0 + 75), desktop.floor_x1 - 75)
            if self.vy > 0:  # falling: land on the first top edge crossed
                for p in desktop.platforms:  # sorted highest-first
                    if old_y <= p.y <= self.y and p.contains_x(self.x, 6.0):
                        self.y = p.y
                        self.vy = 0.0
                        self.vx = 0.0
                        self.airborne = False
                        self.platform = p
                        break
            return

        # grounded
        if self.platform is None:
            self.platform = desktop.platform_below(self.x, self.y)
            self.y = self.platform.y
        else:
            # re-resolve the platform every tick: windows move/close underneath
            cur = desktop.find_platform(self.platform)
            if cur is None:
                self.airborne = True
                self.vy = 0.0
                self.platform = None
                return
            self.x += cur.x0 - self.platform.x0  # ride horizontal window moves
            self.y = cur.y                       # and vertical ones
            self.platform = cur
            if not cur.contains_x(self.x, 12.0):
                self.airborne = True             # carried off the edge: drop
                self.vy = 0.0
                self.platform = None
                return

        if self.target_x is not None:
            dx = self.target_x - self.x
            # edge rule: always turn around before touching the screen edge
            if dx < 0 and self.x <= desktop.floor_x0 + 80:
                self.stop()
                self.facing = 1
            elif dx > 0 and self.x >= desktop.floor_x1 - 80:
                self.stop()
                self.facing = -1
            elif abs(dx) <= max(2.0, self.cur_speed * dt + 2.0):
                self.x = self.target_x  # arrived exactly (no overshoot)
                self.stop()
            else:
                self.facing = 1 if dx > 0 else -1
                # accelerate toward the target speed; brake early enough to
                # stop on the spot (P26: no more instant-on/instant-off)
                brake_dist = self.cur_speed ** 2 / (2 * DECEL) + 4.0
                if abs(dx) <= brake_dist:
                    self.cur_speed = max(MIN_SPEED, self.cur_speed - DECEL * dt)
                else:
                    self.cur_speed = min(self.speed, self.cur_speed + ACCEL * dt)
                step = self.facing * self.cur_speed * dt
                next_x = self.x + step
                wall = self._wall_ahead(next_x, desktop)
                if wall is not None:
                    self.x = wall - self.facing * 2.0
                    self.stop()
                    self.blocked = True
                    self.facing = -self.facing  # wall: turn around (P16)
                else:
                    self.x = next_x
                    # walking off the edge?
                    if not self.platform.contains_x(self.x, -EDGE_MARGIN):
                        self.airborne = True
                        self.vy = 0.0
                        self.vx = step / dt
                        self.platform = None
        else:
            self.vx = 0.0
            self.cur_speed = 0.0
