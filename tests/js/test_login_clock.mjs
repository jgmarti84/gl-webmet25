/**
 * Unit tests for login-clock.js: the "HORA LOCAL" clock of the login page hero.
 * Run with: node tests/js/test_login_clock.mjs
 */
import { formatLocalTime, msUntilNextSecond } from '../../frontend/public/js/login-clock.js';

let passed = 0;
let failed = 0;
function assert(cond, msg) {
    if (cond) { console.log(`  ✓  ${msg}`); passed++; }
    else { console.error(`  ✗  ${msg}`); failed++; }
}

console.log('T1: format');
// Built with the local-time constructor, so the expected text does not depend on the machine's time zone.
assert(formatLocalTime(new Date(2026, 9, 28, 10, 12, 30)) === '10:12:30', 'two digits everywhere');
assert(formatLocalTime(new Date(2026, 9, 28, 5, 3, 9)) === '05:03:09', 'zero padded');
assert(formatLocalTime(new Date(2026, 9, 28, 0, 0, 0)) === '00:00:00', 'midnight is 00, never 24');
assert(formatLocalTime(new Date(2026, 9, 28, 23, 59, 59)) === '23:59:59', 'last second of the day');

console.log('T2: tick alignment');
assert(msUntilNextSecond(new Date(2026, 9, 28, 10, 0, 0, 0)) === 1000, 'just after a tick: wait a full second');
assert(msUntilNextSecond(new Date(2026, 9, 28, 10, 0, 0, 250)) === 750, 'waits only the rest of the second');
assert(msUntilNextSecond(new Date(2026, 9, 28, 10, 0, 0, 999)) === 1, 'never 0: it would spin without waiting');

console.log(`\n${'─'.repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) { console.error('TESTS FAILED'); process.exit(1); }
else console.log('ALL TESTS PASSED');
