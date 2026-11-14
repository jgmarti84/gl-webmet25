/**
 * The user's own profile (spec D), drawn inside any container. The same section is used by the admin panel, the
 * company panel and the viewer's /perfil page, so there is one copy of it: the data of the account, the radars the
 * person may open and, for company admins, the card of their company. The only thing that can be edited is the name.
 *
 * The page that hosts it gives its own modal and notice functions (each panel has them), so the look and the
 * behaviour of the form are the ones of that page: `openModal(title, html, onSubmit)` closes the modal when
 * `onSubmit` resolves and shows its error inside the modal when it rejects.
 */
import { empresaApi } from '../empresa-api.js';
import { confirmAction } from './confirm-dialog.js';
import { perfilApi } from '../perfil-api.js';
import { ALL_RADARS } from './radar-views.js';
import { ROLE_LABELS, initialsOf } from './session-box.js';

/** Text that is safe to put inside innerHTML. */
function safeText(value) {
    const div = document.createElement('div');
    div.textContent = value === null || value === undefined ? '' : String(value);
    return div.innerHTML.replaceAll('"', '&quot;');
}

/** A date as the person reads it (Argentina), or a dash when there is none. */
export function formatDate(value) {
    return value ? new Date(value).toLocaleString('es-AR', { dateStyle: 'medium', timeStyle: 'short' }) : '—';
}

/** The rows of "Datos de la cuenta": [label, value] pairs, with a dash for what the account does not have. */
export function profileRows(profile) {
    return [
        ['Usuario', profile.username],
        ['Nombre', profile.full_name || '—'],
        ['Mail', profile.email || '—'],
        ['Rol', ROLE_LABELS[profile.role] || profile.role],
        ['Institución', profile.organization_name || '—'],
        ['Alta', formatDate(profile.created_at)],
        ['Último ingreso', formatDate(profile.last_login_at)],
    ];
}

/** The note under the table of radar views: the general admin sees all of them, everybody else what was assigned. */
export function viewsNote(role) {
    return role === 'admin'
        ? 'Como administrador general, ves todos los radares que tienen la vista habilitada.'
        : 'Son los radares cuya vista detallada podés abrir desde el mapa.';
}

/** What the head of the card already shows (who the person is), so the details below do not repeat it. */
const DETAILS_SHOWN_IN_HEAD = new Set(['Usuario', 'Nombre', 'Rol']);

/** The skeleton of the section. The ids are the ones the tests and the page header look for. */
function skeleton(isCompanyAdmin, isGeneralAdmin) {
    const companyCard = isCompanyAdmin
        ? `
        <div id="perfil-company" hidden>
            <p class="section-subtitle">Mi institución</p>
            <div class="card-grid">
                <div class="card"><h3>Institución</h3><div class="card-stat" id="perfil-company-name"></div></div>
                <div class="card"><h3>Lugares</h3><div class="card-stat" id="perfil-company-seats"></div></div>
                <div class="card"><h3>Vistas de radar de la institución</h3><div class="card-stat" id="perfil-company-views"></div></div>
                <div class="card"><h3>Seguimiento de tormentas</h3><div class="card-stat" id="perfil-company-tracking"></div></div>
            </div>
        </div>`
        : '';
    return `
        <p class="section-subtitle">Mis datos</p>
        <div class="card profile-card">
            <div class="profile-card-head">
                <div id="perfil-avatar" class="profile-avatar" aria-hidden="true"></div>
                <div class="profile-card-id">
                    <div id="perfil-name" class="profile-name"></div>
                    <div class="profile-card-sub">
                        <span id="perfil-username" class="profile-sub"></span>
                        <span id="perfil-role" class="status-pill"></span>
                    </div>
                </div>
                <button class="btn-secondary profile-edit" id="perfil-edit-name" type="button">
                    <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>
                    Editar nombre
                </button>
            </div>
            <dl id="perfil-details" class="profile-details"></dl>
            <p class="toolbar-note profile-card-note">El usuario y el mail no se pueden cambiar desde acá.</p>
        </div>
        ${companyCard}
        <p class="section-subtitle">Mis vistas de radar</p>
        <div class="table-wrap">
            <table>
                <thead><tr><th>Radar</th><th>Nombre</th></tr></thead>
                <tbody id="perfil-views"></tbody>
            </table>
        </div>
        <p id="perfil-views-note" class="toolbar-note"></p>
        ${deleteBlock(isGeneralAdmin)}`;
}

/**
 * "Eliminar mi cuenta" (spec G): deletes the account of the person for good. The general admin does not get the button (its
 * account is deleted by another general admin), only a note that says so.
 */
