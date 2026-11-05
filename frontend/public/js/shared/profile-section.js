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

/** The skeleton of the section. The ids are the ones the tests and the page header look for. */
function skeleton(isCompanyAdmin) {
    const companyCard = isCompanyAdmin
        ? `
        <div id="perfil-company" hidden>
            <p class="section-subtitle">Mi institución</p>
            <div class="card-grid">
                <div class="card"><h3>Institución</h3><div class="card-stat" id="perfil-company-name"></div></div>
                <div class="card"><h3>Lugares</h3><div class="card-stat" id="perfil-company-seats"></div></div>
                <div class="card"><h3>Vistas de radar de la institución</h3><div class="card-stat" id="perfil-company-views"></div></div>
            </div>
        </div>`
        : '';
    return `
        <p class="section-subtitle">Mis datos</p>
        <div class="card-grid profile-grid">
            <div class="card profile-identity">
                <div id="perfil-avatar" class="profile-avatar" aria-hidden="true"></div>
                <div>
                    <div id="perfil-name" class="profile-name"></div>
                    <div id="perfil-username" class="profile-sub"></div>
                    <span id="perfil-role" class="status-pill"></span>
                </div>
            </div>
            <div class="card">
                <h3>Datos de la cuenta</h3>
                <dl id="perfil-details" class="profile-details"></dl>
            </div>
        </div>
        <div class="toolbar">
            <button class="btn" id="perfil-edit-name" type="button">Editar nombre</button>
            <span class="toolbar-note">El usuario y el mail no se pueden cambiar desde acá.</span>
        </div>
        ${companyCard}
        <p class="section-subtitle">Mis vistas de radar</p>
        <div class="table-wrap">
            <table>
                <thead><tr><th>Radar</th><th>Nombre</th></tr></thead>
                <tbody id="perfil-views"></tbody>
            </table>
        </div>
        <p id="perfil-views-note" class="toolbar-note"></p>`;
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
        .map(([label, value]) => `<div><dt>${safeText(label)}</dt><dd>${safeText(value)}</dd></div>`)
        .join('');
    const views = profile.radar_detail_views;
    $('perfil-views').innerHTML = views.length
        ? views.map((view) => `<tr><td>${safeText(view.code)}</td><td>${safeText(view.title)}</td></tr>`).join('')
        : '<tr><td colspan="2">Todavía no tenés vistas de radar asignadas.</td></tr>';
    $('perfil-views-note').textContent = viewsNote(profile.role);
    // The name also shows in the header of the page (every page that hosts the profile has #session-user).
    const header = document.getElementById('session-user');
    if (header) header.textContent = displayName;
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
    container.innerHTML = skeleton(me.role === 'org_admin');
    let profile = await perfilApi.get();
    fillProfile(container, profile);
    if (me.role === 'org_admin') await fillCompany(container);

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
