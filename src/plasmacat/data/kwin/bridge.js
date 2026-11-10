// bridge.js — persistent KWin helper script for PlasmaCat.
// Loaded via org.kde.kwin.Scripting.loadScript(path, "plasmacat-bridge").
//
// Streams to the app over DBus (all arguments are strings, see ARCHITECTURE.md):
//   SetCursor("x,y")              cursor position, ~30 Hz while moving
//   SetWindows("[{id,x,y,w,h}]")  visible normal windows, bottom→top stacking
//   SetWorkAreas("[{x,y,w,h}]")   one walkable area per screen, active screen first
//   SetActiveFullscreen("0|1")    the active window is fullscreen (cat hides)
//   OverlayTagged(caption)        one of our own windows was tagged
//   KeyEvent("left|right|jump|stop")  control mode only
// It also tags PlasmaCat's own windows (keep above / furniture below, all
// desktops) and moves the small front overlay to the rect encoded in its
// title ('plasmacat@x,y,w,h' → frameGeometry), since Wayland clients cannot
// position themselves.

const SERVICE = "org.plasmacat.Bridge";
const OBJPATH = "/Bridge";
// QtDBus generates the interface name at runtime; the app introspects itself
// and fills this placeholder before loading the script.
const IFACE = "__PLASMACAT_IFACE__";
// true only while the user steers the cat: WASD/arrows become global
// shortcuts, which grab the keys system-wide.
const CONTROL = __CONTROL_MODE__;

const CURSOR_INTERVAL_MS = 33;   // ~30 Hz
const COALESCE_MS = 50;          // window/work-area bursts → one update
const FLOAT_GAP_MAX = 8;         // floating panel gap when no strut tells us

var lastCursorSent = 0;
var lastFullscreen = null;
// per-window bookkeeping keyed by internalId (QObject wrappers are not a
// reliable place for ad-hoc JS properties)
const watched = {};
const tagged = {};

function wid(w) {
  return w.internalId.toString();
}

function call(method, payload) {
  callDBus(SERVICE, OBJPATH, IFACE, method, payload);
}

function isPlasmaCatWindow(w) {
  return w.resourceClass === "plasmacat";
}

function isFurnitureWindow(w) {
  return w.caption.indexOf("plasmacat-furniture") === 0;
}

// -- coalescing ---------------------------------------------------------------
// Dragging a window fires frameGeometryChanged every frame; the app only needs
// the latest state, so changes are collected and flushed once per COALESCE_MS.

var pendingWindows = false;
var pendingAreas = false;
const flushTimer = new QTimer();
flushTimer.singleShot = true;
flushTimer.interval = COALESCE_MS;
flushTimer.timeout.connect(function () {
  if (pendingWindows) { pendingWindows = false; sendWindows(); }
  if (pendingAreas) { pendingAreas = false; sendWorkAreas(); }
});

function scheduleWindows() {
  pendingWindows = true;
  flushTimer.start();
}

function scheduleWorkAreas() {
  pendingAreas = true;
  flushTimer.start();
}

// -- our own windows ----------------------------------------------------------

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
  if (tagged[wid(w)]) return;
  tagged[wid(w)] = true;
  w.skipTaskbar = true;
  w.skipSwitcher = true;
  w.skipPager = true;
  w.desktops = []; // all desktops
  if (isFurnitureWindow(w)) {
    w.keepBelow = true;   // furniture lives on the desktop level
  } else {
    w.keepAbove = true;   // the cat stays on top
    applyCaptionGeometry(w);
    w.captionChanged.connect(function () { applyCaptionGeometry(w); });
  }
  call("OverlayTagged", w.caption);
}

// -- data streams -------------------------------------------------------------

function sendWindows() {
  const wins = [];
  const stack = workspace.stackingOrder;
  for (let i = 0; i < stack.length; i++) {
    const w = stack[i];
    if (isPlasmaCatWindow(w) || !w.normalWindow || w.minimized) continue;
    if (w.desktops.length > 0 && w.desktops.indexOf(workspace.currentDesktop) < 0) continue;
    const g = w.frameGeometry;
    wins.push({
      id: wid(w),
      x: Math.round(g.x),
      y: Math.round(g.y),
      w: Math.round(g.width),
      h: Math.round(g.height),
    });
  }
  call("SetWindows", JSON.stringify(wins));
}

// The walkable floor of a screen: the work area's bottom, or the VISUAL top
// of a panel floating over it. A floating panel's frame includes its float
// gap, so its visible top lies `margin` px below the frame top:
//  - with a strut (Plasma 6.7, measured: frame 62, strut 46) the strut is
//    centred in the frame → margin = (h - reserved) / 2 = 8
//  - without a strut (Plasma 6.8, measured: frame 60, area = full screen,
//    visible panel 44) the gap must be assumed → margin = min(8, h / 4)
//  - a docked panel has frame == strut → margin 0
function visualFloor(areaBottom, reserved, dock) {
  const margin = reserved > 0 ? Math.max(0, (dock.height - reserved) / 2)
                              : Math.min(FLOAT_GAP_MAX, dock.height / 4);
  return Math.min(areaBottom, dock.y + margin);
}

