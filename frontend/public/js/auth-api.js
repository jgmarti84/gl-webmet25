// Auth client shared by every page: login, admin panel, map, radar detail and COG browser.
const AUTH_BASE = '/api/v1/auth';

let refreshInFlight = null;

const REFRESH_MARGIN_S = 120;
let accessExpiresAt = 0;      // ms since epoch; 0 = unknown
let keepAliveEnabled = false;
let keepAliveTimer = null;

/** Milliseconds to wait before renewing a token that lives `expiresIn` more seconds. */
export function refreshDelayMs(expiresIn) {
    const lead = Math.min(REFRESH_MARGIN_S, expiresIn / 2);
    return Math.max(0, Math.round((expiresIn - lead) * 1000));
}

function noteAccessExpiry(expiresIn) {
    if (typeof expiresIn !== 'number') return;
    accessExpiresAt = Date.now() + expiresIn * 1000;
    if (keepAliveEnabled) scheduleKeepAlive(expiresIn);
}

/**
 * Refresh the session once, shared by all concurrent callers.
 * Resolves true when the original request should be retried.
 */
export function refreshSession() {
    if (!refreshInFlight) {
        refreshInFlight = (async () => {
            try {
                const response = await fetch(`${AUTH_BASE}/refresh`, { method: 'POST', credentials: 'same-origin' });
                if (response.ok) {
                    const body = await response.json().catch(() => ({}));
                    noteAccessExpiry(body.access_expires_in);
                    return true;
                }
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

/**
 * fetch() for API data. On a 401 it renews the session and retries once; if the session is
 * gone it reloads the page, and nginx then serves the login in place.
 */
export async function authFetch(input, init) {
    const response = await fetch(input, init);
    if (response.status !== 401) return response;
    if (await refreshSession()) {
        const retried = await fetch(input, init);
        if (retried.status !== 401) return retried;
    }
    window.location.reload();
    return response;
}

function scheduleKeepAlive(expiresIn) {
    clearTimeout(keepAliveTimer);
    keepAliveTimer = setTimeout(keepAliveTick, refreshDelayMs(expiresIn));
}

async function keepAliveTick() {
    const before = accessExpiresAt;
    if (!(await refreshSession())) {
        window.location.reload();
        return;
    }
    // A refresh race gives no new lifetime: ask /me for the cookie the other tab obtained.
    if (accessExpiresAt === before && !(await authApi.me())) window.location.reload();
}

function onVisibilityChange() {
    if (document.visibilityState !== 'visible' || !accessExpiresAt) return;
    if (accessExpiresAt - Date.now() < REFRESH_MARGIN_S * 1000) keepAliveTick();
}

/** Renew the access token shortly before it expires, also after the tab was in background. */
export function startSessionKeepAlive() {
    if (keepAliveEnabled) return;
    keepAliveEnabled = true;
    document.addEventListener('visibilitychange', onVisibilityChange);
    if (accessExpiresAt) scheduleKeepAlive((accessExpiresAt - Date.now()) / 1000);
}

/**
 * Entry point of every protected page: resolves the current user and starts the keep-alive.
 * Resolves null (and reloads, so nginx shows the login) when there is no session.
 */
export async function initPageSession() {
    const me = await authApi.me();
    if (!me) {
        window.location.reload();
        return null;
    }
    startSessionKeepAlive();
    return me;
}

/** Accept only same-site absolute paths, to avoid open redirects. */
export function safeNextPath(raw, fallback = '/') {
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
        if (!response.ok) return null;
        const me = await response.json();
        noteAccessExpiry(me.access_expires_in);
        return me;
    },

    async login(username, password) {
        const response = await fetch(`${AUTH_BASE}/login`, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        if (response.ok) {
            const body = await response.json().catch(() => ({}));
            noteAccessExpiry(body.access_expires_in);
        }
        return { ok: response.ok, status: response.status };
    },

    async logout() {
        await fetch(`${AUTH_BASE}/logout`, { method: 'POST', credentials: 'same-origin' });
    },
};
