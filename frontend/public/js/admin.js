import { adminApi, EXPIRED_SESSION_MESSAGE } from './admin-api.js';

const SECTIONS = ['dashboard', 'radars', 'products', 'references', 'cogs', 'estrategias', 'volumenes', 'tops-cores', 'colormaps', 'colormap-options'];
const STATUS_OPTIONS = ['available', 'missing', 'error', 'pending', 'processing', 'archived'];
const DEFAULT_PAGE_SIZE = 25;
const MAX_PAGE_SIZE = 100;

const state = {
    section: 'dashboard',
    message: null,
    sortBy: {
        radars: 'code',
        products: 'id',
        references: 'id',
        estrategias: 'code',
        volumenes: 'id',
        colormaps: 'cmap_name',
        'colormap-options': 'product_key',
    },
    sortDir: {
        radars: 'asc',
        products: 'asc',
        references: 'asc',
        estrategias: 'asc',
        volumenes: 'asc',
        colormaps: 'asc',
        'colormap-options': 'asc',
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
    // Per-section client-side filter state: { search, facets: { field: value } }
    filters: {},
};

// Django-admin-style filter configuration per client-loaded section.
// `boolean` facets render Sí/No; `select` facets auto-derive distinct values
// from the data unless explicit options are supplied at render time.
const FILTER_CONFIG = {
    radars: {
        placeholder: 'Buscar por código, título, descripción…',
        facets: [{ field: 'is_active', label: 'Activo', type: 'boolean' }],
    },
    products: {
        placeholder: 'Buscar por clave, título, unidad…',
        facets: [
            { field: 'enabled', label: 'Habilitado', type: 'boolean' },
            { field: 'see_in_open', label: 'Visible público', type: 'boolean' },
            { field: 'unit', label: 'Unidad', type: 'select' },
            { field: 'default_cmap', label: 'Cmap por defecto', type: 'select' },
        ],
    },
    references: {
        placeholder: 'Buscar por título, unidad, color…',
        facets: [
            { field: 'product_id', label: 'Producto', type: 'select' },
            { field: 'unit', label: 'Unidad', type: 'select' },
        ],
    },
    estrategias: {
        placeholder: 'Buscar por código o descripción…',
        facets: [],
    },
    volumenes: {
        placeholder: 'Buscar por valor…',
        facets: [],
    },
    colormaps: {
        placeholder: 'Buscar mapas de colores…',
        facets: [{ field: 'is_system', label: 'Sistema', type: 'boolean' }],
    },
    'colormap-options': {
        placeholder: 'Buscar opciones…',
        facets: [
            { field: 'product_key', label: 'Producto', type: 'select' },
            { field: 'cmap_name', label: 'Colormap', type: 'select' },
        ],
    },
};

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
                <span>Buscar</span>
                <input type="search" data-filter-search placeholder="${safeText(config.placeholder || 'Buscar…')}" value="${safeText(current.search)}">
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
                if (String(rowFacets[field] ?? '') !== String(value)) {
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

    bar.querySelectorAll('[data-filter-facet]').forEach((select) => {
        select.onchange = () => {
            const field = select.dataset.filterFacet;
            filters.facets[field] = select.value;
            applyRowFilters(section);
            if (onFacet) onFacet(field, select.value);
        };
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

function showMessage(text, type = 'success') {
    state.message = text;
    elements.feedbackMessage.textContent = text;
    elements.feedbackMessage.classList.remove('hidden', 'success', 'error');
    elements.feedbackMessage.classList.add(type);
}

function hideMessage() {
    state.message = null;
    elements.feedbackMessage.textContent = '';
    elements.feedbackMessage.classList.add('hidden');
    elements.feedbackMessage.classList.remove('success', 'error');
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
    history.replaceState(null, '', `#${target}`);
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
        window.location.href = '/';
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

function openFormModal(title, html, onSubmit) {
    elements.formModalTitle.textContent = title;
    elements.formModalBody.innerHTML = html;
    elements.formModalBody.onsubmit = async (event) => {
        event.preventDefault();
        try {
            await onSubmit(new FormData(elements.formModalBody));
            closeFormModal();
        } catch (error) {
            showMessage(error.message || 'Operation failed', 'error');
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

function requireConfirmation(label) {
    return window.confirm(`Confirm deletion of ${label}?`);
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
                <h3>Radars</h3>
                <div class="card-stat"><span class="num">${counts.radarsTotal}</span><span class="sub">${counts.radarsActive} activos</span></div>
                <a href="#radars" data-section="radars">Abrir sección →</a>
            </div>
            <div class="card">
                <h3>Products</h3>
                <div class="card-stat"><span class="num">${counts.productsTotal}</span><span class="sub">${counts.productsEnabled} habilitados</span></div>
                <a href="#products" data-section="products">Abrir sección →</a>
            </div>
            <div class="card">
                <h3>COGs</h3>
                <div class="card-stat"><span class="num">${counts.cogsTotal}</span><span class="sub">${counts.cogsAvailable} disponibles · ${counts.cogsMissing} faltantes · ${counts.cogsError} con error</span></div>
                <a href="#cogs" data-section="cogs">Abrir sección →</a>
            </div>
            <div class="card">
                <h3>References</h3>
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
        </div>
    `;

    document.getElementById('dash-open-creator').onclick = () => openColormapCreator(products);
    document.getElementById('dash-back-map').onclick = goBackToMap;
}

async function renderRadars() {
    const radars = sortItems(await adminApi.listRadars(), 'radars');

    elements.sectionContent.innerHTML = `
        <div class="toolbar">
            <button class="btn" id="radars-add">+ Add New Radar</button>
        </div>
        ${renderFilterBar('radars', radars)}
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th><button data-sort="code">Code</button></th>
                    <th>Title</th>
                    <th>Center Lat</th>
                    <th>Center Long</th>
                    <th>Img Radio</th>
                    <th>Active</th>
                    <th>Created</th>
                    <th>Actions</th>
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
                        <td>${fmtDate(radar.created_at)}</td>
                        <td class="table-actions">
                            <button class="btn-secondary" data-edit-radar="${radar.code}">Edit</button>
                            <button class="btn-danger" data-delete-radar="${radar.code}">Delete</button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;

    document.getElementById('radars-add').onclick = () => openRadarForm();
    wireFilterBar('radars');
    elements.sectionContent.querySelector('[data-sort="code"]').onclick = () => switchSort('radars', 'code');

    elements.sectionContent.querySelectorAll('[data-toggle-radar]').forEach((element) => {
        element.onchange = async (event) => {
            const code = event.target.dataset.toggleRadar;
            await adminApi.patchRadar(code, { is_active: event.target.checked });
            showMessage(`Radar ${code} updated`, 'success');
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
            showMessage(`Radar ${code} deleted`, 'success');
            renderSection();
        };
    });
}

function openRadarForm(radar = null) {
    const isEdit = Boolean(radar);
    openFormModal(
        isEdit ? `Edit Radar ${radar.code}` : 'Add Radar',
        `
            ${!isEdit ? '<label>Code <input name="code" required maxlength="16"></label>' : ''}
            <label>Title <input name="title" value="${safeText(radar?.title)}" required></label>
            <label>Description <input name="description" value="${safeText(radar?.description)}"></label>
            <label>Center Lat <input name="center_lat" type="number" step="any" value="${safeText(radar?.center_lat)}" required></label>
            <label>Center Long <input name="center_long" type="number" step="any" value="${safeText(radar?.center_long)}" required></label>
            <label>Img Radio <input name="img_radio" type="number" value="${safeText(radar?.img_radio)}" required></label>
            <label>Point1 Lat <input name="point1_lat" type="number" step="any" value="${safeText(radar?.point1_lat ?? 0)}"></label>
            <label>Point1 Long <input name="point1_long" type="number" step="any" value="${safeText(radar?.point1_long ?? 0)}"></label>
            <label>Point2 Lat <input name="point2_lat" type="number" step="any" value="${safeText(radar?.point2_lat ?? 0)}"></label>
            <label>Point2 Long <input name="point2_long" type="number" step="any" value="${safeText(radar?.point2_long ?? 0)}"></label>
            <label>Active <select name="is_active"><option value="true" ${radar?.is_active ? 'selected' : ''}>Yes</option><option value="false" ${radar && !radar.is_active ? 'selected' : ''}>No</option></select></label>
            <div class="form-actions"><button class="btn" type="submit">${isEdit ? 'Save' : 'Create'}</button></div>
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
            if (isEdit) {
                await adminApi.updateRadar(radar.code, payload);
                showMessage(`Radar ${radar.code} updated`, 'success');
            } else {
                await adminApi.createRadar(payload);
                showMessage(`Radar ${payload.code} created`, 'success');
            }
            await renderSection();
        },
    );
}

async function renderProducts() {
    const products = sortItems(await adminApi.listProducts(), 'products');
    elements.sectionContent.innerHTML = `
        <div class="toolbar"><button class="btn" id="products-add">+ Add New Product</button></div>
        ${renderFilterBar('products', products)}
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th><button data-sort="id">ID</button></th>
                    <th>Key</th>
                    <th>Title</th>
                    <th>Enabled</th>
                    <th>See in Open</th>
                    <th>Min</th>
                    <th>Max</th>
                    <th>Unit</th>
                    <th>Default Cmap</th>
                    <th>Actions</th>
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
                            <button class="btn-secondary" data-edit-product="${product.id}">Edit</button>
                            <button class="btn-danger" data-delete-product="${product.id}">Delete</button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;

    document.getElementById('products-add').onclick = () => openProductForm();
    wireFilterBar('products');
    elements.sectionContent.querySelector('[data-sort="id"]').onclick = () => switchSort('products', 'id');

    elements.sectionContent.querySelectorAll('[data-toggle-product-enabled]').forEach((element) => {
        element.onchange = async (event) => {
            await adminApi.patchProduct(event.target.dataset.toggleProductEnabled, { enabled: event.target.checked });
            showMessage('Product enabled flag updated', 'success');
        };
    });

    elements.sectionContent.querySelectorAll('[data-toggle-product-open]').forEach((element) => {
        element.onchange = async (event) => {
            await adminApi.patchProduct(event.target.dataset.toggleProductOpen, { see_in_open: event.target.checked });
            showMessage('Product visibility updated', 'success');
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
            showMessage(`Product ${id} deleted`, 'success');
            renderSection();
        };
    });
}

function openProductForm(product = null) {
    const isEdit = Boolean(product);
    openFormModal(
        isEdit ? `Edit Product ${product.product_key}` : 'Add Product',
        `
            <label>Product Key <input name="product_key" maxlength="16" value="${safeText(product?.product_key)}" required></label>
            <label>Title <input name="product_title" value="${safeText(product?.product_title)}" required></label>
            <label>Description <input name="product_description" value="${safeText(product?.product_description)}"></label>
            <label>Enabled <select name="enabled"><option value="true" ${product?.enabled ? 'selected' : ''}>Yes</option><option value="false" ${product && !product.enabled ? 'selected' : ''}>No</option></select></label>
            <label>See in Open <select name="see_in_open"><option value="true" ${product?.see_in_open ? 'selected' : ''}>Yes</option><option value="false" ${product && !product.see_in_open ? 'selected' : ''}>No</option></select></label>
            <label>Min Value <input name="min_value" type="number" step="any" value="${safeText(product?.min_value)}"></label>
            <label>Max Value <input name="max_value" type="number" step="any" value="${safeText(product?.max_value)}"></label>
            <label>Unit <input name="unit" value="${safeText(product?.unit)}"></label>
            <label>Default Colormap <input name="default_cmap" maxlength="64" value="${safeText(product?.default_cmap)}" placeholder="e.g. grc_th"></label>
            <div class="form-actions"><button class="btn" type="submit">${isEdit ? 'Save' : 'Create'}</button></div>
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
                showMessage(`Product ${product.id} updated`, 'success');
            } else {
                await adminApi.createProduct(payload);
                showMessage('Product created', 'success');
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
            <button class="btn" id="references-add">+ Add Entries</button>
            <button class="btn-danger" id="references-bulk-delete">Delete all in selected product</button>
        </div>
        ${renderFilterBar('references', sorted, { facetOptions: { product_id: productFacetOptions } })}
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th><button data-sort="id">ID</button></th>
                    <th>Product</th>
                    <th>Value</th>
                    <th>Color</th>
                    <th>Color Font</th>
                    <th>Title</th>
                    <th>Unit</th>
                    <th>Actions</th>
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
                            <button class="btn-secondary" data-edit-reference="${reference.id}">Edit</button>
                            <button class="btn-danger" data-delete-reference="${reference.id}">Delete</button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;

    wireFilterBar('references');
    elements.sectionContent.querySelector('[data-sort="id"]').onclick = () => switchSort('references', 'id');
    document.getElementById('references-add').onclick = () => openReferenceBulkForm(products);
    document.getElementById('references-bulk-delete').onclick = async () => {
        const selectedProductId = getFilters('references').facets.product_id || '';
        if (!selectedProductId) {
            showMessage('Select a product in the "Producto" filter first', 'error');
            return;
        }
        const productKey = productsById.get(Number(selectedProductId))?.product_key || selectedProductId;
        if (!requireConfirmation(`all references for product ${productKey}`)) return;
        const result = await adminApi.bulkDeleteReferences(selectedProductId);
        showMessage(`Deleted ${result.deleted_count} references`, 'success');
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
            showMessage(`Reference ${id} deleted`, 'success');
            renderSection();
        };
    });
}

function openReferenceEditForm(reference, products) {
    openFormModal(
        `Edit Reference ${reference.id}`,
        `
            <label>Product
                <select name="product_id">${products.map((p) => `<option value="${p.id}" ${p.id === reference.product_id ? 'selected' : ''}>${p.product_key}</option>`)}</select>
            </label>
            <label>Value <input name="value" type="number" step="any" value="${safeText(reference.value)}" required></label>
            <label>Title <input name="title" value="${safeText(reference.title)}"></label>
            <label>Unit <input name="unit" value="${safeText(reference.unit)}"></label>
            <label>Color <input name="color" type="color" value="${safeText(reference.color || '#000000')}"></label>
            <label>Font Color <input name="color_font" type="color" value="${safeText(reference.color_font || '#ffffff')}"></label>
            <label>Description <input name="description" value="${safeText(reference.description)}"></label>
            <div class="form-actions"><button class="btn" type="submit">Save</button></div>
        `,
        async (formData) => {
            const payload = Object.fromEntries(formData.entries());
            payload.product_id = Number(payload.product_id);
            payload.value = Number(payload.value);
            await adminApi.updateReference(reference.id, payload);
            showMessage(`Reference ${reference.id} updated`, 'success');
            await renderSection();
        },
    );
}

function openReferenceBulkForm(products) {
    // TODO: References admin CRUD is foundational for future user-defined colormap management.
    const row = () => `
        <div class="reference-row">
            <label>Value <input name="value" type="number" step="any" required></label>
            <label>Title <input name="title"></label>
            <label>Unit <input name="unit"></label>
            <label>Color <input name="color" type="color" value="#000000"></label>
            <label>Font Color <input name="color_font" type="color" value="#ffffff"></label>
            <label>Description <input name="description"></label>
        </div>
    `;

    openFormModal(
        'Add Reference Entries',
        `
            <label>Product
                <select name="product_id" required>
                    ${products.map((product) => `<option value="${product.id}">${product.product_key}</option>`).join('')}
                </select>
            </label>
            <div id="reference-bulk-rows">${row()}</div>
            <div class="toolbar">
                <button type="button" class="btn-secondary" id="reference-row-add">Add Row</button>
            </div>
            <div class="form-actions"><button class="btn" type="submit">Create Entries</button></div>
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
            showMessage(`Created ${payloads.length} reference entries`, 'success');
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
            <div>Page ${page} of ${pageCount} — ${total} records</div>
            <div class="table-actions">
                <button class="btn-secondary" id="${prefix}-prev" ${page <= 1 ? 'disabled' : ''}>Prev</button>
                <button class="btn-secondary" id="${prefix}-next" ${page >= pageCount ? 'disabled' : ''}>Next</button>
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
            <button class="btn-danger" id="cogs-delete-filtered">Delete by filters</button>
            <button class="btn-danger" id="cogs-delete-selected">Delete selected</button>
        </div>
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th><input type="checkbox" id="cogs-select-all"></th>
                    <th>ID</th><th>Radar</th><th>Product</th><th>Observation</th><th>File</th>
                    <th>Size</th><th>Status</th><th>Vol</th><th>Polarimetric</th><th>Indexed</th><th>Actions</th>
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
        deleteButton.textContent = 'Delete';
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
            showMessage(`COG ${id} status updated`, 'success');
        };
    });

    elements.sectionContent.querySelectorAll('[data-cog-delete]').forEach((element) => {
        element.onclick = async () => {
            const id = Number(element.dataset.cogDelete);
            if (!requireConfirmation(`COG ${id}`)) return;
            await adminApi.deleteCog(id);
            state.cogs.selected.delete(id);
            showMessage(`COG ${id} deleted`, 'success');
            renderSection();
        };
    });

    document.getElementById('cogs-delete-selected').onclick = async () => {
        const ids = [...state.cogs.selected];
        if (!ids.length) {
            showMessage('Select at least one COG record first', 'error');
            return;
        }
        if (!requireConfirmation(`${ids.length} selected COG records`)) return;
        await Promise.all(ids.map((id) => adminApi.deleteCog(id)));
        state.cogs.selected.clear();
        showMessage(`Deleted ${ids.length} selected COG records`, 'success');
        renderSection();
    };

    document.getElementById('cogs-delete-filtered').onclick = async () => {
        const typed = window.prompt('Type DELETE to confirm deleting all COGs matching active filters');
        if ((typed || '').trim().toUpperCase() !== 'DELETE') return;
        const deletedCount = await adminApi.bulkDelete('cogs', filters);
        showMessage(`Deleted ${deletedCount} COG records by filter`, 'success');
        state.cogs.selected.clear();
        renderSection();
    };
}

// TODO: Estrategia CRUD affects indexer behavior; deleting strategy codes referenced by COGs may fail with FK conflict and returns HTTP 409.
async function renderEstrategias() {
    const [estrategias, volumenes] = await Promise.all([adminApi.listEstrategias(), adminApi.listVolumenes()]);
    const sorted = sortItems(estrategias, 'estrategias');
    elements.sectionContent.innerHTML = `
        <div class="toolbar"><button class="btn" id="estrategias-add">+ Add Estrategia</button></div>
        ${renderFilterBar('estrategias', sorted)}
        <div class="table-wrap">
        <table>
            <thead><tr><th><button data-sort="code">Code</button></th><th>Description</th><th>Associated Volumenes</th><th>Actions</th></tr></thead>
            <tbody>
                ${sorted.map((item) => `
                    <tr${rowFacetAttr('estrategias', item)}>
                        <td>${safeText(item.code)}</td>
                        <td>${safeText(item.description)}</td>
                        <td>${(item.volumen_values || []).join(', ')}</td>
                        <td class="table-actions">
                            <button class="btn-secondary" data-edit-estrategia="${item.code}">Edit</button>
                            <button class="btn-danger" data-delete-estrategia="${item.code}">Delete</button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;

    wireFilterBar('estrategias');
    elements.sectionContent.querySelector('[data-sort="code"]').onclick = () => switchSort('estrategias', 'code');
    document.getElementById('estrategias-add').onclick = () => openEstrategiaForm(null, volumenes);
    elements.sectionContent.querySelectorAll('[data-edit-estrategia]').forEach((element) => {
        element.onclick = async () => openEstrategiaForm(await adminApi.getEstrategia(element.dataset.editEstrategia), volumenes);
    });
    elements.sectionContent.querySelectorAll('[data-delete-estrategia]').forEach((element) => {
        element.onclick = async () => {
            const code = element.dataset.deleteEstrategia;
            if (!requireConfirmation(`estrategia ${code}`)) return;
            await adminApi.deleteEstrategia(code);
            showMessage(`Estrategia ${code} deleted`, 'success');
            renderSection();
        };
    });
}

function openEstrategiaForm(estrategia, volumenes) {
    const isEdit = Boolean(estrategia);
    openFormModal(
        isEdit ? `Edit Estrategia ${estrategia.code}` : 'Add Estrategia',
        `
            ${isEdit ? '' : '<label>Code <input name="code" maxlength="16" required></label>'}
            <label>Description <input name="description" value="${safeText(estrategia?.description)}"></label>
            <label>Volumenes
                <select name="volumen_ids" multiple size="8">
                    ${volumenes.map((volumen) => `<option value="${volumen.id}" ${(estrategia?.volumen_ids || []).includes(volumen.id) ? 'selected' : ''}>${volumen.id} - ${volumen.value}</option>`).join('')}
                </select>
            </label>
            <div class="form-actions"><button class="btn" type="submit">${isEdit ? 'Save' : 'Create'}</button></div>
        `,
        async (formData) => {
            const payload = {
                description: formData.get('description') || '',
                volumen_ids: formData.getAll('volumen_ids').map(Number),
            };
            if (isEdit) {
                await adminApi.updateEstrategia(estrategia.code, payload);
                showMessage(`Estrategia ${estrategia.code} updated`, 'success');
            } else {
                payload.code = formData.get('code');
                await adminApi.createEstrategia(payload);
                showMessage(`Estrategia ${payload.code} created`, 'success');
            }
            await renderSection();
        },
    );
}

async function renderVolumenes() {
    const volumenes = sortItems(await adminApi.listVolumenes(), 'volumenes');
    elements.sectionContent.innerHTML = `
        <div class="toolbar"><button class="btn" id="volumenes-add">+ Add Volumen</button></div>
        ${renderFilterBar('volumenes', volumenes)}
        <div class="table-wrap">
        <table>
            <thead><tr><th><button data-sort="id">ID</button></th><th>Value</th><th>Actions</th></tr></thead>
            <tbody>
                ${volumenes.map((item) => `
                    <tr${rowFacetAttr('volumenes', item)}>
                        <td>${item.id}</td>
                        <td>${item.value}</td>
                        <td class="table-actions">
                            <button class="btn-secondary" data-edit-volumen="${item.id}">Edit</button>
                            <button class="btn-danger" data-delete-volumen="${item.id}">Delete</button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;

    wireFilterBar('volumenes');
    elements.sectionContent.querySelector('[data-sort="id"]').onclick = () => switchSort('volumenes', 'id');
    document.getElementById('volumenes-add').onclick = () => openVolumenForm();
    elements.sectionContent.querySelectorAll('[data-edit-volumen]').forEach((element) => {
        element.onclick = async () => openVolumenForm(await adminApi.getVolumen(element.dataset.editVolumen));
    });
    elements.sectionContent.querySelectorAll('[data-delete-volumen]').forEach((element) => {
        element.onclick = async () => {
            const id = element.dataset.deleteVolumen;
            if (!requireConfirmation(`volumen ${id}`)) return;
            await adminApi.deleteVolumen(id);
            showMessage(`Volumen ${id} deleted`, 'success');
            renderSection();
        };
    });
}

function openVolumenForm(volumen = null) {
    const isEdit = Boolean(volumen);
    openFormModal(
        isEdit ? `Edit Volumen ${volumen.id}` : 'Add Volumen',
        `
            <label>Value <input type="number" name="value" value="${safeText(volumen?.value)}" required></label>
            <div class="form-actions"><button class="btn" type="submit">${isEdit ? 'Save' : 'Create'}</button></div>
        `,
        async (formData) => {
            const payload = { value: Number(formData.get('value')) };
            if (isEdit) {
                await adminApi.updateVolumen(volumen.id, payload);
                showMessage(`Volumen ${volumen.id} updated`, 'success');
            } else {
                await adminApi.createVolumen(payload);
                showMessage('Volumen created', 'success');
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
            <button class="btn-danger" id="tops-delete-filtered">Delete by filters</button>
            <button class="btn-danger" id="tops-delete-selected">Delete selected</button>
        </div>
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th><input type="checkbox" id="tops-select-all"></th>
                    <th>ID</th><th>Radar</th><th>Strategy</th><th>Vol</th><th>Observation</th>
                    <th>Cores</th><th>Tops</th><th>Features</th><th>Status</th><th>File</th><th>Created</th><th>Actions</th>
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
        featuresLink.href = `/api/v1/tops-cores/${itemId}/features`;
        featuresLink.textContent = 'View Features';
        actionsCell.appendChild(featuresLink);

        const deleteButton = document.createElement('button');
        deleteButton.className = 'btn-danger';
        deleteButton.dataset.topDelete = String(itemId);
        deleteButton.type = 'button';
        deleteButton.textContent = 'Delete';
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
            showMessage(`Tops & Cores ${id} status updated`, 'success');
        };
    });

    elements.sectionContent.querySelectorAll('[data-top-delete]').forEach((element) => {
        element.onclick = async () => {
            const id = Number(element.dataset.topDelete);
            if (!requireConfirmation(`tops & cores ${id}`)) return;
            await adminApi.deleteTopsCores(id);
            state.tops.selected.delete(id);
            showMessage(`Tops & Cores ${id} deleted`, 'success');
            renderSection();
        };
    });

    document.getElementById('tops-delete-selected').onclick = async () => {
        const ids = [...state.tops.selected];
        if (!ids.length) {
            showMessage('Select at least one record first', 'error');
            return;
        }
        if (!requireConfirmation(`${ids.length} selected Tops & Cores records`)) return;
        await Promise.all(ids.map((id) => adminApi.deleteTopsCores(id)));
        state.tops.selected.clear();
        showMessage(`Deleted ${ids.length} selected Tops & Cores records`, 'success');
        renderSection();
    };

    document.getElementById('tops-delete-filtered').onclick = async () => {
        const typed = window.prompt('Type DELETE to confirm deleting all Tops & Cores matching active filters');
        if ((typed || '').trim().toUpperCase() !== 'DELETE') return;
        const deletedCount = await adminApi.bulkDelete('tops-cores', filters);
        showMessage(`Deleted ${deletedCount} Tops & Cores records by filter`, 'success');
        state.tops.selected.clear();
        renderSection();
    };
}

// ── Colormap creator ──────────────────────────────────────────────────────────

function openColormapCreator(products) {
    /** In-memory stops state: array of {position: number, color: hex string} */
    let creatorStops = [
        { position: 0.0, color: '#000000' },
        { position: 1.0, color: '#ffffff' },
    ];

    const modal = elements.creatorModal;
    modal.classList.remove('hidden');

    const nameInput = document.getElementById('creator-name');
    const stopsList = document.getElementById('creator-stops-list');
    const canvas = document.getElementById('creator-canvas');
    const ticks = document.getElementById('creator-stop-ticks');
    const productsList = document.getElementById('creator-products-list');

    nameInput.value = '';

    /** Product assignment chips (styled via CSS :has(:checked)). */
    productsList.innerHTML = products
        .map((p) => `<label><input type="checkbox" value="${safeText(p.product_key)}"> ${safeText(p.product_key)}</label>`)
        .join('');

    const clamp01 = (value) => Math.min(1, Math.max(0, value));

    /** Draw a horizontal gradient preview and position the stop ticks. */
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
        ticks.innerHTML = sorted
            .map((s) => `<span class="creator-stop-tick" style="left:${(clamp01(s.position) * 100).toFixed(2)}%;--tick-color:${safeHexColor(s.color, '#000000')}"></span>`)
            .join('');
    }

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
                    showMessage('A colormap needs at least 2 stops.', 'error');
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

    document.getElementById('creator-save').onclick = async () => {
        const cmapName = document.getElementById('creator-name').value.trim();
        if (!cmapName) {
            showMessage('Colormap name is required.', 'error');
            return;
        }
        if (creatorStops.length < 2) {
            showMessage('At least 2 stops are required.', 'error');
            return;
        }
        const productKeys = [...productsList.querySelectorAll('input[type=checkbox]:checked')]
            .map((cb) => cb.value);
        try {
            await adminApi.createColormapFromHex({
                cmap_name: cmapName,
                stops: creatorStops.map((s) => ({ position: s.position, color: s.color })),
                product_keys: productKeys,
            });
            // Invalidate the in-process cache so the API picks up the new colormap.
            await fetch('/api/v1/colormap/cache/invalidate', { method: 'POST' });
            modal.classList.add('hidden');
            showMessage(`Colormap "${cmapName}" created`, 'success');
            renderSection();
        } catch (error) {
            showMessage(error.message || 'Failed to create colormap', 'error');
        }
    };
}

async function renderColormaps() {
    const [cmaps, products] = await Promise.all([
        adminApi.listColormapSummaries(),
        adminApi.listProducts(),
    ]);
    const sorted = sortItems(cmaps, 'colormaps');

    elements.sectionContent.innerHTML = `
        <div class="toolbar">
            <button class="btn" id="cmap-creator-open">🎨 Create Colormap</button>
            <span class="toolbar-note">System colormaps cannot be deleted.</span>
        </div>
        ${renderFilterBar('colormaps', sorted)}
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th><button data-sort="cmap_name" data-section="colormaps">Name</button></th>
                    <th><button data-sort="stop_count" data-section="colormaps">Stops</button></th>
                    <th>System</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                ${sorted.map((c) => `
                    <tr${rowFacetAttr('colormaps', c)}>
                        <td>${safeText(c.cmap_name)}</td>
                        <td>${c.stop_count}</td>
                        <td>${c.is_system ? '✔' : ''}</td>
                        <td class="table-actions">
                            <button class="btn-secondary" data-view-cmap="${safeText(c.cmap_name)}">View Stops</button>
                            ${!c.is_system ? `<button class="btn-danger" data-delete-cmap="${safeText(c.cmap_name)}">Delete</button>` : ''}
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
            const stops = await adminApi.getColormapStops(name);
            const rows = stops.map((s) => `
                <tr>
                    <td>${safeText(s.channel)}</td>
                    <td>${s.position.toFixed(4)}</td>
                    <td>${s.val_left.toFixed(4)}</td>
                    <td>${s.val_right.toFixed(4)}</td>
                    <td>${s.sort_order}</td>
                </tr>
            `).join('');
            openFormModal(`Stops for ${name}`, `
                <div style="overflow:auto;max-height:60vh;">
                    <table>
                        <thead><tr><th>Ch</th><th>Position</th><th>Val Left</th><th>Val Right</th><th>Order</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
                <div style="text-align:right;margin-top:8px;">
                    <button type="button" class="btn btn-secondary" id="close-stops-modal">Close</button>
                </div>
            `, async () => {});
            document.getElementById('close-stops-modal')?.addEventListener('click', closeFormModal);
        };
    });

    elements.sectionContent.querySelectorAll('[data-delete-cmap]').forEach((btn) => {
        btn.onclick = async () => {
            const name = btn.dataset.deleteCmap;
            if (!requireConfirmation(`colormap "${name}"`)) return;
            try {
                await adminApi.deleteColormap(name);
                showMessage(`Colormap "${name}" deleted`, 'success');
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
            <button class="btn" id="cmap-option-add">+ Add Option</button>
        </div>
        ${renderFilterBar('colormap-options', sorted)}
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th><button data-sort="product_key" data-section="colormap-options">Product Key</button></th>
                    <th><button data-sort="cmap_name" data-section="colormap-options">Colormap</button></th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                ${sorted.map((opt) => `
                    <tr${rowFacetAttr('colormap-options', opt)}>
                        <td>${safeText(opt.product_key)}</td>
                        <td>${safeText(opt.cmap_name)}</td>
                        <td class="table-actions">
                            <button class="btn-danger" data-delete-cmap-option="${opt.id}">Remove</button>
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

    document.getElementById('cmap-option-add').onclick = () => {
        openFormModal('Add Colormap Option', `
            <label>Product Key
                <select name="product_key" required>${productOpts}</select>
            </label>
            <label>Colormap
                <select name="cmap_name" required>${cmapOpts}</select>
            </label>
            <button type="submit" class="btn">Add</button>
        `, async (formData) => {
            await adminApi.createColormapOption({
                product_key: formData.get('product_key'),
                cmap_name: formData.get('cmap_name'),
            });
            showMessage('Colormap option added', 'success');
            renderSection();
        });
    };

    elements.sectionContent.querySelectorAll('[data-delete-cmap-option]').forEach((btn) => {
        btn.onclick = async () => {
            const id = parseInt(btn.dataset.deleteCmapOption, 10);
            if (!requireConfirmation(`colormap option #${id}`)) return;
            try {
                await adminApi.deleteColormapOption(id);
                showMessage('Colormap option removed', 'success');
                renderSection();
            } catch (error) {
                showMessage(error.message, 'error');
            }
        };
    });
}

async function renderSection() {
    hideMessage();
    state.section = parseHashSection();
    setActiveSidebar(state.section);

    const titleBySection = {
        dashboard: 'Dashboard',
        radars: 'Radars',
        products: 'Products',
        references: 'References',
        cogs: 'COGs',
        estrategias: 'Estrategias',
        volumenes: 'Volumenes',
        'tops-cores': 'Tops & Cores',
        colormaps: 'Colormaps',
        'colormap-options': 'Colormap Options',
    };
    elements.sectionTitle.textContent = titleBySection[state.section] || 'Dashboard';

    try {
        if (state.section === 'dashboard') await renderDashboard();
        if (state.section === 'radars') await renderRadars();
        if (state.section === 'products') await renderProducts();
        if (state.section === 'references') await renderReferences();
        if (state.section === 'cogs') await renderCogs();
        if (state.section === 'estrategias') await renderEstrategias();
        if (state.section === 'volumenes') await renderVolumenes();
        if (state.section === 'tops-cores') await renderTopsCores();
        if (state.section === 'colormaps') await renderColormaps();
        if (state.section === 'colormap-options') await renderColormapOptions();
        decorateSortHeaders(state.section);
    } catch (error) {
        if ((error.message || '').includes(EXPIRED_SESSION_MESSAGE)) {
            showMessage(EXPIRED_SESSION_MESSAGE, 'error');
        } else {
            showMessage(error.message || 'Unexpected error', 'error');
        }
    }
}

function init() {
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

    history.replaceState(null, '', `#${parseHashSection()}`);
    renderSection();
}

init();
