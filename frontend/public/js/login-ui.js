// Presentation-only behavior of the login page: show/hide the password.
// The authentication logic lives in login.js.
const input = document.getElementById('login-password');
const toggle = document.getElementById('login-pw-toggle');

if (input && toggle) {
    toggle.addEventListener('click', () => {
        const show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        toggle.classList.toggle('is-visible', show);
        toggle.setAttribute('aria-pressed', String(show));
        toggle.setAttribute('aria-label', show ? 'Ocultar contraseña' : 'Mostrar contraseña');
        input.focus();
    });
}
