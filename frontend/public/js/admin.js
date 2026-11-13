import { adminApi, EXPIRED_SESSION_MESSAGE } from './admin-api.js';
import { authApi, redirectToLogin } from './auth-api.js';
import {
    buildMemberRequest, buildOrganizationPayload, eligibleAdmins, filterAdmins, filterOrganizations, soleAdminBlock,
} from './shared/org-form.js';
import { mountProfile } from './shared/profile-section.js';
import { ALL_RADARS, viewsSummary } from './shared/radar-views.js';
import { beyondInstitution, readTools, toolsFieldsHtml, toolsSummary, usableToolsSummary } from './shared/tools-form.js';

const SECTIONS = ['dashboard', 'radars', 'products', 'references', 'cogs', 'estrategias', 'volumenes', 'tops-cores', 'nccubes', 'colormaps', 'colormap-options', 'users', 'organizations', 'invitations', 'mails', 'profile'];
const STATUS_OPTIONS = ['available', 'missing', 'error', 'pending', 'processing', 'archived'];
const DEFAULT_PAGE_SIZE = 25;
const MAX_PAGE_SIZE = 100;

// Inline icons for row actions (inherit button text color via currentColor).
const ICON_EDIT = '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><title>Editar</title><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>';
// Wrench of the "Herramientas" button and padlock of the "Seguridad" button of the users table. Like the other icons,
// each carries its <title>, which the browser shows as a tooltip.
const ICON_TOOLS = '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><title>Herramientas</title><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>';
const ICON_LOCK = '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><title>Seguridad</title><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';
const ICON_TRASH = '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><title>Eliminar</title><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>';

const state = {
    section: 'dashboard',
    me: null,
    message: null,
    sortBy: {
        radars: 'code',
        products: 'id',
        references: 'id',
        estrategias: 'code',
        volumenes: 'id',
        colormaps: 'cmap_name',
        'colormap-options': 'product_key',
        users: 'username',
    },
    sortDir: {
        radars: 'asc',
        products: 'asc',
        references: 'asc',
        estrategias: 'asc',
        volumenes: 'asc',
        colormaps: 'asc',
        'colormap-options': 'asc',
        users: 'asc',
    },
    cogs: {
        page: 1,
        page_size: DEFAULT_PAGE_SIZE,
        total: 0,
        selected: new Set(),
        search: '',
    },
    tops: {
        page: 1,
        page_size: DEFAULT_PAGE_SIZE,
        total: 0,
        selected: new Set(),
        search: '',
    },
    nccubes: {
        page: 1,
        page_size: DEFAULT_PAGE_SIZE,
        total: 0,
        search: '',
    },
    // Per-section client-side filter state: { search, facets: { field: value } }
    filters: {},
};

// Django-admin-style filter configuration per client-loaded section.
// `boolean` facets render Sí/No; `select` facets auto-derive distinct values
// from the data unless explicit options are supplied at render time.
const FILTER_CONFIG = {
    radars: {
        facets: [
            { field: 'code', label: 'Código', type: 'text' },
            { field: 'title', label: 'Título', type: 'text' },
            { field: 'is_active', label: 'Activo', type: 'boolean' },
        ],
    },
    products: {
        facets: [
            { field: 'product_key', label: 'Clave', type: 'text' },
            { field: 'product_title', label: 'Título', type: 'text' },
            { field: 'enabled', label: 'Habilitado', type: 'boolean' },
            { field: 'see_in_open', label: 'Visible público', type: 'boolean' },
            { field: 'unit', label: 'Unidad', type: 'select' },
            { field: 'default_cmap', label: 'Cmap por defecto', type: 'select' },
        ],
    },
    references: {
        facets: [
            { field: 'product_id', label: 'Producto', type: 'select' },
            { field: 'title', label: 'Título', type: 'text' },
            { field: 'unit', label: 'Unidad', type: 'select' },
        ],
    },
    estrategias: {
        facets: [
            { field: 'code', label: 'Código', type: 'text' },
            { field: 'description', label: 'Descripción', type: 'text' },
        ],
    },
    volumenes: {
        facets: [{ field: 'value', label: 'Valor', type: 'text' }],
    },
    colormaps: {
        facets: [
            { field: 'cmap_name', label: 'Nombre', type: 'text' },
            { field: 'is_system', label: 'Sistema', type: 'boolean' },
        ],
    },
    'colormap-options': {
        facets: [
            { field: 'product_key', label: 'Producto', type: 'select' },
            { field: 'cmap_name', label: 'Mapa de colores', type: 'select' },
        ],
    },
    invitations: {
        facets: [
            { field: 'email', label: 'Mail', type: 'text' },
            { field: 'organization_name', label: 'Institución', type: 'select' },
            { field: 'role_label', label: 'Rol', type: 'select' },
        ],
    },
    organizations: {
        facets: [
            { field: 'name', label: 'Institución', type: 'text' },
            { field: 'is_active', label: 'Activa', type: 'boolean' },
            { field: 'seats_state', label: 'Lugares', type: 'select' },
        ],
    },
    users: {
        facets: [
            { field: 'username', label: 'Usuario', type: 'text' },
            { field: 'role', label: 'Rol', type: 'select' },
            { field: 'is_active', label: 'Activo', type: 'boolean' },
        ],
    },
};

/** Facet definition type within a section ('text' | 'select' | 'boolean'). */
function facetType(section, field) {
    const facet = (FILTER_CONFIG[section]?.facets || []).find((f) => f.field === field);
    return facet ? facet.type : 'select';
}

function getFilters(section) {
    if (!state.filters[section]) {
        state.filters[section] = { search: '', facets: {} };
    }
    return state.filters[section];
}

/** Distinct, sorted, non-empty string values of a field across items. */
function distinctValues(items, field) {
    const set = new Set();
    items.forEach((item) => {
        const value = item[field];
        if (value !== null && value !== undefined && value !== '') {
            set.add(String(value));
        }
    });
    return [...set].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
}

/** Build the ` data-facets="{...}"` attribute string for a table row. */
function rowFacetAttr(section, item) {
    const facets = FILTER_CONFIG[section]?.facets || [];
    const obj = {};
    facets.forEach((facet) => {
        let value = item[facet.field];
        if (facet.type === 'boolean') {
            value = String(Boolean(value));
        } else {
            value = value === null || value === undefined ? '' : String(value);
        }
        obj[facet.field] = value;
    });
    return ` data-facets="${safeText(JSON.stringify(obj))}"`;
}

/**
 * Render the reusable filter bar HTML for a section.
 * `options.facetOptions` may override auto-derived select options:
 *   { product_id: [{ value, label }, ...] }
 */
function renderFilterBar(section, items, options = {}) {
    const config = FILTER_CONFIG[section];
    if (!config) return '';
    const current = getFilters(section);
    const facetOptions = options.facetOptions || {};

    const facetsHtml = (config.facets || []).map((facet) => {
        const selected = current.facets[facet.field] ?? '';
        if (facet.type === 'text') {
            return `
                <label class="filter-field">
                    <span>${safeText(facet.label)}</span>
                    <input type="search" data-filter-facet="${safeText(facet.field)}" placeholder="${safeText(facet.label)}…" value="${safeText(selected)}">
                </label>`;
        }
        let optionsHtml;
        if (facet.type === 'boolean') {
            optionsHtml = `
                <option value="true" ${selected === 'true' ? 'selected' : ''}>Sí</option>
                <option value="false" ${selected === 'false' ? 'selected' : ''}>No</option>`;
        } else {
            const values = facetOptions[facet.field]
                || distinctValues(items, facet.field).map((v) => ({ value: v, label: v }));
            optionsHtml = values
                .map((opt) => `<option value="${safeText(opt.value)}" ${selected === String(opt.value) ? 'selected' : ''}>${safeText(opt.label)}</option>`)
                .join('');
        }
        return `
            <label class="filter-field">
                <span>${safeText(facet.label)}</span>
                <select data-filter-facet="${safeText(facet.field)}">
                    <option value="">Todos</option>
                    ${optionsHtml}
                </select>
            </label>`;
    }).join('');

    return `
        <div class="filter-bar" data-filter-section="${section}">
            <div class="filter-field filter-search">
                <span>Buscar en toda la tabla</span>
                <input type="search" data-filter-search placeholder="Buscar en todas las columnas…" value="${safeText(current.search)}">
            </div>
            ${facetsHtml}
            <div class="filter-spacer"></div>
            <button type="button" class="btn-secondary btn-sm" data-filter-clear>Limpiar filtros</button>
            <span class="filter-count" data-filter-count></span>
        </div>`;
}

/** Show/hide table rows based on the section's current search + facet state. */
function applyRowFilters(section) {
    const bar = elements.sectionContent.querySelector(`[data-filter-section="${section}"]`);
    const table = elements.sectionContent.querySelector('table');
    if (!table || !table.tBodies.length) return;
    const filters = getFilters(section);
    const search = (filters.search || '').trim().toLowerCase();
    const rows = [...table.tBodies[0].rows];
    let visible = 0;

    rows.forEach((row) => {
        let show = true;
        if (search && !row.textContent.toLowerCase().includes(search)) {
            show = false;
        }
        if (show) {
            let rowFacets = {};
            try {
                rowFacets = JSON.parse(row.dataset.facets || '{}');
            } catch (error) {
                rowFacets = {};
            }
            for (const [field, value] of Object.entries(filters.facets)) {
                if (value === '' || value === null || value === undefined) continue;
                const rowValue = String(rowFacets[field] ?? '');
                if (facetType(section, field) === 'text') {
                    if (!rowValue.toLowerCase().includes(String(value).toLowerCase().trim())) {
                        show = false;
                        break;
                    }
                } else if (rowValue !== String(value)) {
                    show = false;
                    break;
                }
            }
        }
        row.hidden = !show;
        if (show) visible += 1;
    });

    const countEl = bar?.querySelector('[data-filter-count]');
    if (countEl) countEl.innerHTML = `<b>${visible}</b> de ${rows.length}`;
}

/** Wire the filter bar's inputs. `onFacet` is an optional side-effect callback. */
function wireFilterBar(section, onFacet) {
    const bar = elements.sectionContent.querySelector(`[data-filter-section="${section}"]`);
    if (!bar) return;
    const filters = getFilters(section);

    const searchInput = bar.querySelector('[data-filter-search]');
    if (searchInput) {
        searchInput.oninput = () => {
            filters.search = searchInput.value;
            applyRowFilters(section);
        };
    }

    bar.querySelectorAll('[data-filter-facet]').forEach((control) => {
        const handler = () => {
            const field = control.dataset.filterFacet;
            filters.facets[field] = control.value;
            applyRowFilters(section);
            if (onFacet) onFacet(field, control.value);
        };
        // Text inputs filter live; selects fire on change.
        if (control.tagName === 'INPUT') {
            control.oninput = handler;
        } else {
            control.onchange = handler;
        }
    });

    const clearButton = bar.querySelector('[data-filter-clear]');
    if (clearButton) {
        clearButton.onclick = () => {
            filters.search = '';
            filters.facets = {};
            renderSection();
        };
    }

    applyRowFilters(section);
}

const elements = {
    sectionTitle: document.getElementById('section-title'),
    sectionContent: document.getElementById('section-content'),
    feedbackMessage: document.getElementById('feedback-message'),
    nav: document.getElementById('sidebar-nav'),
    formModal: document.getElementById('form-modal'),
    formModalTitle: document.getElementById('form-modal-title'),
    formModalBody: document.getElementById('form-modal-body'),
    closeFormModal: document.getElementById('close-form-modal'),
    creatorModal: document.getElementById('creator-modal'),
};

// How long a success notice stays on screen before it closes by itself. Errors never close by themselves:
// they carry something the admin has to read and act on, so only the × closes them.
const SUCCESS_MESSAGE_MS = 4000;
let messageTimer = null;

function showMessage(text, type = 'success') {
    state.message = text;
    elements.feedbackMessage.querySelector('.feedback-text').textContent = text;
    elements.feedbackMessage.classList.remove('hidden', 'success', 'error');
    elements.feedbackMessage.classList.add(type);
    // A new notice replaces the previous one, so the old timer must not close the new notice early.
    clearTimeout(messageTimer);
    messageTimer = type === 'success' ? setTimeout(hideMessage, SUCCESS_MESSAGE_MS) : null;
}

function hideMessage() {
    clearTimeout(messageTimer);
    messageTimer = null;
    state.message = null;
    elements.feedbackMessage.querySelector('.feedback-text').textContent = '';
    elements.feedbackMessage.classList.add('hidden');
    elements.feedbackMessage.classList.remove('success', 'error');
}

// The × of any notice (the feedback one and the initial-password warning) hides its own box.
document.addEventListener('click', (event) => {
    const close = event.target.closest('.feedback-close');
    if (!close) return;
    const box = close.closest('.feedback-message');
    if (box === elements.feedbackMessage) hideMessage();
    else box.classList.add('hidden');
});

// An account with a mail that was never confirmed: it shows "Activo: Sí" but cannot log in until the owner opens the
// link of the mail, or an admin vouches for it ("Verificar mail"). Accounts without a mail have nothing to verify.
function needsMailVerification(user) {
    return Boolean(user.email) && !user.email_verified;
}

function safeText(value) {
    const raw = value === null || value === undefined ? '' : String(value);
    return raw
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function safeHexColor(value, fallback) {
    const normalized = String(value || '').trim();
    return /^#[0-9a-fA-F]{6}$/.test(normalized) ? normalized : fallback;
}

function fmtDate(value) {
    if (!value) return '';
    return new Date(value).toLocaleString();
}

function fmtBytes(value) {
    if (value === null || value === undefined) return '';
    const mb = Number(value) / (1024 * 1024);
    return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(Number(value) / 1024).toFixed(0)} KB`;
}

function parseHashSection() {
    const hash = window.location.hash.replace('#', '').trim();
    if (!hash || !SECTIONS.includes(hash)) {
        return 'dashboard';
    }
    return hash;
}

function setActiveSidebar(section) {
    elements.nav.querySelectorAll('a').forEach((link) => {
        link.classList.toggle('active', link.dataset.section === section);
    });
}

/**
 * Switch sections via replaceState so browsing the admin never pushes new
 * history entries. This keeps a single "back" step pointing at the main map.
 */
function navigateTo(section) {
    const target = SECTIONS.includes(section) ? section : 'dashboard';
    // Full path, not just "#section": a relative URL resolves against <base href>, which would move the address
    // bar to the map ("/#users") even though the page stays.
    history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${target}`);
    renderSection();
}

/**
 * Return to the main map. If the admin was opened from the map (flag set on
 * the map's link click), use history.back() so the browser restores the map
 * exactly as it was left (selections, frame, zoom) via the bfcache. Otherwise
 * navigate to the map fresh.
 */
function goBackToMap() {
    const cameFromMain = sessionStorage.getItem('webmet25_admin_from_main') === '1';
    sessionStorage.removeItem('webmet25_admin_from_main');
    if (cameFromMain && window.history.length > 1) {
        history.back();
    } else {
        // "./" is the map inside the base path (<base href>), not the root of the host.
        window.location.href = './';
    }
}

/** Append/refresh ▲▼ sort indicators on the current section's sort headers. */
function decorateSortHeaders(section) {
    if (state.sortBy[section] === undefined) return;
    elements.sectionContent.querySelectorAll('[data-sort]').forEach((button) => {
        const isActive = state.sortBy[section] === button.dataset.sort;
        const arrow = isActive ? (state.sortDir[section] === 'asc' ? '▲' : '▼') : '';
        let indicator = button.querySelector('.sort-ind');
        if (!indicator) {
            indicator = document.createElement('span');
            indicator.className = 'sort-ind';
            button.appendChild(indicator);
        }
        indicator.textContent = arrow;
    });
}

/** Show (or clear, with no text) the error inside the open form modal, just above the buttons. */
function setFormModalError(text) {
    const form = elements.formModalBody;
    let box = form.querySelector('.form-error');
    if (!text) {
        box?.remove();
        return;
    }
    if (!box) {
        box = document.createElement('p');
        box.className = 'form-error';
        box.setAttribute('role', 'alert');
        form.insertBefore(box, form.querySelector('.form-actions'));  // null (no buttons row) appends at the end
    }
    box.textContent = text;
}

/**
 * `onSubmit` gets the FormData; the modal closes when it resolves. A rejection is shown inside the modal (not in the
 * page notice behind it) and the form stays open so the person can fix the data.
 */
function openFormModal(title, html, onSubmit) {
    elements.formModalTitle.textContent = title;
    elements.formModalBody.innerHTML = html;
    elements.formModalBody.onsubmit = async (event) => {
        event.preventDefault();
        setFormModalError('');
        try {
            await onSubmit(new FormData(elements.formModalBody));
            closeFormModal();
        } catch (error) {
            setFormModalError(error.message || 'La operación falló');
        }
    };
    elements.formModal.classList.remove('hidden');
}

function closeFormModal() {
    elements.formModal.classList.add('hidden');
    elements.formModalBody.innerHTML = '';
}

function sortableValue(value) {
    if (value === null || value === undefined) return '';
    return typeof value === 'string' ? value.toLowerCase() : value;
}

function sortItems(items, sectionName) {
    const sortField = state.sortBy[sectionName];
    const sortDirection = state.sortDir[sectionName] === 'asc' ? 1 : -1;
    return [...items].sort((a, b) => {
        const av = sortableValue(a[sortField]);
        const bv = sortableValue(b[sortField]);
        if (av > bv) return sortDirection;
        if (av < bv) return -sortDirection;
        return 0;
    });
}

function switchSort(sectionName, field) {
    if (state.sortBy[sectionName] === field) {
        state.sortDir[sectionName] = state.sortDir[sectionName] === 'asc' ? 'desc' : 'asc';
    } else {
        state.sortBy[sectionName] = field;
        state.sortDir[sectionName] = 'asc';
    }
    renderSection();
}

/** Wire every [data-sort] header button in the current section to switchSort. */
function wireSortHeaders(section) {
    elements.sectionContent.querySelectorAll('[data-sort]').forEach((button) => {
        button.onclick = () => switchSort(section, button.dataset.sort);
    });
}

function requireConfirmation(label) {
    return window.confirm(`¿Confirma la eliminación de ${label}?`);
}

