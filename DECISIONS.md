# DECISIONS — measured facts and architectural choices

All facts below were **measured on the target machine** (Fedora 44, Plasma 6.7.3, Wayland)
on 2026-07-18, not guessed. See PLAN.md §2 for the full measurement list.

## D1 — Wayland requires a KWin helper script (no alternative)
Wayland does not let apps read the global cursor position, enumerate windows, or position
themselves freely. On KDE the supported escape hatch is the KWin scripting API
(`org.kde.kwin.Scripting.loadScript`, verified live). We ship `kwin/plasmacat-bridge.js`,
a persistent script that pushes data to our DBus service via `callDBus(...)`:
- cursor position on `cursorPosChanged()` (throttled ~30 Hz)
- window-top platform list on `windowAdded/Removed`, `frameGeometryChanged`,
  `currentDesktopChanged`, `minimizedChanged` (filtered: `normalWindow`, not minimized,
  current desktop, not our own window)
- tags our overlay window (`keepAbove`, `skipTaskbar`, `skipSwitcher`, `skipPager`,
  all desktops) matched by `resourceClass == "plasmacat"`

## D2 — Single PySide6 process; overlay is a fullscreen input-transparent window
`Qt::WindowTransparentForInput` + `WA_TranslucentBackground` + fullscreen frameless.
Clicks pass through to the desktop; the cat is petted via the global cursor stream, not clicks
(v1 trade-off, accepted). Fallbacks if the flag fails on Wayland:
A) XWayland overlay (`QT_QPA_PLATFORM=xcb` + XShape masks), B) layer-shell QPA plugin
(`liblayer-shell.so` is installed).

## D3 — DBus arguments from KWin are passed as strings
KWin `callDBus` marshals JS values; to avoid numeric-type ambiguity, all bridge methods take a
single `QString` (`"x,y"` CSV or JSON) and parse on the Python side.

## D4 — Stack chosen by user: Python + PySide6 (Essentials + Addons)
abi3 wheels (`cp310-abi3`) install on Python 3.14 — verified via PyPI metadata.
QtDBus for the bridge service, QtMultimedia for sound (fallback: `pw-play`/`paplay` subprocess).

## D5 — Art is code-defined pixel matrices, palette-recolored at runtime
User chose generated art over CC0 packs. This makes wizard customization (fur color, pattern,
eyes, accessory) a palette/render operation, not an asset swap.

## D6 — Sound: synthesized retro pack is default; optional CC0 pack on user request
numpy-synthesized 8-bit-style WAVs (meow, purr, eat, drink, boing, sleep). Mute + volume in tray.
Optional CC0 download pack only with explicit user approval (attribution in README).

## D7 — Persistence: JSON via QStandardPaths
`~/.local/share/plasmacat/save.json` on Linux. Timestamp-based offline need decay.

## D8 — Toys spawn at the cursor position from the control panel
Because the overlay captures no input (D2), "place toy" = pick toy in panel → it spawns at the
current cursor location (ball gets a random throw velocity). Refined click-to-place is post-v1.

## D9 — KWin `loadScript` only registers; `start()` actually runs the script (measured)
`org.kde.kwin.Scripting.loadScript(path, name)` returns an id but the script does NOT execute
until `org.kde.kwin.Scripting.start()` is called. Discovered empirically: no bus traffic and no
script side effects until `start()`. `KWinBridge.start()` therefore does load → (unload+reload on
name clash, e.g. after a crash) → `start()`.

## D10 — QtDBus interface name is nondeterministic → runtime introspection + JS template
`ExportAllSlots` exports our slots under an auto-generated name derived from the shiboken
metaobject — observed BOTH `local.py.main.BridgeService` AND `local.plasmacat.BridgeService`
on the same machine across builds (PySide6 6.11.1 has no Q_CLASSINFO to pin it; classInfo is
ignored). Hardcoding it silently broke the whole KWin→app channel between builds.
Fix: `KWinBridge.start()` introspects the freshly-registered object via
org.freedesktop.DBus.Introspectable, extracts the `*BridgeService` interface name, and renders
`kwin/plasmacat-bridge.js` (template with `__CATGAME_IFACE__` placeholder) into
`kwin/plasmacat-bridge.runtime.js`, which is what KWin loads.

## D11 — KWin sees some non-user windows as `normalWindow` (measured)
e.g. "Aufnahmebrücke von Wayland nach X — Xwayland-Video-Brücke" at (0,0). Platform extraction
(P3) must filter by minimum size / usefulness, not just `normalWindow`.

## D12 — Jump impulse is scaled to the height difference
A fixed strong impulse for downward hops launched the cat off the top of the screen (sim bug).
`CatBody.jump_to` now uses just-enough impulse for upward jumps (capped by JUMP_VY) and a
gentle -350 px/s hop for downward jumps; horizontal speed is derived from flight time and
clamped (MAX_VX_AIR).

