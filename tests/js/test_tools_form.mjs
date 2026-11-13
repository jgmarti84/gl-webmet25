/**
 * Unit tests for tools-form.js: the "Herramientas" form (radar views + one checkbox per tool) and its summaries.
 * Run with: node tests/js/test_tools_form.mjs
 */
const { TOOL_LIST, toolsSummary, toolsFieldsHtml, readTools, hasTool } = await import(
    '../../frontend/public/js/shared/tools-form.js'
);

let passed = 0;
let failed = 0;
function assert(cond, msg) {
    if (cond) { console.log(`  ✓  ${msg}`); passed++; }
    else { console.error(`  ✗  ${msg}`); failed++; }
}
const form = (entries) => ({ get: (name) => (entries[name] ?? null) });
const keys = TOOL_LIST.map((tool) => tool.key);

console.log('TOOL_LIST');
assert(keys.includes('tracking'), 'the storm tracking tool is in the list');
assert(TOOL_LIST.every((tool) => tool.key && tool.label && tool.short), 'every tool has a key, a label and a short name');

console.log('toolsSummary');
assert(toolsSummary(['*'], { tracking: true }) === 'Todas · Tracking', 'views and tracking');
assert(toolsSummary(['RMA1'], { tracking: false }) === 'RMA1', 'views only');
assert(toolsSummary([], { tracking: true }) === 'Ninguna · Tracking', 'tracking without views');
assert(toolsSummary(['RMA1'], undefined) === 'RMA1', 'no tools field: views only');

console.log('toolsFieldsHtml');
const html = toolsFieldsHtml({ values: { tracking: true } });
assert(keys.every((key) => html.includes(`name="tool_${key}"`)), 'one checkbox per tool of the list');
assert(html.includes('checked'), 'checked when on');
assert(!toolsFieldsHtml({ values: { tracking: false } }).includes('checked'), 'unchecked when off');
assert(toolsFieldsHtml({ notes: { tracking: 'No tiene efecto' } }).includes('No tiene efecto'), 'shows the note of a tool');
assert(toolsFieldsHtml({ only: { tracking: false } }) === '', 'only: a tool the institution lacks is not offered, and nothing at all if none');
assert(toolsFieldsHtml({ only: { tracking: true } }).includes('tool_tracking'), 'only: a tool the institution has is offered');

console.log('readTools');
assert(JSON.stringify(readTools(form({ tool_tracking: 'on' }))) === '{"tracking":true}', 'ticked -> true');
assert(JSON.stringify(readTools(form({}))) === '{"tracking":false}', 'not ticked -> false');
assert(JSON.stringify(readTools(form({}), { tracking: false })) === '{}', 'only: tools the institution lacks are not read');

console.log('hasTool');
assert(hasTool({ tools: { tracking: true } }, 'tracking') === true, 'the tool is on');
assert(hasTool({ tools: { tracking: false } }, 'tracking') === false, 'the tool is off');
assert(hasTool({}, 'tracking') === false && hasTool(null, 'tracking') === false, 'no answer: no');

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
