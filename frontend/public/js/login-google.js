// "Continuar con Google" on the login page.
//
// Google draws the button and the choice of account in its own script. When the person picks an account Google hands
// this page an ID token (a signed text saying who they are); the page sends it to the API (POST /auth/google), which
// checks the signature and opens the session. This page never reads the token and has no secret: the client ID that
// draws the button is public (the API gives it in /auth/options, only when "Sign in with Google" is set up).
import { authApi } from './auth-api.js';
import { errorText, statusMessage } from './auth-pages.js';

const GSI_URL = 'https://accounts.google.com/gsi/client';
// Google accepts a button between 200 and 400 px wide.
const MIN_WIDTH = 200;
const MAX_WIDTH = 400;

/** Load Google's script once. Rejects when it cannot be loaded (blocked network, ad blocker...). */
function loadGoogleScript() {
    return new Promise((resolve, reject) => {
        if (window.google?.accounts?.id) {
            resolve();
            return;
        }
        const script = document.createElement('script');
        script.src = GSI_URL;
        script.async = true;
        script.onload = resolve;
        script.onerror = () => reject(new Error('Google script not loaded'));
        document.head.appendChild(script);
    });
}

/**
 * Show the Google button inside `container` (and reveal `wrapper`, which holds it and its "o" divider).
 * `onSuccess()` runs once the API opened the session; `onError(text)` gets the message to show otherwise.
 * If Google's script cannot load, nothing is shown and the normal login stays as the only way in.
 */
export async function setupGoogleSignIn({ clientId, wrapper, container, onSuccess, onError }) {
    if (!clientId) return;
    try {
        await loadGoogleScript();
    } catch (error) {
        return;
    }

    window.google.accounts.id.initialize({
        client_id: clientId,
        // Google calls this with the token after the person chose an account.
        callback: async (response) => {
            try {
                const { ok, status, data } = await authApi.google(response.credential);
                if (ok) {
                    onSuccess();
                    return;
                }
                // 401: the token did not check out. 403: the API explains why this account cannot come in this way
                // (an administrator, a deactivated account...). Both texts are in Spanish and safe to show.
                onError(status === 401 || status === 403
                    ? errorText(data, 'No pudimos iniciar sesión con Google.')
                    : statusMessage(status, data, 'No pudimos iniciar sesión con Google.'));
            } catch (error) {
                onError('No se pudo conectar con el servidor');
            }
        },
        // Never sign in by itself: the person has to press the button.
        auto_select: false,
    });

    wrapper.hidden = false;  // visible before drawing, so the container has a width to fit the button to
    const width = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, Math.round(container.getBoundingClientRect().width) || MAX_WIDTH));
    window.google.accounts.id.renderButton(container, {
        type: 'standard',
        theme: 'outline',
        size: 'large',
        text: 'continue_with',
        shape: 'rectangular',
        logo_alignment: 'left',
        locale: 'es',
        width,
    });
}
