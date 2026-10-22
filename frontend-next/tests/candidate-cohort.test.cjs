const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const context = {exports: {}};
const source = fs.readFileSync(path.join(__dirname, "../src/lib/candidate-cohort.ts"), "utf8");
vm.runInNewContext(ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2017}}).outputText, context);
const {loadCandidateCohort, cohortSelection} = context.exports;

test("the ranking cohort loads beyond the first 100 and 500 profiles", async () => {
  const candidates = Array.from({length: 1127}, (_, i) => ({id: String(i)}));
  const offsets = [];
  const loaded = await loadCandidateCohort(async (limit, offset) => {
    offsets.push(offset);
    return candidates.slice(offset, offset + limit);
  });
  assert.equal(loaded.length, 1127);
  assert.deepEqual(offsets, [0, 500, 1000]);
  assert.equal(cohortSelection(loaded, 1127).length, 1127);
  assert.equal(cohortSelection(loaded, 275).length, 275);
});

test("invalid cohort sizes cannot silently select a different number", () => {
  const candidates = [{id: "one"}, {id: "two"}];
  for (const count of [0, -1, 1.5, 3, NaN]) assert.equal(cohortSelection(candidates, count), null);
  assert.equal(cohortSelection(candidates, 2).join(","), "one,two");
});

test("a failed later page does not return a misleading partial cohort", async () => {
  await assert.rejects(loadCandidateCohort(async (_limit, offset) => {
    if (offset) throw new Error("Connection interrupted");
    return Array.from({length: 500}, (_, i) => ({id: String(i)}));
  }), /Connection interrupted/);
});
