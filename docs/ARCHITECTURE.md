# PlasmaCat architecture

Facts below were measured on Fedora 44 / Plasma 6.7–6.8 / Wayland unless
marked otherwise. Where a choice was made, the reason is given next to it.

## Process model

One Python process (PySide6) plus one KWin script.

```
src/plasmacat/
├── main.py, app.py        CLI; bootstrap, save/restore, signals, lifecycle
├── controller.py          AppController: every user action (tray + Control Center)
├── paths.py               package data, XDG dirs, catgame → plasmacat migration
├── persist.py             save game (JSON, format v3) incl. Settings
├── updater.py             release check / install (see "Updates")
├── bridge/                kwin.py (DBus service + script lifecycle), desktop.py (world model)
├── cat/                   brain + behaviors/, needs, states, household, physics,
│                          interactions, toys, sprites, patterns, render
├── world/                 overlay (front window + tick), furniture_layer, placement,
│                          status_board, window_policy, props
├── sound/player.py        QSoundEffect with per-effect gain and groups; pw-play fallback
├── ui/                    control_center + tabs/, appearance_editor, first_run, tray
└── data/                  kwin/bridge.js, sounds/, icons/, plasmacat.desktop
```

## The KWin bridge

Wayland gives clients no global cursor, no window list and no way to place
their own windows. A persistent KWin script (`data/kwin/bridge.js`, loaded via
`org.kde.kwin.Scripting.loadScript` — which only registers it; `start()` runs
it) streams data to the app's DBus service `org.plasmacat.Bridge`. All
arguments are single strings (JSON/CSV), which avoids number-type ambiguity in
`callDBus`.

| Method | Payload | When |
|---|---|---|
| `SetCursor` | `"x,y"` | cursor moves (throttled to ~30 Hz) |
| `SetWindows` | `[{id,x,y,w,h}]`, bottom→top | window changes, coalesced (50 ms) |
| `SetWorkAreas` | `[{x,y,w,h}]`, active screen first | panels/screens change, coalesced |
| `SetActiveFullscreen` | `"0"`/`"1"` | active window enters/leaves fullscreen |
| `OverlayTagged` | caption | one of our windows was tagged |
| `KeyEvent` | `left/right/jump/stop` | control mode only (keys are grabbed only then) |
| `Activate` | `""` | sent by a second launch: show the Control Center |

- **Window identity is `internalId`**, never the caption — titles change all
  the time (browser tabs, `*` markers) and the cat used to fall off.
- **Our own windows are filtered when a signal fires**, not when they appear:
  a window can be announced before its app id is set; attaching listeners to
  our own moving window once caused ~27 work-area updates per second.
- The QtDBus interface name is generated at runtime; the app introspects
  itself and renders the script from a template into
  `$XDG_RUNTIME_DIR/plasmacat/bridge.js`.
- A 10 s watchdog reloads the script when KWin restarts. SIGINT/SIGTERM quit
  through the Qt loop: final save + script unload.

### The floor

Each screen's floor is its work area bottom — or the **visible top of a panel
floating over it**. A floating panel's frame includes its float gap:

- Plasma 6.7: the panel reserves a strut, centered in its frame
  (frame 62, strut 46) → visible top = frame top + (62 − 46) / 2 = 8 px.
- Plasma 6.8: a floating panel reserves **no** strut (work area = full screen;
  frame 60, panel 44) → the gap is assumed: min(8, height / 4).
- A docked panel: frame == strut → its frame top.

`visualFloor()` in the script estimates this. Only visible, horizontal
panels count (a side panel or an auto-hidden one never lifts the floor;
`hiddenChanged` refreshes it when an auto-hide panel slides in). Because
KWin only sees frames, the app then asks plasmashell (`bridge/panels.py`,
its scripting interface) whether each bottom panel floats and how thick it
is, and puts the floor on the exact visible top — this also covers docked
panels without a strut ("dodge windows"). `tests/bridge.test.mjs` and
`tests/test_panels.py` pin the cases.

## Windows and layers

