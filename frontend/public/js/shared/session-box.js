/**
 * Account button + panel of the map pages: the user's initials in the icon bar, and a panel with an
 * avatar, the name, the role, "Cerrar sesión" and, only for admins, the admin panel link.
 */
import { authApi } from '../auth-api.js';

const ROLE_LABELS = { admin: 'Administrador', viewer: 'Lector' };

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

    const button = document.getElementById('btn-account');
    if (!button) return;
    document.getElementById('account-initials').textContent = initialsOf(displayName);
    button.title = `${displayName} (${ROLE_LABELS[me.role] || me.role})`;
    button.setAttribute('aria-label', `Cuenta de ${displayName}`);

    document.getElementById('account-avatar').textContent = initialsOf(displayName);
    document.getElementById('account-name').textContent = displayName;
    const role = document.getElementById('account-role');
    role.textContent = ROLE_LABELS[me.role] || me.role;
    role.classList.toggle('is-admin', me.role === 'admin');
    document.getElementById('session-box-logout').addEventListener('click', async () => {
        await authApi.logout();
        window.location.reload();  // nginx serves the login in place
    });
    button.hidden = false;
}
