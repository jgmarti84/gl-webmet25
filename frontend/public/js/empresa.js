/**
 * Company admin panel (/empresa, spec C): the company's seats and views, and its users.
 * Company admins manage only the viewers of their company; other company admins are listed read-only (the general
 * admin looks after them).
 */
import { authApi, initPageSession } from './auth-api.js';
import { empresaApi } from './empresa-api.js';
import { api } from './shared/api.js';
import { mountProfile } from './shared/profile-section.js';
import { ALL_RADARS } from './shared/radar-views.js';
import { readTools, toolsFieldsHtml, toolsSummary } from './shared/tools-form.js';

const ROLE_LABELS = { org_admin: 'Admin de institución', viewer: 'Lector' };
// How long a success notice stays before it closes by itself (errors stay until the × is pressed).
const SUCCESS_MESSAGE_MS = 4000;

const state = { company: null, users: [], invitations: [], me: null };
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
        const actions = form.querySelector('.form-actions');
        form.insertBefore(box, actions);  // insertBefore(x, null) appends, for forms with no buttons row
    }
    box.textContent = text;
}

/**
 * Open the shared modal. `onSubmit` gets the FormData; the modal closes when it resolves. A rejection is shown inside
 * the modal (not in the page notice behind it), and the form stays open so the person can fix the data.
 */
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

// --- the page ----------------------------------------------------------------------------------------------------

