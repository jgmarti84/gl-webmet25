// Auth client shared by the login page and the admin panel.
const AUTH_BASE = '/api/v1/auth';

let refreshInFlight = null;

/**
 * Refresh the session once, shared by all concurrent callers.
 * Resolves true when the original request should be retried.
 */
export function refreshSession() {
    if (!refreshInFlight) {
        refreshInFlight = (async () => {
            try {
                const response = await fetch(`${AUTH_BASE}/refresh`, { method: 'POST', credentials: 'same-origin' });
                if (response.ok) return true;
                if (response.status === 401) {
                    const body = await response.json().catch(() => ({}));
                    // Another tab rotated the token; the browser already has the new cookie.
                    return body.code === 'refresh_race';
                }
                return false;
            } catch (error) {
                return false;
            } finally {
                refreshInFlight = null;
            }
        })();
    }
    return refreshInFlight;
}

/** Accept only same-site absolute paths, to avoid open redirects. */
export function safeNextPath(raw, fallback = '/admin') {
    if (typeof raw !== 'string' || !raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\')) {
        return fallback;
    }
    return raw;
}

export function redirectToLogin() {
    const next = window.location.pathname + window.location.search + window.location.hash;
    window.location.assign(`/login?next=${encodeURIComponent(next)}`);
}

export const authApi = {
    /** Current user, trying one refresh; null when there is no session. */
    async me() {
        let response = await fetch(`${AUTH_BASE}/me`, { credentials: 'same-origin' });
        if (response.status === 401 && await refreshSession()) {
            response = await fetch(`${AUTH_BASE}/me`, { credentials: 'same-origin' });
        }
        return response.ok ? response.json() : null;
    },

    async login(username, password) {
        const response = await fetch(`${AUTH_BASE}/login`, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        return { ok: response.ok, status: response.status };
    },

    async logout() {
        await fetch(`${AUTH_BASE}/logout`, { method: 'POST', credentials: 'same-origin' });
    },
};
