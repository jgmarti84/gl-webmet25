/**
 * Session box of the main map: current user, "Cerrar sesión", and the admin link only for admins.
 */
import { authApi } from '../auth-api.js';

export function renderSessionBox(me) {
    const box = document.getElementById('session-box');
    const adminLink = document.getElementById('admin-link');
    if (adminLink && me.role !== 'admin') adminLink.hidden = true;
    if (!box) return;

    document.getElementById('session-box-user').textContent = me.full_name || me.username;
    document.getElementById('session-box-logout').addEventListener('click', async () => {
        await authApi.logout();
        window.location.reload();  // nginx serves the login in place
    });
    box.hidden = false;
}
