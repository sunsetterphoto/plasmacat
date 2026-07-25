// plasmacat-bridge.js — persistent KWin helper script for PlasmaCat.
// Loaded via org.kde.kwin.Scripting.loadScript(path, "plasmacat-bridge").
// Pushes cursor position and window-top platforms to the PlasmaCat app over DBus,
// tags the PlasmaCat overlay windows (above everything / furniture below, all
// desktops), and positions the small front overlay via its title-encoded rect
// ('plasmacat@x,y,w,h' -> frameGeometry; P37).
// All DBus arguments are strings (see DECISIONS.md D3).

const SERVICE = "org.plasmacat.Bridge";
const OBJPATH = "/Bridge";
// Interface name: QtDBus auto-generates it from the shiboken metaobject and it
// is NONDETERMINISTIC (e.g. 'local.py.main.BridgeService' or
// 'local.plasmacat.BridgeService'). bridge/kwin.py introspects the running app
// and replaces __CATGAME_IFACE__ with the discovered name (see DECISIONS.md D10).
const IFACE = "__CATGAME_IFACE__";

const CURSOR_INTERVAL_MS = 33; // ~30 Hz
var lastCursorSent = 0;

// P42 control mode: the app re-renders this script with CONTROL=true while
// the user steers the cat, then reloads it. WASD/arrows become GLOBAL
// shortcuts (they grab the keys system-wide — that's why they only exist
// while the mode is on). Wayland gives overlays no keyboard focus and KWin
// shortcuts fire no key-up, so directions are dead-man's-switch events.
const CONTROL = __CONTROL_MODE__;

function call(method, payload) {
  callDBus(SERVICE, OBJPATH, IFACE, method, payload);
}

function isPlasmaCatWindow(w) {
  return w.resourceClass === "plasmacat";
}

function isFurnitureWindow(w) {
  return w.caption.indexOf("plasmacat-furniture") === 0;
}

// P37: the front overlay is a SMALL window tracking the cat. Wayland clients
// cannot self-position, so the app encodes the desired rect in its title
// ('plasmacat@x,y,w,h') and we apply it here — frameGeometry is read-write.
function applyCaptionGeometry(w) {
  if (w.fullScreen) return; // placement mode uses the whole screen
  const m = /^plasmacat@(-?\d+),(-?\d+),(\d+),(\d+)/.exec(w.caption);
  if (!m) return;
  const x = parseInt(m[1]), y = parseInt(m[2]);
  const width = parseInt(m[3]), height = parseInt(m[4]);
  const g = w.frameGeometry;
  if (g.x === x && g.y === y && g.width === width && g.height === height) return;
  w.frameGeometry = { x: x, y: y, width: width, height: height };
}

function tagWindow(w) {
  if (!isPlasmaCatWindow(w)) return;
  w.skipTaskbar = true;
  w.skipSwitcher = true;
  w.skipPager = true;
  w.desktops = []; // on all desktops
  if (isFurnitureWindow(w)) {
    w.keepBelow = true;   // furniture lives behind all windows (desktop level)
  } else {
    w.keepAbove = true;   // the cat herself stays on top
    applyCaptionGeometry(w);
    w.captionChanged.connect(function () { applyCaptionGeometry(w); });
  }
  call("OverlayTagged", w.caption);
}

function sendWindows() {
  const wins = [];
  const stack = workspace.stackingOrder;
  for (let i = 0; i < stack.length; i++) {
    const w = stack[i];
    if (isPlasmaCatWindow(w)) continue;
    if (!w.normalWindow) continue;
    if (w.minimized) continue;
    if (w.desktops.length > 0 && w.desktops.indexOf(workspace.currentDesktop) < 0) continue;
    const g = w.frameGeometry;
    wins.push({
      x: Math.round(g.x),
      y: Math.round(g.y),
      w: Math.round(g.width),
      h: Math.round(g.height),
      caption: w.caption,
    });
  }
  call("SetWindows", JSON.stringify(wins));
}

