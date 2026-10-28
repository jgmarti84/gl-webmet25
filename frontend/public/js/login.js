import { authApi, safeNextPath } from './auth-api.js';
import { startCooldown, statusMessage } from './auth-pages.js';

const form = document.getElementById('login-form');
const errorBox = document.getElementById('login-error');
const infoBox = document.getElementById('login-info');
const resendButton = document.getElementById('login-resend');
const submit = document.getElementById('login-submit');
// Same wait as the server's minimum interval between mails to one account; the button counts it down.
const RESEND_COOLDOWN_S = 60;

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

function clearMessages() {
    errorBox.classList.add('hidden');
    infoBox.hidden = true;
    resendButton.hidden = true;
}

// Offer only what the server has turned on: the "forgot" and "create account" links.
authApi.options().then((options) => {
    document.getElementById('login-forgot').hidden = !options.password_recovery;
    document.getElementById('login-signup').hidden = !options.registration;
});

// Already logged in (or the refresh cookie is still valid): go straight to the destination.
authApi.me().then((me) => {
    if (me && mayAutoRedirect()) window.location.replace(next);
});

// What the person typed when the server said the mail is not verified: "resend" needs it.
let pendingIdentifier = '';

form.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearMessages();
    submit.disabled = true;
    const identifier = document.getElementById('login-username').value;
    try {
        const { ok, status, code } = await authApi.login(identifier, document.getElementById('login-password').value);
        if (ok) {
            window.location.replace(next);
            return;
        }
        // The server only says this when the password was right, so it is safe to offer the resend.
        if (code === 'email_not_verified') {
            pendingIdentifier = identifier;
            showError('Tu mail todavía no está verificado. Revisá tu bandeja de entrada o pedí un mail nuevo.');
            resendButton.hidden = false;
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

resendButton.addEventListener('click', async () => {
    resendButton.disabled = true;
    try {
        const { status, data } = await authApi.resendVerification(pendingIdentifier);
        if (status === 202) {
            infoBox.textContent = 'Si la cuenta está pendiente de verificar, te enviamos un mail nuevo.';
            infoBox.hidden = false;
            startCooldown(resendButton, RESEND_COOLDOWN_S, 'Reenviar mail de verificación');
            return;
        }
        showError(statusMessage(status, data));
    } catch (error) {
        showError('No se pudo conectar con el servidor');
    }
    resendButton.disabled = false;
});
