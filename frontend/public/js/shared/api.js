/**
 * API Module - Handles all backend communication
 */

const API_BASE = '/api/v1';

export const api = {
    /**
     * Generic GET request
     */
    async get(endpoint) {
        const response = await fetch(`${API_BASE}${endpoint}`);
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        return response.json();
    },

    /**
     * Get all radars
     * @param {boolean} activeOnly - If true, only return active radars (default: true)
     */
    async getRadars(activeOnly = true) {
        const data = await this.get(`/radars?active_only=${activeOnly}`);
        return data.radars || [];
    },

    // Internal: fetch products for a single (volNrs, strategy) clause
    async _getProductsForClause(volNrs, strategy) {
        const params = new URLSearchParams();
        if (volNrs?.length) volNrs.forEach(v => params.append('vol_nr', v));
        [].concat(strategy || []).forEach(s => params.append('strategy', s));
        const q = params.toString();
        const data = await this.get(`/products${q ? '?' + q : ''}`);
        return data.products || [];
    },

    /**
     * Get all products available across the given mode clauses.
     * @param {Array<{volNrs: string[], strategy: string|string[]}>} includes
     */
    async getProducts(includes) {
        const groups = await Promise.all(
            includes.map(c => this._getProductsForClause(c.volNrs, c.strategy))
        );
        const seen = new Set();
        return groups.flat().filter(p => !seen.has(p.product_key) && seen.add(p.product_key));
    },

    /**
     * Get COG images for a radar/product combination
     */
    async getCogs(radarCode, productKey, limit = 20) {
        const params = new URLSearchParams({
            radar_code: radarCode,
            product_key: productKey,
            page_size: limit,
        });
        const data = await this.get(`/cogs?${params}`);
        return data.cogs || [];
    },

    // Return only the includes clauses whose strategy matches the radar's known type.
    // AR* radars use strategy '1000'; RMA* radars use strategy '0315'.
    // Prevents spurious cross-strategy requests that always 404.
    _clausesForRadar(radarCode, includes) {
        const strategyMap = { AR: '1000', RMA: '0315' };
        const prefix = Object.keys(strategyMap).find(p => radarCode.toUpperCase().startsWith(p));
        const radarStrategy = prefix ? strategyMap[prefix] : null;
        if (!radarStrategy) return includes;
        return includes.filter(c => [].concat(c.strategy || []).includes(radarStrategy));
    },

    // Internal: fetch the latest COG for a single (volNrs, strategy) clause
    async _getLatestCogForClause(radarCode, productKey, volNrs, strategy) {
        const params = new URLSearchParams({ radar_code: radarCode, product_key: productKey });
        if (volNrs?.length) volNrs.forEach(v => params.append('vol_nr', v));
        [].concat(strategy || []).forEach(s => params.append('strategy', s));
        return this.get(`/cogs/latest?${params}`);
    },

    /**
     * Get the most recent COG for a radar/product across all mode clauses.
     * @param {string}   radarCode
     * @param {string}   productKey
     * @param {Array<{volNrs: string[], strategy: string|string[]}>} includes
     */
    async getLatestCog(radarCode, productKey, includes) {
        const clauses = this._clausesForRadar(radarCode, includes);
        const results = await Promise.allSettled(
            clauses.map(c => this._getLatestCogForClause(radarCode, productKey, c.volNrs, c.strategy))
        );
        const cogs = results
            .filter(r => r.status === 'fulfilled' && r.value)
            .map(r => r.value);
        if (!cogs.length) throw new Error(`No COG found for ${radarCode}/${productKey}`);
        return cogs.reduce((best, cog) =>
            new Date(cog.observation_time) > new Date(best.observation_time) ? cog : best
        );
    },

    /**
     * Get latest COGs for multiple radars and a product.
     * @param {string[]} radarCodes
     * @param {string}   productKey
     * @param {Array<{volNrs: string[], strategy: string|string[]}>} includes
     */
    async getLatestCogsForRadars(radarCodes, productKey, includes) {
        const promises = radarCodes.map(radarCode =>
            this.getLatestCog(radarCode, productKey, includes)
                .catch(err => {
                    console.warn(`Failed to get latest COG for ${radarCode}:`, err);
                    return null;
                })
        );
        const results = await Promise.all(promises);
        return results
            .map((cog, index) => ({ radarCode: radarCodes[index], cog }))
            .filter(item => item.cog !== null);
    },

    // Internal: fetch COGs for one radar + one clause
    async _getCogsForClause(radarCode, productKey, startTime, endTime, limit, volNrs, strategy) {
        const params = new URLSearchParams({ product_key: productKey, page_size: limit });
        if (startTime) params.append('start_time', startTime.toISOString());
        if (endTime)   params.append('end_time',   endTime.toISOString());
        if (volNrs?.length) volNrs.forEach(v => params.append('vol_nr', v));
        [].concat(strategy || []).forEach(s => params.append('strategy', s));
        params.append('radar_code', radarCode);
        const data = await this.get(`/cogs?${params}`);
        return (data.cogs || []).map(cog => ({ ...cog, radar_code: radarCode }));
    },

    /**
     * Get COGs for multiple radars within a time range across all mode clauses.
     * Results are deduplicated by id and sorted newest-first.
     * @param {string[]}  radarCodes
     * @param {string}    productKey
     * @param {Date|null} startTime
     * @param {Date|null} endTime
     * @param {number}    limit       - max COGs per (radar × clause) request
     * @param {Array<{volNrs: string[], strategy: string|string[]}>} includes
     */
    async getCogsForTimeRange(radarCodes, productKey, startTime, endTime, limit = 100, includes) {
        const promises = radarCodes.flatMap(radarCode =>
            this._clausesForRadar(radarCode, includes).map(clause =>
                this._getCogsForClause(radarCode, productKey, startTime, endTime, limit, clause.volNrs, clause.strategy)
                    .catch(() => [])
            )
        );
        const groups  = await Promise.all(promises);
        const allCogs = groups.flat();
        const seen    = new Set();
        const unique  = allCogs.filter(c => !seen.has(c.id) && seen.add(c.id));
        unique.sort((a, b) => new Date(b.observation_time) - new Date(a.observation_time));
        return unique;
    },

    /**
     * Get colormap for a product (DEPRECATED - uses old endpoint)
     */
    async getColormap(productKey) {
        return this.get(`/products/${productKey}/colormap`);
    },

    /**
     * Get colormap info for a product (NEW - uses predefined colormaps)
     */
    async getColormapInfo(productKey, colormapName = null) {
        const params = new URLSearchParams();
        if (colormapName) params.append('colormap', colormapName);
        const query = params.toString() ? `?${params}` : '';
        return this.get(`/colormap/info/${productKey}${query}`);
    },

    /**
     * Get available colormap options for all products
     */
    async getColormapOptions() {
        return this.get('/colormap/options');
    },

    /**
     * Get default colormaps for all products
     */
    async getColormapDefaults() {
        return this.get('/colormap/defaults');
    },

    /**
     * Get tile URL for a COG with optional colormap/range overrides
     */
    getTileUrl(cogId, cmap = null, vmin = null, vmax = null) {
        const base   = `${API_BASE}/tiles/${cogId}/{z}/{x}/{y}.png`;
        const params = new URLSearchParams();
        if (cmap) params.append('colormap', cmap);
        if (vmin !== null && vmin !== undefined) params.append('vmin', vmin);
        if (vmax !== null && vmax !== undefined) params.append('vmax', vmax);
        const query = params.toString();
        return query ? `${base}?${query}` : base;
    },

    /**
     * Get rendering metadata for a specific COG (data_type, cmap, vmin, vmax)
     */
    async getCogRenderingMetadata(cogId) {
        return this.get(`/tiles/${cogId}/metadata`);
    },
};
