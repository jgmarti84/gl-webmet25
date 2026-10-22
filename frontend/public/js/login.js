import { authApi, safeNextPath } from './auth-api.js';

const form = document.getElementById('login-form');
const errorBox = document.getElementById('login-error');
const submit = document.getElementById('login-submit');
// nginx serves this page in place of a protected one (same URL): after logging in, reload that URL.
// On /login itself, go to ?next= or to the map.
const servedInPlace = window.location.pathname !== '/login';
const next = servedInPlace
    ? window.location.pathname + window.location.search + window.location.hash
    : safeNextPath(new URLSearchParams(window.location.search).get('next'), '/');

// A valid session found on load redirects automatically, but only once every few seconds: if
// nginx kept answering 401 anyway, the user would otherwise bounce forever.
const AUTO_REDIRECT_KEY = 'webmet25_login_auto_at';
const AUTO_REDIRECT_MS = 10000;

function mayAutoRedirect() {
    try {
        const last = Number(sessionStorage.getItem(AUTO_REDIRECT_KEY)) || 0;
        if (Date.now() - last < AUTO_REDIRECT_MS) return false;
        sessionStorage.setItem(AUTO_REDIRECT_KEY, String(Date.now()));
    } catch (error) {
        // sessionStorage unavailable: redirect anyway
    }
    return true;
}

function showError(text) {
    errorBox.textContent = text;
    errorBox.classList.remove('hidden');
}

// Already logged in (or the refresh cookie is still valid): go straight to the destination.
authApi.me().then((me) => {
    if (me && mayAutoRedirect()) window.location.replace(next);
});

form.addEventListener('submit', async (event) => {
    event.preventDefault();
    errorBox.classList.add('hidden');
    submit.disabled = true;
    try {
        const { ok, status } = await authApi.login(
            document.getElementById('login-username').value,
            document.getElementById('login-password').value,
        );
        if (ok) {
            window.location.replace(next);
            return;
        }
        showError(status === 429
            ? 'Demasiados intentos. Esperá un minuto y volvé a probar.'
            : 'Usuario o contraseña incorrectos');
    } catch (error) {
        showError('No se pudo conectar con el servidor');
    } finally {
        submit.disabled = false;
    }
});
