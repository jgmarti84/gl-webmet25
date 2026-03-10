/**
 * COG Browser API Module
 * Handles all API calls for the COG Browser page
 */

const API_BASE = window.location.hostname === 'localhost' 
    ? 'http://localhost:8000/api/v1'
    : '/api/v1';

export const cogBrowserApi = {
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
     */
    async getRadars() {
        const data = await this.get('/radars');
        return data.radars || [];
    },
    
    /**
     * Get all products
     */
    async getProducts() {
        const data = await this.get('/products');
        return data.products || [];
    },
    
    /**
     * Get COGs with filters
     * Returns array of COG objects
     */
    async getCogs(radarCode, productKey) {
        const params = new URLSearchParams({
            radar_code: radarCode,
            product_key: productKey,
            page_size: 100,  // Get more COGs
        });
        const data = await this.get(`/cogs?${params}`);
        return data.cogs || [];
    },
    
    /**
     * Get colormap info for a product
     */
    async getColormapInfo(productKey, colormapName = null) {
        const params = new URLSearchParams();
        if (colormapName) {
            params.append('colormap', colormapName);
        }
        const query = params.toString() ? `?${params}` : '';
        return this.get(`/colormap/info/${productKey}${query}`);
    },
    
    /**
     * Get available colormaps for all products
     */
    async getColormapOptions() {
        return this.get('/colormap/options');
    },
    
    /**
     * Get tile URL for a COG
     * Optionally include colormap parameter
     */
    getTileUrl(cogId, colormapName = null) {
        const baseUrl = `${API_BASE}/tiles/${cogId}/{z}/{x}/{y}.png`;
        if (colormapName) {
            return `${baseUrl}?colormap=${encodeURIComponent(colormapName)}`;
        }
        return baseUrl;
    },
};
