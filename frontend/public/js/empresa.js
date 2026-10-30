/**
 * Company admin panel (/empresa, spec C): the company's seats and views, and its users.
 * Company admins manage only the viewers of their company; other company admins are listed read-only (the general
 * admin looks after them).
 */
import { authApi, initPageSession } from './auth-api.js';
import { empresaApi } from './empresa-api.js';
import { api } from './shared/api.js';
import { ALL_RADARS, viewsSummary } from './shared/radar-views.js';

const ROLE_LABELS = { org_admin: 'Admin de empresa', viewer: 'Lector' };
// How long a success notice stays before it closes by itself (errors stay until the × is pressed).
const SUCCESS_MESSAGE_MS = 4000;

const state = { company: null, users: [], me: null };
let messageTimer = null;

const $ = (id) => document.getElementById(id);

/** Text that is safe to put inside innerHTML. */
function safeText(value) {
    const div = document.createElement('div');
    div.textContent = value === null || value === undefined ? '' : String(value);
    return div.innerHTML.replaceAll('"', '&quot;');
}

// --- notices (same behaviour as the admin panel) ---------------------------------------------------------------

function hideMessage() {
    clearTimeout(messageTimer);
    messageTimer = null;
    const box = $('empresa-message');
    box.querySelector('.feedback-text').textContent = '';
    box.classList.add('hidden');
    box.classList.remove('success', 'error');
}

function showMessage(text, kind = 'success') {
    const box = $('empresa-message');
    box.querySelector('.feedback-text').textContent = text;
    box.classList.remove('hidden', 'success', 'error');
    box.classList.add(kind);
    // A new notice replaces the previous one, so the old timer must not close the new one early.
    clearTimeout(messageTimer);
    messageTimer = kind === 'success' ? setTimeout(hideMessage, SUCCESS_MESSAGE_MS) : null;
}

// --- modal (same markup and classes as the admin panel) ---------------------------------------------------------

function closeModal() {
    $('form-modal').classList.add('hidden');
    $('form-modal-body').innerHTML = '';
}

/** Open the shared modal. `onSubmit` gets the FormData; the modal closes when it resolves, and a rejection is shown. */
function openModal(title, html, onSubmit) {
    $('form-modal-title').textContent = title;
    const form = $('form-modal-body');
    form.innerHTML = html;
    form.onsubmit = async (event) => {
        event.preventDefault();
        try {
            await onSubmit(new FormData(form));
            closeModal();
        } catch (error) {
            showMessage(error.message || 'La operación falló', 'error');
        }
    };
    $('form-modal').classList.remove('hidden');
}

// --- the page ----------------------------------------------------------------------------------------------------

/** Reload the company and its users and draw everything. The notice is cleared first, so show a new one AFTER. */
async function render() {
    hideMessage();
    const [company, users] = await Promise.all([empresaApi.company(), empresaApi.listUsers()]);
    state.company = company;
    state.users = users;

    $('empresa-name').textContent = company.name;
    $('empresa-seats').textContent = `${company.seats_used} de ${company.seat_limit} lugares`;
    $('empresa-views').textContent = viewsSummary(company.radar_detail_views);
    const full = company.seats_used >= company.seat_limit;
    const addButton = $('empresa-add');
    addButton.disabled = full;
    addButton.title = full ? 'No quedan lugares: desactivá a alguien o pedí más lugares' : '';

    const meId = state.me?.id;
    $('empresa-users').innerHTML = users.map((user) => {
        const isViewer = user.role === 'viewer';
        const views = isViewer ? viewsSummary(user.radar_detail_views) : 'Las de la empresa';
        const actions = isViewer
            ? `
                <button class="btn-secondary" data-edit="${user.id}">Editar</button>
                <button class="btn-secondary" data-toggle="${user.id}">${user.is_active ? 'Desactivar' : 'Activar'}</button>
                <button class="btn-secondary" data-views="${user.id}">Vistas</button>
                <button class="btn-secondary" data-reset="${user.id}">Resetear contraseña</button>
                <button class="btn-secondary" data-revoke="${user.id}">Cerrar sesiones</button>`
            : '<span class="toolbar-note">Lo administra el administrador general</span>';
        return `
            <tr>
                <td>${safeText(user.username)}${user.id === meId ? ' <span class="status-pill">vos</span>' : ''}</td>
                <td>${safeText(user.full_name)}</td>
                <td>${ROLE_LABELS[user.role] || safeText(user.role)}</td>
                <td>${user.is_active ? 'Sí' : 'No'}</td>
                <td>${safeText(views)}</td>
                <td class="table-actions">${actions}</td>
            </tr>`;
    }).join('');
    wireRowButtons();
}

const byId = (id) => state.users.find((u) => String(u.id) === String(id));

/** Connect the buttons of the table rows (they are drawn again on every render). */
function wireRowButtons() {
    const each = (selector, handler) => {
        $('empresa-users').querySelectorAll(selector).forEach((el) => {
            el.onclick = () => handler(byId(el.dataset[selector.slice(6, -1)]));
        });
    };
    each('[data-edit]', openEditForm);
    each('[data-toggle]', toggleActive);
    each('[data-views]', openViewsForm);
    each('[data-reset]', openPasswordForm);
    each('[data-revoke]', revokeSessions);
}

