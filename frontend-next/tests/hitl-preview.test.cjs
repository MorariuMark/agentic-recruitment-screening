const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
const {webcrypto} = require("node:crypto");

function apiWithFetch(fetch) {
  const source = fs.readFileSync(path.join(__dirname, "../src/lib/api.ts"), "utf8");
  const output = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
  const context = {exports: {}, window: {}, process: {env: {}}, Headers, FormData,
    AbortController, DOMException, crypto: webcrypto, setTimeout, clearTimeout, fetch,
    require: name => {
      if (name === "./workspace-session") return {workspaceId: () => "demo-tab", registerWorkspaceRequest: () => () => {}};
      if (name === "./processes") return {trackProcess: () => () => {}};
      throw new Error(`Unexpected runtime import: ${name}`);
    }};
  vm.runInNewContext(output, context);
  return context.exports.api;
}

test("human correction preview sends all edits and uses the server totals", async () => {
  let request;
  const serverResult = {id: "evaluation", overall_score: 75, must_have_score: 100, nice_to_have_score: 0};
  const api = apiWithFetch(async (url, options) => {
    request = {url, options};
    return {ok: true, json: async () => serverResult};
  });
  const matches = [{requirement_id: "required", status: "met", score: 1},
    {requirement_id: "preferred", status: "not_met", score: 0}];
  assert.equal(await api.previewHITLCorrections("evaluation", matches), serverResult);
  assert.equal(request.url, "/api/v1/hitl/preview");
  assert.equal(request.options.method, "POST");
  assert.equal(request.options.credentials, "include");
  assert.deepEqual(JSON.parse(request.options.body), {evaluation_id: "evaluation", updated_matches: matches});
});

test("invalid corrections surface the server error without fabricating a preview", async () => {
  const api = apiWithFetch(async () => ({ok: false, status: 422, statusText: "Unprocessable Entity",
    headers: new Headers({"content-type": "application/json"}),
    json: async () => ({detail: "Missing evaluation match for requirement Python"})}));
  await assert.rejects(api.previewHITLCorrections("evaluation", []), /Missing evaluation match/);
});
