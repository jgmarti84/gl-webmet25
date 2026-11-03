/**
 * Unit tests for shared/profile-section.js: the rows and notes the profile shows (the same section is drawn inside
 * the admin panel, the company panel and the viewer's /perfil page).
 * Run with: node tests/js/test_profile_section.mjs
 */
const { formatDate, profileRows, viewsNote } = await import('../../frontend/public/js/shared/profile-section.js');

let passed = 0;
let failed = 0;
function assert(cond, msg) {
    if (cond) { console.log(`  ✓  ${msg}`); passed++; }
    else { console.error(`  ✗  ${msg}`); failed++; }
}

const profile = {
    username: 'ana',
    full_name: 'Ana Pérez',
    email: 'ana@example.com',
    role: 'org_admin',
    organization_name: 'EPEC',
    created_at: '2026-10-20T14:30:00Z',
    last_login_at: null,
    radar_detail_views: [],
};

console.log('T1: dates');
assert(formatDate(null) === '—' && formatDate('') === '—', 'no date: a dash');
assert(formatDate('2026-10-20T14:30:00Z').includes('2026'), 'a real date shows its year');

console.log('T2: rows of the account data');
const rows = Object.fromEntries(profileRows(profile));
assert(rows['Usuario'] === 'ana' && rows['Nombre'] === 'Ana Pérez' && rows['Mail'] === 'ana@example.com', 'user, name and mail');
assert(rows['Rol'] === 'Admin de empresa', 'the role is shown with its label, not its code');
assert(rows['Empresa'] === 'EPEC', 'the company name');
assert(rows['Último ingreso'] === '—', 'a user who never logged in: a dash');
const bare = Object.fromEntries(profileRows({ ...profile, full_name: null, email: null, organization_name: null, role: 'viewer' }));
assert(bare['Nombre'] === '—' && bare['Mail'] === '—' && bare['Empresa'] === '—', 'missing name, mail and company: dashes');

console.log('T3: the note under the radar views');
assert(viewsNote('admin').includes('administrador general'), 'the general admin sees every enabled radar');
assert(!viewsNote('viewer').includes('administrador general'), 'other roles get the plain note');

console.log(`\n${'─'.repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) { console.error('TESTS FAILED'); process.exit(1); }
else console.log('ALL TESTS PASSED');
