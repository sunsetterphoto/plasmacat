# Changelog

## 0.2.1 — 2026-11-10

### Added
- **Docks a floating bottom panel while PlasmaCat runs** (System tab, on by
  default): cats and furniture stand exactly on the panel edge. The panel
  floats again when PlasmaCat quits (also after a crash, on the next start or
  `./run.sh --unload-bridge`).

### Fixed
- The cat walked and sat on thin air: invisible helper windows (the XWayland
  video bridge, any window with zero opacity) counted as platforms.
- With a panel set to "dodge windows", the floor — cats, bowls, furniture —
  jumped up and down whenever a window touched the panel. The floor now stays
  on the panel line; only a true auto-hide panel leaves it at the screen edge.

## 0.2.0 — 2026-11-10

A full rework: everything in one Control Center, finer art, real installs
with update offers, and a long list of fixes.

### Added
- **Control Center** (left-click the tray icon): Cats, Play, Home, Sound and
  System tabs, each with its own *Reset to defaults*.
- Move or remove every piece of furniture separately; **arrange mode** on the
  desktop (click to pick up, Del to remove).
- Status board rows, sound groups and notification types are switchable one
  by one; pixel size preference (fine / normal / chunky).
- Cats hide while a window is fullscreen; *Pause cats* in the tray.
- `install.sh` / `uninstall.sh`; a daily update check that **offers** new
  releases — installed only after your click, then PlasmaCat restarts.
- Quiet fountain bubbling, a hiss when cats have a spat, per-effect mix.
- Coat patterns redone: mackerel tabby, round spots, smooth tortoiseshell,
  tuxedo with bib and socks.
- Real closed-eye blinks; `tools/render_sheet.py` and `tools/render_scene.py`.

### Changed
- Sprites render at twice the resolution with light, shadow and a soft
  outline; slit-pupil eyes, whiskers growing from the muzzle, a curved tail,
  a collar that follows the neck.
- Pixel-exact on fractional scaling (no more uneven pixel columns at 125 %,
  150 %, 165 %).
- Runs on the distro's PySide6 (Fedora: `python3-pyside6`); no 400 MB venv.
- Data dir `~/.local/share/catgame` → `~/.local/share/plasmacat` (migrated);
  save format v3.
- The appearance editor replaces the setup wizard.
- Code split into focused modules (brain behaviors, world, UI tabs).

### Fixed
- On Plasma 6.8 the cat stood **behind** a floating panel.
- The cat fell off a window whenever its title changed, and was dragged along
  when a window in front was moved.
- Logout / Ctrl+C lost up to 30 s of progress and left the KWin script loaded.
- Up to ~27 needless work-area updates per second from the cat's own window.
- With two or more cats, head rubs never registered; a resting cursor caused
  phantom hunts and a slow memory leak.
- *Customize → Cancel* still changed the cat; reopening it reset the eye color.
- Multi-monitor: chasing, greeting and jumping down used the wrong screen's
  floor.
- Drinking replayed a loud lapping sound every 1.4 s; the sound fallback never
  engaged; grass regrew faster with more cats.

### Removed
- `PLAN.md` / `DECISIONS.md` (see `docs/ARCHITECTURE.md`), one-off debug
  tools, the copied sound folder, legacy DBus calls.

## 0.1.0 — 2026-08-03

First public release.