async function renderDashboard() {
    const [counts, products] = await Promise.all([
        adminApi.getDashboardCounts(),
        adminApi.listProducts(),
    ]);
    elements.sectionContent.innerHTML = `
        <p class="section-subtitle">Acciones rápidas</p>
        <div class="dash-actions">
            <button type="button" class="dash-action" id="dash-open-creator">
                <span class="dash-action-ico">🎨</span>
                <span class="dash-action-text">
                    <span class="dash-action-title">Crear mapa de colores</span>
                    <span class="dash-action-sub">Abrir el creador de colormaps personalizado</span>
                </span>
            </button>
            <button type="button" class="dash-action" id="dash-back-map">
                <span class="dash-action-ico">🗺</span>
                <span class="dash-action-text">
                    <span class="dash-action-title">Volver al mapa</span>
                    <span class="dash-action-sub">Regresar al visualizador en el mismo estado</span>
                </span>
            </button>
        </div>

        <p class="section-subtitle">Resumen</p>
        <div class="card-grid">
            <div class="card">
                <h3>Radares</h3>
                <div class="card-stat"><span class="num">${counts.radarsTotal}</span><span class="sub">${counts.radarsActive} activos</span></div>
                <a href="#radars" data-section="radars">Abrir sección →</a>
            </div>
            <div class="card">
                <h3>Productos</h3>
                <div class="card-stat"><span class="num">${counts.productsTotal}</span><span class="sub">${counts.productsEnabled} habilitados</span></div>
                <a href="#products" data-section="products">Abrir sección →</a>
            </div>
            <div class="card">
                <h3>COGs</h3>
                <div class="card-stat"><span class="num">${counts.cogsTotal}</span><span class="sub">${counts.cogsAvailable} disponibles · ${counts.cogsMissing} faltantes · ${counts.cogsError} con error</span></div>
                <a href="#cogs" data-section="cogs">Abrir sección →</a>
            </div>
            <div class="card">
                <h3>Referencias</h3>
                <div class="card-stat"><span class="num">${counts.referencesTotal}</span><span class="sub">entradas de color</span></div>
                <a href="#references" data-section="references">Abrir sección →</a>
            </div>
            <div class="card">
                <h3>Estrategias / Volumenes</h3>
                <div class="card-stat"><span class="num">${counts.estrategiasTotal} / ${counts.volumenesTotal}</span><span class="sub">configuración de escaneo</span></div>
                <a href="#estrategias" data-section="estrategias">Abrir sección →</a>
            </div>
            <div class="card">
                <h3>Tops &amp; Cores</h3>
                <div class="card-stat"><span class="num">${counts.topsTotal}</span><span class="sub">${counts.topsAvailable} disponibles · ${counts.topsMissing} faltantes</span></div>
                <a href="#tops-cores" data-section="tops-cores">Abrir sección →</a>
            </div>
            <div class="card">
                <h3>Cubos NetCDF</h3>
                <div class="card-stat"><span class="num">${counts.nccubesTotal}</span><span class="sub">${counts.nccubesNewest ? `último: ${safeText(fmtDate(counts.nccubesNewest))}` : 'sin cubos indexados'}</span></div>
                <a href="#nccubes" data-section="nccubes">Abrir sección →</a>
            </div>
        </div>
    `;

    document.getElementById('dash-open-creator').onclick = () => openColormapCreator(products);
    document.getElementById('dash-back-map').onclick = goBackToMap;
}

async function renderRadars() {
    const radars = sortItems(await adminApi.listRadars(), 'radars');

    elements.sectionContent.innerHTML = `
        <div class="toolbar">
            <button class="btn" id="radars-add">+ Agregar nuevo radar</button>
        </div>
        ${renderFilterBar('radars', radars)}
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th><button data-sort="code">Código</button></th>
                    <th><button data-sort="title">Título</button></th>
                    <th><button data-sort="center_lat">Lat centro</button></th>
                    <th><button data-sort="center_long">Long centro</button></th>
                    <th><button data-sort="img_radio">Radio img</button></th>
                    <th><button data-sort="is_active">Activo</button></th>
                    <th><button data-sort="detail_view_enabled">Vista detalle</button></th>
                    <th><button data-sort="created_at">Creado</button></th>
                    <th>Acciones</th>
                </tr>
            </thead>
            <tbody>
                ${radars.map((radar) => `
                    <tr${rowFacetAttr('radars', radar)}>
                        <td>${safeText(radar.code)}</td>
                        <td>${safeText(radar.title)}</td>
                        <td>${safeText(radar.center_lat)}</td>
                        <td>${safeText(radar.center_long)}</td>
                        <td>${safeText(radar.img_radio)}</td>
                        <td class="toggle-cell"><input type="checkbox" data-toggle-radar="${radar.code}" ${radar.is_active ? 'checked' : ''}></td>
                        <td class="toggle-cell"><input type="checkbox" data-toggle-detail-view="${radar.code}" ${radar.detail_view_enabled ? 'checked' : ''}></td>
                        <td>${fmtDate(radar.created_at)}</td>
                        <td class="table-actions">
                            <button class="btn-secondary" data-edit-radar="${radar.code}">${ICON_EDIT}</button>
                            <button class="btn-danger" data-delete-radar="${radar.code}">${ICON_TRASH}</button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;

    document.getElementById('radars-add').onclick = () => openRadarForm();
    wireFilterBar('radars');
    wireSortHeaders('radars');

    elements.sectionContent.querySelectorAll('[data-toggle-radar]').forEach((element) => {
        element.onchange = async (event) => {
            const code = event.target.dataset.toggleRadar;
            await adminApi.patchRadar(code, { is_active: event.target.checked });
            showMessage(`Radar ${code} actualizado`, 'success');
        };
    });

    elements.sectionContent.querySelectorAll('[data-toggle-detail-view]').forEach((element) => {
        element.onchange = async (event) => {
            const code = event.target.dataset.toggleDetailView;
            await adminApi.patchRadar(code, { detail_view_enabled: event.target.checked });
            showMessage(`Radar ${code} actualizado`, 'success');
        };
    });

    elements.sectionContent.querySelectorAll('[data-edit-radar]').forEach((element) => {
        element.onclick = async () => openRadarForm(await adminApi.getRadar(element.dataset.editRadar));
    });

    elements.sectionContent.querySelectorAll('[data-delete-radar]').forEach((element) => {
        element.onclick = async () => {
            const code = element.dataset.deleteRadar;
            if (!requireConfirmation(`radar ${code}`)) return;
            await adminApi.deleteRadar(code);
            showMessage(`Radar ${code} eliminado`, 'success');
            renderSection();
        };
    });
}

function openRadarForm(radar = null) {
    const isEdit = Boolean(radar);
    openFormModal(
        isEdit ? `Editar radar ${radar.code}` : 'Agregar radar',
        `
            ${!isEdit ? '<label>Código <input name="code" required maxlength="16"></label>' : ''}
            <label>Título <input name="title" value="${safeText(radar?.title)}" required></label>
            <label>Descripción <input name="description" value="${safeText(radar?.description)}"></label>
            <label>Lat centro <input name="center_lat" type="number" step="any" value="${safeText(radar?.center_lat)}" required></label>
            <label>Long centro <input name="center_long" type="number" step="any" value="${safeText(radar?.center_long)}" required></label>
            <label>Radio img <input name="img_radio" type="number" value="${safeText(radar?.img_radio)}" required></label>
            <label>Lat punto 1 <input name="point1_lat" type="number" step="any" value="${safeText(radar?.point1_lat ?? 0)}"></label>
            <label>Long punto 1 <input name="point1_long" type="number" step="any" value="${safeText(radar?.point1_long ?? 0)}"></label>
            <label>Lat punto 2 <input name="point2_lat" type="number" step="any" value="${safeText(radar?.point2_lat ?? 0)}"></label>
            <label>Long punto 2 <input name="point2_long" type="number" step="any" value="${safeText(radar?.point2_long ?? 0)}"></label>
            <label>Activo <select name="is_active"><option value="true" ${radar?.is_active ? 'selected' : ''}>Sí</option><option value="false" ${radar && !radar.is_active ? 'selected' : ''}>No</option></select></label>
            <label>Vista detalle habilitada <select name="detail_view_enabled"><option value="true" ${radar?.detail_view_enabled ? 'selected' : ''}>Sí</option><option value="false" ${radar && !radar.detail_view_enabled ? 'selected' : ''}>No</option></select></label>
            <div class="form-actions"><button class="btn" type="submit">${isEdit ? 'Guardar' : 'Crear'}</button></div>
        `,
        async (formData) => {
            const payload = Object.fromEntries(formData.entries());
            payload.center_lat = Number(payload.center_lat);
            payload.center_long = Number(payload.center_long);
            payload.img_radio = Number(payload.img_radio);
            payload.point1_lat = Number(payload.point1_lat);
            payload.point1_long = Number(payload.point1_long);
            payload.point2_lat = Number(payload.point2_lat);
            payload.point2_long = Number(payload.point2_long);
            payload.is_active = payload.is_active === 'true';
            payload.detail_view_enabled = payload.detail_view_enabled === 'true';
            if (isEdit) {
                await adminApi.updateRadar(radar.code, payload);
                showMessage(`Radar ${radar.code} actualizado`, 'success');
            } else {
                await adminApi.createRadar(payload);
                showMessage(`Radar ${payload.code} creado`, 'success');
            }
            await renderSection();
        },
    );
}

async function renderProducts() {
    const products = sortItems(await adminApi.listProducts(), 'products');
    elements.sectionContent.innerHTML = `
        <div class="toolbar"><button class="btn" id="products-add">+ Agregar nuevo producto</button></div>
        ${renderFilterBar('products', products)}
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th><button data-sort="id">ID</button></th>
                    <th><button data-sort="product_key">Clave</button></th>
                    <th><button data-sort="product_title">Título</button></th>
                    <th><button data-sort="enabled">Habilitado</button></th>
                    <th><button data-sort="see_in_open">Visible público</button></th>
                    <th><button data-sort="min_value">Mín</button></th>
                    <th><button data-sort="max_value">Máx</button></th>
                    <th><button data-sort="unit">Unidad</button></th>
                    <th><button data-sort="default_cmap">Cmap por defecto</button></th>
                    <th>Acciones</th>
                </tr>
            </thead>
            <tbody>
                ${products.map((product) => `
                    <tr${rowFacetAttr('products', product)}>
                        <td>${product.id}</td>
                        <td>${safeText(product.product_key)}</td>
                        <td>${safeText(product.product_title)}</td>
                        <td class="toggle-cell"><input type="checkbox" data-toggle-product-enabled="${product.id}" ${product.enabled ? 'checked' : ''}></td>
                        <td class="toggle-cell"><input type="checkbox" data-toggle-product-open="${product.id}" ${product.see_in_open ? 'checked' : ''}></td>
                        <td>${safeText(product.min_value)}</td>
                        <td>${safeText(product.max_value)}</td>
                        <td>${safeText(product.unit)}</td>
                        <td>${safeText(product.default_cmap)}</td>
                        <td class="table-actions">
                            <button class="btn-secondary" data-edit-product="${product.id}">${ICON_EDIT}</button>
                            <button class="btn-danger" data-delete-product="${product.id}">${ICON_TRASH}</button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;

    document.getElementById('products-add').onclick = () => openProductForm();
    wireFilterBar('products');
    wireSortHeaders('products');

    elements.sectionContent.querySelectorAll('[data-toggle-product-enabled]').forEach((element) => {
        element.onchange = async (event) => {
            await adminApi.patchProduct(event.target.dataset.toggleProductEnabled, { enabled: event.target.checked });
            showMessage('Estado de habilitación del producto actualizado', 'success');
        };
    });

    elements.sectionContent.querySelectorAll('[data-toggle-product-open]').forEach((element) => {
        element.onchange = async (event) => {
            await adminApi.patchProduct(event.target.dataset.toggleProductOpen, { see_in_open: event.target.checked });
            showMessage('Visibilidad del producto actualizada', 'success');
        };
    });

    elements.sectionContent.querySelectorAll('[data-edit-product]').forEach((element) => {
        element.onclick = async () => openProductForm(await adminApi.getProduct(element.dataset.editProduct));
    });
    elements.sectionContent.querySelectorAll('[data-delete-product]').forEach((element) => {
        element.onclick = async () => {
            const id = element.dataset.deleteProduct;
            if (!requireConfirmation(`product ${id}`)) return;
            await adminApi.deleteProduct(id);
            showMessage(`Producto ${id} eliminado`, 'success');
            renderSection();
        };
    });
}

function openProductForm(product = null) {
    const isEdit = Boolean(product);
    openFormModal(
        isEdit ? `Editar producto ${product.product_key}` : 'Agregar producto',
        `
            <label>Clave de producto <input name="product_key" maxlength="16" value="${safeText(product?.product_key)}" required></label>
            <label>Título <input name="product_title" value="${safeText(product?.product_title)}" required></label>
            <label>Descripción <input name="product_description" value="${safeText(product?.product_description)}"></label>
            <label>Habilitado <select name="enabled"><option value="true" ${product?.enabled ? 'selected' : ''}>Sí</option><option value="false" ${product && !product.enabled ? 'selected' : ''}>No</option></select></label>
            <label>Visible público <select name="see_in_open"><option value="true" ${product?.see_in_open ? 'selected' : ''}>Sí</option><option value="false" ${product && !product.see_in_open ? 'selected' : ''}>No</option></select></label>
            <label>Valor mín <input name="min_value" type="number" step="any" value="${safeText(product?.min_value)}"></label>
            <label>Valor máx <input name="max_value" type="number" step="any" value="${safeText(product?.max_value)}"></label>
            <label>Unidad <input name="unit" value="${safeText(product?.unit)}"></label>
            <label>Mapa de colores por defecto <input name="default_cmap" maxlength="64" value="${safeText(product?.default_cmap)}" placeholder="ej. grc_th"></label>
            <div class="form-actions"><button class="btn" type="submit">${isEdit ? 'Guardar' : 'Crear'}</button></div>
        `,
        async (formData) => {
            const payload = Object.fromEntries(formData.entries());
            payload.enabled = payload.enabled === 'true';
            payload.see_in_open = payload.see_in_open === 'true';
            payload.min_value = payload.min_value ? Number(payload.min_value) : null;
            payload.max_value = payload.max_value ? Number(payload.max_value) : null;
            payload.default_cmap = payload.default_cmap?.trim() || null;
            if (isEdit) {
                await adminApi.updateProduct(product.id, payload);
                showMessage(`Producto ${product.id} actualizado`, 'success');
            } else {
                await adminApi.createProduct(payload);
                showMessage('Producto creado', 'success');
            }
            await renderSection();
        },
    );
}

async function renderReferences() {
    const [references, products] = await Promise.all([adminApi.listReferences(), adminApi.listProducts()]);
    const sorted = sortItems(references, 'references');
    const productsById = new Map(products.map((item) => [item.id, item]));
    const productFacetOptions = products.map((product) => ({ value: String(product.id), label: product.product_key }));

    elements.sectionContent.innerHTML = `
        <div class="toolbar">
            <button class="btn" id="references-add">+ Agregar entradas</button>
            <button class="btn-danger" id="references-bulk-delete">Eliminar todas las del producto seleccionado</button>
        </div>
        ${renderFilterBar('references', sorted, { facetOptions: { product_id: productFacetOptions } })}
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th><button data-sort="id">ID</button></th>
                    <th><button data-sort="product_id">Producto</button></th>
                    <th><button data-sort="value">Valor</button></th>
                    <th><button data-sort="color">Color</button></th>
                    <th><button data-sort="color_font">Color de fuente</button></th>
                    <th><button data-sort="title">Título</button></th>
                    <th><button data-sort="unit">Unidad</button></th>
                    <th>Acciones</th>
                </tr>
            </thead>
            <tbody>
                ${sorted.map((reference) => `
                    <tr${rowFacetAttr('references', reference)}>
                        <td>${reference.id}</td>
                        <td>${safeText(productsById.get(reference.product_id)?.product_key || reference.product_id)}</td>
                        <td>${safeText(reference.value)}</td>
                        <td><span class="color-preview" style="background:${safeHexColor(reference.color, '#000000')}"></span>${safeText(reference.color)}</td>
                        <td><span class="color-preview" style="background:${safeHexColor(reference.color_font, '#ffffff')}"></span>${safeText(reference.color_font)}</td>
                        <td>${safeText(reference.title)}</td>
                        <td>${safeText(reference.unit)}</td>
                        <td class="table-actions">
                            <button class="btn-secondary" data-edit-reference="${reference.id}">${ICON_EDIT}</button>
                            <button class="btn-danger" data-delete-reference="${reference.id}">${ICON_TRASH}</button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;

    wireFilterBar('references');
    wireSortHeaders('references');
    document.getElementById('references-add').onclick = () => openReferenceBulkForm(products);
    document.getElementById('references-bulk-delete').onclick = async () => {
        const selectedProductId = getFilters('references').facets.product_id || '';
        if (!selectedProductId) {
            showMessage('Primero seleccione un producto en el filtro "Producto"', 'error');
            return;
        }
        const productKey = productsById.get(Number(selectedProductId))?.product_key || selectedProductId;
        if (!requireConfirmation(`todas las referencias del producto ${productKey}`)) return;
        const result = await adminApi.bulkDeleteReferences(selectedProductId);
        showMessage(`Se eliminaron ${result.deleted_count} referencias`, 'success');
        renderSection();
    };

    elements.sectionContent.querySelectorAll('[data-edit-reference]').forEach((element) => {
        element.onclick = async () => openReferenceEditForm(await adminApi.getReference(element.dataset.editReference), products);
    });
    elements.sectionContent.querySelectorAll('[data-delete-reference]').forEach((element) => {
        element.onclick = async () => {
            const id = element.dataset.deleteReference;
            if (!requireConfirmation(`reference ${id}`)) return;
            await adminApi.deleteReference(id);
            showMessage(`Referencia ${id} eliminada`, 'success');
            renderSection();
        };
    });
}

function openReferenceEditForm(reference, products) {
    openFormModal(
        `Editar referencia ${reference.id}`,
        `
            <label>Producto
                <select name="product_id">${products.map((p) => `<option value="${p.id}" ${p.id === reference.product_id ? 'selected' : ''}>${p.product_key}</option>`)}</select>
            </label>
            <label>Valor <input name="value" type="number" step="any" value="${safeText(reference.value)}" required></label>
            <label>Título <input name="title" value="${safeText(reference.title)}"></label>
            <label>Unidad <input name="unit" value="${safeText(reference.unit)}"></label>
            <label>Color <input name="color" type="color" value="${safeText(reference.color || '#000000')}"></label>
            <label>Color de fuente <input name="color_font" type="color" value="${safeText(reference.color_font || '#ffffff')}"></label>
            <label>Descripción <input name="description" value="${safeText(reference.description)}"></label>
            <div class="form-actions"><button class="btn" type="submit">Guardar</button></div>
        `,
        async (formData) => {
            const payload = Object.fromEntries(formData.entries());
            payload.product_id = Number(payload.product_id);
            payload.value = Number(payload.value);
            await adminApi.updateReference(reference.id, payload);
            showMessage(`Referencia ${reference.id} actualizada`, 'success');
            await renderSection();
        },
    );
}

function openReferenceBulkForm(products) {
    // TODO: References admin CRUD is foundational for future user-defined colormap management.
    const row = () => `
        <div class="reference-row">
            <label>Valor <input name="value" type="number" step="any" required></label>
            <label>Título <input name="title"></label>
            <label>Unidad <input name="unit"></label>
            <label>Color <input name="color" type="color" value="#000000"></label>
            <label>Color de fuente <input name="color_font" type="color" value="#ffffff"></label>
            <label>Descripción <input name="description"></label>
        </div>
    `;

    openFormModal(
        'Agregar entradas de referencia',
        `
            <label>Producto
                <select name="product_id" required>
                    ${products.map((product) => `<option value="${product.id}">${product.product_key}</option>`).join('')}
                </select>
            </label>
            <div id="reference-bulk-rows">${row()}</div>
            <div class="toolbar">
                <button type="button" class="btn-secondary" id="reference-row-add">Agregar fila</button>
            </div>
            <div class="form-actions"><button class="btn" type="submit">Crear entradas</button></div>
        `,
        async (formData) => {
            const productId = Number(formData.get('product_id'));
            const values = formData.getAll('value');
            const titles = formData.getAll('title');
            const units = formData.getAll('unit');
            const colors = formData.getAll('color');
            const colorFonts = formData.getAll('color_font');
            const descriptions = formData.getAll('description');

            const payloads = values.map((value, index) => ({
                product_id: productId,
                value: Number(value),
                title: titles[index] || '',
                unit: units[index] || '',
                color: colors[index] || '#000000',
                color_font: colorFonts[index] || '#ffffff',
                description: descriptions[index] || '',
            }));

            await Promise.all(payloads.map((payload) => adminApi.createReference(payload)));
            showMessage(`Se crearon ${payloads.length} entradas de referencia`, 'success');
            await renderSection();
        },
    );

    document.getElementById('reference-row-add').onclick = () => {
        document.getElementById('reference-bulk-rows').insertAdjacentHTML('beforeend', row());
    };
}