function openAddForm() {
    openModal(
        'Agregar usuario',
        `
            <label>Usuario <input name="username" type="text" minlength="3" maxlength="32" pattern="[a-zA-Z0-9._-]+" required></label>
            <label>Nombre <input name="full_name" type="text" maxlength="128"></label>
            <label>Email <input name="email" type="email" maxlength="254"></label>
            <label>Contraseña inicial <input name="password" type="password" minlength="12" maxlength="128" autocomplete="new-password" required></label>
            <p class="toolbar-note">Entra como lector de tu empresa y empieza con las vistas de la empresa.</p>
            <div class="form-actions"><button class="btn" type="submit">Crear</button></div>
        `,
        async (formData) => {
            const payload = {
                username: formData.get('username'),
                password: formData.get('password'),
                full_name: formData.get('full_name') || null,
                email: formData.get('email') || null,
            };
            await empresaApi.createUser(payload);
            await render();
            showMessage(`Usuario ${payload.username.toLowerCase()} creado`);
        },
    );
}

function openEditForm(user) {
    openModal(
        `Editar usuario ${user.username}`,
        `
            <label>Nombre <input name="full_name" type="text" maxlength="128" value="${safeText(user.full_name)}"></label>
            <label>Email <input name="email" type="email" maxlength="254" value="${safeText(user.email)}"></label>
            <div class="form-actions"><button class="btn" type="submit">Guardar</button></div>
        `,
        async (formData) => {
            await empresaApi.patchUser(user.id, {
                full_name: formData.get('full_name') || null,
                email: formData.get('email') || null,
            });
            await render();
            showMessage(`Usuario ${user.username} actualizado`);
        },
    );
}

async function toggleActive(user) {
    const action = user.is_active ? 'desactivar' : 'activar';
    if (!window.confirm(`¿Confirma ${action} a ${user.username}?`)) return;
    try {
        await empresaApi.patchUser(user.id, { is_active: !user.is_active });
        await render();
        showMessage(`Usuario ${user.username} ${user.is_active ? 'desactivado' : 'activado'}`);
    } catch (error) {
        // For example 409 when reactivating with no free seat.
        showMessage(error.message, 'error');
    }
}

function openPasswordForm(user) {
    openModal(
        `Resetear contraseña de ${user.username}`,
        `
            <label>Contraseña nueva <input name="password" type="password" minlength="12" maxlength="128" autocomplete="new-password" required></label>
            <p class="toolbar-note">Se cierran todas las sesiones de ${safeText(user.username)}.</p>
            <div class="form-actions"><button class="btn" type="submit">Guardar</button></div>
        `,
        async (formData) => {
            await empresaApi.resetPassword(user.id, formData.get('password'));
            await render();
            showMessage(`Contraseña de ${user.username} actualizada`);
        },
    );
}

async function revokeSessions(user) {
    if (!window.confirm(`¿Cerrar todas las sesiones de ${user.username}?`)) return;
    try {
        await empresaApi.revokeSessions(user.id);
        await render();
        showMessage(`Sesiones de ${user.username} cerradas`);
    } catch (error) {
        showMessage(error.message, 'error');
    }
}

/**
 * Views picker for a member: only what the company has can be offered (decision C4). A company with "Todas" can give
 * "Todas" or any radar; otherwise the choices are exactly the company's radars.
 */
async function openViewsForm(user) {
    const companyViews = state.company.radar_detail_views;
    const companyHasAll = companyViews.includes(ALL_RADARS);
    const radars = (await api.getRadars(false)).filter((radar) => radar.detail_view_enabled);
    const offered = radars.filter((radar) => companyHasAll || companyViews.includes(radar.code));
    const stored = user.radar_detail_views || [];
    const hasAll = stored.includes(ALL_RADARS);
    const offeredCodes = new Set(offered.map((radar) => radar.code));
    // Saved codes that are not offered now (the view is off, or the company lost it) are sent back unchanged.
    const keptHidden = stored.filter((code) => code !== ALL_RADARS && !offeredCodes.has(code));

    const allRow = companyHasAll
        ? `<label class="checkbox-row"><input type="checkbox" name="all"${hasAll ? ' checked' : ''}> Todas</label>`
        : '';
    const rows = offered.length
        ? offered.map((radar) => `
            <label class="checkbox-row">
                <input type="checkbox" name="radar" value="${safeText(radar.code)}"${!hasAll && stored.includes(radar.code) ? ' checked' : ''}>
                ${safeText(radar.code)} - ${safeText(radar.title)}
            </label>`).join('')
        : '<p class="toolbar-note">La empresa no tiene vistas de radar para repartir.</p>';

    openModal(
        `Vistas de radar de ${user.username}`,
        `
            ${allRow}
            <fieldset class="views-radars"><legend>${companyHasAll ? 'O elegir radares' : 'Radares de la empresa'}</legend>${rows}</fieldset>
            <div class="form-actions"><button class="btn" type="submit">Guardar</button></div>
        `,
        async (formData) => {
            const views = formData.get('all') ? [ALL_RADARS] : [...formData.getAll('radar'), ...keptHidden];
            await empresaApi.setRadarViews(user.id, views);
            await render();
            showMessage(`Vistas de ${user.username} actualizadas`);
        },
    );
}

async function init() {
    const me = await initPageSession();
    if (!me) return;  // initPageSession reloads the page, and nginx then serves the login
    state.me = me;
    $('session-user').textContent = me.full_name || me.username;
    $('logout-btn').onclick = async () => {
        await authApi.logout();
        window.location.assign('login');
    };
    $('empresa-add').onclick = openAddForm;
    $('close-form-modal').onclick = closeModal;
    $('form-modal').addEventListener('click', (event) => {
        if (event.target === $('form-modal')) closeModal();
    });
    $('empresa-message').querySelector('.feedback-close').onclick = hideMessage;
    try {
        await render();
    } catch (error) {
        showMessage(error.message || 'No se pudo cargar la empresa', 'error');
    }
}

init();
