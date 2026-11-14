/**
 * The tooltip of the whole app, in place of the browser's own.
 *
 * The browser draws a `title` as a small box with a dark border that cannot be styled, and it always waits the same
 * time. This module replaces it with one floating bubble (the <div id="app-tooltip"> that it adds to the page): soft
 * fade, dark, small, no border. It is loaded by every page that has tooltips (`<script type="module"
 * src="js/shared/tooltip.js">`) and it needs nothing else from them:
 *
 * - Any element with a `title` attribute gets a tooltip, including the ones the app sets later (`button.title = ...`):
 *   the text moves to `data-tooltip`, and the `title` is removed so the browser box does not show too. Text inputs,
 *   selects and text areas are left alone, because their `title` is also the hint of the browser's own format message.
 * - The <title> inside an icon (`<svg><title>Editar</title>...</svg>`) that sits in a button or a link becomes the
 *   tooltip of that button, and the icon's <title> is removed for the same reason.
 * - The text also goes to `aria-label` when the control has no visible text, so screen readers keep reading it.
 *
 * The bubble is a direct child of <body> with `position: fixed`, so no table, panel or modal can clip it or draw
 * over it (a bubble inside a scrolling table was hidden by the sticky header). It opens above its control and flips
 * below when there is no room, and it is kept inside the window. Mouse and keyboard focus both open it.
 */

const BUBBLE_ID = 'app-tooltip';
const SHOW_DELAY_MS = 300; // wait before the first bubble, so it does not flash while the mouse only passes by
const WARM_MS = 400; // within this time after one closed, the next opens at once
const GAP = 8; // px between the control and the bubble
const MARGIN = 6; // px kept free at the edges of the window
const SKIPPED_TAGS = new Set(['INPUT', 'SELECT', 'TEXTAREA', 'IFRAME']);

let bubble = null;
let current = null; // the control whose bubble is open, or about to open
let timer = null;
let visible = false;
let lastHidden = 0;

// The look lives in a file of its own. Its address is worked out from this module's, so it also loads when the site is
// served under a prefix.
const stylesheet = document.createElement('link');
stylesheet.rel = 'stylesheet';
stylesheet.href = new URL('../../css/tooltip.css', import.meta.url).href;
document.head.appendChild(stylesheet);

/** The element (or the closest ancestor) that has a tooltip, or null. */
function controlOf(node) {
    return node instanceof Element ? node.closest('[data-tooltip]') : null;
}

/** `title` -> `data-tooltip`, for one element. */
function moveTitleToTooltip(element) {
    if (element instanceof SVGElement || SKIPPED_TAGS.has(element.tagName)) return;
    const text = (element.getAttribute('title') || '').trim();
    if (!text) return;
    element.setAttribute('data-tooltip', text);
    element.removeAttribute('title');
    if (!element.hasAttribute('aria-label') && !element.textContent.trim()) element.setAttribute('aria-label', text);
}

/** The <title> of an icon inside a button or a link -> the tooltip of that button or link. */
function moveIconTitleToTooltip(iconTitle) {
    const control = iconTitle.parentElement ? iconTitle.parentElement.closest('button, a, [role="button"]') : null;
    if (!control) return;
    const text = iconTitle.textContent.trim();
    iconTitle.remove(); // first, so the check of the visible text below does not count it
    if (!text) return;
    if (!control.hasAttribute('data-tooltip')) control.setAttribute('data-tooltip', text);
    if (!control.hasAttribute('aria-label') && !control.textContent.trim()) control.setAttribute('aria-label', text);
}

/** Convert `root` and everything inside it. */
function convertWithin(root) {
    if (root.matches('[title]')) moveTitleToTooltip(root);
    root.querySelectorAll('[title]').forEach(moveTitleToTooltip);
    root.querySelectorAll('svg > title').forEach(moveIconTitleToTooltip);
}