function renderPagination(page, pageSize, total, prefix) {
    const pageCount = Math.max(1, Math.ceil(total / pageSize));
    return `
        <div class="pagination">
            <div>Página ${page} de ${pageCount} — ${total} registros</div>
            <div class="table-actions">
                <button class="btn-secondary" id="${prefix}-prev" ${page <= 1 ? 'disabled' : ''}>Anterior</button>
                <button class="btn-secondary" id="${prefix}-next" ${page >= pageCount ? 'disabled' : ''}>Siguiente</button>
            </div>
        </div>
    `;
}

function getCogFilterValues() {
    return {
        radar_code: document.getElementById('cogs-filter-radar')?.value || '',
        product_key: document.getElementById('cogs-filter-product')?.value || '',
        status: document.getElementById('cogs-filter-status')?.value || '',
        vol_nr: document.getElementById('cogs-filter-vol')?.value || '',
        start_time: document.getElementById('cogs-filter-start')?.value || '',
        end_time: document.getElementById('cogs-filter-end')?.value || '',
    };
}

async function renderCogs() {
    const [radars, products] = await Promise.all([adminApi.listRadars(), adminApi.listProducts()]);
    const filters = getCogFilterValues();
    const query = {
        ...filters,
        page: state.cogs.page,
        page_size: state.cogs.page_size,
    };
    const response = await adminApi.listCogs(query);
    state.cogs.total = response.total;

    elements.sectionContent.innerHTML = `
        <div class="filter-bar">
            <label class="filter-field"><span>Radar</span><select id="cogs-filter-radar"><option value="">Todos</option></select></label>
            <label class="filter-field"><span>Producto</span><select id="cogs-filter-product"><option value="">Todos</option></select></label>
            <label class="filter-field"><span>Estado</span><select id="cogs-filter-status"><option value="">Todos</option>${STATUS_OPTIONS.map((item) => `<option value="${item}" ${filters.status === item ? 'selected' : ''}>${item}</option>`).join('')}</select></label>
            <label class="filter-field"><span>Vol</span><input id="cogs-filter-vol" placeholder="vol_nr" style="width:90px"></label>
            <label class="filter-field"><span>Desde</span><input id="cogs-filter-start" type="datetime-local"></label>
            <label class="filter-field"><span>Hasta</span><input id="cogs-filter-end" type="datetime-local"></label>
            <button class="btn" id="cogs-apply-filters">Aplicar</button>
            <div class="filter-spacer"></div>
            <div class="filter-field filter-search"><span>Buscar en página</span><input type="search" id="cogs-search" placeholder="Filtrar filas cargadas…" value="${safeText(state.cogs.search)}"></div>
        </div>
        <div class="toolbar">
            <button class="btn-danger" id="cogs-delete-filtered">Eliminar por filtros</button>
            <button class="btn-danger" id="cogs-delete-selected">Eliminar seleccionados</button>
        </div>
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th><input type="checkbox" id="cogs-select-all"></th>
                    <th>ID</th><th>Radar</th><th>Producto</th><th>Observación</th><th>Archivo</th>
                    <th>Tamaño</th><th>Estado</th><th>Vol</th><th>Polarimétrico</th><th>Indexado</th><th>Acciones</th>
                </tr>
            </thead>
            <tbody id="cogs-table-body"></tbody>
        </table>
        </div>
        ${renderPagination(response.page, response.page_size, response.total, 'cogs')}
    `;

    const radarSelect = document.getElementById('cogs-filter-radar');
    const productSelect = document.getElementById('cogs-filter-product');
    radars.forEach((item) => {
        const option = document.createElement('option');
        option.value = item.code || '';
        option.textContent = item.code || '';
        radarSelect.appendChild(option);
    });
    products.forEach((item) => {
        const option = document.createElement('option');
        option.value = item.product_key || '';
        option.textContent = item.product_key || '';
        productSelect.appendChild(option);
    });
    radarSelect.value = filters.radar_code || '';
    productSelect.value = filters.product_key || '';
    document.getElementById('cogs-filter-vol').value = filters.vol_nr || '';
    document.getElementById('cogs-filter-start').value = filters.start_time || '';
    document.getElementById('cogs-filter-end').value = filters.end_time || '';

    const cogsTableBody = document.getElementById('cogs-table-body');
    response.items.forEach((item) => {
        const itemId = Number(item.id);
        const row = document.createElement('tr');

        const selectCell = document.createElement('td');
        const selectInput = document.createElement('input');
        selectInput.type = 'checkbox';
        selectInput.dataset.cogSelect = String(itemId);
        selectInput.checked = state.cogs.selected.has(itemId);
        selectCell.appendChild(selectInput);
        row.appendChild(selectCell);

        const idCell = document.createElement('td');
        idCell.textContent = String(itemId);
        row.appendChild(idCell);

        [item.radar_code, item.product_key, fmtDate(item.observation_time), item.file_name, item.file_size_bytes].forEach((value) => {
            const cell = document.createElement('td');
            cell.textContent = value === null || value === undefined ? '' : String(value);
            row.appendChild(cell);
        });

        const statusCell = document.createElement('td');
        const statusSelect = document.createElement('select');
        statusSelect.dataset.cogStatus = String(itemId);
        STATUS_OPTIONS.forEach((statusValue) => {
            const option = document.createElement('option');
            option.value = statusValue;
            option.textContent = statusValue;
            option.selected = item.status === statusValue;
            statusSelect.appendChild(option);
        });
        statusCell.appendChild(statusSelect);
        row.appendChild(statusCell);

        [item.vol_nr, item.polarimetric_var, fmtDate(item.indexed_at)].forEach((value) => {
            const cell = document.createElement('td');
            cell.textContent = value === null || value === undefined ? '' : String(value);
            row.appendChild(cell);
        });

        const actionsCell = document.createElement('td');
        actionsCell.className = 'table-actions';
        const deleteButton = document.createElement('button');
        deleteButton.className = 'btn-danger';
        deleteButton.dataset.cogDelete = String(itemId);
        deleteButton.type = 'button';
        deleteButton.innerHTML = ICON_TRASH;
        deleteButton.title = 'Eliminar';
        actionsCell.appendChild(deleteButton);
        row.appendChild(actionsCell);

        cogsTableBody.appendChild(row);
    });

    document.getElementById('cogs-apply-filters').onclick = () => { state.cogs.page = 1; renderSection(); };

    const cogsSearch = document.getElementById('cogs-search');
    const applyCogsSearch = () => {
        const term = (state.cogs.search || '').trim().toLowerCase();
        [...cogsTableBody.rows].forEach((row) => {
            row.hidden = term ? !row.textContent.toLowerCase().includes(term) : false;
        });
    };
    cogsSearch.oninput = () => { state.cogs.search = cogsSearch.value; applyCogsSearch(); };
    applyCogsSearch();
    document.getElementById('cogs-prev').onclick = () => { if (state.cogs.page > 1) { state.cogs.page -= 1; renderSection(); } };
    document.getElementById('cogs-next').onclick = () => {
        const maxPage = Math.max(1, Math.ceil(state.cogs.total / state.cogs.page_size));
        if (state.cogs.page < maxPage) { state.cogs.page += 1; renderSection(); }
    };

    document.getElementById('cogs-select-all').onchange = (event) => {
        response.items.forEach((item) => {
            if (event.target.checked) state.cogs.selected.add(item.id);
            else state.cogs.selected.delete(item.id);
        });
        renderSection();
    };

    elements.sectionContent.querySelectorAll('[data-cog-select]').forEach((element) => {
        element.onchange = (event) => {
            const id = Number(event.target.dataset.cogSelect);
            if (event.target.checked) state.cogs.selected.add(id);
            else state.cogs.selected.delete(id);
        };
    });

    elements.sectionContent.querySelectorAll('[data-cog-status]').forEach((element) => {
        element.onchange = async (event) => {
            const id = Number(event.target.dataset.cogStatus);
            await adminApi.patchCogStatus(id, event.target.value);
            showMessage(`Estado del COG ${id} actualizado`, 'success');
        };
    });

    elements.sectionContent.querySelectorAll('[data-cog-delete]').forEach((element) => {
        element.onclick = async () => {
            const id = Number(element.dataset.cogDelete);
            if (!requireConfirmation(`COG ${id}`)) return;
            await adminApi.deleteCog(id);
            state.cogs.selected.delete(id);
            showMessage(`COG ${id} eliminado`, 'success');
            renderSection();
        };
    });

    document.getElementById('cogs-delete-selected').onclick = async () => {
        const ids = [...state.cogs.selected];
        if (!ids.length) {
            showMessage('Primero seleccione al menos un registro COG', 'error');
            return;
        }
        if (!requireConfirmation(`${ids.length} registros COG seleccionados`)) return;
        await Promise.all(ids.map((id) => adminApi.deleteCog(id)));
        state.cogs.selected.clear();
        showMessage(`Se eliminaron ${ids.length} registros COG seleccionados`, 'success');
        renderSection();
    };

    document.getElementById('cogs-delete-filtered').onclick = async () => {
        const typed = window.prompt('Escriba DELETE para confirmar la eliminación de todos los COGs que coincidan con los filtros activos');
        if ((typed || '').trim().toUpperCase() !== 'DELETE') return;
        const deletedCount = await adminApi.bulkDelete('cogs', filters);
        showMessage(`Se eliminaron ${deletedCount} registros COG por filtro`, 'success');
        state.cogs.selected.clear();
        renderSection();
    };
}

// TODO: Estrategia CRUD affects indexer behavior; deleting strategy codes referenced by COGs may fail with FK conflict and returns HTTP 409.
async function renderEstrategias() {
    const [estrategias, volumenes] = await Promise.all([adminApi.listEstrategias(), adminApi.listVolumenes()]);
    const sorted = sortItems(estrategias, 'estrategias');
    elements.sectionContent.innerHTML = `
        <div class="toolbar"><button class="btn" id="estrategias-add">+ Agregar estrategia</button></div>
        ${renderFilterBar('estrategias', sorted)}
        <div class="table-wrap">
        <table>
            <thead><tr><th><button data-sort="code">Código</button></th><th><button data-sort="description">Descripción</button></th><th>Volúmenes asociados</th><th>Acciones</th></tr></thead>
            <tbody>
                ${sorted.map((item) => `
                    <tr${rowFacetAttr('estrategias', item)}>
                        <td>${safeText(item.code)}</td>
                        <td>${safeText(item.description)}</td>
                        <td>${(item.volumen_values || []).join(', ')}</td>
                        <td class="table-actions">
                            <button class="btn-secondary" data-edit-estrategia="${item.code}">${ICON_EDIT}</button>
                            <button class="btn-danger" data-delete-estrategia="${item.code}">${ICON_TRASH}</button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;

    wireFilterBar('estrategias');
    wireSortHeaders('estrategias');
    document.getElementById('estrategias-add').onclick = () => openEstrategiaForm(null, volumenes);
    elements.sectionContent.querySelectorAll('[data-edit-estrategia]').forEach((element) => {
        element.onclick = async () => openEstrategiaForm(await adminApi.getEstrategia(element.dataset.editEstrategia), volumenes);
    });
    elements.sectionContent.querySelectorAll('[data-delete-estrategia]').forEach((element) => {
        element.onclick = async () => {
            const code = element.dataset.deleteEstrategia;
            if (!requireConfirmation(`estrategia ${code}`)) return;
            await adminApi.deleteEstrategia(code);
            showMessage(`Estrategia ${code} eliminada`, 'success');
            renderSection();
        };
    });
}

function openEstrategiaForm(estrategia, volumenes) {
    const isEdit = Boolean(estrategia);
    openFormModal(
        isEdit ? `Editar estrategia ${estrategia.code}` : 'Agregar estrategia',
        `
            ${isEdit ? '' : '<label>Código <input name="code" maxlength="16" required></label>'}
            <label>Descripción <input name="description" value="${safeText(estrategia?.description)}"></label>
            <label>Volúmenes
                <select name="volumen_ids" multiple size="8">
                    ${volumenes.map((volumen) => `<option value="${volumen.id}" ${(estrategia?.volumen_ids || []).includes(volumen.id) ? 'selected' : ''}>${volumen.id} - ${volumen.value}</option>`).join('')}
                </select>
            </label>
            <div class="form-actions"><button class="btn" type="submit">${isEdit ? 'Guardar' : 'Crear'}</button></div>
        `,
        async (formData) => {
            const payload = {
                description: formData.get('description') || '',
                volumen_ids: formData.getAll('volumen_ids').map(Number),
            };
            if (isEdit) {
                await adminApi.updateEstrategia(estrategia.code, payload);
                showMessage(`Estrategia ${estrategia.code} actualizada`, 'success');
            } else {
                payload.code = formData.get('code');
                await adminApi.createEstrategia(payload);
                showMessage(`Estrategia ${payload.code} creada`, 'success');
            }
            await renderSection();
        },
    );
}

async function renderVolumenes() {
    const volumenes = sortItems(await adminApi.listVolumenes(), 'volumenes');
    elements.sectionContent.innerHTML = `
        <div class="toolbar"><button class="btn" id="volumenes-add">+ Agregar volumen</button></div>
        ${renderFilterBar('volumenes', volumenes)}
        <div class="table-wrap">
        <table>
            <thead><tr><th><button data-sort="id">ID</button></th><th><button data-sort="value">Valor</button></th><th>Acciones</th></tr></thead>
            <tbody>
                ${volumenes.map((item) => `
                    <tr${rowFacetAttr('volumenes', item)}>
                        <td>${item.id}</td>
                        <td>${item.value}</td>
                        <td class="table-actions">
                            <button class="btn-secondary" data-edit-volumen="${item.id}">${ICON_EDIT}</button>
                            <button class="btn-danger" data-delete-volumen="${item.id}">${ICON_TRASH}</button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;

    wireFilterBar('volumenes');
    wireSortHeaders('volumenes');
    document.getElementById('volumenes-add').onclick = () => openVolumenForm();
    elements.sectionContent.querySelectorAll('[data-edit-volumen]').forEach((element) => {
        element.onclick = async () => openVolumenForm(await adminApi.getVolumen(element.dataset.editVolumen));
    });
    elements.sectionContent.querySelectorAll('[data-delete-volumen]').forEach((element) => {
        element.onclick = async () => {
            const id = element.dataset.deleteVolumen;
            if (!requireConfirmation(`volumen ${id}`)) return;
            await adminApi.deleteVolumen(id);
            showMessage(`Volumen ${id} eliminado`, 'success');
            renderSection();
        };
    });
}

function openVolumenForm(volumen = null) {
    const isEdit = Boolean(volumen);
    openFormModal(
        isEdit ? `Editar volumen ${volumen.id}` : 'Agregar volumen',
        `
            <label>Valor <input type="number" name="value" value="${safeText(volumen?.value)}" required></label>
            <div class="form-actions"><button class="btn" type="submit">${isEdit ? 'Guardar' : 'Crear'}</button></div>
        `,
        async (formData) => {
            const payload = { value: Number(formData.get('value')) };
            if (isEdit) {
                await adminApi.updateVolumen(volumen.id, payload);
                showMessage(`Volumen ${volumen.id} actualizado`, 'success');
            } else {
                await adminApi.createVolumen(payload);
                showMessage('Volumen creado', 'success');
            }
            await renderSection();
        },
    );
}

function getTopsFilterValues() {
    return {
        radar_code: document.getElementById('tops-filter-radar')?.value || '',
        strategy: document.getElementById('tops-filter-strategy')?.value || '',
        vol_nr: document.getElementById('tops-filter-vol')?.value || '',
        status: document.getElementById('tops-filter-status')?.value || '',
        start_time: document.getElementById('tops-filter-start')?.value || '',
        end_time: document.getElementById('tops-filter-end')?.value || '',
    };
}

