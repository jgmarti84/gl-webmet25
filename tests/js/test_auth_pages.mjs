/**
 * Unit tests for auth-pages.js: the form rules and texts shared by the sign-up and recovery pages.
 * Run with: node tests/js/test_auth_pages.mjs
 */
import {
    cooldownLabel,
    errorText,
    statusMessage,
    validatePassword,
    validateRegistration,
} from '../../frontend/public/js/auth-pages.js';

let passed = 0;
let failed = 0;
function assert(cond, msg) {
    if (cond) { console.log(`  ✓  ${msg}`); passed++; }
    else { console.error(`  ✗  ${msg}`); failed++; }
}

const valid = {
    username: 'ana.perez', email: 'ana@ejemplo.com.ar', password: 'una-clave-larga-1', repeat: 'una-clave-larga-1',
    accepted: true,
};

console.log('T1: registration form');
assert(validateRegistration(valid) === null, 'a correct form passes');
assert(validateRegistration({ ...valid, username: 'ab' }) !== null, 'username too short');
assert(validateRegistration({ ...valid, username: 'con@arroba' }) !== null, 'username with @');
assert(validateRegistration({ ...valid, username: 'Ana.Perez' }) === null, 'username is lower-cased before checking');
assert(validateRegistration({ ...valid, email: 'no-es-un-mail' }) !== null, 'bad mail');
assert(validateRegistration({ ...valid, repeat: 'otra-cosa-larga-1' }) !== null, 'passwords differ');
assert(validateRegistration({ ...valid, accepted: false }) !== null, 'terms not accepted');

console.log('T2: password rules');
assert(validatePassword('corta', 'corta') !== null, 'shorter than 12');
assert(validatePassword('x'.repeat(129), 'x'.repeat(129)) !== null, 'longer than 128');
assert(validatePassword(' '.repeat(14), ' '.repeat(14)) !== null, 'only spaces');
assert(validatePassword('ana.perez.123', 'ana.perez.123', 'Ana.Perez.123') !== null, 'same as the username');
assert(validatePassword('una-clave-larga-1', 'una-clave-larga-1') === null, 'a good password');

console.log('T3: texts');
assert(errorText({ detail: 'Ese usuario ya existe' }, 'x') === 'Ese usuario ya existe', 'server text is used');
assert(errorText({ detail: [{ msg: 'x' }] }, 'respaldo') === 'respaldo', 'validation lists fall back');
assert(errorText(null, 'respaldo') === 'respaldo', 'no body falls back');
assert(statusMessage(429, {}).startsWith('Demasiados intentos'), '429 text');
assert(statusMessage(503, {}).includes('no está disponible'), '503 text');
assert(statusMessage(409, { detail: 'Ese usuario ya existe' }) === 'Ese usuario ya existe', '409 uses the server text');
assert(cooldownLabel('Reenviar mail', 42) === 'Reenviar mail (42 s)', 'cooldown label');

console.log(`\n${'─'.repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) { console.error('TESTS FAILED'); process.exit(1); }
else console.log('ALL TESTS PASSED');
