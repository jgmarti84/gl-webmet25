import { authApi } from './auth-api.js';
import { statusMessage, tokenFromHash } from './auth-pages.js';

const sections = {
    working: document.getElementById('verify-working'),
    ok: document.getElementById('verify-ok'),
    error: document.getElementById('verify-error'),
};
const errorText = document.getElementById('verify-error-text');
const resendForm = document.getElementById('verify-resend-form');
const resendInfo = document.getElementById('verify-resend-info');

// The link carries a one-time token after "#" (never sent to the server): take it out of the address bar and of
// the history.
const token = tokenFromHash(window.location.hash);
window.history.replaceState(null, '', window.location.pathname);

// Shows one of the three screens (working / ok / error) and hides the others.
function show(name) {
    Object.entries(sections).forEach(([key, element]) => {
        element.hidden = key !== name;
    });
}

// Why this page makes the request itself instead of the server doing it on the GET: mail filters and link
// scanners open links in mails, and that would spend the one-time token before the person clicks.
(async () => {
    if (!token) {
        show('error');
        return;
    }
    try {
        const { status, data } = await authApi.verifyEmail(token);
        if (status === 204) {
            show('ok');
            return;
        }
        errorText.textContent = status === 400 ? 'El link no es válido o ya venció.' : statusMessage(status, data);
    } catch (error) {
        errorText.textContent = 'No se pudo conectar con el servidor';
    }
    show('error');
})();

// The error screen lets the person ask for a new mail with their username or mail.
resendForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const identifier = document.getElementById('verify-identifier').value.trim();
    if (!identifier) return;
    try {
        const { status, data } = await authApi.resendVerification(identifier);
        resendInfo.textContent = status === 202
            ? 'Si la cuenta está pendiente de verificar, te enviamos un mail nuevo.'
            : statusMessage(status, data);
    } catch (error) {
        resendInfo.textContent = 'No se pudo conectar con el servidor';
    }
    resendInfo.hidden = false;
});
