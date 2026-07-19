# PlasmaCat — Desktop Companion Cat: Implementation Plan

> **STATUS: COMPLETE (2026-07-18)** — all phases P0–P23 implemented, tested and
> committed. User accepted the result. For the full build log see PROGRESS.md,
> for architectural decisions DECISIONS.md (D1–D18), for how to run README.md.

## 1. Goal

A platform-independent desktop companion game: a cute retro pixel-art cat living on the
user's desktop (primary target: this machine, KDE Plasma 6 + Wayland). The cat:

- walks/runs/jumps on the desktop and on top of real application windows
- has needs: food, water, sleep, play — expressed like a real cat (meowing, begging, rubbing)
- reacts to the mouse pointer as the "owner's hand": petting, head-rub, tail-snuggle,
  hunt/pounce play
- gains attachment with continued interaction (persistent progression)
- appearance is customizable in a first-run setup wizard (fur color/pattern, eyes, accessory, name)
- makes sounds (retro style, muteable, volume control)
- user can place toys (ball, plush mouse, string) that the cat plays with

## 2. Measured environment (2026-07-18, do not re-guess)

- OS: Fedora 44 KDE Plasma Desktop Edition; **Plasma 6.7.3, KWin 6.7.3**
- Session: **Wayland** (`XDG_SESSION_TYPE=wayland`, `WAYLAND_DISPLAY=wayland-0`, `DISPLAY=:0` via XWayland)
- Python 3.14.6, pip 26.0.1, `venv` works; system numpy 2.4.6 + pillow 12.3.0
- PySide6 6.11.1 / PyQt6 6.11.0 ship `cp310-abi3` manylinux wheels → **installable on Python 3.14**
- `qdbus-qt6` present; DBus interface `org.kde.kwin.Scripting` with `loadScript(path, pluginName)`,
  `unloadScript(pluginName)`, `isScriptLoaded` verified live
- `liblayer-shell.so` QPA plugin installed (kept as fallback, not primary)
- `xdotool` present (X11-only fallback), `kdotool` absent (not needed; we ship our own script)

Verified against official KWin 6 scripting API docs (develop.kde.org/docs/plasma/kwin/api/):
`workspace.cursorPos`, signal `cursorPosChanged()`, `workspace.stackingOrder`,
`windowAdded/windowRemoved`, per-window `frameGeometry` + `frameGeometryChanged`, `caption`,
`normalWindow/dock/desktopWindow`, `minimized`, `desktops/onAllDesktops`, and read-write
`keepAbove`, `skipTaskbar`, `skipSwitcher`; scripts can call out via
`callDBus(service, path, interface, method, args..., callback)` and `registerShortcut(...)`.
The kdotool project confirms this loadScript pattern works on Plasma 6 Wayland.

## 3. Architecture (one Python process, PySide6)

```
PlasmaCat/
├── PLAN.md / PROGRESS.md / DECISIONS.md / README.md   # continuation docs (PLAN.md = this file)
├── pyproject.toml            # deps: PySide6 (Essentials+Addons), numpy, pillow
├── .venv/                    # project-local venv
├── run.sh                    # activates venv, runs app
├── kwin/plasmacat-bridge.js    # persistent KWin helper script (see below)
└── src/plasmacat/
    ├── main.py               # entry, single-instance guard, clean shutdown (unloads KWin script)
    ├── overlay.py            # fullscreen transparent input-transparent game canvas + 60 Hz loop
    ├── bridge/
    │   ├── kwin.py           # loads/unloads KWin script, hosts org.plasmacat.Bridge DBus service
    │   └── desktop.py        # DesktopBridge abstraction (cursor, screen, window-tops) — future X11/Windows backends
    ├── cat/
    │   ├── sprites.py        # code-defined pixel matrices + palette recolor (customization)
    │   ├── animations.py     # frame sequences per state
    │   ├── brain.py          # needs/mood/attachment + utility-AI behavior picker
    │   └── physics.py        # gravity, jump arcs, floor + window-top platforms
    ├── sound/
    │   ├── synth.py          # numpy → retro WAV pack (meow, purr, eat, drink, boing, sleep)
    │   └── packs.py          # SoundPack loading (retro default / optional CC0), mute + volume
    ├── ui/
    │   ├── wizard.py         # first-run customization wizard with live preview
    │   ├── panel.py          # control panel: needs bars, toy buttons, settings, mute
    │   └── tray.py           # system tray icon + menu
    └── persist.py            # JSON save (QStandardPaths), timestamp-based offline decay
```

### Key decisions (with fallbacks)

1. **Overlay window** — Qt fullscreen, frameless, `Qt::WA_TranslucentBackground`,
   `Qt::WindowTransparentForInput` (clicks pass through to the desktop; the cat is "petted" by
   hover/motion, not clicks — v1 trade-off, documented). Our KWin script marks the window
   `keepAbove=true, skipTaskbar, skipSwitcher, onAllDesktops` (matched via resourceClass).
   *Fallback A:* run overlay under XWayland (`QT_QPA_PLATFORM=xcb`, XShape input masks).
   *Fallback B:* layer-shell QPA plugin (`QT_WAYLAND_SHELL_INTEGRATION=layer-shell`).
2. **Compositor bridge** — persistent KWin script `plasmacat-bridge.js` pushes data to our DBus
   service `org.plasmacat.Bridge`: cursor position on `cursorPosChanged()` (throttled ~30 Hz),
   window-top platform list on `stackingOrderChanged`/`frameGeometryChanged` (filtered:
   normalWindow, not minimized, on current desktop, not our own window). No polling in our app.
   Unloaded on exit; `--unload-bridge` CLI escape hatch if the app crashes.
