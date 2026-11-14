/**
 * The app's own confirmation window, in place of the browser's `window.confirm`.
 *
 * The browser box cannot be styled or animated and looks different on every system. This one is a small modal with the
 * look and the motion of the other windows of the panels (see css/modal-motion.css and js/shared/modal-motion.js). It
 * asks a question and answers with a promise:
 *
 *     if (!(await confirmAction({ message: '¿Eliminar a ana?', confirmLabel: 'Eliminar', danger: true }))) return;
 *
 * `true` when the person accepts, `false` when they cancel, press Escape or click outside the window. For an action that
 * cannot be undone (`danger: true`) the red button is the one that deletes and the focus starts on Cancel, so pressing
 * Enter by mistake does not do it. The window is built the first time it is needed and reused, and it sits above the
 * other windows (a form window may be open under it). It needs the classes of admin.css (`.modal`, `.btn`).
 */
import { hideModal, showModal } from './modal-motion.js';

let dialog = null;
let resolveCurrent = null;
let returnFocusTo = null;

/** Build the window once and wire its buttons. */
function ensureDialog() {
    if (dialog) return dialog;
    dialog = document.createElement('div');
    dialog.id = 'confirm-dialog';
    dialog.className = 'modal confirm-modal hidden';
    dialog.setAttribute('role', 'alertdialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-labelledby', 'confirm-title');
    dialog.setAttribute('aria-describedby', 'confirm-message');
    dialog.innerHTML = `
        <div class="modal-card confirm-card">
            <div class="modal-header"><h2 id="confirm-title"></h2></div>
            <div class="confirm-body"><p id="confirm-message"></p></div>
            <div class="confirm-actions">
                <button id="confirm-cancel" class="btn btn-secondary" type="button"></button>
                <button id="confirm-accept" class="btn" type="button"></button>
            </div>
        </div>`;
    document.body.appendChild(dialog);

    dialog.querySelector('#confirm-cancel').addEventListener('click', () => settle(false));
    dialog.querySelector('#confirm-accept').addEventListener('click', () => settle(true));
    // A click on the dark backdrop (not on the window) cancels.
    dialog.addEventListener('click', (event) => {
        if (event.target === dialog) settle(false);
    });
    dialog.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            event.stopPropagation();
            settle(false);
        } else if (event.key === 'Tab') {
            // Two buttons only: Tab moves between them and never leaves the window.
            event.preventDefault();
            const cancel = dialog.querySelector('#confirm-cancel');
            const accept = dialog.querySelector('#confirm-accept');
            (document.activeElement === accept ? cancel : accept).focus();
        }
    });
    return dialog;
}

/** Answer the pending question, close the window and give the focus back to where it was. */
function settle(answer) {
    if (!resolveCurrent) return;
    const resolve = resolveCurrent;
    resolveCurrent = null;
    hideModal(dialog);
    if (returnFocusTo && returnFocusTo.isConnected) returnFocusTo.focus();
    returnFocusTo = null;
    resolve(answer);
}

/**
 * Ask a question. `message` is plain text (never HTML). Returns a promise of true (accepted) or false.
 * @param {{message: string, title?: string, confirmLabel?: string, cancelLabel?: string, danger?: boolean}} options
 */
export function confirmAction({ message, title = 'Confirmar', confirmLabel = 'Aceptar', cancelLabel = 'Cancelar', danger = false }) {
    const box = ensureDialog();
    if (resolveCurrent) settle(false); // a second question while one is open: the first one is cancelled
    return new Promise((resolve) => {
        resolveCurrent = resolve;
        returnFocusTo = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        box.querySelector('#confirm-title').textContent = title;
        box.querySelector('#confirm-message').textContent = message;
        const cancel = box.querySelector('#confirm-cancel');
        const accept = box.querySelector('#confirm-accept');
        cancel.textContent = cancelLabel;
        accept.textContent = confirmLabel;
        accept.classList.toggle('btn-danger', danger);
        showModal(box);
        (danger ? cancel : accept).focus();
    });
}
