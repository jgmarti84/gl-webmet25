/**
 * Profile page (/perfil, spec D) for viewers. Admins and company admins have the profile inside their own panels
 * (admin#profile and empresa#perfil), so this page sends them there. The profile itself is drawn by
 * shared/profile-section.js, the same code the panels use.
 */
import { initPageSession } from './auth-api.js';
import { mountProfile } from './shared/profile-section.js';
import { renderSessionBox } from './shared/session-box.js';

// How long a success notice stays before it closes by itself (errors stay until the × is pressed).
const SUCCESS_MESSAGE_MS = 4000;

let messageTimer = null;

const $ = (id) => document.getElementById(id);

// --- notices (same behaviour as the company panel) --------------------------------------------------------------

function hideMessage() {
    clearTimeout(messageTimer);
    messageTimer = null;
    const box = $('perfil-message');
    box.querySelector('.feedback-text').textContent = '';
    box.classList.add('hidden');
    box.classList.remove('success', 'error');
}

function showMessage(text, kind = 'success') {
    const box = $('perfil-message');
    box.querySelector('.feedback-text').textContent = text;
    box.classList.remove('hidden', 'success', 'error');
    box.classList.add(kind);
    clearTimeout(messageTimer);
    messageTimer = kind === 'success' ? setTimeout(hideMessage, SUCCESS_MESSAGE_MS) : null;
}

// --- modal (errors are shown INSIDE it, like the other panels) --------------------------------------------------

function closeModal() {
    $('form-modal').classList.add('hidden');
    $('form-modal-body').innerHTML = '';
}

/** Show (or clear, with no text) the error inside the open modal, just above the buttons. */
function setModalError(form, text) {
    let box = form.querySelector('.form-error');
    if (!text) {
        box?.remove();
        return;
    }
    if (!box) {
        box = document.createElement('p');
        box.className = 'form-error';
        box.setAttribute('role', 'alert');
        form.insertBefore(box, form.querySelector('.form-actions'));
    }
    box.textContent = text;
}

/** Open the shared modal. `onSubmit` gets the FormData; the modal closes when it resolves, a rejection is shown. */
function openModal(title, html, onSubmit) {
    $('form-modal-title').textContent = title;
    const form = $('form-modal-body');
    form.innerHTML = html;
    form.onsubmit = async (event) => {
        event.preventDefault();
        setModalError(form, '');
        try {
            await onSubmit(new FormData(form));
            closeModal();
        } catch (error) {
            setModalError(form, error.message || 'La operación falló');
        }
    };
    $('form-modal').classList.remove('hidden');
}

// --- the page ---------------------------------------------------------------------------------------------------

async function init() {
    const me = await initPageSession();
    if (!me) return;  // initPageSession reloads the page, and nginx then serves the login

    // The profile of an admin or a company admin lives inside their panel. Relative on purpose (base path rule).
    if (me.role === 'admin') {
        window.location.replace('admin#profile');
        return;
    }
    if (me.role === 'org_admin') {
        window.location.replace('empresa#perfil');
        return;
    }

    renderSessionBox(me, { afterLogout: () => window.location.assign('login') });
    $('close-form-modal').onclick = closeModal;
    $('form-modal').addEventListener('click', (event) => {
        if (event.target === $('form-modal')) closeModal();
    });
    $('perfil-message').querySelector('.feedback-close').onclick = hideMessage;

    try {
        await mountProfile($('perfil-content'), { me, openModal, showMessage });
    } catch (error) {
        showMessage(error.message || 'No se pudo cargar el perfil', 'error');
    }
}

init();