3. **Petting without click capture** — global cursor stream + known cat hitbox ⇒ hover, slow
   strokes (petting), cursor near head (head-rub), cursor near rear (tail-wrap at high
   attachment), fast erratic movement (trigger hunt/pounce). Placement clicks for toys are
   handled via the control panel (toy spawns at current cursor position) — no overlay input needed.
4. **Window-top platforms** — bridge sends top-edge segments of visible normal windows; cat
   physics treats floor + window tops as platforms; jump onto them when wandering.
5. **Rendering** — QPainter, integer-scaled QPixmaps (NearestNeighbor), partial `update(rect)`
   repaints; sprite art defined as pixel matrices in code, palette-recolored at runtime
   (this powers the customization wizard).
6. **Sound** — `SoundPack` interface. Default `retro` pack: WAVs synthesized with numpy at
   first run (8-bit style meow/purr/eat/drink/boing/sleep). Optional `cc0` pack: downloaded
   CC0 sounds (user-approved in wizard/settings, attribution in README). Playback via
   QtMultimedia `QSoundEffect` with global mute + volume. *Fallback:* `pw-play`/`paplay` subprocess.
7. **Persistence** — JSON at `QStandardPaths::AppDataLocation` (Linux: `~/.local/share/plasmacat/`):
   needs, attachment XP/level, customization, toy placement, timestamps → needs decay while offline.
8. **Cat brain** — needs (hunger, thirst, energy, play, affection 0–100, individual decay rates),
   mood derived from needs; utility-AI picks behaviors: wander, sit, groom, sleep, beg (meow+rub
   against cursor), chase cursor, stalk/pounce, sit-on-window, play-with-toy, eat/drink at bowls.
   Attachment XP from petting/feeding/playing; higher attachment unlocks tail-snuggle, following,
   greeting behaviors. Thought bubbles (pixel hearts, Zzz, food icon) communicate needs.

## 4. Phases (each ends with a verification step)

- **P0 — Scaffold & docs**: git init + initial commit; `.venv`; install deps; skeleton; write
  PLAN.md/PROGRESS.md/DECISIONS.md/README.md into repo.
  *Verify:* `python -c "import PySide6.QtDBus, PySide6.QtMultimedia"` in venv.
- **P1 — Compositor spike (riskiest first)**: overlay window (fullscreen/translucent/input-transparent,
  keepAbove via bridge); KWin script streams cursor + window list; test sprite follows cursor;
  dump window-top segments. *Verify:* sprite tracks cursor over any app; desktop fully clickable;
  reported window geometries match reality. If `WindowTransparentForInput` fails → Fallback A/B.
- **P2 — Sprite pipeline**: pixel-matrix cat (idle, sit, walk 4f, run 4f, jump, fall, land, sleep 2f,
  groom, eat, drink, pounce, beg, head-rub, tail-wrap), palette system, recoloring, animation
  test harness. *Verify:* harness cycles all animations at correct scale.
- **P3 — Cat core**: physics + platforms, movement states, brain v1 (needs decay + utility AI:
  wander/sit/sleep/beg), state→animation mapping. *Verify:* cat lives on desktop, jumps onto real
  window tops, needs decay visibly logged.
- **P4 — Pointer interactions**: petting detection, head-rub, tail-wrap, hunt/pounce, attachment XP,
  purr/meow reactions. *Verify:* manual interaction checklist.
- **P5 — Needs loop & sound**: food/water bowls via panel, eat/drink, sleep cycle, thought bubbles,
  retro sound pack synthesis + playback + mute/volume in tray. *Verify:* full
  hunger→beg→feed→satisfied loop with sound on/off.
- **P6 — Toys**: ball (bounce + cat bats it), plush mouse (cat hunts it), string (dangles at cursor
  when summoned from panel); spawn at cursor position. *Verify:* cat chases and interacts.
- **P7 — Wizard, persistence, polish**: first-run customization wizard (live preview, sound pack
  choice), save/load with offline decay, settings (volume/pack/reset), optional CC0 sound pack
  download (with approval), README run instructions, PROGRESS.md final update.
  *Verify:* full acceptance pass against every requirement in §1.

## 5. Documentation for continuation (user requirement)

- `PLAN.md` — this plan, copied into the repo at P0.
- `DECISIONS.md` — measured environment facts + every architectural decision with its fallback.
- `PROGRESS.md` — living status file: what's done, what's next, known issues; updated at the end
  of every work session so a new session/AI can resume cold.
- `README.md` — how to run (`run.sh`), controls, settings, attribution for CC0 assets if used.

## 6. Risks

| Risk | Mitigation |
|---|---|
| `WindowTransparentForInput` broken on Qt6/Wayland | Fallback A (XWayland overlay), Fallback B (layer-shell QPA) |
| QtMultimedia has no working backend in venv wheel | Fallback: `pw-play`/`paplay` subprocess for WAV playback |
| Fullscreen+keepAbove behaves oddly (panels, screenshots) | Accept cat drawn over panels (input passes through); tune via KWin script |
| KWin script left loaded after crash | Inert without our DBus service; `run.sh --unload-bridge`; auto-unload on clean exit |
| Hand-authored pixel art quality | Harness-driven iteration in P2; placeholder-first, refine before P7 |
