const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

function monitor() {
  const storage = new Map();
  const invalidated = [];
  const state = {data: undefined, options: undefined, changes: 0};
  const ref = {current: ""};
  const modules = {
    react: {
      useEffect: effect => effect(), useRef: () => ref,
      useSyncExternalStore: (subscribe, snapshot) => {subscribe(() => state.changes++); return snapshot();},
    },
    "@tanstack/react-query": {
      useQuery: options => {state.options = options; return {data: state.data};},
      useQueryClient: () => ({invalidateQueries: ({queryKey}) => {invalidated.push(queryKey[0]); return Promise.resolve();}}),
    },
    "./api": {api: {getBatchStatus: async () => state.data}},
  };
  const context = {exports: {}, require: id => modules[id], sessionStorage: {
    getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key),
  }};
  const source = fs.readFileSync(path.join(__dirname, "../src/lib/parsing-batch.ts"), "utf8");
  vm.runInNewContext(ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2017}}).outputText, context);
  return {api: context.exports, state, invalidated};
}

test("a newly started library batch is immediately shared with the verification view", () => {
  const {api, state} = monitor();
  assert.equal(api.useParsingBatch().batchId, "");
  api.setParsingBatch("library-batch");
  assert.ok(state.changes > 0);
  assert.equal(api.useParsingBatch().batchId, "library-batch");
  api.setParsingBatch("");
  assert.equal(api.useParsingBatch().batchId, "");
});

test("each saved profile refreshes both views before the batch completes", () => {
  const {api, state, invalidated} = monitor();
  api.setParsingBatch("live");
  state.data = {processed_files: 0, failed_files: 0, status: "PROCESSING"};
  api.useLiveParsingUpdates();
  assert.equal(invalidated.length, 0);
  state.data = {...state.data, processed_files: 1};
  api.useLiveParsingUpdates();
  assert.deepEqual(invalidated, ["recruiter-candidates", "cv-library"]);
  api.useLiveParsingUpdates();
  assert.equal(invalidated.length, 2);
  state.data = {...state.data, processed_files: 2};
  api.useLiveParsingUpdates();
  assert.equal(invalidated.length, 4);
});

test("only the central monitor polls active batches and polling stops on completion", () => {
  const {api, state} = monitor();
  api.setParsingBatch("live");
  api.useParsingBatch();
  assert.equal(state.options.refetchInterval({state: {data: {status: "PROCESSING"}}}), false);
  api.useParsingBatch(true);
  assert.equal(state.options.refetchInterval({state: {data: {status: "PROCESSING"}}}), 1000);
  assert.equal(state.options.refetchInterval({state: {data: {status: "COMPLETED"}}}), false);
  assert.equal(state.options.refetchInterval({state: {data: {status: "CANCELLED"}}}), false);
  for (const status of ["PARTIAL", "FAILED", "INTERRUPTED"]) {
    assert.equal(state.options.refetchInterval({state: {data: {status}}}), false);
  }
  assert.equal(state.options.refetchOnMount, false);
  assert.equal(state.options.refetchOnWindowFocus, false);
  assert.equal(state.options.refetchOnReconnect, false);
});
