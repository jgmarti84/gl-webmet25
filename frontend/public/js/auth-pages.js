// Rules and small helpers shared by the sign-up and password recovery pages (presentation only: the
// server validates everything again).

// Same shapes the server enforces (radar_db.accounts.USERNAME_RE and the password policy), so the person
// gets the message while typing instead of after a round trip.
export const USERNAME_RE = /^[a-z0-9._-]{3,32}$/;
// Deliberately loose: it only catches typos like a missing "@". The server runs the real validation.
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const MIN_PASSWORD = 12;
export const MAX_PASSWORD = 128;
// Size of users.full_name: the optional "Nombre y apellido" of the sign-up form.
export const MAX_FULL_NAME = 128;

/** The server's own message (a string `detail`), or the fallback for validation lists and empty bodies. */
export function errorText(data, fallback) {
    return data && typeof data.detail === 'string' ? data.detail : fallback;
}

/** Text to show for a failed request: fixed texts for 429 and 503, otherwise what the server said. */
export function statusMessage(status, data, fallback = 'No se pudo completar el pedido. Probá de nuevo.') {
    if (status === 429) return 'Demasiados intentos. Esperá un minuto y volvé a probar.';
    if (status === 503) return 'Esta función no está disponible por ahora.';
    return errorText(data, fallback);
}

/** Null when the password is acceptable, else the message to show. */
export function validatePassword(password, repeat, username = '') {
    if (password.length < MIN_PASSWORD) return `La contraseña debe tener al menos ${MIN_PASSWORD} caracteres.`;
    if (password.length > MAX_PASSWORD) return `La contraseña puede tener hasta ${MAX_PASSWORD} caracteres.`;
    if (!password.trim()) return 'La contraseña no puede estar formada solo por espacios.';
    if (username && password.trim().toLowerCase() === username.trim().toLowerCase()) {
        return 'La contraseña no puede ser igual al usuario.';
    }
    if (password !== repeat) return 'Las contraseñas no coinciden.';
    return null;
}

/** Null when the whole sign-up form is acceptable, else the first problem found. */
export function validateRegistration({ username, email, password, repeat, accepted, fullName = '', termsRequired = true }) {
    const normalized = username.trim().toLowerCase();
    if (!USERNAME_RE.test(normalized)) {
        return 'El usuario debe tener entre 3 y 32 caracteres: letras minúsculas, números, punto, guion o guion bajo.';
    }
    if (!EMAIL_RE.test(email.trim())) return 'Ingresá un mail válido.';
    // Optional: an empty name is fine, only a too long one is refused (the server cleans the rest up).
    if (fullName.trim().length > MAX_FULL_NAME) return `El nombre puede tener hasta ${MAX_FULL_NAME} caracteres.`;
    const passwordProblem = validatePassword(password, repeat, normalized);
    if (passwordProblem) return passwordProblem;
    // Only when the server asks for the terms (TERMS_REQUIRED); by default the form shows no checkbox at all.
    if (termsRequired && !accepted) return 'Tenés que aceptar los términos y la política de privacidad.';
    return null;
}

/** "Reenviar mail (42 s)": the label of a button that is counting down. */
export function cooldownLabel(label, remaining) {
    return `${label} (${remaining} s)`;
}

// Messages go in with textContent, never innerHTML: some of the text comes from the server.
export function showMessage(box, text) {
    box.textContent = text;
    box.classList.remove('hidden');
    box.hidden = false;
}

export function hideMessage(box) {
    box.hidden = true;
    box.classList.add('hidden');
}

/** Disables the button for `seconds`, counting down in its label. Returns a function that stops it. */
export function startCooldown(button, seconds, label) {
    let remaining = seconds;
    button.disabled = true;
    button.textContent = cooldownLabel(label, remaining);
    const timer = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
            clearInterval(timer);
            button.disabled = false;
            button.textContent = label;
            return;
        }
        button.textContent = cooldownLabel(label, remaining);
    }, 1000);
    return () => clearInterval(timer);
}
