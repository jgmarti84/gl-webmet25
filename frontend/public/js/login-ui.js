// Presentation-only behavior of the login, sign-up and reset pages: show/hide a password field.
// Every .login-pw-toggle button points at its input with data-target (the input's id).
// The authentication logic lives in the page scripts.
document.querySelectorAll('.login-pw-toggle[data-target]').forEach((toggle) => {
    const input = document.getElementById(toggle.dataset.target);
    if (!input) return;
    toggle.addEventListener('click', () => {
        const show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        toggle.classList.toggle('is-visible', show);
        toggle.setAttribute('aria-pressed', String(show));
        toggle.setAttribute('aria-label', show ? 'Ocultar contraseña' : 'Mostrar contraseña');
        input.focus();
    });
});
