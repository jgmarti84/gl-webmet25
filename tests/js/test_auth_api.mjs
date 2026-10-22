/**
 * Unit tests for auth-api.js: authFetch retry logic and the keep-alive delay.
 * Run with: node tests/js/test_auth_api.mjs
 */
let reloads = 0;
let assigned = [];
const store = new Map();
globalThis.window = {
    location: {
        pathname: '/radar.html', search: '?code=X', hash: '',
        reload() { reloads++; },
        assign(url) { assigned.push(url); },
    },
};
globalThis.sessionStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
};

const queue = [];
const calls = [];
globalThis.fetch = async (url) => {
    calls.push(url);
    const next = queue.shift();
    if (!next) throw new Error(`unexpected fetch ${url}`);
    return next;
};
const res = (status, body = {}) => ({ ok: status >= 200 && status < 300, status, json: async () => body });

const { authFetch, refreshDelayMs } = await import('../../frontend/public/js/auth-api.js');

let passed = 0;
let failed = 0;
function assert(cond, msg) {
    if (cond) { console.log(`  ✓  ${msg}`); passed++; }
    else { console.error(`  ✗  ${msg}`); failed++; }
}
const reset = () => { queue.length = 0; calls.length = 0; reloads = 0; assigned = []; store.clear(); };

console.log('T1: a 200 passes through');
{
    reset();
    queue.push(res(200));
    const r = await authFetch('/api/v1/radars');
    assert(r.status === 200 && calls.length === 1 && reloads === 0, 'one call, no reload');
}

console.log('T2: 401 → refresh → retry');
{
    reset();
    queue.push(res(401), res(200, { access_expires_in: 1800 }), res(200));
    const r = await authFetch('/api/v1/radars');
    assert(r.status === 200, 'retried request succeeds');
    assert(calls[1] === '/api/v1/auth/refresh' && calls[2] === '/api/v1/radars', 'refresh then retry');
    assert(reloads === 0, 'no reload');
}

console.log('T3: 401 → failed refresh → reload');
{
    reset();
    queue.push(res(401), res(401, { detail: 'Sesión vencida' }));
    await authFetch('/api/v1/radars');
    assert(reloads === 1, 'page reloads so nginx shows the login');
}

console.log('T4: 401 → refresh ok → still 401 → reload');
{
    reset();
    queue.push(res(401), res(200, { access_expires_in: 1800 }), res(401));
    await authFetch('/api/v1/radars');
    assert(reloads === 1, 'reloads instead of looping');
    assert(calls.length === 3, 'retries only once');
}

console.log('T5: refresh delay');
{
    assert(refreshDelayMs(1800) === (1800 - 120) * 1000, '2 minutes before a 30-minute token');
    assert(refreshDelayMs(60) === 30 * 1000, 'half the life when shorter than the margin');
    assert(refreshDelayMs(0) === 0, 'never negative');
}

console.log('T6: no reload loop when the page keeps loading without a session');
{
    reset();
    queue.push(res(401), res(401), res(401), res(401));
    await authFetch('/api/v1/radars');
    assert(reloads === 1 && assigned.length === 0, 'first failure reloads (nginx should serve the login)');
    await authFetch('/api/v1/radars');
    assert(reloads === 1, 'second failure within seconds does not reload again');
    assert(assigned.length === 1 && assigned[0].startsWith('/login?next='), 'it goes to /login instead');
    assert(decodeURIComponent(assigned[0]).includes('/radar.html?code=X'), 'and remembers where to come back');
}

console.log(`\n${'─'.repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) { console.error('TESTS FAILED'); process.exit(1); }
else console.log('ALL TESTS PASSED');
