/**
 * Logic of the "Agregar institución" form of the admin panel (spec C follow-up): who can be offered as the admin of a new
 * company and the body the form sends. Kept apart from admin.js (which draws the form) so it can be tested without a
 * browser: tests/js/test_org_form.mjs.
 */
import { ALL_RADARS } from './radar-views.js';

/**
 * The users that can be chosen as the admin of a NEW company: active viewers that belong to no company, sorted by
 * name. A user of another company, a company admin, the general admin or a deactivated account are not offered (the
 * server refuses them too).
 */
export function eligibleAdmins(users) {
    return users
        .filter((user) => user.role === 'viewer' && user.is_active && (user.organization_id === null || user.organization_id === undefined))
        .sort((a, b) => a.username.localeCompare(b.username));
}

/** Lower case and without accents, so "Perez" finds "Pérez" and "MARIA" finds "María". */
function plain(text) {
    return String(text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

/**
 * The users whose username, name or mail match what was typed in the search box. The text is split into words and
 * ALL of them must appear somewhere in "username name mail" (in any order), ignoring case and accents. An empty
 * search keeps everybody. The users come back as they were given (not copies) and in the same order.
 */
export function filterAdmins(users, query) {
    const words = plain(query).split(/\s+/).filter(Boolean);
    if (words.length === 0) return users;
    return users.filter((user) => {
        const haystack = plain(`${user.username} ${user.full_name || ''} ${user.email || ''}`);
        return words.every((word) => haystack.includes(word));
    });
}

/**
 * The institutions (or other `{name}` entries, like the "Ninguna" option) whose name matches what was typed in the
 * institution search box of the user form. Same rule as filterAdmins: every word must appear in the name, ignoring
 * case and accents; an empty search keeps everything. Entries come back as given and in the same order.
 */
export function filterOrganizations(items, query) {
    const words = plain(query).split(/\s+/).filter(Boolean);
    if (words.length === 0) return items;
    return items.filter((item) => {
        const haystack = plain(item.name);
        return words.every((word) => haystack.includes(word));
    });
}

/** The "admin" block of the request for the chosen option, or null for "no admin for now". Throws a Spanish message. */
function adminBlock(values) {
    if (values.adminMode === 'new') {
        const admin = values.newAdmin || {};
        const username = String(admin.username || '').trim();
        if (!username || !admin.password) throw new Error('El administrador nuevo necesita un usuario y una contraseña');
        return {
            mode: 'new',
            username,
            password: admin.password,
            full_name: admin.fullName ? admin.fullName : null,
            email: admin.email ? admin.email : null,
        };
    }
    if (values.adminMode === 'existing') {
        if (!values.existingUserId) throw new Error('Elegí el usuario que va a ser administrador de la institución');
        return { mode: 'existing', user_id: Number(values.existingUserId) };
    }
    return null;
}

/**
 * The body of POST /admin/organizations from the values of the form. `admin` and `radar_detail_view` are only sent
 * when they were chosen, so a company without them is created exactly as before. "Todas" wins over single radars.
 *
 * @param {{name: string, seatLimit: string|number, isActive: boolean, adminMode: 'new'|'existing'|'none',
 *          newAdmin?: object, existingUserId?: string, allViews: boolean, radars: string[]}} values
 */
export function buildOrganizationPayload(values) {
    const payload = {
        name: values.name,
        seat_limit: Number(values.seatLimit),
        is_active: values.isActive,
    };
    const admin = adminBlock(values);
    if (admin) payload.admin = admin;
    if (values.allViews) payload.radar_detail_view = [ALL_RADARS];
    else if (values.radars && values.radars.length) payload.radar_detail_view = values.radars;
    return payload;
}
