const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

function session() {
  const values = new Map([["atos_recruiter_batch", "old-batch"], ["unrelated", "keep"]]);
  const navigation = [];
  let nextId = 0;
  const context = {exports: {}, AbortController, DOMException, Date,
    crypto: {randomUUID: () => `tab-${++nextId}`},
    sessionStorage: {getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key)},
    window: {location: {pathname: "/"}, history: {replaceState: (...args) => navigation.push(args)}}};
  const source = fs.readFileSync(path.join(__dirname, "../src/lib/workspace-session.ts"), "utf8");
  vm.runInNewContext(ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2017}}).outputText, context);
  return {api: context.exports, values, navigation};
}

test("workspace identity is stable inside a tab and separate between tabs", () => {
  const first = session(), second = session();
  assert.equal(first.api.workspaceId(), first.api.workspaceId());
  assert.equal(first.values.get("atos_workspace_id"), first.api.workspaceId());
  first.values.set("atos_workspace_id", "tab-a");
  second.values.set("atos_workspace_id", "tab-b");
  assert.notEqual(first.api.workspaceId(), second.api.workspaceId());
});

test("successful reset aborts outstanding reads and prevents new work until complete", () => {
  const {api} = session();
  const pending = new AbortController();
  api.registerWorkspaceRequest(pending, "/api/v1/candidates");
  api.beginWorkspaceReset();
  assert.throws(() => api.registerWorkspaceRequest(new AbortController(), "/api/v1/screening/rank"), {name: "AbortError"});
  const reset = new AbortController();
  const unregister = api.registerWorkspaceRequest(reset, "/api/v1/processes/reset");
  unregister();
  api.finishWorkspaceReset(true);
  assert.equal(pending.signal.aborted, true);
  assert.equal(reset.signal.aborted, false);
  api.registerWorkspaceRequest(new AbortController(), "/api/v1/candidates");
});

test("reset clears only tab progress and navigation, preserving unrelated storage", () => {
  const {api, values, navigation} = session();
  const id = api.workspaceId();
  api.clearWorkspaceSession();
  assert.equal(values.has("atos_recruiter_batch"), false);
  assert.equal(values.get("unrelated"), "keep");
  assert.equal(api.workspaceId(), id);
  assert.ok(api.freshWorkspaceAfter() > 0);
  assert.equal(navigation[0][2], "/?step=jobs");
});

test("a failed reset leaves pending requests and saved view state available", () => {
  const {api, values} = session();
  const controller = new AbortController();
  api.registerWorkspaceRequest(controller, "/api/v1/candidates");
  api.beginWorkspaceReset();
  api.finishWorkspaceReset(false);
  assert.equal(controller.signal.aborted, false);
  assert.equal(values.get("atos_recruiter_batch"), "old-batch");
});
