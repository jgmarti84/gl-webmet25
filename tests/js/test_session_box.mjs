/**
 * Unit tests for session-box.js: initials shown on the account button.
 * Run with: node tests/js/test_session_box.mjs
 */
const { initialsOf, ROLE_LABELS, chipLinksFor } = await import('../../frontend/public/js/shared/session-box.js');

let passed = 0;
let failed = 0;
function assert(cond, msg) {
    if (cond) { console.log(`  ✓  ${msg}`); passed++; }
    else { console.error(`  ✗  ${msg}`); failed++; }
}

console.log('T1: initials');
assert(initialsOf('admin') === 'AD', 'one word: first two letters');
assert(initialsOf('OHMC') === 'OH', 'uppercase word');
assert(initialsOf('Juan Pérez') === 'JP', 'two words: first letter of each');
assert(initialsOf('  María  José   López ') === 'MJ', 'extra spaces and three words');
assert(initialsOf('') === '?' && initialsOf(null) === '?', 'empty name');

console.log('T2: role labels');
assert(ROLE_LABELS.admin === 'Administrador', 'general admin label');
assert(ROLE_LABELS.org_admin === 'Admin de empresa', 'company admin label');
assert(ROLE_LABELS.viewer === 'Lector', 'viewer label');

console.log('T3: which buttons the account chip shows');
const viewer = chipLinksFor('viewer');
assert(viewer.profile === true && viewer.admin === false && viewer.empresa === false, 'viewer: only the profile button');
const companyAdmin = chipLinksFor('org_admin');
assert(companyAdmin.empresa === true && companyAdmin.profile === false && companyAdmin.admin === false, 'company admin: only its panel button (the profile lives inside the panel)');
const generalAdmin = chipLinksFor('admin');
assert(generalAdmin.admin === true && generalAdmin.profile === false && generalAdmin.empresa === false, 'general admin: only the admin panel button');
const unknown = chipLinksFor('otro');
assert(unknown.profile === false && unknown.admin === false && unknown.empresa === false, 'unknown role: no extra buttons');

console.log(`\n${'─'.repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) { console.error('TESTS FAILED'); process.exit(1); }
else console.log('ALL TESTS PASSED');
