const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

// Exercise the actual controller with deterministic time and browser events.
function mount({reduced = false} = {}) {
  let now = 10000, sequence = 0;
  const timers = new Map(), effects = [], refs = [], classes = new Set();
  const listeners = new Map();
  const surface = prefix => ({
    addEventListener: (name, callback) => listeners.set(`${prefix}:${name}`, callback),
    removeEventListener: name => listeners.delete(`${prefix}:${name}`),
  });
  const rig = {style: {transform: ""}};
  const el = {dataset: {}, querySelector: () => rig, offsetWidth: 64,
    classList: {add: value => classes.add(value), remove: (...values) => values.forEach(value => classes.delete(value))},
    getBoundingClientRect: () => ({left: 0, top: 0, width: 64, height: 64, right: 64}), contains: () => false};
  const doc = {hidden: false, ...surface("document"), documentElement: surface("html")};
  const media = {matches: reduced, ...surface("motion")};
  let queryListener, mutationListener;
  const cache = {
    getQueryCache: () => ({subscribe: callback => {queryListener = callback; return () => {queryListener = null;};}}),
    getMutationCache: () => ({subscribe: callback => {mutationListener = callback; return () => {mutationListener = null;};}}),
  };
  const context = {exports: {}, Date: {now: () => now}, Element: class {},
    setTimeout: (callback, delay) => {const id = ++sequence; timers.set(id, {callback, at: now + delay}); return id;},
    clearTimeout: id => timers.delete(id), requestAnimationFrame: callback => {const id = ++sequence; timers.set(id, {callback, at: now + 16}); return id;},
    cancelAnimationFrame: id => timers.delete(id), document: doc,
    window: {...surface("window"), innerWidth: 1000, innerHeight: 800,
      matchMedia: query => query.includes("reduced") ? media : {matches: true}},
    require: name => {
      if (name === "react") return {useRef: initial => {const ref = {current: initial}; refs.push(ref); return ref;},
        useEffect: callback => effects.push(callback), useId: () => "test", useSyncExternalStore: () => []};
      if (name === "react/jsx-runtime") return require(name);
      if (name === "@tanstack/react-query") return {useQueryClient: () => cache};
      if (name === "./process-indicator") return {useWorkspaceActivity: () => false};
      return {};
    }};
  const source = fs.readFileSync(path.join(__dirname, "../src/components/recruiter/ghost-mascot.tsx"), "utf8");
  vm.runInNewContext(ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX}}).outputText, context);
  context.exports.GhostMascot({activityKey: "jobs"});
  refs[0].current = el;
  const cleanup = effects[0]();
  const advance = amount => {
    const end = now + amount;
    for (;;) {
      const due = [...timers].filter(([, timer]) => timer.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!due) break;
      now = due[1].at; timers.delete(due[0]); due[1].callback();
    }
    now = end;
  };
  return {el, rig, doc, timers, listeners, cleanup, advance, react: name => refs[1].current.react(name),
    queryError: () => queryListener({type: "updated", action: {type: "error"}}),
    mutationSuccess: () => mutationListener({type: "updated", action: {type: "success"}})};
}

test("expressions return to idle and random idle animation is scheduled", () => {
  const ghost = mount();
  ghost.react("happy");
  assert.equal(ghost.el.dataset.expression, "happy");
  ghost.advance(1950);
  assert.equal(ghost.el.dataset.expression, "idle");
  ghost.advance(9000);
  assert.ok(ghost.timers.size > 0);
  ghost.cleanup();
  assert.equal(ghost.timers.size, 0);
  assert.equal(ghost.listeners.size, 0);
});

test("cursor motion is clamped and does not override an active expression", () => {
  const ghost = mount();
  ghost.listeners.get("window:pointermove")({pointerType: "mouse", clientX: 100000, clientY: 100000});
  ghost.advance(16);
  const values = ghost.rig.style.transform.match(/-?[\d.]+/g).map(Number);
  assert.ok(Math.abs(values[0]) <= 28 && Math.abs(values[1]) <= 22);
  ghost.react("curious");
  ghost.listeners.get("window:pointermove")({pointerType: "mouse", clientX: 0, clientY: 0});
  ghost.advance(16);
  assert.equal(ghost.rig.style.transform, "");
  ghost.cleanup();
});

test("reduced motion and hidden tabs suspend animation work", () => {
  const reduced = mount({reduced: true});
  reduced.react("happy");
  assert.equal(reduced.timers.size, 0);
  reduced.cleanup();
  const ghost = mount();
  ghost.react("curious");
  ghost.doc.hidden = true;
  ghost.listeners.get("document:visibilitychange")();
  assert.equal(ghost.timers.size, 0);
  assert.equal(ghost.el.dataset.paused, "true");
  ghost.doc.hidden = false;
  ghost.listeners.get("document:visibilitychange")();
  assert.equal(ghost.timers.size, 1);
  ghost.cleanup();
});

test("errors react without a false success celebration", () => {
  const ghost = mount();
  ghost.queryError();
  assert.equal(ghost.el.dataset.expression, "surprised");
  ghost.advance(1700);
  ghost.mutationSuccess();
  assert.equal(ghost.el.dataset.expression, "idle");
  ghost.advance(1500);
  ghost.mutationSuccess();
  assert.equal(ghost.el.dataset.expression, "happy");
  ghost.cleanup();
});