async function renderTopsCores() {
    const radars = await adminApi.listRadars();
    const filters = getTopsFilterValues();
    const response = await adminApi.listTopsCores({
        ...filters,
        page: state.tops.page,
        page_size: state.tops.page_size,
    });
    state.tops.total = response.total;

    elements.sectionContent.innerHTML = `
        <div class="filter-bar">
            <label class="filter-field"><span>Radar</span><select id="tops-filter-radar"><option value="">Todos</option></select></label>
            <label class="filter-field"><span>Estrategia</span><input id="tops-filter-strategy" placeholder="strategy" style="width:110px"></label>
            <label class="filter-field"><span>Vol</span><input id="tops-filter-vol" placeholder="vol_nr" style="width:90px"></label>
            <label class="filter-field"><span>Estado</span><select id="tops-filter-status"><option value="">Todos</option>${STATUS_OPTIONS.map((item) => `<option value="${item}" ${filters.status === item ? 'selected' : ''}>${item}</option>`).join('')}</select></label>
            <label class="filter-field"><span>Desde</span><input id="tops-filter-start" type="datetime-local"></label>
            <label class="filter-field"><span>Hasta</span><input id="tops-filter-end" type="datetime-local"></label>
            <button class="btn" id="tops-apply-filters">Aplicar</button>
            <div class="filter-spacer"></div>
            <div class="filter-field filter-search"><span>Buscar en página</span><input type="search" id="tops-search" placeholder="Filtrar filas cargadas…" value="${safeText(state.tops.search)}"></div>
        </div>
        <div class="toolbar">
            <button class="btn-danger" id="tops-delete-filtered">Eliminar por filtros</button>
            <button class="btn-danger" id="tops-delete-selected">Eliminar seleccionados</button>
        </div>
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th><input type="checkbox" id="tops-select-all"></th>
                    <th>ID</th><th>Radar</th><th>Estrategia</th><th>Vol</th><th>Observación</th>
                    <th>Cores</th><th>Tops</th><th>Elementos</th><th>Estado</th><th>Archivo</th><th>Creado</th><th>Acciones</th>
                </tr>
            </thead>
            <tbody id="tops-table-body"></tbody>
        </table>
        </div>
        ${renderPagination(response.page, response.page_size, response.total, 'tops')}
    `;

    const topsRadarSelect = document.getElementById('tops-filter-radar');
    radars.forEach((item) => {
        const option = document.createElement('option');
        option.value = item.code || '';
        option.textContent = item.code || '';
        topsRadarSelect.appendChild(option);
    });
    topsRadarSelect.value = filters.radar_code || '';
    document.getElementById('tops-filter-strategy').value = filters.strategy || '';
    document.getElementById('tops-filter-vol').value = filters.vol_nr || '';
    document.getElementById('tops-filter-start').value = filters.start_time || '';
    document.getElementById('tops-filter-end').value = filters.end_time || '';

    const topsTableBody = document.getElementById('tops-table-body');
    response.items.forEach((item) => {
        const itemId = Number(item.id);
        const row = document.createElement('tr');

        const selectCell = document.createElement('td');
        const selectInput = document.createElement('input');
        selectInput.type = 'checkbox';
        selectInput.dataset.topSelect = String(itemId);
        selectInput.checked = state.tops.selected.has(itemId);
        selectCell.appendChild(selectInput);
        row.appendChild(selectCell);

        [
            itemId,
            item.radar_code,
            item.strategy,
            item.vol_nr,
            fmtDate(item.observation_time),
            item.core_count,
            item.top_count,
            item.feature_count,
        ].forEach((value) => {
            const cell = document.createElement('td');
            cell.textContent = value === null || value === undefined ? '' : String(value);
            row.appendChild(cell);
        });

        const statusCell = document.createElement('td');
        const statusSelect = document.createElement('select');
        statusSelect.dataset.topStatus = String(itemId);
        STATUS_OPTIONS.forEach((statusValue) => {
            const option = document.createElement('option');
            option.value = statusValue;
            option.textContent = statusValue;
            option.selected = item.status === statusValue;
            statusSelect.appendChild(option);
        });
        statusCell.appendChild(statusSelect);
        row.appendChild(statusCell);

        const fileCell = document.createElement('td');
        fileCell.textContent = item.file_name || '';
        row.appendChild(fileCell);

        const createdCell = document.createElement('td');
        createdCell.textContent = fmtDate(item.created_at);
        row.appendChild(createdCell);

        const actionsCell = document.createElement('td');
        actionsCell.className = 'table-actions';
        const featuresLink = document.createElement('a');
        featuresLink.className = 'btn-secondary';
        featuresLink.target = '_blank';
        featuresLink.rel = 'noopener noreferrer';
        featuresLink.href = `api/v1/tops-cores/${itemId}/features`;
        featuresLink.textContent = 'Ver elementos';
        actionsCell.appendChild(featuresLink);

        const deleteButton = document.createElement('button');
        deleteButton.className = 'btn-danger';
        deleteButton.dataset.topDelete = String(itemId);
        deleteButton.type = 'button';
        deleteButton.innerHTML = ICON_TRASH;
        deleteButton.title = 'Eliminar';
        actionsCell.appendChild(deleteButton);
        row.appendChild(actionsCell);

        topsTableBody.appendChild(row);
    });

    document.getElementById('tops-apply-filters').onclick = () => { state.tops.page = 1; renderSection(); };

    const topsSearch = document.getElementById('tops-search');
    const applyTopsSearch = () => {
        const term = (state.tops.search || '').trim().toLowerCase();
        [...topsTableBody.rows].forEach((row) => {
            row.hidden = term ? !row.textContent.toLowerCase().includes(term) : false;
        });
    };
    topsSearch.oninput = () => { state.tops.search = topsSearch.value; applyTopsSearch(); };
    applyTopsSearch();
    document.getElementById('tops-prev').onclick = () => { if (state.tops.page > 1) { state.tops.page -= 1; renderSection(); } };
    document.getElementById('tops-next').onclick = () => {
        const maxPage = Math.max(1, Math.ceil(state.tops.total / state.tops.page_size));
        if (state.tops.page < maxPage) { state.tops.page += 1; renderSection(); }
    };

    document.getElementById('tops-select-all').onchange = (event) => {
        response.items.forEach((item) => {
            if (event.target.checked) state.tops.selected.add(item.id);
            else state.tops.selected.delete(item.id);
        });
        renderSection();
    };

    elements.sectionContent.querySelectorAll('[data-top-select]').forEach((element) => {
        element.onchange = (event) => {
            const id = Number(event.target.dataset.topSelect);
            if (event.target.checked) state.tops.selected.add(id);
            else state.tops.selected.delete(id);
        };
    });

    elements.sectionContent.querySelectorAll('[data-top-status]').forEach((element) => {
        element.onchange = async (event) => {
            const id = Number(event.target.dataset.topStatus);
            await adminApi.patchTopsCoresStatus(id, event.target.value);
            showMessage(`Estado de Tops & Cores ${id} actualizado`, 'success');
        };
    });

    elements.sectionContent.querySelectorAll('[data-top-delete]').forEach((element) => {
        element.onclick = async () => {
            const id = Number(element.dataset.topDelete);
            if (!requireConfirmation(`tops & cores ${id}`)) return;
            await adminApi.deleteTopsCores(id);
            state.tops.selected.delete(id);
            showMessage(`Tops & Cores ${id} eliminado`, 'success');
            renderSection();
        };
    });

    document.getElementById('tops-delete-selected').onclick = async () => {
        const ids = [...state.tops.selected];
        if (!ids.length) {
            showMessage('Primero seleccione al menos un registro', 'error');
            return;
        }
        if (!requireConfirmation(`${ids.length} registros de Tops & Cores seleccionados`)) return;
        await Promise.all(ids.map((id) => adminApi.deleteTopsCores(id)));
        state.tops.selected.clear();
        showMessage(`Se eliminaron ${ids.length} registros de Tops & Cores seleccionados`, 'success');
        renderSection();
    };

    document.getElementById('tops-delete-filtered').onclick = async () => {
        const typed = window.prompt('Escriba DELETE para confirmar la eliminación de todos los Tops & Cores que coincidan con los filtros activos');
        if ((typed || '').trim().toUpperCase() !== 'DELETE') return;
        const deletedCount = await adminApi.bulkDelete('tops-cores', filters);
        showMessage(`Se eliminaron ${deletedCount} registros de Tops & Cores por filtro`, 'success');
        state.tops.selected.clear();
        renderSection();
    };
}

// ── NC cubes (read only) ──────────────────────────────────────────────────────

function getNCCubeFilterValues() {
    return {
        radar_code: document.getElementById('nccubes-filter-radar')?.value || '',
        strategy: document.getElementById('nccubes-filter-strategy')?.value || '',
        vol_nr: document.getElementById('nccubes-filter-vol')?.value || '',
        start_time: document.getElementById('nccubes-filter-start')?.value || '',
        end_time: document.getElementById('nccubes-filter-end')?.value || '',
    };
}

/**
 * Read-only on purpose: the indexer creates a row per *_NCCUBE.nc file and
 * deletes it when retention removes the file. Deleting a row here would not
 * touch the file, only hide that volume from storm tracking until re-indexed.
 */
async function renderNCCubes() {
    const radars = await adminApi.listRadars();
    const filters = getNCCubeFilterValues();
    const response = await adminApi.listNCCubes({
        ...filters,
        page: state.nccubes.page,
        page_size: state.nccubes.page_size,
    });
    state.nccubes.total = response.total;

    elements.sectionContent.innerHTML = `
        <p class="section-note">Volúmenes 3D que usa el seguimiento de tormentas. Sólo lectura: el indexador agrega y quita las filas según los archivos en disco.</p>
        <div class="filter-bar">
            <label class="filter-field"><span>Radar</span><select id="nccubes-filter-radar"><option value="">Todos</option></select></label>
            <label class="filter-field"><span>Estrategia</span><input id="nccubes-filter-strategy" placeholder="strategy" style="width:110px"></label>
            <label class="filter-field"><span>Vol</span><input id="nccubes-filter-vol" placeholder="vol_nr" style="width:90px"></label>
            <label class="filter-field"><span>Desde</span><input id="nccubes-filter-start" type="datetime-local"></label>
            <label class="filter-field"><span>Hasta</span><input id="nccubes-filter-end" type="datetime-local"></label>
            <button class="btn" id="nccubes-apply-filters">Aplicar</button>
            <div class="filter-spacer"></div>
            <div class="filter-field filter-search"><span>Buscar en página</span><input type="search" id="nccubes-search" placeholder="Filtrar filas cargadas…" value="${safeText(state.nccubes.search)}"></div>
        </div>
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>ID</th><th>Radar</th><th>Estrategia</th><th>Vol</th><th>Observación</th>
                    <th>Tamaño</th><th>Estado</th><th>Archivo</th><th>Modificado</th><th>Indexado</th>
                </tr>
            </thead>
            <tbody id="nccubes-table-body"></tbody>
        </table>
        </div>
        ${renderPagination(response.page, response.page_size, response.total, 'nccubes')}
    `;

    const radarSelect = document.getElementById('nccubes-filter-radar');
    radars.forEach((item) => {
        const option = document.createElement('option');
        option.value = item.code || '';
        option.textContent = item.code || '';
        radarSelect.appendChild(option);
    });
    radarSelect.value = filters.radar_code || '';
    document.getElementById('nccubes-filter-strategy').value = filters.strategy || '';
    document.getElementById('nccubes-filter-vol').value = filters.vol_nr || '';
    document.getElementById('nccubes-filter-start').value = filters.start_time || '';
    document.getElementById('nccubes-filter-end').value = filters.end_time || '';

    const tableBody = document.getElementById('nccubes-table-body');
    response.items.forEach((item) => {
        const row = document.createElement('tr');
        [
            item.id,
            item.radar_code,
            item.strategy,
            item.vol_nr,
            fmtDate(item.observation_time),
            fmtBytes(item.file_size_bytes),
            item.status,
            item.file_name,
            fmtDate(item.file_mtime),
            fmtDate(item.created_at),
        ].forEach((value) => {
            const cell = document.createElement('td');
            cell.textContent = value === null || value === undefined ? '' : String(value);
            row.appendChild(cell);
        });
        // Full path on hover: it is where the tracking sidecar reads the cube from.
        row.cells[7].title = item.file_path || '';
        tableBody.appendChild(row);
    });

    document.getElementById('nccubes-apply-filters').onclick = () => { state.nccubes.page = 1; renderSection(); };

    const search = document.getElementById('nccubes-search');
    const applySearch = () => {
        const term = (state.nccubes.search || '').trim().toLowerCase();
        [...tableBody.rows].forEach((row) => {
            row.hidden = term ? !row.textContent.toLowerCase().includes(term) : false;
        });
    };
    search.oninput = () => { state.nccubes.search = search.value; applySearch(); };
    applySearch();
    document.getElementById('nccubes-prev').onclick = () => { if (state.nccubes.page > 1) { state.nccubes.page -= 1; renderSection(); } };
    document.getElementById('nccubes-next').onclick = () => {
        const maxPage = Math.max(1, Math.ceil(state.nccubes.total / state.nccubes.page_size));
        if (state.nccubes.page < maxPage) { state.nccubes.page += 1; renderSection(); }
    };
}

// ── Colormap creator ──────────────────────────────────────────────────────────

/** Convert three [0,1] channel floats to #RRGGBB. */
function rgbFloatToHex(r, g, b) {
    const channel = (v) => {
        const n = Math.round(Math.min(1, Math.max(0, Number(v) || 0)) * 255);
        return n.toString(16).padStart(2, '0');
    };
    return `#${channel(r)}${channel(g)}${channel(b)}`;
}

/** Reconstruct hex stops [{position, color}] from channel-based colormap_stops rows. */
function stopsToHexStops(stops) {
    const byOrder = new Map();
    stops.forEach((s) => {
        if (!byOrder.has(s.sort_order)) byOrder.set(s.sort_order, {});
        const entry = byOrder.get(s.sort_order);
        entry.position = s.position;
        entry[s.channel] = s.val_left;
    });
    return [...byOrder.values()]
        .sort((a, b) => a.position - b.position)
        .map((e) => ({ position: e.position, color: rgbFloatToHex(e.r, e.g, e.b) }));
}

/** Fetch the rendered hex color list for a colormap from the public endpoint. */
async function fetchColormapColors(name, steps = 64) {
    try {
        const res = await fetch(`api/v1/colormap/colors/${encodeURIComponent(name)}?steps=${steps}`);
        if (!res.ok) return [];
        const data = await res.json();
        return Array.isArray(data.colors) ? data.colors : [];
    } catch (error) {
        return [];
    }
}

/** Build a CSS left-to-right linear-gradient from a list of hex colors. */
function gradientCss(colors) {
    if (!colors.length) return 'transparent';
    if (colors.length === 1) return colors[0];
    const stops = colors
        .map((c, i) => `${c} ${((i / (colors.length - 1)) * 100).toFixed(1)}%`)
        .join(', ');
    return `linear-gradient(to right, ${stops})`;
}

/**
 * Open the colormap creator.
 * @param {Array} products  Product list for the assignment chips.
 * @param {Object|null} existing  When provided, opens in edit mode:
 *   { cmap_name, stops: [{position, color}], product_keys: [], optionRows: [{id, product_key}] }
 */
function openColormapCreator(products, existing = null) {
    const isEdit = Boolean(existing);

    /** In-memory stops state: array of {position: number, color: hex string} */
    let creatorStops = isEdit && existing.stops.length >= 2
        ? existing.stops.map((s) => ({ position: s.position, color: safeHexColor(s.color, '#888888') }))
        : [
            { position: 0.0, color: '#000000' },
            { position: 1.0, color: '#ffffff' },
        ];

    const modal = elements.creatorModal;
    modal.classList.remove('hidden');

    const title = document.getElementById('creator-modal-title');
    const nameInput = document.getElementById('creator-name');
    const stopsList = document.getElementById('creator-stops-list');
    const canvas = document.getElementById('creator-canvas');
    const ticks = document.getElementById('creator-stop-ticks');
    const productsList = document.getElementById('creator-products-list');
    const saveButton = document.getElementById('creator-save');

    title.textContent = isEdit ? `🎨 Editar "${existing.cmap_name}"` : '🎨 Crear mapa de colores';
    saveButton.textContent = isEdit ? 'Guardar cambios' : 'Crear mapa de colores';
    nameInput.value = isEdit ? existing.cmap_name : '';
    nameInput.readOnly = isEdit;  // renaming would orphan options/defaults

    const assigned = isEdit ? new Set(existing.product_keys) : new Set();
    /** Product assignment chips (styled via CSS :has(:checked)). */
    productsList.innerHTML = products
        .map((p) => `<label><input type="checkbox" value="${safeText(p.product_key)}" ${assigned.has(p.product_key) ? 'checked' : ''}> ${safeText(p.product_key)}</label>`)
        .join('');

    const clamp01 = (value) => Math.min(1, Math.max(0, value));

    /** Draw a horizontal gradient preview and position the (draggable) stop ticks. */
    function drawPreview() {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const sorted = [...creatorStops].sort((a, b) => a.position - b.position);
        if (sorted.length === 1) {
            ctx.fillStyle = safeHexColor(sorted[0].color, '#000000');
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        } else if (sorted.length >= 2) {
            const gradient = ctx.createLinearGradient(0, 0, canvas.width, 0);
            sorted.forEach((s) => gradient.addColorStop(clamp01(s.position), safeHexColor(s.color, '#000000')));
            ctx.fillStyle = gradient;
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        }
        // Ticks use the original index so dragging maps to the right stop.
        ticks.innerHTML = creatorStops
            .map((s, i) => `<span class="creator-stop-tick" data-idx="${i}" title="Arrastrar para mover (${clamp01(s.position).toFixed(2)})" style="left:${(clamp01(s.position) * 100).toFixed(2)}%;--tick-color:${safeHexColor(s.color, '#000000')}"></span>`)
            .join('');
    }

    // ── Drag stop ticks horizontally over the preview ──
    const previewWrap = canvas.parentElement;
    let dragIdx = null;
    ticks.onpointerdown = (event) => {
        const tick = event.target.closest('.creator-stop-tick');
        if (!tick) return;
        dragIdx = parseInt(tick.dataset.idx, 10);
        ticks.setPointerCapture(event.pointerId);
        event.preventDefault();
    };
    ticks.onpointermove = (event) => {
        if (dragIdx === null) return;
        const rect = previewWrap.getBoundingClientRect();
        const pos = clamp01((event.clientX - rect.left) / rect.width);
        creatorStops[dragIdx].position = pos;
        const slider = stopsList.querySelector(`.stop-slider[data-idx="${dragIdx}"]`);
        const number = stopsList.querySelector(`.stop-pos[data-idx="${dragIdx}"]`);
        if (slider) slider.value = pos;
        if (number) number.value = pos.toFixed(2);
        drawPreview();
    };
    const endDrag = (event) => {
        if (dragIdx === null) return;
        dragIdx = null;
        try { ticks.releasePointerCapture(event.pointerId); } catch (_) { /* noop */ }
    };
    ticks.onpointerup = endDrag;
    ticks.onpointercancel = endDrag;

    /** Re-render the stops list and refresh the preview. */
    function rebuildStops() {
        stopsList.innerHTML = creatorStops
            .map((s, i) => `
                <div class="creator-stop-row" data-idx="${i}">
                    <span class="stop-handle">${i + 1}</span>
                    <input type="range" class="stop-slider" min="0" max="1" step="0.01" value="${clamp01(s.position)}" data-idx="${i}">
                    <input type="number" class="stop-pos" min="0" max="1" step="0.01" value="${clamp01(s.position)}" data-idx="${i}">
                    <input type="color" class="stop-color" value="${safeHexColor(s.color, '#888888')}" data-idx="${i}">
                    <button type="button" class="btn-danger btn-sm stop-remove" data-idx="${i}" title="Eliminar punto">✕</button>
                </div>
            `)
            .join('');

        const syncPosition = (idx, value) => {
            const v = clamp01(value);
            creatorStops[idx].position = v;
            const slider = stopsList.querySelector(`.stop-slider[data-idx="${idx}"]`);
            const number = stopsList.querySelector(`.stop-pos[data-idx="${idx}"]`);
            if (slider && document.activeElement !== slider) slider.value = v;
            if (number && document.activeElement !== number) number.value = v;
            drawPreview();
        };

        stopsList.querySelectorAll('.stop-slider').forEach((input) => {
            input.oninput = () => syncPosition(parseInt(input.dataset.idx, 10), parseFloat(input.value));
        });
        stopsList.querySelectorAll('.stop-pos').forEach((input) => {
            input.oninput = () => {
                const val = parseFloat(input.value);
                if (!isNaN(val)) syncPosition(parseInt(input.dataset.idx, 10), val);
            };
        });
        stopsList.querySelectorAll('.stop-color').forEach((input) => {
            input.oninput = () => {
                const idx = parseInt(input.dataset.idx, 10);
                creatorStops[idx].color = input.value;
                drawPreview();
            };
        });
        stopsList.querySelectorAll('.stop-remove').forEach((btn) => {
            btn.onclick = () => {
                const idx = parseInt(btn.dataset.idx, 10);
                if (creatorStops.length <= 2) {
                    showMessage('Un mapa de colores necesita al menos 2 puntos.', 'error');
                    return;
                }
                creatorStops.splice(idx, 1);
                rebuildStops();
            };
        });

        drawPreview();
    }

    rebuildStops();

    document.getElementById('creator-add-stop').onclick = () => {
        creatorStops.push({ position: 0.5, color: '#888888' });
        rebuildStops();
    };

    saveButton.onclick = async () => {
        const cmapName = isEdit ? existing.cmap_name : nameInput.value.trim();
        if (!cmapName) {
            showMessage('El nombre del mapa de colores es obligatorio.', 'error');
            return;
        }
        if (creatorStops.length < 2) {
            showMessage('Se requieren al menos 2 puntos.', 'error');
            return;
        }
        const productKeys = [...productsList.querySelectorAll('input[type=checkbox]:checked')]
            .map((cb) => cb.value);
        const stops = creatorStops.map((s) => ({ position: s.position, color: s.color }));
        try {
            if (isEdit) {
                // No update endpoint: delete then recreate with the same name.
                await adminApi.deleteColormap(cmapName);
                await adminApi.createColormapFromHex({ cmap_name: cmapName, stops, product_keys: productKeys });
                // create-from-hex only ADDS options; remove the ones now unchecked.
                const toRemove = (existing.optionRows || []).filter((o) => !productKeys.includes(o.product_key));
                await Promise.all(toRemove.map((o) => adminApi.deleteColormapOption(o.id)));
            } else {
                await adminApi.createColormapFromHex({ cmap_name: cmapName, stops, product_keys: productKeys });
            }
            // Invalidate the in-process cache so the API picks up the change.
            await adminApi.invalidateColormapCache();
            modal.classList.add('hidden');
            showMessage(`Mapa de colores "${cmapName}" ${isEdit ? 'actualizado' : 'creado'}`, 'success');
            renderSection();
        } catch (error) {
            showMessage(error.message || `No se pudo ${isEdit ? 'actualizar' : 'crear'} el mapa de colores`, 'error');
        }
    };
}

