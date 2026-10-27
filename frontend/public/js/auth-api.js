// Auth client shared by every page: login, admin panel, map, radar detail and COG browser.
const AUTH_BASE = '/api/v1/auth';

// What the pages may offer when /options cannot be read: nothing extra.
const DEFAULT_OPTIONS = { registration: false, password_recovery: false, terms_url: null, privacy_url: null };

/** POST a JSON body to a public endpoint. Resolves { ok, status, data }; `data` is {} for an empty (204) answer. */
async function postJson(path, body) {
    const response = await fetch(`${AUTH_BASE}${path}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const data = response.status === 204 ? {} : await response.json().catch(() => ({}));
    return { ok: response.ok, status: response.status, data };
}

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

const RELOAD_GUARD_KEY = 'webmet25_auth_reload_at';
const RELOAD_GUARD_MS = 10000;

/**
 * The session is gone: reload so nginx serves the login in place. If this page already reloaded a few
 * seconds ago and still has no session (nginx did not stop it), go to /login instead of looping.
 */
function sessionLost() {
    let last = 0;
    try {
        last = Number(sessionStorage.getItem(RELOAD_GUARD_KEY)) || 0;
        sessionStorage.setItem(RELOAD_GUARD_KEY, String(Date.now()));
    } catch (error) {
        // sessionStorage unavailable: fall through to a plain reload
    }
    if (Date.now() - last < RELOAD_GUARD_MS) {
        redirectToLogin();
        return;
    }
    window.location.reload();
}

/**
 * fetch() for API data. On a 401 it renews the session and retries once; if the session is
 * gone it reloads the page (see sessionLost), and nginx then serves the login in place.
 */
export async function authFetch(input, init) {
    const response = await fetch(input, init);
    if (response.status !== 401) return response;
    if (await refreshSession()) {
        const retried = await fetch(input, init);
        if (retried.status !== 401) return retried;
    }
    sessionLost();
    return response;
}

function scheduleKeepAlive(expiresIn) {
    clearTimeout(keepAliveTimer);
    keepAliveTimer = setTimeout(keepAliveTick, refreshDelayMs(expiresIn));
}

async function keepAliveTick() {
    const before = accessExpiresAt;
    if (!(await refreshSession())) {
        sessionLost();
        return;
    }
    // A refresh race gives no new lifetime: ask /me for the cookie the other tab obtained.
    if (accessExpiresAt === before && !(await authApi.me())) sessionLost();
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
        sessionLost();
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
        const body = await response.json().catch(() => ({}));
        if (response.ok) noteAccessExpiry(body.access_expires_in);
        // `code` tells the page why a login failed beyond the status (e.g. "email_not_verified" on a 403).
        return { ok: response.ok, status: response.status, code: response.ok ? null : body.code || null };
    },

    /** What the pages may offer: sign-up and password recovery. Never throws. */
    async options() {
        try {
            const response = await fetch(`${AUTH_BASE}/options`, { credentials: 'same-origin' });
            return response.ok ? await response.json() : DEFAULT_OPTIONS;
        } catch (error) {
            return DEFAULT_OPTIONS;
        }
    },

    register: (payload) => postJson('/register', payload),
    verifyEmail: (token) => postJson('/verify-email', { token }),
    resendVerification: (identifier) => postJson('/resend-verification', { identifier }),
    forgotPassword: (email) => postJson('/forgot-password', { email }),
    resetPassword: (token, password) => postJson('/reset-password', { token, password }),

    async logout() {
        await fetch(`${AUTH_BASE}/logout`, { method: 'POST', credentials: 'same-origin' });
    },
};
