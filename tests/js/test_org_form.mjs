/**
 * Unit tests for shared/org-form.js: what the "Agregar institución" form offers and what it sends (the company with its
 * optional admin and radar views, in one request).
 * Run with: node tests/js/test_org_form.mjs
 */
const { eligibleAdmins, buildOrganizationPayload, buildMemberRequest } = await import('../../frontend/public/js/shared/org-form.js');

let passed = 0;
let failed = 0;
function assert(cond, msg) {
    if (cond) { console.log(`  ✓  ${msg}`); passed++; }
    else { console.error(`  ✗  ${msg}`); failed++; }
}
function throws(fn) {
    try { fn(); } catch (error) { return error.message; }
    return null;
}

console.log('T1: which users can be chosen as the admin of a new company');
const users = [
    { id: 1, username: 'zeta', role: 'viewer', is_active: true, organization_id: null },
    { id: 2, username: 'ana', role: 'viewer', is_active: true, organization_id: null },
    { id: 3, username: 'beto', role: 'viewer', is_active: true, organization_id: 7 },   // already in a company
    { id: 4, username: 'dora', role: 'viewer', is_active: false, organization_id: null }, // deactivated
    { id: 5, username: 'jefe', role: 'org_admin', is_active: true, organization_id: 7 },
    { id: 6, username: 'boss', role: 'admin', is_active: true, organization_id: null },
];
const chosen = eligibleAdmins(users).map((user) => user.username);
assert(JSON.stringify(chosen) === JSON.stringify(['ana', 'zeta']), 'only active viewers without a company, sorted by name');
assert(eligibleAdmins([]).length === 0, 'no users: an empty list');

console.log('T2: the payload without admin or views is the old one');
const base = { name: 'EPEC', seatLimit: '5', isActive: true, adminMode: 'none', radars: [], allViews: false };
const plain = buildOrganizationPayload(base);
assert(plain.name === 'EPEC' && plain.seat_limit === 5 && plain.is_active === true, 'name, seats as a number, active');
assert(!('admin' in plain) && !('radar_detail_view' in plain), 'no admin and no views: those keys are not sent');

console.log('T3: a new admin');
const withNew = buildOrganizationPayload({
    ...base,
    adminMode: 'new',
    newAdmin: { username: 'jefa', password: 'una-clave-larga-1', fullName: 'Jefa Nueva', email: '' },
});
assert(withNew.admin.mode === 'new' && withNew.admin.username === 'jefa', 'mode and username');
assert(withNew.admin.password === 'una-clave-larga-1' && withNew.admin.full_name === 'Jefa Nueva', 'password and name');
assert(withNew.admin.email === null, 'an empty mail is sent as null');
assert(throws(() => buildOrganizationPayload({ ...base, adminMode: 'new', newAdmin: { username: '', password: 'x' } })) !== null,
    'a new admin needs a username and a password');

console.log('T4: an existing admin');
const withExisting = buildOrganizationPayload({ ...base, adminMode: 'existing', existingUserId: '2' });
assert(withExisting.admin.mode === 'existing' && withExisting.admin.user_id === 2, 'mode and the id as a number');
assert(!('username' in withExisting.admin), 'no new-user fields are sent with an existing user');
assert(throws(() => buildOrganizationPayload({ ...base, adminMode: 'existing', existingUserId: '' })) !== null,
    'choosing "existing" without choosing a user is an error');

console.log('T5: the radar views');
const some = buildOrganizationPayload({ ...base, radars: ['RMA1', 'RMA17'] });
assert(JSON.stringify(some.radar_detail_view) === JSON.stringify(['RMA1', 'RMA17']), 'the ticked radars');
const all = buildOrganizationPayload({ ...base, allViews: true, radars: ['RMA1'] });
assert(JSON.stringify(all.radar_detail_view) === JSON.stringify(['*']), '"Todas" wins over the individual radars');

console.log('T6: everything together');
const full = buildOrganizationPayload({
    ...base,
    adminMode: 'existing',
    existingUserId: '2',
    radars: ['RMA1'],
});
assert(full.admin.user_id === 2 && full.radar_detail_view[0] === 'RMA1' && full.seat_limit === 5, 'admin and views in one payload');

console.log('T7: adding one person to a company that already exists (the "Editar institución" form)');
const member = { organizationId: 7, role: 'viewer' };
assert(buildMemberRequest({ ...member, mode: 'none' }) === null, '"none" (the default) adds nobody');

const invite = buildMemberRequest({ ...member, mode: 'invite', role: 'org_admin', inviteEmail: '  ana@ejemplo.com.ar ' });
assert(invite.kind === 'invite', 'inviting by mail is its own kind of request');
assert(invite.body.email === 'ana@ejemplo.com.ar' && invite.body.organization_id === 7 && invite.body.role === 'org_admin',
    'the invitation carries the trimmed mail, the company and the chosen role');
assert(throws(() => buildMemberRequest({ ...member, mode: 'invite', inviteEmail: '  ' })) !== null,
    'inviting without a mail is an error');

const created = buildMemberRequest({
    ...member,
    mode: 'new',
    newUser: { username: ' lucia ', password: 'clave-larga-1!', fullName: 'Lucía', email: '' },
});
assert(created.kind === 'create' && created.body.username === 'lucia', 'a new user is created with a trimmed username');
assert(created.body.role === 'viewer' && created.body.organization_id === 7, 'it goes into the company with the chosen role');
assert(created.body.full_name === 'Lucía' && created.body.email === null, 'an empty optional field is sent as null');
assert(throws(() => buildMemberRequest({ ...member, mode: 'new', newUser: { username: 'lucia', password: '' } })) !== null,
    'a new user needs a username and a password');

const asViewer = buildMemberRequest({ ...member, mode: 'existing', existingUserId: '12' });
assert(asViewer.kind === 'move' && asViewer.userId === 12, 'an existing user is moved: its id as a number');
assert(asViewer.body.organization_id === 7 && !('role' in asViewer.body), 'as a viewer only the company is sent (the role stays)');
const asAdmin = buildMemberRequest({ ...member, mode: 'existing', role: 'org_admin', existingUserId: '12' });
assert(asAdmin.body.organization_id === 7 && asAdmin.body.role === 'org_admin', 'as admin the role is sent with the company');
assert(throws(() => buildMemberRequest({ ...member, mode: 'existing', existingUserId: '' })) !== null,
    'choosing "existing" without choosing a user is an error');

console.log('T8: the tracking tool of a new company');
const withTool = buildOrganizationPayload({ ...base, tools: { tracking: true } });
assert(JSON.stringify(withTool.tools) === '{"tracking":true}', 'ticked: the tools are sent'); 
assert(!('tools' in buildOrganizationPayload(base)), 'no tools: no tools key (a company is created as before)');
assert(!('tools' in buildOrganizationPayload({ ...base, tools: { tracking: false } })), 'all unticked: no tools key either');

console.log(`\n${'─'.repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) { console.error('TESTS FAILED'); process.exit(1); }
else console.log('ALL TESTS PASSED');
