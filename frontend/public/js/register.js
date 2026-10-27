import { authApi } from './auth-api.js';
import { hideMessage, showMessage, startCooldown, statusMessage, validateRegistration } from './auth-pages.js';

const form = document.getElementById('register-form');
const errorBox = document.getElementById('register-error');
const submit = document.getElementById('register-submit');
const done = document.getElementById('register-done');
const resendButton = document.getElementById('register-resend');
const resendInfo = document.getElementById('register-resend-info');
// Same wait as the server's minimum interval between mails to one account; the button counts it down.
const RESEND_COOLDOWN_S = 60;
// Kept for the "resend" button: the screen after sign-up has no input to read it from.
let registeredEmail = '';

function setLink(id, url) {
    const link = document.getElementById(id);
    if (url) link.href = url;
}

// Whether the form asks to accept the terms and the privacy policy: decided by the server (TERMS_REQUIRED).
let termsRequired = false;

// The sign-up form only exists while the server has registration on. The terms checkbox and the legal links
// are shown only when the server asks for them; by default the form has neither.
authApi.options().then((options) => {
    if (!options.registration) {
        form.hidden = true;
        document.getElementById('register-unavailable').hidden = false;
        return;
    }
    termsRequired = Boolean(options.terms_required);
    document.getElementById('reg-terms-block').hidden = !termsRequired;
    if (termsRequired) {
        setLink('terms-link', options.terms_url);
        setLink('privacy-link', options.privacy_url);
    }
});

// "Check your mail" screen, replacing the form.
function showDone() {
    form.hidden = true;
    document.getElementById('register-done-text').textContent =
        `Te enviamos un mail a ${registeredEmail} para verificar tu dirección y activar tu cuenta.`;
    done.hidden = false;
    startCooldown(resendButton, RESEND_COOLDOWN_S, 'Reenviar mail');
}

form.addEventListener('submit', async (event) => {
    event.preventDefault();
    hideMessage(errorBox);
    const values = {
        username: document.getElementById('reg-username').value,
        email: document.getElementById('reg-email').value,
        fullName: document.getElementById('reg-fullname').value,
        password: document.getElementById('reg-password').value,
        repeat: document.getElementById('reg-repeat').value,
        accepted: document.getElementById('reg-terms').checked,
    };
    // Same rules as the server, so the person sees the problem at once. The server checks everything again.
    const problem = validateRegistration({ ...values, termsRequired });
    if (problem) {
        showMessage(errorBox, problem);
        return;
    }
    submit.disabled = true;
    try {
        const { status, data } = await authApi.register({
            username: values.username.trim().toLowerCase(),
            email: values.email.trim(),
            // Left out when empty (undefined is dropped by JSON.stringify): the name is optional.
            full_name: values.fullName.trim() || undefined,
            password: values.password,
            // What the person ticked: false when the form has no terms checkbox (TERMS_REQUIRED off).
            accept_terms: values.accepted,
            // Decoy field: empty for a person, filled by bots (the server ignores the request when it has text).
            website: document.getElementById('reg-website').value,
        });
        // 202 is the same answer for a new mail and for one that already has an account: say "check your mail".
        if (status === 202) {
            registeredEmail = values.email.trim();
            showDone();
            return;
        }
        showMessage(errorBox, statusMessage(status, data, 'No se pudo crear la cuenta. Revisá los datos e intentá de nuevo.'));
    } catch (error) {
        showMessage(errorBox, 'No se pudo conectar con el servidor');
    } finally {
        submit.disabled = false;
    }
});

resendButton.addEventListener('click', async () => {
    resendButton.disabled = true;
    try {
        const { status, data } = await authApi.resendVerification(registeredEmail);
        if (status === 202) {
            resendInfo.textContent = 'Si el mail está pendiente de verificar, te enviamos uno nuevo.';
            resendInfo.hidden = false;
            startCooldown(resendButton, RESEND_COOLDOWN_S, 'Reenviar mail');
            return;
        }
        resendInfo.textContent = statusMessage(status, data);
        resendInfo.hidden = false;
    } catch (error) {
        resendInfo.textContent = 'No se pudo conectar con el servidor';
        resendInfo.hidden = false;
    }
    resendButton.disabled = false;
});
