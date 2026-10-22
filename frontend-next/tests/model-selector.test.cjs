const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
const React = require("react");
const {renderToStaticMarkup} = require("react-dom/server");

const source = fs.readFileSync(path.join(__dirname, "../src/components/recruiter/workspace.tsx"), "utf8");
const output = ts.transpileModule(source, {compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
}}).outputText;
const modelData = {active_provider: "groq", active_model: "demo-model", fallback_enabled: true,
  providers_catalog: {groq: {name: "Groq", models: [{id: "demo-model", name: "Demo"}, {id: "alternate", name: "Alternate"}]}}};

function renderSelector({data = modelData, active = false, fetching = false, compact = false} = {}) {
  const context = {exports: {}, require: name => {
    if (name === "react" || name === "react/jsx-runtime") return require(name);
    if (name === "lucide-react") return new Proxy({}, {get: () => () => null});
    if (name === "@tanstack/react-query") return {
      useQuery: () => ({data, isFetching: fetching}), useQueryClient: () => ({}),
    };
    if (name === "./process-indicator") return {useWorkspaceActivity: () => active, ProcessIndicator: () => null};
    return {};
  }};
  vm.runInNewContext(output + "\nexports.Selector = EngineSelector;", context);
  return renderToStaticMarkup(React.createElement(context.exports.Selector, {compact}));
}

test("user model selection is enabled when models are available and work is idle", () => {
  for (const compact of [false, true]) {
    const html = renderSelector({compact});
    const select = html.match(/<select[^>]*id="recruiter-model"[^>]*>/)[0];
    assert.doesNotMatch(select, /\bdisabled\b/);
    assert.match(html, /value="groq\|alternate"/);
    assert.doesNotMatch(html, /Managed by Admin/);
  }
});

test("model selection remains locked before catalog loading and during active work", () => {
  for (const options of [{data: null}, {active: true}]) {
    const select = renderSelector(options).match(/<select[^>]*id="recruiter-model"[^>]*>/)[0];
    assert.match(select, /\bdisabled\b/);
  }
});

test("a background catalog refresh does not disable an otherwise usable model selector", () => {
  const select = renderSelector({fetching: true}).match(/<select[^>]*id="recruiter-model"[^>]*>/)[0];
  assert.doesNotMatch(select, /\bdisabled\b/);
});
