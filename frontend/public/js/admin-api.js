const ADMIN_API_BASE = '/api/v1/admin';
const EXPIRED_SESSION_MESSAGE = 'Authentication failed. Refresh the page and verify your admin credentials.';

function buildQuery(params = {}) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value === undefined || value === null || value === '') {
            return;
        }
        search.append(key, value);
    });
    const query = search.toString();
    return query ? `?${query}` : '';
}

async function request(path, options = {}) {
    const response = await fetch(`${ADMIN_API_BASE}${path}`, {
        headers: {
            'Content-Type': 'application/json',
            ...(options.headers || {}),
        },
        ...options,
    });

    if (response.status === 401) {
        throw new Error(EXPIRED_SESSION_MESSAGE);
    }

    if (!response.ok) {
        let detail = `API error: ${response.status}`;
        try {
            const payload = await response.json();
            if (payload?.detail) {
                detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail);
            }
        } catch (error) {
            // Ignore JSON parse failures on empty responses
        }
        throw new Error(detail);
    }

    if (response.status === 204) {
        return null;
    }

    return response.json();
}

export const adminApi = {
    async getDashboardCounts() {
        const [radars, products, references, estrategias, volumenes, cogTotals, cogAvailable, cogMissing, cogError, topsTotals, topsAvailable, topsMissing] = await Promise.all([
            this.listRadars(),
            this.listProducts(),
            this.listReferences(),
            this.listEstrategias(),
            this.listVolumenes(),
            this.listCogs({ page: 1, page_size: 1 }),
            this.listCogs({ page: 1, page_size: 1, status: 'available' }),
            this.listCogs({ page: 1, page_size: 1, status: 'missing' }),
            this.listCogs({ page: 1, page_size: 1, status: 'error' }),
            this.listTopsCores({ page: 1, page_size: 1 }),
            this.listTopsCores({ page: 1, page_size: 1, status: 'available' }),
            this.listTopsCores({ page: 1, page_size: 1, status: 'missing' }),
        ]);

        return {
            radarsTotal: radars.length,
            radarsActive: radars.filter((item) => item.is_active).length,
            productsTotal: products.length,
            productsEnabled: products.filter((item) => item.enabled).length,
            referencesTotal: references.length,
            estrategiasTotal: estrategias.length,
            volumenesTotal: volumenes.length,
            cogsTotal: cogTotals.total,
            cogsAvailable: cogAvailable.total,
            cogsMissing: cogMissing.total,
            cogsError: cogError.total,
            topsTotal: topsTotals.total,
            topsAvailable: topsAvailable.total,
            topsMissing: topsMissing.total,
        };
    },

    listRadars() { return request('/radars'); },
    getRadar(code) { return request(`/radars/${encodeURIComponent(code)}`); },
    createRadar(payload) { return request('/radars', { method: 'POST', body: JSON.stringify(payload) }); },
    updateRadar(code, payload) { return request(`/radars/${encodeURIComponent(code)}`, { method: 'PUT', body: JSON.stringify(payload) }); },
    patchRadar(code, payload) { return request(`/radars/${encodeURIComponent(code)}`, { method: 'PATCH', body: JSON.stringify(payload) }); },
    deleteRadar(code) { return request(`/radars/${encodeURIComponent(code)}`, { method: 'DELETE' }); },

    listProducts() { return request('/products'); },
    getProduct(id) { return request(`/products/${id}`); },
    createProduct(payload) { return request('/products', { method: 'POST', body: JSON.stringify(payload) }); },
    updateProduct(id, payload) { return request(`/products/${id}`, { method: 'PUT', body: JSON.stringify(payload) }); },
    patchProduct(id, payload) { return request(`/products/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }); },
    deleteProduct(id) { return request(`/products/${id}`, { method: 'DELETE' }); },

    listReferences(params = {}) { return request(`/references${buildQuery(params)}`); },
    getReference(id) { return request(`/references/${id}`); },
    createReference(payload) { return request('/references', { method: 'POST', body: JSON.stringify(payload) }); },
    updateReference(id, payload) { return request(`/references/${id}`, { method: 'PUT', body: JSON.stringify(payload) }); },
    deleteReference(id) { return request(`/references/${id}`, { method: 'DELETE' }); },
    bulkDeleteReferences(productId) { return request(`/references${buildQuery({ product_id: productId })}`, { method: 'DELETE' }); },

    listCogs(params = {}) { return request(`/cogs${buildQuery(params)}`); },
    getCog(id) { return request(`/cogs/${id}`); },
    patchCogStatus(id, status) { return request(`/cogs/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }); },
    deleteCog(id) { return request(`/cogs/${id}`, { method: 'DELETE' }); },

    listEstrategias() { return request('/estrategias'); },
    getEstrategia(code) { return request(`/estrategias/${encodeURIComponent(code)}`); },
    createEstrategia(payload) { return request('/estrategias', { method: 'POST', body: JSON.stringify(payload) }); },
    updateEstrategia(code, payload) { return request(`/estrategias/${encodeURIComponent(code)}`, { method: 'PUT', body: JSON.stringify(payload) }); },
    deleteEstrategia(code) { return request(`/estrategias/${encodeURIComponent(code)}`, { method: 'DELETE' }); },

    listVolumenes() { return request('/volumenes'); },
    getVolumen(id) { return request(`/volumenes/${id}`); },
    createVolumen(payload) { return request('/volumenes', { method: 'POST', body: JSON.stringify(payload) }); },
    updateVolumen(id, payload) { return request(`/volumenes/${id}`, { method: 'PUT', body: JSON.stringify(payload) }); },
    deleteVolumen(id) { return request(`/volumenes/${id}`, { method: 'DELETE' }); },

    listTopsCores(params = {}) { return request(`/tops-cores${buildQuery(params)}`); },
    getTopsCores(id) { return request(`/tops-cores/${id}`); },
    patchTopsCoresStatus(id, status) { return request(`/tops-cores/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }); },
    deleteTopsCores(id) { return request(`/tops-cores/${id}`, { method: 'DELETE' }); },

    // Colormap stops
    listColormapSummaries() { return request('/colormap-stops'); },
    getColormapStops(cmapName) { return request(`/colormap-stops/${encodeURIComponent(cmapName)}`); },
    deleteColormap(cmapName) { return request(`/colormap-stops/${encodeURIComponent(cmapName)}`, { method: 'DELETE' }); },
    createColormapStop(payload) { return request('/colormap-stops', { method: 'POST', body: JSON.stringify(payload) }); },

    // Colormap creator (hex stops → server-side channel conversion)
    createColormapFromHex(payload) { return request('/colormap-from-hex', { method: 'POST', body: JSON.stringify(payload) }); },

    // Product colormap options
    listColormapOptions(productKey) {
        const q = productKey ? buildQuery({ product_key: productKey }) : '';
        return request(`/colormap-options${q}`);
    },
    createColormapOption(payload) { return request('/colormap-options', { method: 'POST', body: JSON.stringify(payload) }); },
    deleteColormapOption(id) { return request(`/colormap-options/${id}`, { method: 'DELETE' }); },

    async bulkDelete(resource, filters) {
        const data = await request(`/${resource}${buildQuery(filters)}`, { method: 'DELETE' });
        return data?.deleted_count ?? 0;
    },
};

export { EXPIRED_SESSION_MESSAGE };