async function renderColormaps() {
    const [cmaps, products, allOptions] = await Promise.all([
        adminApi.listColormapSummaries(),
        adminApi.listProducts(),
        adminApi.listColormapOptions(),
    ]);
    const sorted = sortItems(cmaps, 'colormaps');

    elements.sectionContent.innerHTML = `
        <div class="toolbar">
            <button class="btn" id="cmap-creator-open">🎨 Crear mapa de colores</button>
            <span class="toolbar-note">Los mapas de colores del sistema no se pueden eliminar.</span>
        </div>
        ${renderFilterBar('colormaps', sorted)}
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th><button data-sort="cmap_name" data-section="colormaps">Nombre</button></th>
                    <th><button data-sort="stop_count" data-section="colormaps">Puntos</button></th>
                    <th>Sistema</th>
                    <th>Acciones</th>
                </tr>
            </thead>
            <tbody>
                ${sorted.map((c) => `
                    <tr${rowFacetAttr('colormaps', c)}>
                        <td>${safeText(c.cmap_name)}</td>
                        <td>${c.stop_count}</td>
                        <td>${c.is_system ? '✔' : ''}</td>
                        <td class="table-actions">
                            <button class="btn-secondary" data-view-cmap="${safeText(c.cmap_name)}">Ver puntos</button>
                            ${!c.is_system ? `<button class="btn-secondary" data-edit-cmap="${safeText(c.cmap_name)}">${ICON_EDIT}</button>` : ''}
                            ${!c.is_system ? `<button class="btn-danger" data-delete-cmap="${safeText(c.cmap_name)}">${ICON_TRASH}</button>` : ''}
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;

    wireFilterBar('colormaps');
    elements.sectionContent.querySelectorAll('[data-sort]').forEach((btn) => {
        btn.onclick = () => switchSort('colormaps', btn.dataset.sort);
    });

    document.getElementById('cmap-creator-open').onclick = () => openColormapCreator(products);

    elements.sectionContent.querySelectorAll('[data-view-cmap]').forEach((btn) => {
        btn.onclick = async () => {
            const name = btn.dataset.viewCmap;
            const [stops, colors] = await Promise.all([
                adminApi.getColormapStops(name),
                fetchColormapColors(name, 64),
            ]);
            const rows = stops.map((s) => `
                <tr>
                    <td>${safeText(s.channel)}</td>
                    <td>${s.position.toFixed(4)}</td>
                    <td>${s.val_left.toFixed(4)}</td>
                    <td>${s.val_right.toFixed(4)}</td>
                    <td>${s.sort_order}</td>
                </tr>
            `).join('');
            openFormModal(`Puntos de ${name}`, `
                <div class="cmap-view-gradient" style="background:${gradientCss(colors)}"></div>
                <div class="cmap-view-scale"><span>0.0</span><span>0.5</span><span>1.0</span></div>
                <div style="overflow:auto;max-height:50vh;">
                    <table>
                        <thead><tr><th>Canal</th><th>Posición</th><th>Val izq</th><th>Val der</th><th>Orden</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
                <div style="text-align:right;margin-top:8px;">
                    <button type="button" class="btn btn-secondary" id="close-stops-modal">Cerrar</button>
                </div>
            `, async () => {});
            document.getElementById('close-stops-modal')?.addEventListener('click', closeFormModal);
        };
    });

    elements.sectionContent.querySelectorAll('[data-edit-cmap]').forEach((btn) => {
        btn.onclick = async () => {
            const name = btn.dataset.editCmap;
            try {
                const stops = await adminApi.getColormapStops(name);
                const optionRows = allOptions.filter((o) => o.cmap_name === name);
                openColormapCreator(products, {
                    cmap_name: name,
                    stops: stopsToHexStops(stops),
                    product_keys: optionRows.map((o) => o.product_key),
                    optionRows,
                });
            } catch (error) {
                showMessage(error.message || 'No se pudo cargar el mapa de colores para editar', 'error');
            }
        };
    });

    elements.sectionContent.querySelectorAll('[data-delete-cmap]').forEach((btn) => {
        btn.onclick = async () => {
            const name = btn.dataset.deleteCmap;
            if (!requireConfirmation(`el mapa de colores "${name}"`)) return;
            try {
                await adminApi.deleteColormap(name);
                showMessage(`Mapa de colores "${name}" eliminado`, 'success');
                renderSection();
            } catch (error) {
                showMessage(error.message, 'error');
            }
        };
    });
}

async function renderColormapOptions() {
    const [options, cmaps, products] = await Promise.all([
        adminApi.listColormapOptions(),
        adminApi.listColormapSummaries(),
        adminApi.listProducts(),
    ]);
    const sorted = sortItems(options, 'colormap-options');

    const cmapOpts = cmaps.map((c) => `<option value="${safeText(c.cmap_name)}">${safeText(c.cmap_name)}</option>`).join('');
    const productOpts = products.map((p) => `<option value="${safeText(p.product_key)}">${safeText(p.product_key)}</option>`).join('');

    elements.sectionContent.innerHTML = `
        <div class="toolbar">
            <button class="btn" id="cmap-option-add">+ Agregar opción</button>
        </div>
        ${renderFilterBar('colormap-options', sorted)}
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th><button data-sort="product_key" data-section="colormap-options">Clave de producto</button></th>
                    <th><button data-sort="cmap_name" data-section="colormap-options">Mapa de colores</button></th>
                    <th>Acciones</th>
                </tr>
            </thead>
            <tbody>
                ${sorted.map((opt) => `
                    <tr${rowFacetAttr('colormap-options', opt)}>
                        <td>${safeText(opt.product_key)}</td>
                        <td>${safeText(opt.cmap_name)}</td>
                        <td class="table-actions">
                            <button class="btn-secondary" data-edit-cmap-option="${opt.id}">${ICON_EDIT}</button>
                            <button class="btn-danger" data-delete-cmap-option="${opt.id}">${ICON_TRASH}</button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;

    wireFilterBar('colormap-options');
    elements.sectionContent.querySelectorAll('[data-sort]').forEach((btn) => {
        btn.onclick = () => switchSort('colormap-options', btn.dataset.sort);
    });

    const withSelected = (optionsHtml, selected) => optionsHtml.replace(
        `value="${safeText(selected)}"`,
        `value="${safeText(selected)}" selected`,
    );

    const openColormapOptionForm = (option = null) => {
        const isEdit = Boolean(option);
        openFormModal(isEdit ? 'Editar opción de mapa de colores' : 'Agregar opción de mapa de colores', `
            <label>Clave de producto
                <select name="product_key" required>${isEdit ? withSelected(productOpts, option.product_key) : productOpts}</select>
            </label>
            <label>Mapa de colores
                <select name="cmap_name" required>${isEdit ? withSelected(cmapOpts, option.cmap_name) : cmapOpts}</select>
            </label>
            <div class="form-actions"><button type="submit" class="btn">${isEdit ? 'Guardar' : 'Agregar'}</button></div>
        `, async (formData) => {
            const productKey = formData.get('product_key');
            const cmapName = formData.get('cmap_name');
            if (isEdit && productKey === option.product_key && cmapName === option.cmap_name) {
                return;  // unchanged
            }
            // No update endpoint: create the new pairing, then drop the old row.
            await adminApi.createColormapOption({ product_key: productKey, cmap_name: cmapName });
            if (isEdit) {
                await adminApi.deleteColormapOption(option.id);
            }
            showMessage(`Opción de mapa de colores ${isEdit ? 'actualizada' : 'agregada'}`, 'success');
            renderSection();
        });
    };

    document.getElementById('cmap-option-add').onclick = () => openColormapOptionForm();

    elements.sectionContent.querySelectorAll('[data-edit-cmap-option]').forEach((btn) => {
        btn.onclick = () => {
            const id = parseInt(btn.dataset.editCmapOption, 10);
            const option = options.find((o) => o.id === id);
            if (option) openColormapOptionForm(option);
        };
    });

    elements.sectionContent.querySelectorAll('[data-delete-cmap-option]').forEach((btn) => {
        btn.onclick = async () => {
            const id = parseInt(btn.dataset.deleteCmapOption, 10);
            if (!requireConfirmation(`la opción de mapa de colores #${id}`)) return;
            try {
                await adminApi.deleteColormapOption(id);
                showMessage('Opción de mapa de colores eliminada', 'success');
                renderSection();
            } catch (error) {
                showMessage(error.message, 'error');
            }
        };
    });
}

const ROLE_LABELS = { admin: 'Administrador', org_admin: 'Admin de institución', viewer: 'Lector' };

async function renderUsers() {
    const [allUsers, orgs] = await Promise.all([adminApi.listUsers(), adminApi.listOrganizations()]);
    state.organizations = orgs;  // the add-user form offers them
    // Coming from the Instituciones section ("Usuarios" link) shows only that company's users until "ver todos".
    const orgFilter = state.usersOrgFilter || null;
    const orgFilterName = orgs.find((o) => o.id === orgFilter)?.name;
    const users = sortItems(orgFilter ? allUsers.filter((u) => u.organization_id === orgFilter) : allUsers, 'users');
    const meId = state.me?.id;
    elements.sectionContent.innerHTML = `
        <div class="toolbar"><button class="btn" id="users-add">+ Agregar usuario</button></div>
        ${orgFilter ? `<p class="toolbar-note">Usuarios de ${safeText(orgFilterName)} · <a href="admin#users" id="users-clear-org">ver todos</a></p>` : ''}
        ${renderFilterBar('users', users)}
        <div class="table-wrap">
        <table>
            <thead><tr>
                <th><button data-sort="username">Usuario</button></th>
                <th><button data-sort="full_name">Nombre</button></th>
                <th><button data-sort="role">Rol</button></th>
                <th>Institución</th>
                <th>Herramientas</th>
                <th><button data-sort="is_active">Activo</button></th>
                <th><button data-sort="last_login_at">Último ingreso</button></th>
                <th>Acciones</th>
            </tr></thead>
            <tbody>
                ${users.map((user) => `
                    <tr${rowFacetAttr('users', user)}>
                        <td>${safeText(user.username)}${user.password_is_bootstrap ? ' <span class="status-pill">contraseña inicial</span>' : ''}${needsMailVerification(user) ? ' <span class="status-pill">mail sin verificar</span>' : ''}${user.email ? `<div class="cell-sub">${safeText(user.email)}</div>` : ''}</td>
                        <td>${safeText(user.full_name)}</td>
                        <td>${ROLE_LABELS[user.role] || safeText(user.role)}</td>
                        <td>${user.organization_name ? safeText(user.organization_name) : '—'}</td>
                        <td>${user.role === 'admin' ? 'Todas (admin)' : safeText(usableToolsSummary(user, orgs.find((o) => o.id === user.organization_id) || null))}</td>
                        <td>${user.is_active ? 'Sí' : 'No'}</td>
                        <td>${user.last_login_at ? fmtDate(user.last_login_at) : '—'}</td>
                        <td class="table-actions">
                            <button class="btn-secondary" data-edit-user="${user.id}" title="Editar">${ICON_EDIT}</button>
                            ${user.role === 'admin' ? '' : `<button class="btn-secondary" data-views-user="${user.id}" title="Herramientas" aria-label="Herramientas">${ICON_TOOLS}</button>`}
                            <button class="btn-secondary" data-security-user="${user.id}" title="Seguridad" aria-label="Seguridad">${ICON_LOCK}</button>
                            ${needsMailVerification(user) ? `<button class="btn-secondary" data-verify-user="${user.id}">Verificar mail</button>` : ''}
                            ${user.id === meId ? '' : `<button class="btn-secondary" data-delete-user="${user.id}" title="Eliminar">${ICON_TRASH}</button>`}
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;

    wireFilterBar('users');
    wireSortHeaders('users');
    const byId = (id) => users.find((u) => String(u.id) === String(id));

    document.getElementById('users-add').onclick = () => openUserForm();
    const clearOrgFilter = document.getElementById('users-clear-org');
    if (clearOrgFilter) {
        // Already on #users, so changing the hash would not redraw: do it by hand.
        clearOrgFilter.onclick = (event) => {
            event.preventDefault();
            state.usersOrgFilter = null;
            renderSection();
        };
    }
    elements.sectionContent.querySelectorAll('[data-edit-user]').forEach((el) => {
        el.onclick = () => openUserForm(byId(el.dataset.editUser));
    });
    elements.sectionContent.querySelectorAll('[data-delete-user]').forEach((el) => {
        el.onclick = () => deleteUser(byId(el.dataset.deleteUser), allUsers);
    });
    elements.sectionContent.querySelectorAll('[data-security-user]').forEach((el) => {
        el.onclick = () => openSecurityForm(byId(el.dataset.securityUser), allUsers);
    });
    elements.sectionContent.querySelectorAll('[data-views-user]').forEach((el) => {
        el.onclick = () => openViewsForm(byId(el.dataset.viewsUser));
    });
    elements.sectionContent.querySelectorAll('[data-verify-user]').forEach((el) => {
        el.onclick = async () => {
            const user = byId(el.dataset.verifyUser);
            if (!window.confirm(`¿Marcar como verificado el mail de ${user.username} (${user.email})? Va a poder ingresar sin abrir el link.`)) return;
            await adminApi.verifyUserEmail(user.id);
            await renderSection();
            showMessage(`Mail de ${user.username} verificado`, 'success');
        };
    });
}

/**
 * Activate or deactivate an account (the last action of the Seguridad window). Deactivating the only admin of an institution that
 * has more users opens the "name another admin" window first (see openSoleAdminForm).
 */
async function toggleUserActive(user, allUsers) {
    const block = user.is_active ? soleAdminBlock(user, allUsers) : null;
    if (block) {
        openSoleAdminForm(user, block, 'deactivate', allUsers);
        return;
    }
    const action = user.is_active ? 'desactivar' : 'activar';
    if (!window.confirm(`¿Confirma ${action} a ${user.username}?`)) return;
    const wasActive = user.is_active;
    await adminApi.patchUser(user.id, { is_active: !wasActive });
    await renderSection();
    showMessage(`Usuario ${user.username} ${wasActive ? 'desactivado' : 'activado'}`, 'success');
}

/**
 * The window that explains why `user` cannot be deleted (or deactivated): it is the only admin of its institution and
 * the institution would be left with active users and no admin. It offers a search box with the institution's active
 * readers; "Asignar como administrador" promotes the picked one, and then the original action goes on with its usual
 * confirmation (so naming the admin and deleting stay two separate decisions). `block` comes from soleAdminBlock.
 * Changing a user's role closes that user's sessions, and the window says so.
 */
function openSoleAdminForm(user, block, action, allUsers) {
    const verb = action === 'delete' ? 'eliminar' : 'desactivar';
    const orgName = user.organization_name || 'su institución';
    const left = block.remaining === 1 ? '1 usuario activo' : `${block.remaining} usuarios activos`;
    openFormModal(
        `No se puede ${verb} a ${user.username}`,
        `
            <p><strong>${safeText(user.username)}</strong> es el único administrador de <strong>${safeText(orgName)}</strong> y la
            institución quedaría con ${left} y sin administrador.</p>
            <p class="toolbar-note">Nombrá administrador a otro de sus usuarios y después seguimos con el ${action === 'delete' ? 'borrado' : 'cambio'}.
            Al cambiarle el rol a esa persona se le cierran las sesiones.</p>
            <label for="sole-admin-search">Nuevo administrador</label>
            <div class="combo">
                <input id="sole-admin-search" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="sole-admin-list" autocomplete="off" placeholder="Escribí para buscar por usuario, nombre o mail…">
                <input type="hidden" name="new_admin_id" value="">
                <ul id="sole-admin-list" class="combo-list" role="listbox" hidden></ul>
            </div>
            <div class="form-actions"><button class="btn" type="submit">Asignar como administrador</button></div>
        `,
        async (formData) => {
            const newAdminId = formData.get('new_admin_id');
            if (!newAdminId) throw new Error('Elegí a quién nombrar administrador');
            const newAdmin = block.candidates.find((candidate) => String(candidate.id) === newAdminId);
            await adminApi.patchUser(Number(newAdminId), { role: 'org_admin' });
            closeFormModal();
            await renderSection();
            showMessage(`${newAdmin.username} ahora es administrador de ${orgName}`, 'success');
            // The list changed: ask again with fresh data. The block is gone now, so the usual confirmation follows.
            const fresh = await adminApi.listUsers();
            const current = fresh.find((candidate) => candidate.id === user.id);
            if (!current) return;
            if (action === 'delete') await deleteUser(current, fresh);
            else await toggleUserActive(current, fresh);
        },
    );
    wireAdminCombobox(block.candidates, { search: '#sole-admin-search', list: '#sole-admin-list', hidden: 'new_admin_id' });
}

/**
 * Delete an account for good (the trash button of the users table). A manual confirmation names the user; the server
 * may refuse (for example an institution's only admin), and then its message is shown instead of deleting anything.
 */
async function deleteUser(user, allUsers) {
    // The only admin of an institution that has more users cannot go: name another admin first.
    const block = soleAdminBlock(user, allUsers);
    if (block) {
        openSoleAdminForm(user, block, 'delete', allUsers);
        return;
    }
    if (!window.confirm(`¿Eliminar a ${user.username}? Se borra su cuenta, sus sesiones y sus vistas. No se puede deshacer.`)) return;
    try {
        await adminApi.deleteUser(user.id);
        await renderSection();
        showMessage(`Usuario ${user.username} eliminado`, 'success');
    } catch (error) {
        showMessage(error.message, 'error');
    }
}

/**
 * "Seguridad": the window of the padlock button of a user row, with the account actions: reset the password (opens its
 * own window), close every session (asks for confirmation) and deactivate or activate the account (see
 * toggleUserActive, which asks its own confirmation). On your own row only "Cerrar sesiones" is offered. The window has
 * no Guardar: each action does its own thing. `allUsers` is the full list of users, which the deactivation needs to
 * know whether the user is the only admin of an institution.
 */
