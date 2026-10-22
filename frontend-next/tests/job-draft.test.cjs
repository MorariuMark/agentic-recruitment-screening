const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
const source = fs.readFileSync(path.join(__dirname, "../src/lib/job-draft.ts"), "utf8");
const output = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
const context = {exports: {}};
vm.runInNewContext(output, context);
const {validateJobDraft} = context.exports;
const draft = () => ({title: "Imported support role", requirements: [{id: "req_001", title: "English", weight: .7}]});
test("valid imported decimal weights save and continue without rounding", () => {
  for (const weight of [.1, .33, .7, 1.25, 10]) {
    const job = draft(); job.requirements[0].weight = weight;
    assert.equal(validateJobDraft(job, true).length, 0);
  }
});
test("invalid hidden criteria identify the field that needs attention", () => {
  const job = draft(); job.requirements[0].weight = 11;
  assert.equal(validateJobDraft(job)[0].field, "criterion-0-weight");
  job.requirements[0].weight = .7; job.requirements[0].minimum_years_experience = 1.5;
  assert.equal(validateJobDraft(job)[0].field, "criterion-0-years");
});
test("empty or inactive criteria cannot silently continue to screening", () => {
  const job = draft(); job.requirements = [];
  assert.equal(validateJobDraft(job).length, 0);
  assert.equal(validateJobDraft(job, true)[0].field, "criteria");
  job.title = " "; assert.equal(validateJobDraft(job)[0].field, "title");
});
test("duplicate imported criterion IDs are surfaced before saving", () => {
  const job = draft(); job.requirements.push({...job.requirements[0]});
  assert.equal(validateJobDraft(job)[0].field, "criterion-1-title");
});