function deleteBlock(isGeneralAdmin) {
    const body = isGeneralAdmin
        ? '<p id="profile-delete-note" class="toolbar-note">Un administrador general no puede borrar su propia cuenta: pedile a otro administrador general.</p>'
        : `<p id="profile-delete-note" class="toolbar-note">Se borran tu cuenta, tus sesiones y tus vistas de radar. No se puede deshacer.</p>
            <div id="profile-delete-error" class="form-error" role="alert" hidden></div>
            <div><button class="btn-danger" id="profile-delete" type="button">Eliminar mi cuenta</button></div>`;
    return `
        <p class="section-subtitle">Eliminar mi cuenta</p>
        <div class="card profile-danger">${body}</div>`;
}

/** Fill the account data, the avatar with the initials and the table of radar views. */
function fillProfile(container, profile) {
    const $ = (id) => container.querySelector(`#${id}`);
    const displayName = profile.full_name || profile.username;
    $('perfil-avatar').textContent = initialsOf(displayName);
    $('perfil-name').textContent = displayName;
    $('perfil-username').textContent = `@${profile.username}`;
    $('perfil-role').textContent = ROLE_LABELS[profile.role] || profile.role;
    $('perfil-details').innerHTML = profileRows(profile)
        .filter(([label]) => !DETAILS_SHOWN_IN_HEAD.has(label))
        .map(([label, value]) => `<div><dt>${safeText(label)}</dt><dd>${safeText(value)}</dd></div>`)
        .join('');
    const views = profile.radar_detail_views;
    $('perfil-views').innerHTML = views.length
        ? views.map((view) => `<tr><td>${safeText(view.code)}</td><td>${safeText(view.title)}</td></tr>`).join('')
        : '<tr><td colspan="2">Todavía no tenés vistas de radar asignadas.</td></tr>';
    $('perfil-views-note').textContent = viewsNote(profile.role);
    // The name also shows in the account chip of the page header (every page that hosts the profile has it).
    const chipName = document.getElementById('account-name');
    if (chipName) chipName.textContent = displayName;
    const chipAvatar = document.getElementById('account-avatar');
    if (chipAvatar) chipAvatar.textContent = initialsOf(displayName);
}

/** The card of the company of a company admin: name, seats and the company's views. */
async function fillCompany(container) {
    const company = await empresaApi.company();
    container.querySelector('#perfil-company-name').textContent = company.name;
    container.querySelector('#perfil-company-seats').textContent = `${company.seats_used} de ${company.seat_limit}`;
    const views = company.radar_detail_views;
    container.querySelector('#perfil-company-views').textContent = views.includes(ALL_RADARS)
        ? 'Todas'
        : (views.length ? views.join(', ') : 'ninguna');
    container.querySelector('#perfil-company-tracking').textContent = company.tools?.tracking ? 'Sí' : 'No';
    container.querySelector('#perfil-company').hidden = false;
}

/**
 * Draw the profile inside `container` (its content is replaced) and wire the edit button.
 * Rejects if the data cannot be loaded: the page shows that error in its own notice.
 *
 * @param {HTMLElement} container
 * @param {{me: {role: string}, openModal: Function, showMessage: Function}} host
 */
export async function mountProfile(container, { me, openModal, showMessage }) {
    container.innerHTML = skeleton(me.role === 'org_admin', me.role === 'admin');
    let profile = await perfilApi.get();
    fillProfile(container, profile);
    if (me.role === 'org_admin') await fillCompany(container);

    // Eliminar mi cuenta: a manual confirmation, then the server decides (an institution's only admin is told to name another
    // admin first). On success the session is gone, so the person goes to the login (relative URL, base path rule).
    const deleteButton = container.querySelector('#profile-delete');
    if (deleteButton) {
        deleteButton.onclick = async () => {
            const error = container.querySelector('#profile-delete-error');
            error.hidden = true;
            const accepted = await confirmAction({
                message: '¿Eliminar tu cuenta? Se borran tu cuenta, tus sesiones y tus vistas de radar. No se puede deshacer.',
                confirmLabel: 'Eliminar mi cuenta',
                danger: true,
            });
            if (!accepted) return;
            try {
                await perfilApi.deleteAccount();
                window.location.assign('login');
            } catch (failure) {
                error.textContent = failure.message;
                error.hidden = false;
            }
        };
    }

    container.querySelector('#perfil-edit-name').onclick = () => {
        openModal(
            'Editar nombre',
            `
                <label>Nombre <input name="full_name" type="text" maxlength="128" value="${safeText(profile.full_name)}" autocomplete="name"></label>
                <p class="toolbar-note">Es el nombre que se ve en tu cuenta. Si lo dejás vacío, se usa tu usuario.</p>
                <div class="form-actions"><button class="btn" type="submit">Guardar</button></div>
            `,
            async (formData) => {
                profile = await perfilApi.setName(formData.get('full_name') || null);
                fillProfile(container, profile);
                showMessage('Nombre actualizado');
            },
        );
    };
}
