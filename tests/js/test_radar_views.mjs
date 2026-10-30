/**
 * Unit tests for radar-views.js: who may open a one-radar detail view, and the admin summary.
 * Run with: node tests/js/test_radar_views.mjs
 */
const { ALL_RADARS, canOpenDetailView, viewsSummary } = await import('../../frontend/public/js/shared/radar-views.js');

let passed = 0;
let failed = 0;
function assert(cond, msg) {
    if (cond) { console.log(`  ✓  ${msg}`); passed++; }
    else { console.error(`  ✗  ${msg}`); failed++; }
}

console.log('T1: canOpenDetailView');
assert(canOpenDetailView('RMA1', ['RMA1', 'RMA17']) === true, 'a listed radar opens');
assert(canOpenDetailView('RMA5', ['RMA1']) === false, 'an unlisted radar does not');
assert(canOpenDetailView('RMA1', []) === false, 'an empty list opens nothing');
assert(canOpenDetailView('RMA1', undefined) === false, 'a missing list opens nothing');

console.log('T2: viewsSummary');
assert(viewsSummary([]) === 'Ninguna', 'no views');
assert(viewsSummary([ALL_RADARS]) === 'Todas', 'the wildcard');
assert(viewsSummary(['RMA1', 'RMA17']) === 'RMA1, RMA17', 'a list');

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
