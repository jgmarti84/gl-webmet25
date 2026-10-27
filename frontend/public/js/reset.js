import { authApi } from './auth-api.js';
import { hideMessage, showMessage, statusMessage, validatePassword } from './auth-pages.js';

const formSection = document.getElementById('reset-form-section');
const form = document.getElementById('reset-form');
const errorBox = document.getElementById('reset-error');
const submit = document.getElementById('reset-submit');
const ok = document.getElementById('reset-ok');
const invalid = document.getElementById('reset-invalid');

// The link carries a one-time token: take it out of the address bar and of the history.
const token = new URLSearchParams(window.location.search).get('token') || '';
window.history.replaceState(null, '', window.location.pathname);

// Opened without a token (typed by hand, or the address was cleaned): there is nothing to redeem.
if (!token) {
    formSection.hidden = true;
    invalid.hidden = false;
}

form.addEventListener('submit', async (event) => {
    event.preventDefault();
    hideMessage(errorBox);
    const password = document.getElementById('reset-password').value;
    // A weak password is refused here and by the server, which in that case keeps the link usable.
    const problem = validatePassword(password, document.getElementById('reset-repeat').value);
    if (problem) {
        showMessage(errorBox, problem);
        return;
    }
    submit.disabled = true;
    try {
        const { status, data } = await authApi.resetPassword(token, password);
        if (status === 204) {
            formSection.hidden = true;
            ok.hidden = false;
            return;
        }
        // 400: the link is unknown, expired or already used. Nothing to retry with this token.
        if (status === 400) {
            formSection.hidden = true;
            invalid.hidden = false;
            return;
        }
        showMessage(errorBox, statusMessage(status, data, 'No se pudo cambiar la contraseña.'));
    } catch (error) {
        showMessage(errorBox, 'No se pudo conectar con el servidor');
    } finally {
        submit.disabled = false;
    }
});