## D13 — Exactly one CursorTracker, owned by InteractionDetector
The overlay (and tests) once fed a separate tracker while the detector read its own empty one —
detection silently never fired. Rule: always feed `detector.tracker`; never construct a second
CursorTracker. tools/sim_test.py guards this (petting strokes must be > 0).

## D14 — Accessories are diff layers, not sprite variants
The collar is built by generating every pose twice (with/without collar) and diffing:
`ACCESSORIES[state][frame]` holds only the added pixels, drawn on top of the base frame.
Customization costs no sprite-table duplication; poses without heads-up area (sleep, crouch)
get empty layers.

## D15 — Persistence format and offline decay
JSON save at QStandardPaths AppDataLocation (~/.local/share/plasmacat/save.json), version field
included. Needs decay while the game is closed, capped at 4 h worth (MAX_OFFLINE_SECONDS) so
returning after a weekend isn't instant death. Autosave every 30 s + on quit.

## D16 — "Reset cat" restarts the process
Reset deletes the save and re-execs (`os.execvpe`) so the next run hits the first-run wizard
cleanly. The leftover KWin script is handled by the new instance's idempotent load (D9).

## D20 — Multi-monitor world model (P38)
The world is the virtual desktop; the KWin script sends one work area per
output (`SetWorkAreas`, active screen first) via `clientArea(WorkArea, output,
desktop)`. DesktopState holds `work_areas` (one floor platform each);
`floor_y_at(x)` resolves any x to its screen's floor, `floor_x0/x1` are the
union. Floor seams are walkable: same level crosses on foot, steps up to 60 px
(STEP_UP_MAX) are snapped, taller steps and gaps between screens are walls
(turn around); jumping across stays legal. Falling into a gap snaps to the
nearest floor (`nearest_floor`, x clamped onto its span) — the cat's version
of the P25 toy safety net. Floor edges have no -EDGE_MARGIN lip-drop (that is
a window-top behavior); single-screen behavior is unchanged. Rendering: one
fullscreen FurnitureLayer per screen (`QWindow.setScreen` + `showFullScreen`,
each translating world→screen), the small front window (D19) roams all
screens in virtual coords via KWin. Sim-covered (P38 block); live dual-screen
test pending (single-screen machine at implementation time).

## D18 — Occlusion model for windows (P16)
- Platforms = window top edges CLIPPED by foreground windows (KWin stacking
  order, later covers earlier): a background window is jumpable only along
  its visible edge segments (≥30 px), computed in DesktopState._rebuild_platforms.
- Window sides are walls for grounded walking (vertical overlap with the cat's
  body; the window the cat stands on is exempt). The cat stops and turns
  around. Jumping onto/over a window stays legal (only horizontal ground
  movement is blocked; full arc-through-window collision is out of scope).

## D17 — Rendering/performance contract (measured, P12c; SOLVED by P37/D19)
The fullscreen translucent surface costs a native buffer copy per repaint
(~7 MB at 1707x1067 logical). Measured on the live machine: ~13-24% of one
core while the cat is active (varies with user mouse activity), py-spy shows
only ~15% of that in Python paintEvent — the rest is native Qt/Wayland buffer
handling. Mitigations in place: adaptive frame rate (33 ms active / 66 ms
idle), repaint gating by a change signature (no repaint unless something
visible changed), 30 Hz bridge cursor throttle. Estimated idle: ~2-3%.
**P37 replaced the fullscreen front overlay with a small cat-following window
(D19): measured ~0.0%/core while walking — the buffer-copy cost is gone.**
The furniture layer stays fullscreen (keepBelow) but repaints only on content
changes (signature-gated), so its cost stays negligible.

## D19 — Small front window, geometry via window title (P37)
Wayland clients cannot position themselves; KWin scripts can (`frameGeometry`
is read-write, kdotool proves it). Channel: the app encodes the desired rect
in the overlay's window title (`plasmacat@x,y,w,h`); the bridge script
connects `captionChanged` and applies it (plain `plasmacat` title = leave
alone, used while placement mode goes fullscreen temporarily). No polling, no
extra DBus surface. Window policy: cover the world bounding box of all
front-layer content (cat, bubble, cat door, ALL toys — a resting ball far
from the cat must stay visible) + 24 px margin, min 240x180, clamped to the
virtual screen geometry; recenter when content escapes (moves are cheap),
shrink only after 5 s below 60% fill (resizes reallocate the buffer).
Rendering translates world→window by the requested origin (KWin applies the
position, so we trust our own request). Verified: window follows a walking
cat across the whole screen, no trails, ~0.0%/core.

