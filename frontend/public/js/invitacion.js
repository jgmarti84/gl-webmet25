// The invitation page (spec E): the person arrives from the link in the mail ("/invitacion#token=..."), sees which
// institution invited them and creates the account with a form or with Google. The server checks everything again.
// When the mail already has an account the page asks to LOG IN with it instead and then joins the institution.
import { authApi } from './auth-api.js';
import {
    errorText,
    hideMessage,
    showMessage,
    statusMessage,
    tokenFromHash,
    validatePassword,
    USERNAME_RE,
} from './auth-pages.js';
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
    document.getElementById('invitation-google')?.remove();
    document.getElementById('invitation-existing')?.remove();
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
}

/** The mail has no account: the sign-up form (and Google) are what the person sees. */
function showCreate() {
    intro.textContent = 'Creá tu cuenta para entrar.';
    form.hidden = false;
}

// --- the mail already has an account: log in with it and join -------------------------------------------
const existing = document.getElementById('invitation-existing');
const existingGoogle = document.getElementById('invitation-existing-google');
const loginForm = document.getElementById('invitation-login-form');
const loginError = document.getElementById('invitation-login-error');
const joinBlock = document.getElementById('invitation-join-block');
const joinError = document.getElementById('invitation-join-error');
const wrongAccount = document.getElementById('invitation-wrong-account');
let invitationDetails = null;

/** The login answered with a problem: what to tell the person (the page never says which part was wrong). */
function loginProblem(result) {
    if (result.status === 429) return 'Demasiados intentos. Esperá un minuto y volvé a probar.';
    if (result.status === 403 && result.code === 'email_not_verified') return 'Tenés que verificar tu mail antes de entrar.';
    if (result.status === 403) return 'Tu cuenta no puede entrar en este momento.';
    return 'Usuario o contraseña incorrectos.';
}

/** The session is of another account than the invited mail: say so and offer to log out. */
function showWrongAccount(data) {
    loginForm.hidden = true;
    joinBlock.hidden = true;
    existingGoogle.hidden = true;
    document.getElementById('invitation-wrong-account-text').textContent = errorText(
        data,
        'Esta invitación es para otra cuenta. Cerrá sesión e ingresá con la cuenta del mail invitado.',
    );
    wrongAccount.hidden = false;
}

/**
 * Join the institution with the account that is logged in. The server checks that the account is the one of the invited
 * mail (403 otherwise) and every rule again; on success the session is renewed and the person goes into the app.
 * Returns true when it worked.
 */
async function join(box) {
    hideMessage(box);
    let result;
    try {
        result = await authApi.acceptExistingInvitation(token);
    } catch (error) {
        showMessage(box, 'No se pudo conectar con el servidor');
        return false;
    }
    if (result.ok) {
        enter(result.data);
        return true;
    }
    if (result.status === 404) {
        showInvalid();
    } else if (result.status === 403) {
        showWrongAccount(result.data);
    } else {
        showMessage(box, statusMessage(result.status, result.data, 'No se pudo completar la invitación. Probá de nuevo.'));
    }
    return false;
}

/** Google for the existing account: sign in, and straight after join (the token stays in this page's memory only). */
async function setupExistingGoogle() {
    if (!invitationDetails || !invitationDetails.google_available) return;
    const options = await authApi.options();
    setupGoogleSignIn({
        clientId: options.google_client_id,
        wrapper: existingGoogle,
        container: document.getElementById('invitation-existing-google-button'),
        signIn: async (credential) => {
            const signedIn = await authApi.google(credential);
            return signedIn.ok ? authApi.acceptExistingInvitation(token) : signedIn;
        },
        onSuccess: enter,
        onError: (text) => showMessage(loginError, text),
    });
}

/** The login screen for an account that already exists: its own login (and Google), or one button if already inside. */
async function showExisting() {
    form.remove();
    document.getElementById('invitation-google')?.remove();
    existing.hidden = false;
    intro.textContent = 'Ya tenés una cuenta con este mail: iniciá sesión con ella para sumarte.';
    const me = await authApi.me().catch(() => null);
    if (me) {
        document.getElementById('invitation-join-text').textContent = `Estás conectado como ${me.full_name || me.username}.`;
        joinBlock.hidden = false;
    } else {
        loginForm.hidden = false;
        await setupExistingGoogle();
    }
}

loginForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    hideMessage(loginError);
    const username = document.getElementById('inv-login-username').value.trim();
    const password = document.getElementById('inv-login-password').value;
    if (!username || !password) {
        showMessage(loginError, 'Escribí tu usuario y tu contraseña.');
        return;
    }
    const button = document.getElementById('invitation-login-submit');
    button.disabled = true;
    try {
        const result = await authApi.login(username, password);
        if (!result.ok) {
            showMessage(loginError, loginProblem(result));
            return;
        }
        await join(loginError);
    } catch (error) {
        showMessage(loginError, 'No se pudo conectar con el servidor');
    } finally {
        button.disabled = false;
    }
});

document.getElementById('invitation-join').addEventListener('click', () => join(joinError));

// Wrong account: log out and offer the login again.
document.getElementById('invitation-logout').addEventListener('click', async () => {
    await authApi.logout();
    wrongAccount.hidden = true;
    loginForm.hidden = false;
    await setupExistingGoogle();
});

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
            document.getElementById('invitation-google')?.remove();
            document.getElementById('invitation-existing')?.remove();
            form.remove();
        }
        return;
    }
    showDetails(result.data);
    invitationDetails = result.data;
    if (result.data.account_exists) {
        // The mail has an account: no sign-up form, a login instead (the server checks everything again when joining).
        await showExisting();
        return;
    }
    showCreate();

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