function sendWorkAreas() {
  // one work area per screen (P38); the active screen first, so the app's
  // 'primary' area semantics stay stable
  const outs = workspace.screens || [];
  const ordered = [];
  if (workspace.activeScreen) ordered.push(workspace.activeScreen);
  for (let i = 0; i < outs.length; i++) {
    if (outs[i] !== workspace.activeScreen) ordered.push(outs[i]);
  }
  // P43: a FLOATING panel (dock) intrudes into the clientArea — measured:
  // area bottom 1021 vs panel top 1005. The world floor must sit on the
  // panel's VISUAL top or the bottom ~16 px of the furniture hide behind it.
  const docks = [];
  const stack = workspace.stackingOrder;
  for (let i = 0; i < stack.length; i++) {
    if (stack[i].dock) docks.push(stack[i].frameGeometry);
  }
  const areas = [];
  for (let i = 0; i < ordered.length; i++) {
    const a = workspace.clientArea(KWin.WorkArea, ordered[i],
                                   workspace.currentDesktop);
    let bottom = a.y + a.height;
    for (let d = 0; d < docks.length; d++) {
      const dg = docks[d];
      const hOverlap = dg.x < a.x + a.width && dg.x + dg.width > a.x;
      // a bottom-edge dock whose top crosses the area bottom floats over it
      if (hOverlap && dg.y < bottom && dg.y + dg.height >= bottom - 4) {
        bottom = Math.min(bottom, dg.y);
      }
    }
    areas.push({x: Math.round(a.x), y: Math.round(a.y),
                w: Math.round(a.width), h: Math.round(bottom - a.y)});
  }
  call("SetWorkAreas", JSON.stringify(areas));
}

function onCursor() {
  const now = Date.now();
  if (now - lastCursorSent < CURSOR_INTERVAL_MS) return;
  lastCursorSent = now;
  const p = workspace.cursorPos;
  call("SetCursor", Math.round(p.x) + "," + Math.round(p.y));
}

function watchWindow(w) {
  if (isPlasmaCatWindow(w)) {
    tagWindow(w);
    return;
  }
  w.frameGeometryChanged.connect(sendWindows);
  w.frameGeometryChanged.connect(sendWorkAreas); // panel/strut changes too
  w.minimizedChanged.connect(sendWindows);
  w.stackingOrderChanged.connect(sendWindows);
  sendWindows();
}

// Tag already-open windows (in case we load after the overlay appeared) and watch them.
const existing = workspace.stackingOrder;
for (let i = 0; i < existing.length; i++) {
  watchWindow(existing[i]);
}

workspace.windowAdded.connect(watchWindow);
workspace.windowRemoved.connect(sendWindows);
workspace.currentDesktopChanged.connect(sendWindows);
workspace.currentDesktopChanged.connect(sendWorkAreas);
workspace.currentActivityChanged.connect(sendWorkAreas);
workspace.desktopsChanged.connect(sendWorkAreas);
workspace.desktopLayoutChanged.connect(sendWorkAreas);
workspace.screensChanged.connect(sendWorkAreas);
workspace.virtualScreenGeometryChanged.connect(sendWorkAreas);
workspace.cursorPosChanged.connect(onCursor);

sendWindows();
sendWorkAreas();

// P42: register the control keys only in control mode (see CONTROL above)
function reg(name, key, payload) {
  registerShortcut("plasmacat-" + name, "PlasmaCat control: " + name, key,
                   function () { call("KeyEvent", payload); });
}
if (CONTROL) {
  reg("left", "Left", "left");
  reg("left-a", "A", "left");
  reg("right", "Right", "right");
  reg("right-d", "D", "right");
  reg("jump", "Up", "jump");
  reg("jump-w", "W", "jump");
  reg("jump-space", "Space", "jump");
  reg("stop", "Down", "stop");
  reg("stop-s", "S", "stop");
}
