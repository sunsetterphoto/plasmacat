// Tests for the KWin helper script (src/plasmacat/data/kwin/bridge.js).
// The script runs in a vm context with small stubs for the KWin JS API.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const SRC = readFileSync(new URL("../src/plasmacat/data/kwin/bridge.js", import.meta.url), "utf8")
  .replace("__PLASMACAT_IFACE__", "local.plasmacat.BridgeService")
  .replace("__CONTROL_MODE__", "false");

function sig() {
  const fns = [];
  const s = (...a) => fns.forEach((f) => f(...a));
  s.connect = (f) => fns.push(f);
  s.count = () => fns.length;
  return s;
}

function makeWindow(props) {
  return Object.assign({
    resourceClass: "app", caption: "App", normalWindow: true, dock: false,
    minimized: false, fullScreen: false, desktops: [],
    internalId: (() => { const id = "{id-" + Math.random() + "}"; return { toString: () => id }; })(),
    frameGeometry: { x: 10, y: 20, width: 300, height: 200 },
    frameGeometryChanged: sig(), minimizedChanged: sig(), stackingOrderChanged: sig(),
    captionChanged: sig(), windowClassChanged: sig(), fullScreenChanged: sig(),
  }, props);
}

function load({ windows = [], area = { x: 0, y: 0, width: 1745, height: 1091 },
                full = { x: 0, y: 0, width: 1745, height: 1091 } } = {}) {
  const calls = [];
  const timers = [];
  class QTimer {
    constructor() { this.timeout = sig(); this.active = false; timers.push(this); }
    start() { this.active = true; }
    stop() { this.active = false; }
  }
  const workspace = {
    stackingOrder: windows, screens: [{ name: "eDP-1" }], activeScreen: null,
    currentDesktop: 1, activeWindow: null, cursorPos: { x: 0, y: 0 },
    clientArea: (kind) => (kind === 1 ? full : area),
  };
  workspace.activeScreen = workspace.screens[0];
  for (const n of ["windowAdded", "windowRemoved", "currentDesktopChanged", "currentActivityChanged",
                   "desktopsChanged", "desktopLayoutChanged", "screensChanged",
                   "virtualScreenGeometryChanged", "cursorPosChanged", "windowActivated"]) {
    workspace[n] = sig();
  }
  const ctx = {
    workspace, QTimer, KWin: { WorkArea: 0, FullScreenArea: 1 },
    callDBus: (svc, path, iface, method, payload) => calls.push({ method, payload }),
    registerShortcut: () => {},
  };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  const flush = () => timers.filter((t) => t.active).forEach((t) => { t.active = false; t.timeout(); });
  flush();
  calls.length = 0;
  return { ctx, calls, flush, workspace, count: (m) => calls.filter((c) => c.method === m).length };
}

test("visualFloor: floating panel without strut (Plasma 6.8, measured)", () => {
  const { ctx } = load();
  assert.equal(ctx.visualFloor(1091, 0, { y: 1031, height: 60 }), 1039);
});

test("visualFloor: floating panel with strut (Plasma 6.7, measured P43)", () => {
  const { ctx } = load();
  assert.equal(ctx.visualFloor(1045, 46, { y: 1013, height: 62 }), 1021);
});

test("visualFloor: docked panel sits exactly on the area bottom", () => {
  const { ctx } = load();
  assert.equal(ctx.visualFloor(1050, 41, { y: 1050, height: 41 }), 1050);
});

test("work area bottom follows a strut-less floating panel", () => {
  const panel = makeWindow({ dock: true, normalWindow: false, resourceClass: "plasmashell",
                             frameGeometry: { x: 0, y: 1031, width: 1745, height: 60 } });
  const { ctx, calls, flush } = load({ windows: [panel] });
  ctx.sendWorkAreas();
  const areas = JSON.parse(calls.find((c) => c.method === "SetWorkAreas").payload);
  assert.equal(areas[0].h, 1039);
  flush();
});

test("bursts of geometry changes are coalesced into one update", () => {
  const w = makeWindow({});
  const { calls, flush, count } = load({ windows: [w] });
  for (let i = 0; i < 50; i++) w.frameGeometryChanged();
  assert.equal(count("SetWindows"), 0);
  flush();
  assert.equal(count("SetWindows"), 1);
  assert.equal(count("SetWorkAreas"), 0);  // a normal window never moves the floor
  calls.length = 0;
});

