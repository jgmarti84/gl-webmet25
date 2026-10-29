import { authApi } from './auth-api.js';
import { EMAIL_RE, hideMessage, showMessage, statusMessage } from './auth-pages.js';

const form = document.getElementById('forgot-form');
const errorBox = document.getElementById('forgot-error');
const submit = document.getElementById('forgot-submit');
const done = document.getElementById('forgot-done');

// Recovery needs the mail to be configured on the server: when it is not, say so instead of showing the form.
authApi.options().then((options) => {
    if (!options.password_recovery) {
        form.hidden = true;
        document.getElementById('forgot-unavailable').hidden = false;
    }
});

form.addEventListener('submit', async (event) => {
    event.preventDefault();
    hideMessage(errorBox);
    const email = document.getElementById('forgot-email').value.trim();
    if (!EMAIL_RE.test(email)) {
        showMessage(errorBox, 'Ingresá un mail válido.');
        return;
    }
    submit.disabled = true;
    try {
        const { status, data } = await authApi.forgotPassword(email);
        // Always the same screen: the server answers 202 whether or not the mail has an account.
        if (status === 202) {
            form.hidden = true;
            done.hidden = false;
            return;
        }
        showMessage(errorBox, statusMessage(status, data));
    } catch (error) {
        showMessage(errorBox, 'No se pudo conectar con el servidor');
    } finally {
        submit.disabled = false;
    }
});
