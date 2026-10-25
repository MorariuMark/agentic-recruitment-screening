const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
const context = {exports: {}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, "../src/lib/guided-workflow.ts"), "utf8"), {
  compilerOptions: {module: ts.ModuleKind.CommonJS},
}).outputText, context);
const {workflowProgress, workflowStages} = context.exports;
const run = () => ({status: "completed", rows: [{candidate_id: "a", deep_status: "completed", deep_evaluation: {overall_score: 20}}], shortlist_ids: ["a"], decisions: {}, interviews: {}});

test("empty workspaces wait for parsed CVs and a saved role", () => {
  assert.equal(workflowStages[0].id, "library");
  assert.equal(workflowStages.at(-1).id, "interview");
  assert.equal(workflowProgress(0, false, null).complete.some(Boolean), false);
});
test("screening must finish before comparison, including partially successful runs", () => {
  const value = run();
  for (const status of ["ranking", "evaluating", "failed", "cancelled"]) {
    value.status = status;
    assert.equal(workflowProgress(5, true, value).complete[2], false);
  }
  for (const status of ["completed", "partial"]) {
    value.status = status;
    assert.equal(workflowProgress(5, true, value).complete[2], true);
  }
  value.rows[0].deep_status = "pending";
  assert.equal(workflowProgress(5, true, value).complete[2], false);
});
test("low match scores are still completed evaluations; missing evaluations are not", () => {
  const value = run();
  assert.equal(workflowProgress(5, true, value).evaluatedCount, 1);
  value.rows[0].deep_evaluation = null;
  assert.equal(workflowProgress(5, true, value).complete[2], false);
});
test("only saved shortlisted approvals progress to interview", () => {
  const value = run();
  value.decisions.other = {decision: "interview"};
  assert.equal(workflowProgress(5, true, value).complete[3], false);
  value.decisions.a = {decision: "hold"};
  assert.equal(workflowProgress(5, true, value).complete[3], false);
  value.decisions.a = {decision: "interview"};
  assert.equal(workflowProgress(5, true, value).complete[3], true);
  assert.equal(workflowProgress(5, true, value).complete[4], false);
  value.interviews.a = {questions: [{question_text: "Example"}]};
  assert.equal(workflowProgress(5, true, value).complete.every(Boolean), true);
});
