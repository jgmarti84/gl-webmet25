// The invitation page (spec E): the person arrives from the link in the mail ("/invitacion#token=..."), sees which
// institution invited them and creates the account with a form or with Google. The server checks everything again.
import { authApi } from './auth-api.js';
import { hideMessage, showMessage, statusMessage, tokenFromHash, validatePassword, USERNAME_RE } from './auth-pages.js';
import { setupGoogleSignIn } from './login-google.js';

const form = document.getElementById('invitation-form');
const errorBox = document.getElementById('invitation-error');
const googleErrorBox = document.getElementById('invitation-google-error');
const submit = document.getElementById('invitation-submit');
const intro = document.getElementById('invitation-intro');

// The link carries a one-time token after "#" (never sent to the server): take it out of the address bar and of the
// history, and keep it only in this variable.
const token = tokenFromHash(window.location.hash);
window.history.replaceState(null, '', window.location.pathname);

// Whether the form asks to accept the terms: decided by the server (TERMS_REQUIRED), like in the sign-up.
let termsRequired = false;

// What the person will be in the institution, in a sentence.
const ROLE_TEXT = {
    org_admin: 'Vas a ser administrador de la institución: vas a poder agregar y administrar a sus usuarios.',
    viewer: 'Vas a ser usuario de la institución.',
};

/** The link does not work: say so and take the form out of the page, so there is nothing to fill in. */
function showInvalid() {
    intro.textContent = 'No pudimos abrir tu invitación.';
    document.getElementById('invitation-invalid').hidden = false;
    document.getElementById('invitation-google').remove();
    form.remove();
}

/** Where the new account lands: the institution panel for an admin, the map for a reader. */
function enter(me) {
    // Relative to <base href>, like every URL of the site (so it also works under a prefix).
    window.location.replace(me && me.role === 'org_admin' ? 'empresa' : './');
}

function showDetails(details) {
    document.getElementById('invitation-company').textContent = details.organization_name;
    document.getElementById('invitation-email').textContent = details.email;
    document.getElementById('invitation-role').textContent = ROLE_TEXT[details.role] || '';
    document.getElementById('invitation-details').hidden = false;
    intro.textContent = 'Creá tu cuenta para entrar.';
    form.hidden = false;
}

function setLink(id, url) {
    const link = document.getElementById(id);
    if (url) link.href = url;
}

async function start() {
    if (!token) {
        showInvalid();
        return;
    }
    let result;
    try {
        result = await authApi.invitationDetails(token);
    } catch (error) {
        showMessage(errorBox, 'No se pudo conectar con el servidor');
        form.hidden = false;
        return;
    }
    if (!result.ok) {
        // 404 is "this link does not work"; anything else (429, 503...) is a problem to try again later.
        if (result.status === 404) {
            showInvalid();
        } else {
            intro.textContent = statusMessage(result.status, result.data);
            document.getElementById('invitation-google').remove();
            form.remove();
        }
        return;
    }
    showDetails(result.data);

    const options = await authApi.options();
    termsRequired = Boolean(options.terms_required);
    document.getElementById('inv-terms-block').hidden = !termsRequired;
    if (termsRequired) {
        setLink('terms-link', options.terms_url);
        setLink('privacy-link', options.privacy_url);
    }
    if (result.data.google_available) {
        setupGoogleSignIn({
            clientId: options.google_client_id,
            wrapper: document.getElementById('invitation-google'),
            container: document.getElementById('invitation-google-button'),
            // Like the login page, the Google way asks for no terms checkbox: the server only checks them on the form.
            signIn: (credential) => authApi.acceptInvitationWithGoogle(token, credential),
            onSuccess: enter,
            onError: (text) => showMessage(googleErrorBox, text),
        });
    }
}

form.addEventListener('submit', async (event) => {
    event.preventDefault();
    hideMessage(errorBox);
    const username = document.getElementById('inv-username').value.trim().toLowerCase();
    const password = document.getElementById('inv-password').value;
    const repeat = document.getElementById('inv-repeat').value;
    // Same rules as the server, so the person sees the problem at once.
    let problem = null;
    if (!USERNAME_RE.test(username)) {
        problem = 'El usuario debe tener entre 3 y 32 caracteres: letras minúsculas, números, punto, guion o guion bajo.';
    } else {
        problem = validatePassword(password, repeat, username);
    }
    if (!problem && termsRequired && !document.getElementById('inv-terms').checked) {
        problem = 'Tenés que aceptar los términos y la política de privacidad.';
    }
    if (problem) {
        showMessage(errorBox, problem);
        return;
    }
    submit.disabled = true;
    try {
        const { ok, status, data } = await authApi.acceptInvitation({
            token,
            username,
            password,
            // Left out when empty (undefined is dropped by JSON.stringify): the name is optional.
            full_name: document.getElementById('inv-fullname').value.trim() || undefined,
            accept_terms: document.getElementById('inv-terms').checked,
        });
        if (ok) {
            enter(data);
            return;
        }
        // 404 here means the link stopped working while the form was open (cancelled, expired or used).
        if (status === 404) {
            showInvalid();
            return;
        }
        showMessage(errorBox, statusMessage(status, data, 'No se pudo crear la cuenta. Revisá los datos e intentá de nuevo.'));
    } catch (error) {
        showMessage(errorBox, 'No se pudo conectar con el servidor');
    } finally {
        submit.disabled = false;
    }
});

start();