/** Reload the company and its users and draw everything. The notice is cleared first, so show a new one AFTER. */
async function render() {
    hideMessage();
    const [company, users, invitations] = await Promise.all([
        empresaApi.company(),
        empresaApi.listUsers(),
        empresaApi.listInvitations(),
    ]);
    state.company = company;
    state.users = users;
    state.invitations = invitations;

    $('empresa-name').textContent = company.name;
    // Summary cards, drawn like the admin dashboard cards: a big number and a small line under it.
    const card = (num, sub) => `<span class="num">${safeText(num)}</span> <span class="sub">${safeText(sub)}</span>`;
    // A pending invitation reserves a seat (spec E): the card says how many are held.
    const held = company.pending_invitations || 0;
    $('empresa-seats').innerHTML = card(
        `${company.seats_used} de ${company.seat_limit}`,
        held ? `lugares (+${held} reservado${held === 1 ? '' : 's'} por invitaciones)` : 'lugares',
    );
    const activeUsers = users.filter((user) => user.is_active).length;
    $('empresa-active').innerHTML = card(activeUsers, `de ${users.length} en total`);
    const views = company.radar_detail_views;
    $('empresa-views').innerHTML = views.includes(ALL_RADARS)
        ? card('Todas', 'incluidas las de radares futuros')
        : card(views.length, views.length ? views.join(', ') : 'ninguna');
    const full = company.seats_used + held >= company.seat_limit;
    const addButton = $('empresa-add');
    addButton.disabled = full;
    addButton.title = full ? 'No quedan lugares: desactivá a alguien o pedí más lugares' : '';

    const meId = state.me?.id;
    $('empresa-users').innerHTML = users.map((user) => {
        const isViewer = user.role === 'viewer';
        const views = isViewer ? toolsSummary(user.radar_detail_views, user.tools) : 'Las de la institución';
        const actions = isViewer
            ? `
                <button class="btn-secondary" data-edit="${user.id}">Editar</button>
                <button class="btn-secondary" data-views="${user.id}">Herramientas</button>
                <button class="btn-secondary" data-reset="${user.id}">Resetear contraseña</button>
                <button class="btn-secondary" data-revoke="${user.id}">Cerrar sesiones</button>
                <button class="btn-secondary" data-unlink="${user.id}">Desvincular</button>`
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
    renderInvitations();
}

/** The pending invitations: who, with which views, until when, and the Reenviar / Cancelar buttons. */
function renderInvitations() {
    const rows = state.invitations.map((invitation) => `
        <tr>
            <td>${safeText(invitation.email)}${invitation.existing_account ? ' <span class="status-pill">Ya tiene cuenta</span>' : ''}</td>
            <td>${safeText(toolsSummary(invitation.radar_views || state.company.radar_detail_views, invitation.tools ?? state.company.tools))}</td>
            <td>${safeText(new Date(invitation.expires_at).toLocaleDateString('es-AR'))}</td>
            <td class="table-actions">
                <button class="btn-secondary" data-resend-invitation="${safeText(invitation.id)}">Reenviar</button>
                <button class="btn-secondary" data-cancel-invitation="${safeText(invitation.id)}">Cancelar</button>
            </td>
        </tr>`).join('');
    $('empresa-invitations').innerHTML = rows
        || '<tr><td colspan="4" class="toolbar-note">No hay invitaciones pendientes</td></tr>';
    $('empresa-invitations').querySelectorAll('[data-resend-invitation]').forEach((el) => {
        el.onclick = () => resendInvitation(el.dataset.resendInvitation);
    });
    $('empresa-invitations').querySelectorAll('[data-cancel-invitation]').forEach((el) => {
        el.onclick = () => cancelInvitation(el.dataset.cancelInvitation);
    });
}

/** A new link for the same person (the old one stops working). */
async function resendInvitation(id) {
    try {
        const invitation = await empresaApi.resendInvitation(id);
        await render();
        showMessage(`Invitación reenviada a ${invitation.email}`);
    } catch (error) {
        showMessage(error.message, 'error');
    }
}

/** Close an invitation: its link stops working and its seat is free again. */
async function cancelInvitation(id) {
    const invitation = state.invitations.find((item) => String(item.id) === String(id));
    if (!window.confirm(`¿Cancelar la invitación a ${invitation ? invitation.email : 'esta persona'}? El link deja de funcionar.`)) return;
    try {
        await empresaApi.cancelInvitation(id);
        await render();
        showMessage('Invitación cancelada');
    } catch (error) {
        showMessage(error.message, 'error');
    }
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
    each('[data-views]', openViewsForm);
    each('[data-reset]', openPasswordForm);
    each('[data-revoke]', revokeSessions);
    each('[data-unlink]', unlinkUser);
}

/**
 * Radar views the invited person starts with: only what the institution has can be offered (decision C4), as in the
 * views form. Everything starts ticked (the institution's own list, which is what a new member gets).
 */
async function invitationViewsHtml() {
    const companyViews = state.company.radar_detail_views;
    const companyHasAll = companyViews.includes(ALL_RADARS);
    const radars = (await api.getRadars(false)).filter((radar) => radar.detail_view_enabled);
    const offered = radars.filter((radar) => companyHasAll || companyViews.includes(radar.code));
    const allRow = companyHasAll
        ? '<label class="checkbox-row"><input type="checkbox" name="all" checked> Todas</label>'
        : '';
    const rows = offered.length
        ? offered.map((radar) => `
            <label class="checkbox-row">
                <input type="checkbox" name="radar" value="${safeText(radar.code)}"${companyHasAll ? '' : ' checked'}>
                ${safeText(radar.code)} - ${safeText(radar.title)}
            </label>`).join('')
        : '<p class="toolbar-note">La institución no tiene vistas de radar para repartir.</p>';
    return `${allRow}<fieldset class="views-radars"><legend>${companyHasAll ? 'O elegir radares' : 'Vistas de radar'}</legend>${rows}</fieldset>`;
}

/**
 * "Agregar usuario": create the account now with an initial password, or invite the person by mail (spec E): they get
 * a link, fill in their own data (or use Google) and come in as a viewer of this institution with the views chosen here.
 */
async function openAddForm() {
    // Only the tools the institution has are offered, ticked: it cannot give what it does not have.
    const companyTools = state.company.tools || {};
    let viewsHtml;
    try {
        viewsHtml = await invitationViewsHtml();
    } catch (error) {
        showMessage(error.message || 'No se pudo preparar el formulario', 'error');
        return;
    }
    openModal(
        'Agregar usuario',
        `
            <label class="checkbox-row"><input type="radio" name="create_mode" value="password" checked> Crear con una contraseña inicial</label>
            <label class="checkbox-row"><input type="radio" name="create_mode" value="invite"> Invitar por mail</label>
            <div id="add-password-fields">
                <label>Usuario <input name="username" type="text" minlength="3" maxlength="32" pattern="[a-zA-Z0-9._-]+"></label>
                <label>Nombre <input name="full_name" type="text" maxlength="128"></label>
                <label>Email <input name="email" type="email" maxlength="254"></label>
                <label>Contraseña inicial <input name="password" type="password" minlength="10" maxlength="128" autocomplete="new-password"></label>
                <p class="toolbar-note">Mínimo 10 caracteres, con al menos un carácter especial (por ejemplo ! - _ . @ #).</p>
                <p class="toolbar-note">Entra como lector de tu institución, con las vistas que marques abajo.</p>
            </div>
            <div id="add-invite-fields" hidden>
                <label>Mail de la persona <input name="invite_email" type="email" maxlength="254" autocomplete="off"></label>
                <p class="toolbar-note">Le mandamos un mail con un link (vale 7 días). Completa sus datos o entra con Google y queda como lector de tu institución, con las vistas que marques abajo. Mientras no lo acepte, la invitación reserva un lugar.</p>
            </div>
            ${viewsHtml}
            ${toolsFieldsHtml({ values: companyTools, only: companyTools })}
            <div class="form-actions"><button class="btn" type="submit">Continuar</button></div>
        `,
        async (formData) => {
            // The views picked below apply to both ways: the account made now and the invitation.
            const views = formData.get('all') ? [ALL_RADARS] : formData.getAll('radar');
            const chosen = readTools(formData, companyTools);
            const tools = Object.keys(chosen).length ? { tools: chosen } : {};
            if (formData.get('create_mode') === 'invite') {
                const email = String(formData.get('invite_email') || '').trim();
                if (!email) throw new Error('Escribí el mail de la persona a invitar');
                const sent = await empresaApi.createInvitation({ email, radar_views: views, ...tools });
                await render();
                // The mail already has an account: a warning, the invitation was sent anyway.
                showMessage(sent.existing_account
                    ? `Invitación enviada a ${email}. Ese mail ya tiene una cuenta: la invitación se envió igual. Al aceptarla, entrará a ${sent.organization_name} con su cuenta actual.`
                    : `Invitación enviada a ${email}`);
                return;
            }
            if (!formData.get('username') || !formData.get('password')) {
                throw new Error('Completá el usuario y la contraseña inicial');
            }
            const payload = {
                username: formData.get('username'),
                password: formData.get('password'),
                full_name: formData.get('full_name') || null,
                email: formData.get('email') || null,
                radar_detail_view: views,
                ...tools,
            };
            await empresaApi.createUser(payload);
            await render();
            showMessage(`Usuario ${payload.username.toLowerCase()} creado`);
        },
    );
    // Show only the fields of the chosen way (the other block stays hidden and is not read).
    const form = $('form-modal-body');
    const switchMode = () => {
        const inviting = form.querySelector('input[name="create_mode"]:checked').value === 'invite';
        $('add-password-fields').hidden = inviting;
        $('add-invite-fields').hidden = !inviting;
    };
    form.querySelectorAll('input[name="create_mode"]').forEach((radio) => radio.addEventListener('change', switchMode));
    switchMode();
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

/**
 * Take a user out of the institution: it stops taking a seat, loses the radar views the institution gave it and its
 * sessions are closed. Its account stays active (only the general admin activates or deactivates accounts), and once
 * it is out only the general admin can put it back, so it is confirmed first.
 */
async function unlinkUser(user) {
    const question = `¿Confirma desvincular a ${user.username} de la institución? Se le cierran las sesiones y pierde `
        + 'sus vistas de radar. Deja de ocupar un lugar. Solo el administrador general podrá volver a sumarlo.';
    if (!window.confirm(question)) return;
    try {
        await empresaApi.unlinkUser(user.id);
        await render();
        showMessage(`Usuario ${user.username} desvinculado de la institución`);
    } catch (error) {
        showMessage(error.message, 'error');
    }
}

function openPasswordForm(user) {
    openModal(
        `Resetear contraseña de ${user.username}`,
        `
            <label>Contraseña nueva <input name="password" type="password" minlength="10" maxlength="128" autocomplete="new-password" required></label>
            <p class="toolbar-note">Mínimo 10 caracteres, con al menos un carácter especial (por ejemplo ! - _ . @ #).</p>
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
        : '<p class="toolbar-note">La institución no tiene vistas de radar para repartir.</p>';

    // Only the tools the institution has are offered: it cannot give what it does not have.
    const companyTools = state.company.tools || {};
    openModal(
        `Herramientas de ${user.username}`,
        `
            ${allRow}
            <fieldset class="views-radars"><legend>${companyHasAll ? 'O elegir radares' : 'Radares de la institución'}</legend>${rows}</fieldset>
            ${toolsFieldsHtml({ values: user.tools || {}, only: companyTools })}
            <div class="form-actions"><button class="btn" type="submit">Guardar</button></div>
        `,
        async (formData) => {
            const views = formData.get('all') ? [ALL_RADARS] : [...formData.getAll('radar'), ...keptHidden];
            const chosen = readTools(formData, companyTools);
            await empresaApi.setPermissions(user.id, {
                radar_detail_view: views,
                ...(Object.keys(chosen).length ? { tools: chosen } : {}),
            });
            await render();
            showMessage(`Herramientas de ${user.username} actualizadas`);
        },
    );
}

// --- sections of the panel --------------------------------------------------------------------------------------

const SECTIONS = ['usuarios', 'perfil'];

/** The section named in the address (#perfil), or the users by default. */
function currentSection() {
    const hash = window.location.hash.replace('#', '');
    return SECTIONS.includes(hash) ? hash : 'usuarios';
}

/** Show one section (the company's users, or the person's own profile), mark its menu entry and load it. */
async function showSection(section) {
    hideMessage();
    $('empresa-section-usuarios').hidden = section !== 'usuarios';
    $('empresa-section-perfil').hidden = section !== 'perfil';
    document.querySelectorAll('#sidebar-nav [data-section]').forEach((link) => {
        link.classList.toggle('active', link.dataset.section === section);
    });
    try {
        if (section === 'perfil') {
            $('empresa-name').textContent = 'Mi perfil';  // the users section puts the company name back (render)
            await mountProfile($('perfil-content'), { me: state.me, openModal, showMessage });
        } else {
            await render();
        }
    } catch (error) {
        showMessage(error.message || 'No se pudo cargar la sección', 'error');
    }
}

/** Switch section without adding history entries. */
function navigateTo(section) {
    // Full path, not just "#section": a relative URL resolves against <base href>, which would move the address bar
    // to the map ("/#perfil") even though the page stays.
    history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${section}`);
    showSection(section);
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
    // The side menu: [data-section] links switch sections instead of following their address.
    $('sidebar-nav').addEventListener('click', (event) => {
        const link = event.target.closest('[data-section]');
        if (!link) return;
        event.preventDefault();
        navigateTo(link.dataset.section);
    });
    // A hand-edited address (or the back button) also switches sections.
    window.addEventListener('hashchange', () => showSection(currentSection()));
    await showSection(currentSection());
}

init();
