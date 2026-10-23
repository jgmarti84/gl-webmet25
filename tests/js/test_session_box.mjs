/**
 * Unit tests for session-box.js: initials shown on the account button.
 * Run with: node tests/js/test_session_box.mjs
 */
const { initialsOf } = await import('../../frontend/public/js/shared/session-box.js');

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

console.log(`\n${'─'.repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) { console.error('TESTS FAILED'); process.exit(1); }
else console.log('ALL TESTS PASSED');
