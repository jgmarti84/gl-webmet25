import { authApi, safeNextPath } from './auth-api.js';

const form = document.getElementById('login-form');
const errorBox = document.getElementById('login-error');
const submit = document.getElementById('login-submit');
const next = safeNextPath(new URLSearchParams(window.location.search).get('next'));

function showError(text) {
    errorBox.textContent = text;
    errorBox.classList.remove('hidden');
}

// Already logged in: go straight to the destination.
authApi.me().then((me) => {
    if (me) window.location.replace(next);
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
