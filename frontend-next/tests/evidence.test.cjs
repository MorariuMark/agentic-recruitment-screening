const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
const source = fs.readFileSync(path.join(__dirname, "../src/lib/evidence.ts"), "utf8");
const output = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}}).outputText;
const context = {exports: {}};
vm.runInNewContext(output, context);
const {sourceSpans} = context.exports;
test("PDF whitespace and punctuation preserve original source offsets", () => {
  const text = "Languages: English\n  (Native)";
  const spans = sourceSpans(text, "English Native");
  assert.equal(spans.length, 1);
  assert.equal(text.slice(...spans[0]), "English\n  (Native");
});
test("technical tokens retain their meaning", () => {
  assert.equal(sourceSpans("C++ and C#", "C").length, 0);
  assert.equal(sourceSpans("C++ and C#", "C++").length, 1);
});
test("Unicode compatibility normalization matches backend policy", () => {
  assert.equal(sourceSpans("ＥＮＧＬＩＳＨ", "english").length, 1);
});