function openSecurityForm(user, allUsers) {
    const isSelf = user.id === state.me?.id;
    const action = (id, title, text) => `<button id="${id}" class="security-action" type="button"><strong>${title}</strong><span>${text}</span></button>`;
    const toggle = user.is_active
        ? action('user-toggle', 'Desactivar usuario', 'No puede ingresar y se le cierran las sesiones. Se puede volver a activar.')
        : action('user-toggle', 'Activar usuario', 'Vuelve a poder ingresar.');
    openFormModal(
        `Seguridad de ${user.username}`,
        `<div class="security-list">
            ${isSelf ? '' : action('user-reset', 'Resetear contraseña', 'Define una contraseña nueva y cierra sus sesiones')}
            ${action('user-revoke', 'Cerrar sesiones', 'Lo obliga a volver a entrar en todos sus dispositivos')}
            ${isSelf ? '' : toggle}
        </div>`,
        async () => {},
    );
    const resetButton = document.getElementById('user-reset');
    if (resetButton) resetButton.onclick = () => openPasswordResetForm(user);
    document.getElementById('user-revoke').onclick = () => revokeUserSessions(user);
    const toggleButton = document.getElementById('user-toggle');
    if (toggleButton) {
        toggleButton.onclick = () => {
            closeFormModal();  // toggleUserActive may open another window (the only admin of an institution)
            toggleUserActive(user, allUsers);
        };
    }
}

/**
 * Close every session of a user (a button of the Seguridad window). Closing your own also logs you out, so the question
 * says so.
 */
async function revokeUserSessions(user) {
    const self = user.id === state.me?.id ? ' (incluida la tuya: vas a tener que volver a entrar)' : '';
    if (!window.confirm(`¿Cerrar todas las sesiones de ${user.username}${self}?`)) return;
    try {
        await adminApi.revokeUserSessions(user.id);
        closeFormModal();
        await renderSection();
        showMessage(`Sesiones de ${user.username} cerradas`, 'success');
    } catch (error) {
        setFormModalError(error.message);
    }
}

function openUserForm(user = null) {
    const isEdit = Boolean(user);
    const isSelf = isEdit && user.id === state.me?.id;
    // Editing: the roles that fit the account (a company user is viewer or company admin, never the general admin;
    // the company never changes). Creating: all three, and the API answers 422 for a mismatch with the company.
    const allowedRoles = !isEdit ? Object.keys(ROLE_LABELS)
        : user.organization_id ? ['org_admin', 'viewer'] : ['admin', 'viewer'];
    const roleOptions = allowedRoles
        .map((value) => `<option value="${value}"${(user?.role || 'viewer') === value ? ' selected' : ''}>${ROLE_LABELS[value]}</option>`)
        .join('');
    // Only a viewer can change company (a company admin or the general admin never moves). When editing, the
    // current company is the selected option; creating starts with "Ninguna".
    const canMove = isEdit && user.role === 'viewer';
    // An institution admin can only be taken out (never moved): the selector offers its institution or "none", which
    // demotes it to viewer and unlinks it in one step.
    const canLeave = isEdit && user.role === 'org_admin' && Boolean(user.organization_id);
    const currentOrgId = user?.organization_id ?? null;
    // The institution is picked in a search box (typing filters by name), not in a plain select. The first entry is
    // always "Ninguna". An institution admin only has two entries: its institution, or "Ninguna", which demotes it.
    let orgField = '';
    let orgItems = [];
    if (!isEdit || canMove || canLeave) {
        const none = { id: '', name: canLeave ? 'Ninguna (lo baja a lector y lo desvincula)' : 'Ninguna' };
        orgItems = canLeave
            ? [{ id: user.organization_id, name: user.organization_name }, none]
            : [none, ...(state.organizations || [])];
        const current = isEdit && currentOrgId !== null ? orgItems.find((item) => item.id === currentOrgId) : null;
        orgField = `<label for="user-org-search">Institución</label>
            <div class="combo">
                <input id="user-org-search" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="user-org-list" autocomplete="off" placeholder="Ninguna: escribí para buscar una institución…" value="${current ? safeText(current.name) : ''}" data-picked="${current ? '1' : ''}">
                <input type="hidden" name="organization_id" value="${current ? current.id : ''}">
                <ul id="user-org-list" class="combo-list" role="listbox" hidden></ul>
            </div>
            ${isEdit ? '<p class="toolbar-note" id="org-move-note"></p>' : ''}`;
    } else if (user.organization_name) {
        orgField = `<p class="toolbar-note">Institución: ${safeText(user.organization_name)}</p>`;
    }
    openFormModal(
        isEdit ? `Editar usuario ${user.username}` : 'Agregar usuario',
        `
            ${isEdit ? '' : '<label>Usuario <input name="username" type="text" minlength="3" maxlength="32" pattern="[a-zA-Z0-9._-]+" required></label>'}
            <label>Nombre <input name="full_name" type="text" maxlength="128" value="${safeText(user?.full_name)}"></label>
            <label>Email <input name="email" type="email" maxlength="254" value="${safeText(user?.email)}"></label>
            <label>Rol <select name="role"${isSelf ? ' disabled' : ''}>${roleOptions}</select></label>
            ${orgField}
            ${isEdit ? '' : '<label>Contraseña inicial <input name="password" type="password" minlength="10" maxlength="128" autocomplete="new-password" required></label><p class="toolbar-note">Mínimo 10 caracteres, con al menos un carácter especial (por ejemplo ! - _ . @ #).</p>'}
            <div class="form-actions"><button class="btn" type="submit">${isEdit ? 'Guardar' : 'Crear'}</button></div>
        `,
        async (formData) => {
            const payload = {
                full_name: formData.get('full_name') || null,
                email: formData.get('email') || null,
            };
            if (!isSelf) payload.role = formData.get('role');
            const orgSearch = elements.formModalBody.querySelector('#user-org-search');
            if (orgSearch && orgSearch.value.trim() && !orgSearch.dataset.picked) {
                throw new Error('Elegí una institución de la lista, o dejá el campo vacío para ninguna');
            }
            let message;
            if (isEdit) {
                if (canLeave && !formData.get('organization_id')) {
                    // The server demotes it to viewer itself; sending the old role would contradict that.
                    payload.organization_id = null;
                    delete payload.role;
                }
                if (canMove) {
                    // Sent only when it changed: the server replaces the account's views when it moves.
                    const chosen = formData.get('organization_id');
                    const newOrgId = chosen ? Number(chosen) : null;
                    if (newOrgId !== currentOrgId) payload.organization_id = newOrgId;
                }
                await adminApi.patchUser(user.id, payload);
                message = `Usuario ${user.username} actualizado`;
            } else {
                payload.username = formData.get('username');
                payload.password = formData.get('password');
                const orgId = formData.get('organization_id');
                if (orgId) payload.organization_id = Number(orgId);
                await adminApi.createUser(payload);
                message = `Usuario ${payload.username.toLowerCase()} creado`;
            }
            await renderSection();
            showMessage(message, 'success');
        },
    );
    if (orgItems.length) wireOrgCombobox(orgItems);
    if (canMove) wireMoveNote(user, currentOrgId);
    if (canLeave) wireLeaveNote(user);
}

/**
 * The institution search box of the user form. Typing filters the entries by name (see filterOrganizations); each
 * shows its seats when it has them. Click or Enter picks the highlighted one (arrows move, Esc closes). The picked id
 * goes in the hidden field `organization_id` ('' = Ninguna), which is what the form reads; typing again forgets the
 * pick. The hidden field fires "change" after a pick or a typing, so the notes under the box can react. The list is
 * drawn inside the form, like the admin picker, so the modal scrolls with it.
 */
function wireOrgCombobox(items) {
    const form = elements.formModalBody;
    const input = form.querySelector('#user-org-search');
    const hidden = form.querySelector('input[name="organization_id"]');
    const list = form.querySelector('#user-org-list');
    let shown = [];
    let active = -1;

    const detail = (item) => {
        if (item.seat_limit === undefined) return '';
        return `${item.seats_used} de ${item.seat_limit} lugares${item.is_active === false ? ' · inactiva' : ''}`;
    };
    const optionId = (item) => `user-org-opt-${item.id === '' ? 'none' : item.id}`;
    const optionHtml = (item, index) => `
        <li role="option" id="${optionId(item)}" data-id="${item.id}" aria-selected="${index === active}">
            <span class="combo-main"><strong>${safeText(item.name)}</strong></span>
            ${detail(item) ? `<small class="combo-mail">${safeText(detail(item))}</small>` : ''}
        </li>`;

    const close = () => {
        list.hidden = true;
        list.innerHTML = '';
        input.setAttribute('aria-expanded', 'false');
        input.removeAttribute('aria-activedescendant');
        active = -1;
    };
    // What is searched: what is typed, unless an entry is already picked (then the whole list is offered again).
    const open = () => {
        shown = filterOrganizations(items, input.dataset.picked ? '' : input.value);
        if (active >= shown.length) active = shown.length - 1;
        list.innerHTML = shown.length
            ? shown.map(optionHtml).join('')
            : '<li class="combo-empty">Ninguna institución coincide con la búsqueda</li>';
        list.hidden = false;
        input.setAttribute('aria-expanded', 'true');
        if (active >= 0 && shown[active]) input.setAttribute('aria-activedescendant', optionId(shown[active]));
    };
    const pick = (item) => {
        // "Ninguna" is shown as text but sends '' (no institution); typing later forgets it like any pick.
        hidden.value = String(item.id);
        input.value = item.name;
        input.dataset.picked = '1';
        close();
        hidden.dispatchEvent(new Event('change'));
    };
    const move = (step) => {
        if (!shown.length) return;
        active = (active + step + shown.length) % shown.length;
        open();
        list.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' });
    };

    input.addEventListener('focus', open);
    input.addEventListener('input', () => {
        hidden.value = '';
        input.dataset.picked = '';
        active = 0;
        open();
        hidden.dispatchEvent(new Event('change'));
    });
    input.addEventListener('blur', close);
    input.addEventListener('keydown', (event) => {
        const isOpen = !list.hidden;
        if (event.key === 'ArrowDown') { event.preventDefault(); if (isOpen) move(1); else open(); }
        else if (event.key === 'ArrowUp') { event.preventDefault(); if (isOpen) move(-1); }
        else if (event.key === 'Enter' && isOpen) {
            event.preventDefault();  // Enter picks, it does not submit the form
            if (active >= 0 && shown[active]) pick(shown[active]);
        } else if (event.key === 'Escape' && isOpen) { event.stopPropagation(); close(); }
    });
    // mousedown (not click) so the box keeps the focus and its blur does not close the list before the pick.
    list.addEventListener('mousedown', (event) => {
        const item = event.target.closest('[role="option"]');
        if (!item) return;
        event.preventDefault();
        pick(shown.find((entry) => String(entry.id) === item.dataset.id));
    });
}

/** Under the selector of an institution admin: say what choosing "Ninguna" does before saving. */
function wireLeaveNote(user) {
    const select = elements.formModalBody.querySelector('input[name="organization_id"]');
    const note = elements.formModalBody.querySelector('#org-move-note');
    const update = () => {
        note.textContent = select.value ? ''
            : `Deja de ser administrador y sale de ${user.organization_name}: pasa a lector sin institución, libera su lugar, `
            + 'se le quitan sus vistas y se cierran sus sesiones. Si la institución sigue con usuarios activos, '
            + 'antes tiene que quedar otro administrador activo.';
    };
    select.addEventListener('change', update);
    update();
}

/** Views as a short text for the move notice: radar codes, "Todas" or "ninguna". */
function describeViews(views) {
    if (views.includes(ALL_RADARS)) return 'Todas';
    return views.length ? views.join(', ') : 'ninguna';
}

/**
 * Under the "Institución" selector of the edit form, say what saving will do to the account's views before it happens:
 * joining a company REPLACES the account's views with the company's list (and closes its sessions); leaving keeps them.
 */
function wireMoveNote(user, currentOrgId) {
    const select = elements.formModalBody.querySelector('input[name="organization_id"]');
    const note = elements.formModalBody.querySelector('#org-move-note');
    const update = () => {
        const chosen = select.value ? Number(select.value) : null;
        if (chosen === currentOrgId) {
            note.textContent = '';
        } else if (chosen === null) {
            note.textContent = `Sale de ${user.organization_name}: libera su lugar, se le quitan sus vistas (${describeViews(user.radar_detail_views)}) y se cierran sus sesiones.`;
        } else {
            const target = (state.organizations || []).find((org) => org.id === chosen);
            note.textContent = `Se reemplazan sus vistas actuales (${describeViews(user.radar_detail_views)}) por las de la institución `
                + `(${describeViews(target?.radar_detail_views || [])}) y se cierran sus sesiones. Ocupa un lugar de la institución.`;
        }
    };
    select.addEventListener('change', update);
    update();
}

/**
 * Modal to choose one-radar detail views (spec C), for a user or a company.
 * Only radars with the view enabled are listed. Saved codes of radars whose view is now off are kept as they are
 * (sent back unchanged), so switching a view off for maintenance does not lose anybody's access.
 * Below the radars, the checkbox of each tool; `tools` is what is saved ({tool: bool}) and `toolNotes` optional
 * warnings shown under a tool ({tool: text}).
 * `institution` (the user's institution, when it is a user of one) turns on a live warning under the form for what is
 * ticked beyond the institution's own list and tools, because it would do nothing (see wireInstitutionLimitWarning);
 * `isInstitutionAdmin` says the user is the institution's admin, who uses the institution's lists, not their own.
 * `onSave` saves the list and the tools and RETURNS the success message: it is shown after `renderSection()`, because
 * `renderSection()` starts by clearing the notice (showing it before would make it vanish at once).
 * @param {{title: string, stored: string[], tools?: object, toolNotes?: object, institution?: object|null,
 *          isInstitutionAdmin?: boolean, onSave: (views: string[], tools: object) => Promise<string>}} options
 */
async function openToolsForm({ title, stored, tools, toolNotes = {}, institution = null, isInstitutionAdmin = false, onSave }) {
    const radars = (await adminApi.listRadars()).filter((radar) => radar.detail_view_enabled);
    const hasAll = stored.includes(ALL_RADARS);
    const listedCodes = new Set(radars.map((radar) => radar.code));
    const keptHidden = stored.filter((code) => code !== ALL_RADARS && !listedCodes.has(code));
    const radarRows = radars.length
        ? radars.map((radar) => `
            <label class="checkbox-row">
                <input type="checkbox" name="radar" value="${safeText(radar.code)}"${!hasAll && stored.includes(radar.code) ? ' checked' : ''}>
                ${safeText(radar.code)} - ${safeText(radar.title)}
            </label>`).join('')
        : '<p class="toolbar-note">Ningún radar tiene la vista de detalle habilitada.</p>';
    openFormModal(
        title,
        `
            <label class="checkbox-row"><input type="checkbox" name="all"${hasAll ? ' checked' : ''}> Todas</label>
            <fieldset class="views-radars"><legend>O elegir radares</legend>${radarRows}</fieldset>
            <p class="toolbar-note">Solo se listan los radares con la vista de detalle habilitada.</p>
            ${toolsFieldsHtml({ values: tools || {}, notes: toolNotes })}
            ${isInstitutionAdmin ? '<p class="form-warning">Es administrador de la institución: usa lo que tiene la institución, así que lo que marques acá no tiene efecto.</p>' : ''}
            <p id="tools-warning" class="form-warning" hidden></p>
            <div class="form-actions"><button class="btn" type="submit">Guardar</button></div>
        `,
        async (formData) => {
            const views = formData.get('all') ? [ALL_RADARS] : [...formData.getAll('radar'), ...keptHidden];
            const message = await onSave(views, readTools(formData));
            await renderSection();
            showMessage(message, 'success');
        },
    );
    if (institution && !isInstitutionAdmin) wireInstitutionLimitWarning(institution);
}

/**
 * Live warning of the tools window of a reader of an institution: what is ticked beyond the institution's views and
 * tools does nothing, because a reader has what it was given AND what the institution has. It does not block saving
 * (the institution may get it later); it only says so, and what to do (give it to the institution first).
 */
function wireInstitutionLimitWarning(org) {
    const form = elements.formModalBody;
    const box = form.querySelector('#tools-warning');
    const update = () => {
        const views = form.querySelector('input[name="all"]').checked
            ? [ALL_RADARS]
            : [...form.querySelectorAll('input[name="radar"]:checked')].map((input) => input.value);
        const beyond = beyondInstitution(views, readTools(new FormData(form)), org);
        const lines = [];
        if (beyond.all) lines.push('"Todas" no tiene efecto completo: la institución no tiene todas las vistas, solo valen las suyas.');
        if (beyond.radars.length) {
            lines.push(`${beyond.radars.length === 1 ? 'La vista' : 'Las vistas'} ${beyond.radars.join(', ')} no ${beyond.radars.length === 1 ? 'tiene' : 'tienen'} efecto: la institución no ${beyond.radars.length === 1 ? 'la tiene' : 'las tiene'}.`);
        }
        for (const label of beyond.tools) lines.push(`${label} no tiene efecto: la institución no tiene esa herramienta.`);
        box.hidden = lines.length === 0;
        box.innerHTML = lines.length
            ? `${lines.map((line) => safeText(line)).join('<br>')}<br>Para que valga, dáselo primero a la institución.`
            : '';
    };
    form.addEventListener('change', update);
    update();
}

/**
 * Users section: views and tools of one user. A user of an institution can be given more than the institution has, but
 * it does nothing until the institution has it (members have what they were given AND what the institution has), so
 * the form warns while the admin ticks it (wireInstitutionLimitWarning). An institution admin uses the institution's
 * lists, so the form says that nothing ticked there counts.
 */
async function openViewsForm(user) {
    let institution = null;
    if (user.organization_id) {
        const orgs = state.organizations || await adminApi.listOrganizations();
        institution = orgs.find((candidate) => candidate.id === user.organization_id) || null;
    }
    return openToolsForm({
        title: `Herramientas de ${user.username}`,
        stored: user.radar_detail_views || [],
        tools: user.tools,
        institution,
        isInstitutionAdmin: user.role === 'org_admin',
        onSave: async (views, tools) => {
            await adminApi.setUserPermissions(user.id, { radar_detail_view: views, tools });
            return `Herramientas de ${user.username} actualizadas`;
        },
    });
}

