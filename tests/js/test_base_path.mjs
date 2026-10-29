/**
 * Unit tests for base-path.js: the prefix the site is served under, read from <base href>.
 * Run with: node tests/js/test_base_path.mjs
 */
const { basePath, appPath } = await import('../../frontend/public/js/shared/base-path.js');

let passed = 0;
let failed = 0;
function assert(cond, msg) {
    if (cond) { console.log(`  ✓  ${msg}`); passed++; }
    else { console.error(`  ✗  ${msg}`); failed++; }
}

console.log('T1: basePath');
assert(basePath('https://h.example/') === '', 'root: empty prefix');
assert(basePath('https://h.example/nacho/') === '/nacho', 'one segment');
assert(basePath('https://h.example/nacho') === '/nacho', 'without the final slash');
assert(basePath() === '', 'no document (node): empty prefix');

console.log('T2: appPath');
assert(appPath('/nacho/login', '/nacho') === '/login', 'strips the prefix');
assert(appPath('/nacho', '/nacho') === '/', 'the prefix alone is the root');
assert(appPath('/login', '') === '/login', 'no prefix: unchanged');
assert(appPath('/nachos/login', '/nacho') === '/nachos/login', 'a longer segment is not the prefix');

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