function sendWorkAreas() {
  const outs = workspace.screens || [];
  const ordered = [];
  if (workspace.activeScreen) ordered.push(workspace.activeScreen);
  for (let i = 0; i < outs.length; i++) {
    if (outs[i] !== workspace.activeScreen) ordered.push(outs[i]);
  }
  // only visible, horizontal panels can carry a floor (a side panel or an
  // auto-hidden one must never lift it)
  const docks = [];
  const stack = workspace.stackingOrder;
  for (let i = 0; i < stack.length; i++) {
    const w = stack[i];
    const g = w.frameGeometry;
    if (w.dock && !w.hidden && g.width > g.height) docks.push(g);
  }
  const areas = [];
  for (let i = 0; i < ordered.length; i++) {
    const a = workspace.clientArea(KWin.WorkArea, ordered[i], workspace.currentDesktop);
    const fa = workspace.clientArea(KWin.FullScreenArea, ordered[i], workspace.currentDesktop);
    const areaBottom = a.y + a.height;
    const reserved = Math.max(0, (fa.y + fa.height) - areaBottom);  // bottom strut
    let bottom = areaBottom;
    const panels = [];
    for (let d = 0; d < docks.length; d++) {
      const dg = docks[d];
      const hOverlap = dg.x < a.x + a.width && dg.x + dg.width > a.x;
      const atBottom = dg.y + dg.height >= areaBottom - 4;
      if (hOverlap && atBottom && dg.y < areaBottom) {
        bottom = Math.min(bottom, visualFloor(areaBottom, reserved, dg));
        panels.push({ y: Math.round(dg.y), h: Math.round(dg.height),
                      reserved: Math.round(reserved) });
      }
    }
    // the app refines the floor with Plasma's panel settings (floating?
    // thickness?) — it needs the raw bottom and the panels for that
    areas.push({ x: Math.round(a.x), y: Math.round(a.y),
                 w: Math.round(a.width), h: Math.round(bottom - a.y),
                 raw_bottom: Math.round(areaBottom), panels: panels });
  }
  call("SetWorkAreas", JSON.stringify(areas));
}

function sendFullscreen() {
  const w = workspace.activeWindow;
  const fs = !!(w && !isPlasmaCatWindow(w) && w.fullScreen);
  if (fs === lastFullscreen) return;
  lastFullscreen = fs;
  call("SetActiveFullscreen", fs ? "1" : "0");
}

function onCursor() {
  const now = Date.now();
  if (now - lastCursorSent < CURSOR_INTERVAL_MS) return;
  lastCursorSent = now;
  const p = workspace.cursorPos;
  call("SetCursor", Math.round(p.x) + "," + Math.round(p.y));
}

// -- window watching ----------------------------------------------------------
// The class is checked when a signal FIRES, not when the window appears: a
// window may be announced before its app id is known, and our own (moving)
// overlay must never trigger updates.

function watchWindow(w) {
  if (watched[wid(w)]) return;
  watched[wid(w)] = true;
  if (isPlasmaCatWindow(w)) tagWindow(w);
  w.windowClassChanged.connect(function () {
    if (isPlasmaCatWindow(w)) tagWindow(w);
    scheduleWindows();
  });
  w.frameGeometryChanged.connect(function () {
    if (isPlasmaCatWindow(w)) return;
    if (w.dock) scheduleWorkAreas();   // panels move the floor
    else scheduleWindows();
  });
  w.minimizedChanged.connect(function () {
    if (!isPlasmaCatWindow(w)) scheduleWindows();
  });
  w.stackingOrderChanged.connect(function () {
    if (!isPlasmaCatWindow(w)) scheduleWindows();
  });
  w.fullScreenChanged.connect(function () {
    if (!isPlasmaCatWindow(w)) sendFullscreen();
  });
  if (w.hiddenChanged) {
    w.hiddenChanged.connect(function () {
      if (w.dock) scheduleWorkAreas();   // auto-hide panels slide in/out
    });
  }
  if (!isPlasmaCatWindow(w)) {
    scheduleWindows();
    if (w.dock) scheduleWorkAreas();
  }
}

const existing = workspace.stackingOrder;
for (let i = 0; i < existing.length; i++) watchWindow(existing[i]);

workspace.windowAdded.connect(watchWindow);
workspace.windowRemoved.connect(function (w) {
  if (w) { delete watched[wid(w)]; delete tagged[wid(w)]; }
  scheduleWindows();
  if (w && w.dock) scheduleWorkAreas();
});
workspace.windowActivated.connect(sendFullscreen);
workspace.currentDesktopChanged.connect(scheduleWindows);
workspace.currentDesktopChanged.connect(scheduleWorkAreas);
workspace.currentActivityChanged.connect(scheduleWorkAreas);
workspace.desktopsChanged.connect(scheduleWorkAreas);
workspace.desktopLayoutChanged.connect(scheduleWorkAreas);
workspace.screensChanged.connect(scheduleWorkAreas);
workspace.virtualScreenGeometryChanged.connect(scheduleWorkAreas);
workspace.cursorPosChanged.connect(onCursor);

sendWindows();
sendWorkAreas();
sendFullscreen();

// -- control mode -------------------------------------------------------------

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