- **Front window**: small, frameless, translucent, input-transparent, kept
  above. It covers only the front content (cats, bubbles, carried toys) plus a
  margin; the app writes the desired rect into its title
  (`plasmacat@x,y,w,h`) and the script applies it. A fullscreen translucent
  overlay cost 13–24 % of a core in buffer copies; the small window ~0 %.
- **Furniture layer**: one fullscreen window per screen, kept below (desktop
  level), repainted only on content changes. Furniture, bowls, resting toys
  and the status board live here, behind your windows.
- **Placement / arrange mode** temporarily makes the front window fullscreen
  and input-receiving (plain title: the script leaves it alone).
- **Hiding**: `Overlay.set_hidden(reason, on)` hides every window while any
  reason holds (`pause`, `fullscreen`). Needs keep running, but hidden cats
  are silent, ignore the cursor and send no notifications (except an update
  offer).

## World model and physics

`DesktopState` turns windows and work areas into platforms: one floor per
screen plus the visible segments of window top edges (clipped by windows in
front, ≥ 30 px). Window sides are walls for walking. Furniture adds synthetic
platforms from `props.FURNITURE_SURFACES` (measured against the art). A cat
standing on a window rides it by the window's own x, not the clipped segment.
`floor_under(x)` resolves the floor of the cat's own screen.

## The brain

Needs decay in real time (offline decay capped at 4 h). A utility-AI picks
behaviors; each state's per-tick logic is a handler in `cat/behaviors/*`
(motion, rest, care, furniture, social, play, human) dispatched through a
registry. Reflex shields are nested sets: a returning human interrupts least,
a startle more, a hunt trigger most (`states.py`). The household (bowls,
furniture, litter, grass) is shared by all cats and ticked once per frame.

Every cat owns an `InteractionDetector`; all share one `CursorTracker` fed by
the overlay. The detector's clock ages a resting cursor out of the speed
window (no phantom hunts).

## Rendering

- Poses are authored in a 64×48 coordinate space and rasterized at
  `DETAIL = 2` (128×96 grid): finer curves and a one-cell outline. Growth
  stages warp the coordinates (big kitten heads, hunched seniors).
- `render.shade_rgba` adds light from above: rim light, ambient occlusion,
  and a soft outline on the lit side — on cats and props alike.
- **Pixel-exact on fractional scaling**: every grid cell is a whole number of
  device pixels and pixmaps carry the window's device pixel ratio (measured
  window dpr 1.65 while `QScreen` reports 2.0). Props use the same cell size
  (`PROP_DETAIL = 3`), so the cat-to-furniture ratio stays exact.
- Sprite tables are cached gzip-compressed in `~/.cache/plasmacat/sprites`,
  keyed by a hash of the generator source.
- Coat patterns (`patterns.py`) are hash-noise based and deterministic.

## Persistence

`~/.local/share/plasmacat/save.json`, atomic write (tmp + rename, previous
save kept as `.bak`), autosave every 30 s and on quit. Format v3 adds
`settings`; older saves (v1 single cat, v2 settings inside the cat's look,
the pre-rename `catgame` dir) migrate on load.

## Updates

`install.sh` clones the repository to `~/.local/share/plasmacat/app` and
checks out the newest `vX.Y.Z` tag. A daily systemd user timer (and the app,
20 s after start) runs `python3 -m plasmacat.updater`, which only *checks* and
writes `.available`; the app offers the release (only a click on that offer
— not on any other notification — installs it). *Check now* uses
`--manual`, which works even with automatic checks switched off. `--apply` fast-forwards to
the newest tag (never untagged work, never over local changes) and the app
restarts. Releases are git tags on `main`.

## Tests

- `python3 -m pytest` — unit tests plus two long headless scenarios run in
  subprocesses (`tests/sim_test.py`: minutes of simulated cat life;
  `tests/window_geo_test.py`: the small-window policy).
- `node --test tests/*.test.mjs` — the KWin script against stubbed KWin APIs.
- CI (GitHub Actions) runs both on every push.
