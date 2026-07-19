// plasmacat-bridge.js — persistent KWin helper script for PlasmaCat.
// Loaded via org.kde.kwin.Scripting.loadScript(path, "plasmacat-bridge").
// Pushes cursor position and window-top platforms to the PlasmaCat app over DBus,
// and tags the PlasmaCat overlay window so it stays above everything on all desktops.
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

function call(method, payload) {
  callDBus(SERVICE, OBJPATH, IFACE, method, payload);
}

function isPlasmaCatWindow(w) {
  return w.resourceClass === "plasmacat";
}

function tagWindow(w) {
  if (!isPlasmaCatWindow(w)) return;
  w.skipTaskbar = true;
  w.skipSwitcher = true;
  w.skipPager = true;
  w.desktops = []; // on all desktops
  if (w.caption.indexOf("plasmacat-furniture") >= 0) {
    w.keepBelow = true;   // furniture lives behind all windows (desktop level)
  } else {
    w.keepAbove = true;   // the cat herself stays on top
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

function sendWorkArea() {
  const a = workspace.clientArea(KWin.WorkArea, workspace.activeScreen,
                                 workspace.currentDesktop);
  call("SetWorkArea", JSON.stringify({x: Math.round(a.x), y: Math.round(a.y),
                                      w: Math.round(a.width), h: Math.round(a.height)}));
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
  w.frameGeometryChanged.connect(sendWorkArea); // panel/strut changes too
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
workspace.currentDesktopChanged.connect(sendWorkArea);
workspace.currentActivityChanged.connect(sendWorkArea);
workspace.desktopsChanged.connect(sendWorkArea);
workspace.desktopLayoutChanged.connect(sendWorkArea);
workspace.screensChanged.connect(sendWorkArea);
workspace.virtualScreenGeometryChanged.connect(sendWorkArea);
workspace.cursorPosChanged.connect(onCursor);

sendWindows();
sendWorkArea();
