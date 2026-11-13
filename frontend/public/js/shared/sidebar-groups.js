/**
 * The collapsible groups of the side menu (admin, institution and profile panels).
 *
 * The menu is a list of groups, each one a header button (`.nav-group-label`) and a body with its links
 * (`.nav-group-body`). Pressing the header opens or closes the body, with a soft animation (the CSS animates the height
 * and the arrow). This module only keeps the state:
 *
 * - The group that holds the active link is always open, so the person sees where they are. It opens by itself when the
 *   active link changes (the panels move the `active` class when they switch sections).
 * - The other groups start closed in the admin panel, so its long menu stays short. The institution and profile panels
 *   have only a couple of links, so their menu says `data-groups-open="true"` and every group starts open. What the
 *   person opens or closes is remembered between visits, for each panel on its own (`data-menu` names it, and the key
 *   is `webmet25_sidebar_groups_<menu>`).
 * - The first state is set without animation, so nothing moves while the page loads.
 *
 * Each page loads it with `<script type="module" src="js/shared/sidebar-groups.js">`.
 */

const nav = document.getElementById('sidebar-nav');
const STORAGE_KEY = `webmet25_sidebar_groups_${(nav && nav.dataset.menu) || 'menu'}`;
// What a group does when the person has not chosen yet: the small menus start open, the long one closed.
const OPEN_BY_DEFAULT = Boolean(nav) && nav.dataset.groupsOpen === 'true';

/** The saved choices, {groupName: true|false}. Storage may be blocked or hold garbage: then there are none. */
function readSaved() {
    try {
        const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
        return saved && typeof saved === 'object' ? saved : {};
    } catch (error) {
        return {};
    }
}

function writeSaved(saved) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
    } catch (error) {
        // Storage blocked (private window): the menu simply forgets the choice next time.
    }
}

/** Open or close one group: the class drives the animation, `aria-expanded` tells screen readers. */
function setOpen(group, open) {
    group.classList.toggle('is-collapsed', !open);
    const header = group.querySelector('.nav-group-label');
    if (header) header.setAttribute('aria-expanded', String(open));
}

/** Open the group that holds the active link (all of them hold at most one). */
function openActiveGroup() {
    const active = nav.querySelector('.nav-group a.active');
    if (active) setOpen(active.closest('.nav-group'), true);
}

if (nav) {
    const saved = readSaved();
    nav.classList.add('no-anim'); // the first state is set without animation
    nav.querySelectorAll('.nav-group').forEach((group) => {
        const choice = saved[group.dataset.group];
        setOpen(group, typeof choice === 'boolean' ? choice : OPEN_BY_DEFAULT);
    });
    openActiveGroup();
    requestAnimationFrame(() => requestAnimationFrame(() => nav.classList.remove('no-anim')));

    nav.addEventListener('click', (event) => {
        const header = event.target.closest('.nav-group-label');
        if (!header || !nav.contains(header)) return;
        const group = header.closest('.nav-group');
        const open = group.classList.contains('is-collapsed'); // it was closed: now it opens
        setOpen(group, open);
        const choices = readSaved();
        choices[group.dataset.group] = open;
        writeSaved(choices);
    });

    // The panels move the `active` class from one link to another: the group of the new one opens. Only the links are
    // watched: closing a group changes the class of the group itself, and that must not open it again.
    new MutationObserver((mutations) => {
        if (mutations.some((mutation) => mutation.target.tagName === 'A')) openActiveGroup();
    }).observe(nav, { subtree: true, attributes: true, attributeFilter: ['class'] });
}
