/**
 * Show and hide a modal (or a notice) of the panels with a soft transition.
 *
 * The modals of the admin, institution and profile panels are a `.modal` that is shown by taking off its `hidden` class
 * and hidden by putting it back. Opening already animates by itself (css/modal-motion.css plays when the modal stops being
 * hidden), but a modal that is hidden at once cannot fade out. These two functions close it in two steps: first the
 * `is-closing` class plays the fade-out, and when it ends the `hidden` class goes on and `afterClosed` runs (the place to
 * empty the form, which must not happen while the modal is still fading, or it would collapse in front of the person).
 *
 * If the modal is opened again while it is closing (a button closes it and another window opens right away), the closing
 * is cancelled: the new content stays on screen and `afterClosed` does not run. People who asked for less motion get
 * the old behaviour, immediate.
 */

const CLOSE_MS = 160; // the same as the fade-out in css/modal-motion.css
const pending = new WeakMap(); // modal -> the timer of its closing

function prefersLessMotion() {
    return Boolean(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
}

/** Open the modal. If it was closing, the closing is cancelled. */
export function showModal(modal) {
    clearTimeout(pending.get(modal));
    pending.delete(modal);
    modal.classList.remove('is-closing', 'hidden');
}

/** Close the modal with a fade-out, then run `afterClosed`. Nothing happens if it is already hidden or closing. */
export function hideModal(modal, afterClosed = () => {}) {
    if (modal.classList.contains('hidden')) {
        afterClosed();
        return;
    }
    if (pending.has(modal)) return; // already closing
    if (prefersLessMotion()) {
        modal.classList.add('hidden');
        afterClosed();
        return;
    }
    modal.classList.add('is-closing');
    pending.set(
        modal,
        setTimeout(() => {
            pending.delete(modal);
            modal.classList.remove('is-closing');
            modal.classList.add('hidden');
            afterClosed();
        }, CLOSE_MS),
    );
}

/**
 * Play a one-time CSS animation again: the class is taken off, the browser is made to notice (reading `offsetWidth`
 * forces it to apply the style), and the class goes on, which restarts the animation. The class is removed after `ms`, so
 * the next call starts it again from zero.
 */
export function playOnce(element, className, ms) {
    element.classList.remove(className);
    void element.offsetWidth;
    element.classList.add(className);
    setTimeout(() => element.classList.remove(className), ms);
}
