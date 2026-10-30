/**
 * Account chip of the map pages: always visible, bottom-left under the color legend. It shows the user's avatar (initials),
 * the name, the role badge (admins only) and the "Cerrar sesión" button. For admins it also reveals the
 * admin panel link that lives in the settings panel.
 */
import { authApi } from '../auth-api.js';

export const ROLE_LABELS = { admin: 'Administrador', org_admin: 'Admin de empresa', viewer: 'Lector' };

/** Up to two letters: initials of the first two words, or the first two characters of one word. */
export function initialsOf(name) {
    const words = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (words.length === 0) return '?';
    const letters = words.length > 1 ? words[0][0] + words[1][0] : words[0].slice(0, 2);
    return letters.toUpperCase();
}

export function renderSessionBox(me) {
    const displayName = me.full_name || me.username;

    const adminLink = document.getElementById('admin-link');
    if (adminLink) adminLink.hidden = me.role !== 'admin';
    const chipAdminLink = document.getElementById('admin-chip-link');
    if (chipAdminLink) chipAdminLink.hidden = me.role !== 'admin';
    // Company admins get a shortcut to their own panel (spec C).
    const chipEmpresaLink = document.getElementById('empresa-chip-link');
    if (chipEmpresaLink) chipEmpresaLink.hidden = me.role !== 'org_admin';

    const chip = document.getElementById('account-chip');
    if (!chip) return;
    chip.title = `${displayName} (${ROLE_LABELS[me.role] || me.role})`;
    chip.setAttribute('aria-label', `Cuenta de ${displayName}`);

    document.getElementById('account-avatar').textContent = initialsOf(displayName);
    document.getElementById('account-name').textContent = displayName;
    const role = document.getElementById('account-role');
    role.textContent = ROLE_LABELS[me.role] || me.role;
    role.classList.toggle('is-admin', me.role === 'admin');
    // The role badge is only worth the space when it is not the everyday case.
    role.hidden = me.role === 'viewer';
    document.getElementById('session-box-logout').addEventListener('click', async () => {
        await authApi.logout();
        window.location.reload();  // nginx serves the login in place
    });
    chip.hidden = false;
}
