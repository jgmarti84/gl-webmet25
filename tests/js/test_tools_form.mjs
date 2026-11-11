/**
 * Unit tests for tools-form.js: the "Herramientas" form (radar views + the tracking checkbox) and its summaries.
 * Run with: node tests/js/test_tools_form.mjs
 */
const { toolsSummary, trackingFieldHtml, readTools } = await import('../../frontend/public/js/shared/tools-form.js');

let passed = 0;
let failed = 0;
function assert(cond, msg) {
    if (cond) { console.log(`  ✓  ${msg}`); passed++; }
    else { console.error(`  ✗  ${msg}`); failed++; }
}
const form = (entries) => ({ get: (name) => (entries[name] ?? null) });

console.log('toolsSummary');
assert(toolsSummary(['*'], { tracking: true }) === 'Todas · Tracking', 'views and tracking');
assert(toolsSummary(['RMA1'], { tracking: false }) === 'RMA1', 'views only');
assert(toolsSummary([], { tracking: true }) === 'Ninguna · Tracking', 'tracking without views');
assert(toolsSummary(['RMA1'], undefined) === 'RMA1', 'no tools field: views only');

console.log('trackingFieldHtml');
assert(trackingFieldHtml({ checked: true }).includes('checked'), 'checked when on');
assert(!trackingFieldHtml({ checked: false }).includes('checked'), 'unchecked when off');
assert(trackingFieldHtml({ checked: false, note: 'No tiene efecto' }).includes('No tiene efecto'), 'shows the note');

console.log('readTools');
assert(JSON.stringify(readTools(form({ tracking: 'on' }))) === '{"tracking":true}', 'ticked -> true');
assert(JSON.stringify(readTools(form({}))) === '{"tracking":false}', 'not ticked -> false');

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