/** Companies section (spec C): list, create, edit, seats and the company's views. */
async function renderOrganizations() {
    const orgs = await adminApi.listOrganizations();
    // The "Lugares" filter is computed here: the API gives the numbers, the filter needs a word to compare.
    const filterable = orgs.map((org) => ({
        ...org,
        // A pending invitation reserves a seat (spec E), so the seats are full counting them too.
        seats_state: org.seats_used + (org.pending_invitations || 0) >= org.seat_limit ? 'Completa' : 'Con lugares libres',
    }));
    elements.sectionContent.innerHTML = `
        <div class="toolbar"><button class="btn" id="orgs-add">+ Agregar institución</button></div>
        ${renderFilterBar('organizations', filterable)}
        <div class="table-wrap">
        <table>
            <thead><tr>
                <th>Institución</th><th>Lugares</th><th>Activa</th><th>Herramientas</th><th>Acciones</th>
            </tr></thead>
            <tbody>
                ${filterable.map((org) => `
                    <tr${rowFacetAttr('organizations', org)}>
                        <td>${safeText(org.name)}</td>
                        <td>${org.seats_used} de ${org.seat_limit}${org.pending_invitations ? ` (+${org.pending_invitations} invitación${org.pending_invitations === 1 ? '' : 'es'})` : ''}</td>
                        <td>${org.is_active ? 'Sí' : 'No'}</td>
                        <td>${safeText(toolsSummary(org.radar_detail_views, org.tools))}</td>
                        <td class="table-actions">
                            <button class="btn-secondary" data-edit-org="${org.id}" title="Editar">${ICON_EDIT}</button>
                            <button class="btn-secondary" data-views-org="${org.id}">Herramientas</button>
                            <a class="btn-secondary" href="admin#users" data-section="users" data-users-of-org="${org.id}">Usuarios</a>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;
    const byId = (id) => orgs.find((o) => String(o.id) === String(id));
    wireFilterBar('organizations');
    document.getElementById('orgs-add').onclick = () => openOrganizationForm();
    elements.sectionContent.querySelectorAll('[data-edit-org]').forEach((el) => {
        el.onclick = () => openOrganizationForm(byId(el.dataset.editOrg));
    });
    elements.sectionContent.querySelectorAll('[data-views-org]').forEach((el) => {
        const org = byId(el.dataset.viewsOrg);
        el.onclick = () => openToolsForm({
            title: `Herramientas de ${org.name}`,
            stored: org.radar_detail_views,
            tools: org.tools,
            // Turning a tool on gives it to every user of the institution; its admin can then switch it off by hand.
            toolNotes: org.tools?.tracking
                ? {}
                : { tracking: 'Al activarla se habilita para todos los usuarios de la institución; el admin de la institución puede quitarla a mano.' },
            onSave: async (views, tools) => {
                await adminApi.setOrganizationPermissions(org.id, { radar_detail_view: views, tools });
                return `Herramientas de ${org.name} actualizadas`;
            },
        });
    });
    elements.sectionContent.querySelectorAll('[data-users-of-org]').forEach((el) => {
        // Opens the users section filtered by this company (see renderUsers). Sets the filter here; the delegated
        // [data-section] handler then does the navigation. The link's own address is the full "admin#users": a bare
        // "#users" would resolve against <base href> and leave the panel for the map.
        el.onclick = () => { state.usersOrgFilter = Number(el.dataset.usersOfOrg); };
    });
}

/**
 * Invitations section (spec E): the pending invitations of every institution, with Reenviar and Cancelar, and a form to
 * invite someone to an institution that already exists (an admin for one without admin, or a viewer).
 */
