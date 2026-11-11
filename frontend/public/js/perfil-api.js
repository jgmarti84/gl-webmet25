/**
 * Client of the profile endpoints (/api/v1/profile, spec D). authFetch renews the session on a 401.
 */
import { authFetch } from './auth-api.js';

// Relative on purpose (base path rule): the page's <base href> adds the prefix when the site is served under one.
const BASE = 'api/v1/profile';

async function request(options = {}) {
    const response = await authFetch(BASE, {
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
        // The API answers {"detail": "..."} in Spanish on 4xx; a 422 from validation is a list.
        const detail = Array.isArray(body.detail) ? 'Revisá los datos del formulario' : body.detail;
        throw new Error(detail || `Error ${response.status}`);
    }
    return body;
}

export const perfilApi = {
    get() { return request(); },
    // Delete the account of the logged-in user (spec G). No id: it always acts on the user of the session.
    deleteAccount() { return request({ method: 'DELETE' }); },
    setName(fullName) { return request({ method: 'PATCH', body: JSON.stringify({ full_name: fullName }) }); },
};