test("own window that gets its class late is tagged and never reported", () => {
  const { workspace, flush, count, calls } = load();
  const w = makeWindow({ resourceClass: "", caption: "plasmacat@1,2,240,180" });
  workspace.windowAdded(w);
  flush();
  calls.length = 0;
  w.resourceClass = "plasmacat";
  w.windowClassChanged();
  assert.equal(w.keepAbove, true);
  flush();  // one SetWindows that drops it from the list is expected
  calls.length = 0;
  for (let i = 0; i < 10; i++) w.frameGeometryChanged();
  flush();
  assert.equal(count("SetWindows"), 0);
  assert.equal(count("SetWorkAreas"), 0);
});

test("windows payload carries stable ids and no captions", () => {
  const w = makeWindow({ internalId: { toString: () => "{abc}" }, caption: "secret tab" });
  const { ctx, calls } = load({ windows: [w] });
  ctx.sendWindows();
  const wins = JSON.parse(calls.find((c) => c.method === "SetWindows").payload);
  assert.equal(wins[0].id, "{abc}");
  assert.equal(wins[0].x, 10);
  assert.equal("caption" in wins[0], false);
});

test("active fullscreen window is reported", () => {
  const w = makeWindow({ fullScreen: true });
  const { workspace, calls } = load({ windows: [w] });
  workspace.activeWindow = w;
  workspace.windowActivated(w);
  assert.deepEqual(calls.filter((c) => c.method === "SetActiveFullscreen").map((c) => c.payload), ["1"]);
});

test("a side panel without a strut never becomes the floor", () => {
  const left = makeWindow({ dock: true, normalWindow: false, resourceClass: "plasmashell",
                            frameGeometry: { x: 0, y: 0, width: 60, height: 1091 } });
  const { ctx, calls } = load({ windows: [left] });
  ctx.sendWorkAreas();
  const areas = JSON.parse(calls.find((c) => c.method === "SetWorkAreas").payload);
  assert.equal(areas[0].h, 1091);
});

test("an auto-hidden panel is ignored, and showing it updates the floor", () => {
  const panel = makeWindow({ dock: true, normalWindow: false, resourceClass: "plasmashell",
                             hidden: true, hiddenChanged: sig(),
                             frameGeometry: { x: 0, y: 1031, width: 1745, height: 60 } });
  const { ctx, calls, flush } = load({ windows: [panel] });
  ctx.sendWorkAreas();
  let areas = JSON.parse(calls.filter((c) => c.method === "SetWorkAreas").pop().payload);
  assert.equal(areas[0].h, 1091);
  assert.equal(areas[0].panels[0].hidden, true);   // reported, for the app to decide
  calls.length = 0;
  panel.hidden = false;
  panel.hiddenChanged();
  flush();
  areas = JSON.parse(calls.filter((c) => c.method === "SetWorkAreas").pop().payload);
  assert.equal(areas[0].h, 1039);
});

test("work areas carry the raw bottom and the panels for refinement", () => {
  const panel = makeWindow({ dock: true, normalWindow: false, resourceClass: "plasmashell",
                             frameGeometry: { x: 0, y: 1047, width: 1745, height: 44 } });
  const { ctx, calls } = load({ windows: [panel] });
  ctx.sendWorkAreas();
  const a = JSON.parse(calls.find((c) => c.method === "SetWorkAreas").payload)[0];
  assert.equal(a.raw_bottom, 1091);
  assert.deepEqual(a.panels, [{ y: 1047, h: 44, reserved: 0, hidden: false }]);
});

test("invisible helper windows are never platforms", () => {
  const ghost = makeWindow({ resourceClass: "xwaylandvideobridge", opacity: 0,
                             internalId: { toString: () => "{ghost}" } });
  const faded = makeWindow({ opacity: 0, internalId: { toString: () => "{faded}" } });
  const real = makeWindow({ opacity: 1, internalId: { toString: () => "{real}" } });
  const { ctx, calls } = load({ windows: [ghost, faded, real] });
  ctx.sendWindows();
  const ids = JSON.parse(calls.find((c) => c.method === "SetWindows").payload).map((w) => w.id);
  assert.deepEqual(ids, ["{real}"]);
});
