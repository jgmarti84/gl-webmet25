/**
 * Client of the company admin endpoints (/api/v1/org, spec C). authFetch renews the session on a 401.
 */
import { authFetch } from './auth-api.js';

// Relative on purpose (base path rule): the page's <base href> adds the prefix when the site is served under one.
const BASE = 'api/v1/org';

async function request(path, options = {}) {
    const response = await authFetch(`${BASE}${path}`, {
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    if (response.status === 204) return null;
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
        // The API always answers {"detail": "..."} in Spanish on 4xx; 422 from validation is a list.
        const detail = Array.isArray(body.detail) ? 'Revisá los datos del formulario' : body.detail;
        throw new Error(detail || `Error ${response.status}`);
    }
    return body;
}

export const empresaApi = {
    company() { return request(''); },
    listUsers() { return request('/users'); },
    createUser(payload) { return request('/users', { method: 'POST', body: JSON.stringify(payload) }); },
    patchUser(id, payload) { return request(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }); },
    resetPassword(id, password) {
        return request(`/users/${id}/reset-password`, { method: 'POST', body: JSON.stringify({ password }) });
    },
    revokeSessions(id) { return request(`/users/${id}/revoke-sessions`, { method: 'POST' }); },
    setRadarViews(id, views) {
        return request(`/users/${id}/permissions`, { method: 'PUT', body: JSON.stringify({ radar_detail_view: views }) });
    },
};