function ensureBubble() {
    if (bubble) return bubble;
    bubble = document.createElement('div');
    bubble.id = BUBBLE_ID;
    bubble.setAttribute('role', 'tooltip');
    document.body.appendChild(bubble);
    return bubble;
}

/** Write the text and put the bubble above the control (below it if it does not fit), inside the window. */
function place(control) {
    const box = ensureBubble();
    box.textContent = control.getAttribute('data-tooltip');
    box.style.left = '0px'; // measured from a known spot: its size depends on the text
    box.style.top = '0px';
    const rect = control.getBoundingClientRect();
    const width = box.offsetWidth;
    const height = box.offsetHeight;
    let top = rect.top - height - GAP;
    let placement = 'above';
    if (top < MARGIN) {
        top = rect.bottom + GAP;
        placement = 'below';
    }
    const left = Math.max(MARGIN, Math.min(rect.left + rect.width / 2 - width / 2, window.innerWidth - width - MARGIN));
    box.style.left = `${Math.round(left)}px`;
    box.style.top = `${Math.round(top)}px`;
    box.dataset.placement = placement; // the CSS makes it rise from below or drop from above
}

function show(control) {
    if (!control.isConnected || !control.getAttribute('data-tooltip')) return;
    if (current && current !== control) current.removeAttribute('aria-describedby');
    place(control);
    ensureBubble().classList.add('is-visible');
    control.setAttribute('aria-describedby', BUBBLE_ID);
    current = control;
    visible = true;
}

function hide() {
    clearTimeout(timer);
    timer = null;
    if (visible) lastHidden = Date.now();
    if (bubble) bubble.classList.remove('is-visible');
    if (current) current.removeAttribute('aria-describedby');
    current = null;
    visible = false;
}

/** Open the bubble of `control`: after a short wait, at once if one is already open or one just closed. */
function schedule(control) {
    if (control === current) return;
    clearTimeout(timer);
    if (visible) {
        show(control);
        return;
    }
    current = control; // pending: repeated mouse events over its children do nothing
    timer = setTimeout(() => show(control), Date.now() - lastHidden < WARM_MS ? 0 : SHOW_DELAY_MS);
}

document.addEventListener('mouseover', (event) => {
    const control = controlOf(event.target);
    if (control) schedule(control);
});
document.addEventListener('mouseout', (event) => {
    const control = controlOf(event.target);
    if (control && control === current && !control.contains(event.relatedTarget)) hide();
});
// Keyboard: only when the focus came from the keyboard, so a click does not leave a bubble open.
document.addEventListener('focusin', (event) => {
    const control = controlOf(event.target);
    if (control && control.matches(':focus-visible')) schedule(control);
});
document.addEventListener('focusout', (event) => {
    if (controlOf(event.target) === current) hide();
});
// A click, a key press that closes something, a scroll or a resize all close it: the control may have moved.
document.addEventListener('pointerdown', hide, true);
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') hide();
}, true);
window.addEventListener('scroll', hide, true);
window.addEventListener('resize', hide);

convertWithin(document.body);

// The pages draw and redraw their content all the time, so what is added later (and every `title` the code sets later)
// is converted as it appears. Our own changes (removing a `title`) come back here and find nothing left to do.
new MutationObserver((mutations) => {
    for (const mutation of mutations) {
        if (mutation.type === 'attributes') {
            const target = mutation.target;
            if (target.hasAttribute('title') && !target.getAttribute('title').trim()) {
                // The code cleared the title (for example "no hay lugares" no longer applies): drop the old tooltip.
                target.removeAttribute('title');
                target.removeAttribute('data-tooltip');
            } else {
                moveTitleToTooltip(target);
            }
        } else {
            mutation.addedNodes.forEach((node) => {
                if (node.nodeType === Node.ELEMENT_NODE) convertWithin(node);
            });
        }
    }
    if (current && !current.isConnected) hide(); // its control was removed while the bubble was open
}).observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['title'] });