async function renderInvitations() {
    const [invitations, orgs] = await Promise.all([adminApi.listInvitations(), adminApi.listOrganizations()]);
    state.organizations = orgs;
    // "Rol" filter needs words: the API gives the code.
    const items = invitations.map((invitation) => ({ ...invitation, role_label: ROLE_LABELS[invitation.role] || invitation.role }));
    const views = (invitation) => {
        if (invitation.role === 'org_admin') return 'Las de la institución';
        if (!invitation.radar_views && !invitation.tools) return 'Copia de las de la institución';
        const base = invitation.radar_views ? viewsSummary(invitation.radar_views) : 'Vistas de la institución';
        return invitation.tools?.tracking ? `${base} · Tracking` : base;
    };
    elements.sectionContent.innerHTML = `
        <div class="toolbar"><button class="btn" id="invitations-add">+ Invitar por mail</button></div>
        ${renderFilterBar('invitations', items)}
        <div class="table-wrap">
        <table>
            <thead><tr>
                <th>Mail</th><th>Institución</th><th>Rol</th><th>Herramientas</th><th>Vence</th><th>Acciones</th>
            </tr></thead>
            <tbody>
                ${items.map((invitation) => `
                    <tr${rowFacetAttr('invitations', invitation)}>
                        <td>${safeText(invitation.email)}${invitation.existing_account ? ' <span class="status-pill">Ya tiene cuenta</span>' : ''}</td>
                        <td>${safeText(invitation.organization_name)}</td>
                        <td>${safeText(invitation.role_label)}</td>
                        <td>${safeText(views(invitation))}</td>
                        <td>${safeText(new Date(invitation.expires_at).toLocaleDateString('es-AR'))}</td>
                        <td class="table-actions">
                            <button class="btn-secondary" data-resend-invitation="${safeText(invitation.id)}">Reenviar</button>
                            <button class="btn-secondary" data-cancel-invitation="${safeText(invitation.id)}">Cancelar</button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
        <p class="toolbar-note">Cada invitación pendiente reserva un lugar de su institución hasta que se acepta, se cancela o vence (7 días).</p>
    `;
    wireFilterBar('invitations');
    document.getElementById('invitations-add').onclick = () => openInvitationForm();
    elements.sectionContent.querySelectorAll('[data-resend-invitation]').forEach((el) => {
        el.onclick = async () => {
            try {
                const sent = await adminApi.resendInvitation(el.dataset.resendInvitation);
                await renderSection();
                showMessage(`Invitación reenviada a ${sent.email}`, 'success');
            } catch (error) {
                showMessage(error.message, 'error');
            }
        };
    });
    elements.sectionContent.querySelectorAll('[data-cancel-invitation]').forEach((el) => {
        el.onclick = async () => {
            const invitation = invitations.find((item) => String(item.id) === el.dataset.cancelInvitation);
            if (!window.confirm(`¿Cancelar la invitación a ${invitation ? invitation.email : 'esta persona'}? El link deja de funcionar.`)) return;
            try {
                await adminApi.cancelInvitation(el.dataset.cancelInvitation);
                await renderSection();
                showMessage('Invitación cancelada', 'success');
            } catch (error) {
                showMessage(error.message, 'error');
            }
        };
    });
}

/**
 * What to tell the admin after inviting. When the mail already has an account it is a WARNING, not an error: the
 * invitation was sent anyway, and the person will join with the account it has (leaving another institution if it is in one).
 */
function invitationSentMessage(sent) {
    if (!sent.existing_account) return `Invitación enviada a ${sent.email}`;
    const leaves = sent.leaves_organization ? ` y saldrá de ${sent.leaves_organization}` : '';
    return `Invitación enviada a ${sent.email}. Ese mail ya tiene una cuenta: la invitación se envió igual. `
        + `Al aceptarla, entrará a ${sent.organization_name} con su cuenta actual${leaves}.`;
}

/** Form "Invitar por mail": the mail, the institution (search box) and the role it will have. */
function openInvitationForm() {
    const orgs = (state.organizations || []).filter((org) => org.is_active);
    openFormModal(
        'Invitar por mail',
        `
            <label>Mail de la persona <input name="email" type="email" maxlength="254" required autocomplete="off"></label>
            <label for="user-org-search">Institución</label>
            <div class="combo">
                <input id="user-org-search" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="user-org-list" autocomplete="off" placeholder="Escribí para buscar una institución…" data-picked="">
                <input type="hidden" name="organization_id" value="">
                <ul id="user-org-list" class="combo-list" role="listbox" hidden></ul>
            </div>
            <label>Rol <select name="role">
                <option value="org_admin">Admin de institución</option>
                <option value="viewer">Lector</option>
            </select></label>
            <p class="toolbar-note">Le mandamos un mail con un link (vale 7 días). Completa sus datos o entra con Google y queda dentro de la institución con ese rol. Un lector necesita que la institución ya tenga un admin activo. Mientras no lo acepte, la invitación reserva un lugar.</p>
            ${toolsFieldsHtml({ notes: { tracking: 'Solo para lectores. Sin marcar: no tiene seguimiento de tormentas.' } })}
            <div class="form-actions"><button class="btn" type="submit">Enviar invitación</button></div>
        `,
        async (formData) => {
            const organizationId = formData.get('organization_id');
            if (!organizationId) throw new Error('Elegí una institución de la lista');
            const role = formData.get('role');
            const sent = await adminApi.createInvitation({
                email: String(formData.get('email') || '').trim(),
                organization_id: Number(organizationId),
                role,
                // An institution admin uses its institution's tools: only a reader's invitation carries the choice.
                ...(role === 'viewer' ? { tools: readTools(formData) } : {}),
            });
            await renderSection();
            showMessage(invitationSentMessage(sent), 'success');
        },
    );
    wireOrgCombobox(orgs.length ? orgs : []);
}

// The fields of a mail, in the order of the form: [name, label, kind]. `body` is a text area (paragraphs separated
// by a blank line); the others are one line.
const MAIL_FIELDS = [
    ['subject', 'Asunto', 'line'],
    ['heading', 'Título', 'line'],
    ['body', 'Párrafos (separados por una línea en blanco)', 'area'],
    ['button', 'Texto del botón', 'line'],
    ['footer', 'Pie', 'line'],
    ['fallback', 'Texto del link alternativo', 'line'],
];
// Wait this long after the last key before asking for a new preview.
const MAIL_PREVIEW_DELAY_MS = 350;

/**
 * "Textos de los mails" (spec F): the general admin changes the TEXT of the four mails the app sends. The design (logo,
 * colors, the button with its link) is not editable. Left: the four mails. Right: the fields of the chosen one, the
 * markers that can be inserted, Guardar / Restaurar original, and a preview that the server builds with the same code
 * that builds the real mail. The preview is shown in an iframe with `sandbox=""` (no scripts, no forms, no navigation),
 * and the texts are put in the fields with `.value` and in the page with `textContent`, never with innerHTML.
 */
async function renderMails() {
    let items = await adminApi.listMailTemplates();
    let current = null;  // the key of the mail being edited
    let lastField = null;  // where the marker buttons insert: the field the admin was in last
    let previewTimer = null;

    elements.sectionContent.innerHTML = `
        <div class="mail-editor">
            <div class="mail-side">
                <p class="toolbar-note">Elegí un mail para cambiar su texto. El diseño no se puede cambiar.</p>
                <ul id="mail-list" class="mail-list"></ul>
            </div>
            <div id="mail-main" class="mail-main"><p class="toolbar-note">Elegí un mail de la lista.</p></div>
        </div>`;
    const $ = (id) => document.getElementById(id);

    const drawList = () => {
        $('mail-list').innerHTML = items.map((item) => `
            <li><button type="button" class="mail-item${item.key === current ? ' active' : ''}" data-mail-key="${safeText(item.key)}">
                <span>${safeText(item.title)}</span>
                ${item.customized ? '<small class="mail-tag">personalizado</small>' : ''}
            </button></li>`).join('');
        $('mail-list').querySelectorAll('[data-mail-key]').forEach((button) => {
            button.onclick = () => select(button.dataset.mailKey);
        });
    };

    const itemOf = (key) => items.find((item) => item.key === key);
    const draft = () => Object.fromEntries(MAIL_FIELDS.map(([name]) => [name, $('mail-form').elements[name].value]));
    const showError = (text) => { $('mail-error').textContent = text || ''; $('mail-error').hidden = !text; };

    /** Ask the server for the preview of the draft; a refused draft shows its message instead of a preview. */
    const refreshPreview = async () => {
        if (!current) return;
        try {
            const preview = await adminApi.previewMailTemplate(current, draft());
            $('mail-preview-subject').textContent = `Asunto: ${preview.subject}`;
            $('mail-preview').srcdoc = preview.html;
            showError('');
        } catch (error) {
            showError(error.message);
        }
    };
    const schedulePreview = () => {
        clearTimeout(previewTimer);
        previewTimer = setTimeout(refreshPreview, MAIL_PREVIEW_DELAY_MS);
    };

    /** True when a field differs from the text saved for this mail (what "Guardar" would change). */
    const isDirty = () => {
        const form = $('mail-form');
        const saved = current && itemOf(current);
        return Boolean(form && saved) && MAIL_FIELDS.some(([name]) => form.elements[name].value !== saved.texts[name]);
    };
    /** Show "Volver" and the unsaved note, and enable "Guardar", only while there are changes to save or undo. */
    const syncButtons = () => {
        const dirty = isDirty();
        $('mail-save').disabled = !dirty;
        $('mail-revert').hidden = !dirty;
        $('mail-dirty').hidden = !dirty;
    };

    /** Put the texts of `item` in the fields, and enable "Restaurar" only when the mail is customized. */
    const fillForm = (item) => {
        MAIL_FIELDS.forEach(([name]) => { $('mail-form').elements[name].value = item.texts[name]; });
        $('mail-restore').disabled = !item.customized;
        const stamp = item.customized && item.updated_at
            ? `Personalizado${item.updated_by_username ? ` por ${item.updated_by_username}` : ''} el ${new Date(item.updated_at).toLocaleString('es-AR')}`
            : 'Texto original';
        $('mail-state').textContent = stamp;
        syncButtons();
    };

    const select = (key) => {
        // Do not lose what was typed by changing mail by mistake.
        if (current && current !== key && isDirty() && !window.confirm('Tenés cambios sin guardar en este mail. ¿Querés descartarlos?')) return;
        current = key;
        const item = itemOf(key);
        lastField = null;
        $('mail-main').innerHTML = `
            <h3>${safeText(item.title)}</h3>
            <p id="mail-state" class="toolbar-note"></p>
            <form id="mail-form" class="form-grid mail-form" novalidate>
                ${MAIL_FIELDS.map(([name, label, kind]) => `
                    <label>${safeText(label)}
                        ${kind === 'area' ? `<textarea name="${name}" rows="7"></textarea>` : `<input name="${name}" type="text" autocomplete="off">`}
                    </label>`).join('')}
                <div>
                    <p class="toolbar-note">Marcas que podés usar (se reemplazan al enviar; con el cursor en un campo, tocá una para insertarla):</p>
                    <div id="mail-placeholders" class="mail-placeholders">
                        ${item.placeholders.map((p) => `<button type="button" class="btn-secondary btn-sm" data-placeholder="${safeText(p.name)}" title="Ejemplo: ${safeText(p.example)}">{${safeText(p.name)}}</button>`).join('')}
                    </div>
                </div>
                <div id="mail-error" class="form-error" role="alert" hidden></div>
                <div class="mail-actions">
                    <button id="mail-save" class="btn" type="submit">Guardar</button>
                    <button id="mail-revert" class="btn-secondary" type="button" hidden>Volver</button>
                    <span id="mail-dirty" class="mail-dirty" hidden>Cambios sin guardar</span>
                    <button id="mail-restore" class="btn-secondary mail-restore" type="button">Restaurar original</button>
                </div>
            </form>
            <p id="mail-preview-subject" class="mail-preview-subject"></p>
            <iframe id="mail-preview" class="mail-preview" title="Vista previa del mail" sandbox=""></iframe>`;
        fillForm(item);
        const form = $('mail-form');
        form.addEventListener('focusin', (event) => { if (MAIL_FIELDS.some(([name]) => name === event.target.name)) lastField = event.target; });
        form.addEventListener('input', () => { syncButtons(); schedulePreview(); });
        // A marker button inserts "{name}" where the cursor is in the last field the admin was in (the body by default).
        $('mail-placeholders').querySelectorAll('[data-placeholder]').forEach((button) => {
            button.onmousedown = (event) => event.preventDefault();  // keep the focus in the field
            button.onclick = () => {
                const field = lastField || form.elements.body;
                const marker = `{${button.dataset.placeholder}}`;
                const start = field.selectionStart ?? field.value.length;
                const end = field.selectionEnd ?? start;
                field.value = field.value.slice(0, start) + marker + field.value.slice(end);
                field.focus();
                field.setSelectionRange(start + marker.length, start + marker.length);
                syncButtons();
                schedulePreview();
            };
        });
        form.onsubmit = async (event) => {
            event.preventDefault();
            showError('');
            try {
                const saved = await adminApi.saveMailTemplate(current, draft());
                items = items.map((entry) => (entry.key === current ? saved : entry));
                drawList();
                fillForm(saved);
                showMessage(`Texto de «${saved.title}» guardado`, 'success');
                refreshPreview();
            } catch (error) {
                showError(error.message);
            }
        };
        $('mail-revert').onclick = () => {
            fillForm(itemOf(current));
            showError('');
            refreshPreview();
        };
        // Restaurar original: delete the customization, so the mail goes back to its default text.
        $('mail-restore').onclick = async () => {
            if (!window.confirm('¿Volver al texto original de este mail? Se pierde el texto personalizado.')) return;
            try {
                await adminApi.restoreMailTemplate(current);
                items = await adminApi.listMailTemplates();
                drawList();
                fillForm(itemOf(current));
                showError('');
                showMessage('Texto original restaurado', 'success');
                refreshPreview();
            } catch (error) {
                showError(error.message);
            }
        };
        drawList();
        refreshPreview();
    };

    drawList();
}

/**
 * The extra blocks of the form that CREATES a company (not shown when editing): who administers it and which radar
 * views it has. Both are optional and are sent in the same request as the company, which is created all or nothing.
 */
function organizationExtrasHtml(radars) {
    const radarRows = radars.length
        ? radars.map((radar) => `
            <label class="checkbox-row">
                <input type="checkbox" name="radar" value="${safeText(radar.code)}">
                ${safeText(radar.code)} - ${safeText(radar.title)}
            </label>`).join('')
        : '<p class="toolbar-note">Ningún radar tiene la vista de detalle habilitada.</p>';
    return `
        <fieldset class="org-admin-block">
            <legend>Administrador de la institución</legend>
            <label class="checkbox-row"><input type="radio" name="admin_mode" value="new" checked> Crear un usuario nuevo</label>
            <div id="org-admin-new" class="org-admin-fields">
                <label>Usuario <input name="admin_username" type="text" minlength="3" maxlength="32" pattern="[a-zA-Z0-9._-]+" autocomplete="off"></label>
                <label>Nombre <input name="admin_fullname" type="text" maxlength="128"></label>
                <label>Email <input name="admin_email" type="email" maxlength="254"></label>
                <label>Contraseña inicial <input name="admin_password" type="password" minlength="10" maxlength="128" autocomplete="new-password"></label>
                <p class="toolbar-note">Mínimo 10 caracteres, con al menos un carácter especial (por ejemplo ! - _ . @ #).</p>
            </div>
            <label class="checkbox-row"><input type="radio" name="admin_mode" value="existing"> Elegir uno que ya existe</label>
            <div id="org-admin-existing" class="org-admin-fields" hidden>
                <label for="org-admin-search">Usuario</label>
                <div class="combo">
                    <input id="org-admin-search" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="org-admin-list" autocomplete="off" placeholder="Escribí para buscar por usuario, nombre o mail…">
                    <input type="hidden" name="admin_user_id" value="">
                    <ul id="org-admin-list" class="combo-list" role="listbox" hidden></ul>
                </div>
                <p class="toolbar-note">Solo se ofrecen lectores activos que no están en ninguna institución. Pasa a ser administrador de esta institución: se le cierran las sesiones y sus vistas propias se reemplazan por las de la institución.</p>
            </div>
            <label class="checkbox-row"><input type="radio" name="admin_mode" value="invite"> Invitar por mail</label>
            <div id="org-admin-invite" class="org-admin-fields" hidden>
                <label>Mail de la persona <input name="admin_invite_email" type="email" maxlength="254" autocomplete="off"></label>
                <p class="toolbar-note">Le mandamos un mail con un link (vale 7 días). Completa sus datos o entra con Google y queda como administrador de esta institución. Mientras no lo acepte, la invitación reserva un lugar.</p>
            </div>
            <label class="checkbox-row"><input type="radio" name="admin_mode" value="none"> Sin administrador por ahora</label>
        </fieldset>
        <fieldset class="views-radars">
            <legend>Vistas de radar de la institución</legend>
            <label class="checkbox-row"><input type="checkbox" name="all"> Todas</label>
            ${radarRows}
        </fieldset>
        ${toolsFieldsHtml()}
        <p class="toolbar-note">Las vistas y las herramientas se pueden cambiar después con el botón Herramientas de la institución.</p>`;
}

/** Show only the fields of the chosen admin option (the other blocks stay hidden). */
function wireAdminModeBlocks() {
    const form = elements.formModalBody;
    const update = () => {
        const mode = form.querySelector('input[name="admin_mode"]:checked')?.value;
        form.querySelector('#org-admin-new').hidden = mode !== 'new';
        form.querySelector('#org-admin-existing').hidden = mode !== 'existing';
        form.querySelector('#org-admin-invite').hidden = mode !== 'invite';
    };
    form.querySelectorAll('input[name="admin_mode"]').forEach((radio) => radio.addEventListener('change', update));
    update();
}

/**
 * The search box that picks the admin among the users that can be chosen. Typing filters the list by username, name
 * or mail (see filterAdmins); each option shows the username and name, and the mail under them. Click or Enter picks
 * the highlighted one (arrows move, Esc closes). The id of the picked user goes in the hidden field `admin_user_id`,
 * which is what the form sends; typing again forgets the pick. The list is drawn inside the form (not floating over
 * it), so the modal can scroll with it.
 */
function wireAdminCombobox(candidates, ids = {}) {
    // The same box is used by the create form (admin of the new company) and by the edit form (person to add); only
    // the element ids and the name of the hidden field change.
    const { search = '#org-admin-search', list: listId = '#org-admin-list', hidden: hiddenName = 'admin_user_id' } = ids;
    const form = elements.formModalBody;
    const input = form.querySelector(search);
    const hidden = form.querySelector(`input[name="${hiddenName}"]`);
    const list = form.querySelector(listId);
    let shown = [];
    let active = -1;

    const optionHtml = (user, index) => `
        <li role="option" id="org-admin-opt-${user.id}" data-id="${user.id}" aria-selected="${index === active}">
            <span class="combo-main"><strong>${safeText(user.username)}</strong>${user.full_name ? ` <span class="combo-name">${safeText(user.full_name)}</span>` : ''}</span>
            <small class="combo-mail">${user.email ? safeText(user.email) : 'sin mail'}</small>
        </li>`;

    const close = () => {
        list.hidden = true;
        list.innerHTML = '';  // nothing stale in the page while it is closed
        input.setAttribute('aria-expanded', 'false');
        input.removeAttribute('aria-activedescendant');
        active = -1;
    };

    // What is searched: what is typed, unless a user is already picked (then the whole list is offered again).
    const open = () => {
        const query = hidden.value ? '' : input.value;
        shown = filterAdmins(candidates, query);
        if (active >= shown.length) active = shown.length - 1;
        if (shown.length) {
            list.innerHTML = shown.map(optionHtml).join('');
        } else {
            const text = candidates.length ? 'Ningún usuario coincide con la búsqueda' : 'No hay usuarios disponibles';
            list.innerHTML = `<li class="combo-empty">${text}</li>`;
        }
        list.hidden = false;
        input.setAttribute('aria-expanded', 'true');
        if (active >= 0 && shown[active]) input.setAttribute('aria-activedescendant', `org-admin-opt-${shown[active].id}`);
    };

    const pick = (user) => {
        hidden.value = String(user.id);
        input.value = user.full_name ? `${user.username} — ${user.full_name}` : user.username;
        close();
    };

    const move = (step) => {
        if (!shown.length) return;
        active = (active + step + shown.length) % shown.length;
        open();
        list.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' });
    };

    input.addEventListener('focus', open);
    input.addEventListener('input', () => {
        hidden.value = '';  // typing again forgets the pick
        active = 0;
        open();
    });
    input.addEventListener('blur', close);
    input.addEventListener('keydown', (event) => {
        const isOpen = !list.hidden;
        if (event.key === 'ArrowDown') { event.preventDefault(); if (isOpen) move(1); else open(); }
        else if (event.key === 'ArrowUp') { event.preventDefault(); if (isOpen) move(-1); }
        else if (event.key === 'Enter' && isOpen) {
            event.preventDefault();  // Enter picks, it does not submit the form
            if (active >= 0 && shown[active]) pick(shown[active]);
        } else if (event.key === 'Escape' && isOpen) { event.stopPropagation(); close(); }
    });
    // mousedown (not click) so the box keeps the focus and its blur does not close the list before the pick.
    list.addEventListener('mousedown', (event) => {
        const item = event.target.closest('[role="option"]');
        if (!item) return;
        event.preventDefault();
        pick(candidates.find((user) => String(user.id) === item.dataset.id));
    });
}

/**
 * Create or edit a company. Editing: name, seat limit and whether it is active. Creating adds, in the same form, the
 * company admin (a new user, an existing one, or none for now) and the radar views of the company.
 */
async function openOrganizationForm(org = null) {
    const isEdit = Boolean(org);
    let extras = '';
    let candidates = [];  // the users that can be picked (the search box works on them)
    try {
        if (isEdit) {
            // Editing: the block "Agregar gente" can pick a loose reader, so the users are needed here too.
            candidates = eligibleAdmins(await adminApi.listUsers());
            extras = membersBlockHtml();
        } else {
            const [users, radars] = await Promise.all([adminApi.listUsers(), adminApi.listRadars()]);
            candidates = eligibleAdmins(users);
            extras = organizationExtrasHtml(radars.filter((radar) => radar.detail_view_enabled));
        }
    } catch (error) {
        showMessage(error.message || 'No se pudo preparar el formulario', 'error');
        return;
    }
    openFormModal(
        isEdit ? `Editar institución ${org.name}` : 'Agregar institución',
        `
            <label>Nombre <input name="name" type="text" maxlength="128" required value="${safeText(org?.name)}"></label>
            <label>Lugares (usuarios activos, admins incluidos) <input name="seat_limit" type="number" min="1" max="10000" required value="${org?.seat_limit ?? 5}"></label>
            <label class="checkbox-row"><input type="checkbox" name="is_active"${!isEdit || org.is_active ? ' checked' : ''}> Activa (si no, ninguno de sus usuarios puede entrar)</label>
            ${extras}
            <div class="form-actions"><button class="btn" type="submit">${isEdit ? 'Guardar' : 'Crear'}</button></div>
        `,
        async (formData) => {
            if (isEdit) {
                const payload = {
                    name: formData.get('name'),
                    seat_limit: Number(formData.get('seat_limit')),
                    is_active: formData.get('is_active') === 'on',
                };
                // Checked BEFORE saving anything, so an option left without its data does not half-save the form.
                const member = buildMemberRequest({
                    mode: formData.get('member_mode') || 'none',
                    role: formData.get('member_role'),
                    organizationId: org.id,
                    inviteEmail: formData.get('member_invite_email'),
                    newUser: {
                        username: formData.get('member_username'),
                        password: formData.get('member_password'),
                        fullName: formData.get('member_fullname'),
                        email: formData.get('member_email'),
                    },
                    existingUserId: formData.get('member_user_id'),
                });
                // The company is saved first, so the seats can be raised and someone added in the same form.
                await adminApi.patchOrganization(org.id, payload);
                let added = '';
                if (member) {
                    try {
                        added = await addMemberToOrganization(member, candidates, payload.name);
                    } catch (error) {
                        // The company data IS saved: redraw the list and say so, keeping the form open with the reason.
                        await renderSection();
                        throw new Error(`Los datos de la institución se guardaron, pero no se pudo agregar a la persona: ${error.message}`);
                    }
                }
                await renderSection();
                showMessage(added ? `Institución ${payload.name} actualizada. ${added}` : `Institución ${payload.name} actualizada`, 'success');
                return;
            }
            const adminMode = formData.get('admin_mode') || 'none';
            const payload = buildOrganizationPayload({
                name: formData.get('name'),
                seatLimit: formData.get('seat_limit'),
                isActive: formData.get('is_active') === 'on',
                adminMode,
                newAdmin: {
                    username: formData.get('admin_username'),
                    password: formData.get('admin_password'),
                    fullName: formData.get('admin_fullname'),
                    email: formData.get('admin_email'),
                },
                existingUserId: formData.get('admin_user_id'),
                inviteEmail: formData.get('admin_invite_email'),
                allViews: formData.get('all') === 'on',
                radars: formData.getAll('radar'),
                tools: readTools(formData),
            });
            const created = await adminApi.createOrganization(payload);
            await renderSection();
            const inviting = payload.admin && payload.admin.mode === 'invite';
            const hasAccount = inviting && created.invited_admin_has_account
                ? '. Ese mail ya tiene una cuenta: la invitación se envió igual y entrará con su cuenta actual'
                : '';
            showMessage(
                inviting
                    ? `Institución ${payload.name} creada: invitamos a ${payload.admin.email} como administrador${hasAccount}`
                    : `Institución ${payload.name} creada${payload.admin ? ' con su administrador' : ''}`,
                'success',
            );
        },
    );
    if (isEdit) {
        wireMemberBlocks();
        wireAdminCombobox(candidates, { search: '#member-search', list: '#member-list', hidden: 'member_user_id' });
    } else {
        wireAdminModeBlocks();
        wireAdminCombobox(candidates);
    }
}

/**
 * The block "Agregar gente a esta institución" of the EDIT form: one optional person, added after the company data is
 * saved. Options: nobody (default), invite by mail, a new user, or a loose reader that already exists; and the role the
 * person gets (reader or admin of the company). Only the fields of the chosen option are shown (see wireMemberBlocks).
 */
function membersBlockHtml() {
    return `
        <fieldset class="org-admin-block">
            <legend>Agregar gente a esta institución</legend>
            <label class="checkbox-row"><input type="radio" name="member_mode" value="none" checked> No agregar a nadie</label>
            <label class="checkbox-row"><input type="radio" name="member_mode" value="invite"> Invitar por mail</label>
            <label class="checkbox-row"><input type="radio" name="member_mode" value="new"> Crear un usuario nuevo</label>
            <label class="checkbox-row"><input type="radio" name="member_mode" value="existing"> Elegir uno que ya existe</label>
            <label id="member-role-row">Rol
                <select name="member_role">
                    <option value="viewer">Lector</option>
                    <option value="org_admin">Admin de institución</option>
                </select>
            </label>
            <div id="member-invite" class="org-admin-fields" hidden>
                <label>Mail de la persona <input name="member_invite_email" type="email" maxlength="254" autocomplete="off"></label>
                <p class="toolbar-note">Le mandamos un mail con un link (vale 7 días). Completa sus datos o entra con Google, o con su cuenta si ya tiene una. Mientras no lo acepte, la invitación reserva un lugar.</p>
            </div>
            <div id="member-new" class="org-admin-fields" hidden>
                <label>Usuario <input name="member_username" type="text" minlength="3" maxlength="32" pattern="[a-zA-Z0-9._-]+" autocomplete="off"></label>
                <label>Nombre <input name="member_fullname" type="text" maxlength="128"></label>
                <label>Email <input name="member_email" type="email" maxlength="254"></label>
                <label>Contraseña inicial <input name="member_password" type="password" minlength="10" maxlength="128" autocomplete="new-password"></label>
                <p class="toolbar-note">Mínimo 10 caracteres, con al menos un carácter especial (por ejemplo ! - _ . @ #).</p>
            </div>
            <div id="member-existing" class="org-admin-fields" hidden>
                <label for="member-search">Usuario</label>
                <div class="combo">
                    <input id="member-search" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="member-list" autocomplete="off" placeholder="Escribí para buscar por usuario, nombre o mail…">
                    <input type="hidden" name="member_user_id" value="">
                    <ul id="member-list" class="combo-list" role="listbox" hidden></ul>
                </div>
                <p class="toolbar-note">Solo se ofrecen lectores activos que no están en ninguna institución. Al sumarse se le cierran las sesiones y sus vistas propias se reemplazan por las de la institución.</p>
            </div>
            <p class="toolbar-note">Un lector solo puede sumarse a una institución que ya tiene un admin activo. Cada lugar ocupado, o reservado por una invitación, cuenta contra el límite de lugares.</p>
        </fieldset>`;
}

/** Show only the fields (and the role) of the chosen option of the block "Agregar gente". */
function wireMemberBlocks() {
    const form = elements.formModalBody;
    const update = () => {
        const mode = form.querySelector('input[name="member_mode"]:checked')?.value;
        form.querySelector('#member-invite').hidden = mode !== 'invite';
        form.querySelector('#member-new').hidden = mode !== 'new';
        form.querySelector('#member-existing').hidden = mode !== 'existing';
        form.querySelector('#member-role-row').hidden = mode === 'none';
    };
    form.querySelectorAll('input[name="member_mode"]').forEach((radio) => radio.addEventListener('change', update));
    update();
}

/**
 * Do the request that buildMemberRequest shaped (invite, create or move a user) and return the sentence that tells
 * the admin what happened. The server applies the usual rules (seats, an active admin for a reader...) and a refusal
 * comes back as an Error with its reason.
 */
async function addMemberToOrganization(member, candidates, orgName) {
    if (member.kind === 'invite') {
        return invitationSentMessage(await adminApi.createInvitation(member.body));
    }
    if (member.kind === 'create') {
        await adminApi.createUser(member.body);
        return `Usuario ${member.body.username} creado en ${orgName}`;
    }
    const user = candidates.find((candidate) => candidate.id === member.userId);
    await adminApi.patchUser(member.userId, member.body);
    return `${user ? user.username : 'El usuario'} se sumó a ${orgName}`;
}

function openPasswordResetForm(user) {
    openFormModal(
        `Resetear contraseña de ${user.username}`,
        `
            <label>Contraseña nueva <input name="password" type="password" minlength="10" maxlength="128" autocomplete="new-password" required></label>
            <p class="toolbar-note">Mínimo 10 caracteres, con al menos un carácter especial (por ejemplo ! - _ . @ #).</p>
            <p class="toolbar-note">Se cierran todas las sesiones de ${safeText(user.username)}.</p>
            <div class="form-actions"><button class="btn" type="submit">Guardar</button></div>
        `,
        async (formData) => {
            await adminApi.resetUserPassword(user.id, formData.get('password'));
            await renderSection();
            showMessage(`Contraseña de ${user.username} actualizada`, 'success');
        },
    );
}

/**
 * "Mi perfil": the logged-in admin's own profile, drawn by the section every role shares (shared/profile-section.js).
 * The form and the notices are the ones of this panel. The success notice is shown by the section itself after it
 * redraws, so renderSection() clearing the notice first does not hide it.
 */
async function renderProfile() {
    await mountProfile(elements.sectionContent, { me: state.me, openModal: openFormModal, showMessage });
}

async function renderSection() {
    hideMessage();
    state.section = parseHashSection();
    // The "only this company's users" filter belongs to one visit of the users section.
    if (state.section !== 'users') state.usersOrgFilter = null;
    setActiveSidebar(state.section);

    const titleBySection = {
        dashboard: 'Panel',
        radars: 'Radares',
        products: 'Productos',
        references: 'Referencias',
        cogs: 'COGs',
        estrategias: 'Estrategias',
        volumenes: 'Volúmenes',
        'tops-cores': 'Tops & Cores',
        nccubes: 'Cubos NetCDF',
        colormaps: 'Mapas de colores',
        'colormap-options': 'Opciones de mapa de colores',
        users: 'Usuarios',
        organizations: 'Instituciones',
        invitations: 'Invitaciones',
        mails: 'Textos de los mails',
        profile: 'Mi perfil',
    };
    elements.sectionTitle.textContent = titleBySection[state.section] || 'Panel';

    try {
        if (state.section === 'dashboard') await renderDashboard();
        if (state.section === 'radars') await renderRadars();
        if (state.section === 'products') await renderProducts();
        if (state.section === 'references') await renderReferences();
        if (state.section === 'cogs') await renderCogs();
        if (state.section === 'estrategias') await renderEstrategias();
        if (state.section === 'volumenes') await renderVolumenes();
        if (state.section === 'tops-cores') await renderTopsCores();
        if (state.section === 'nccubes') await renderNCCubes();
        if (state.section === 'colormaps') await renderColormaps();
        if (state.section === 'colormap-options') await renderColormapOptions();
        if (state.section === 'users') await renderUsers();
        if (state.section === 'organizations') await renderOrganizations();
        if (state.section === 'invitations') await renderInvitations();
        if (state.section === 'mails') await renderMails();
        if (state.section === 'profile') await renderProfile();
        decorateSortHeaders(state.section);
    } catch (error) {
        if ((error.message || '').includes(EXPIRED_SESSION_MESSAGE)) {
            showMessage(EXPIRED_SESSION_MESSAGE, 'error');
        } else {
            showMessage(error.message || 'Error inesperado', 'error');
        }
    }
}

async function logout() {
    await authApi.logout();
    window.location.assign('login');
}

function renderNoPermission() {
    document.getElementById('sidebar-nav').classList.add('hidden');
    elements.sectionTitle.textContent = 'Sin permisos';
    elements.sectionContent.innerHTML = `
        <div class="empty-state">
            <p>No tenés permisos de administración.</p>
            <button class="btn" id="no-permission-back" type="button">Volver al mapa</button>
        </div>
    `;
    document.getElementById('no-permission-back').onclick = goBackToMap;
}

async function init() {
    const me = await authApi.me();
    if (!me) {
        redirectToLogin();
        return;
    }
    state.me = me;
    document.getElementById('session-user').textContent = me.full_name || me.username;
    document.getElementById('logout-btn').onclick = logout;
    document.getElementById('back-to-map').onclick = goBackToMap;
    document.getElementById('sidebar-back-map').onclick = goBackToMap;
    if (me.role !== 'admin') {
        renderNoPermission();
        return;
    }

    elements.closeFormModal.onclick = closeFormModal;
    elements.formModal.addEventListener('click', (event) => {
        if (event.target === elements.formModal) {
            closeFormModal();
        }
    });

    const hideCreator = () => elements.creatorModal.classList.add('hidden');
    document.getElementById('close-creator-modal').onclick = hideCreator;
    document.getElementById('creator-cancel').onclick = hideCreator;
    elements.creatorModal.addEventListener('click', (event) => {
        if (event.target === elements.creatorModal) hideCreator();
    });

    // Back-to-map buttons (header + sidebar).
    document.getElementById('back-to-map').onclick = goBackToMap;
    document.getElementById('sidebar-back-map').onclick = goBackToMap;

    // Delegated section navigation: any [data-section] link switches sections
    // via replaceState so admin browsing never pushes browser history entries.
    document.addEventListener('click', (event) => {
        const link = event.target.closest('[data-section]');
        if (link) {
            event.preventDefault();
            navigateTo(link.dataset.section);
        }
    });

    // Manual hash edits / external hash changes still re-render.
    window.addEventListener('hashchange', renderSection);

    // Full path for the same reason as navigateTo: "#section" alone would resolve against <base href>.
    history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${parseHashSection()}`);
    renderSection();
}

init();
