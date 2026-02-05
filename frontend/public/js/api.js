/**
 * API Module - Handles all backend communication
 */

const API_BASE = window.location.hostname === 'localhost' 
    ? 'http://localhost:8000/api/v1'
    : '/api/v1';

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
    
    /**
     * Get latest COG for multiple radars and a product
     */
    async getLatestCogs(radarCodes, productKey) {
        const promises = radarCodes.map(radarCode => 
            this.getLatestCog(radarCode, productKey)
                .catch(err => {
                    console.warn(`Failed to get latest COG for ${radarCode}:`, err);
                    return null;
                })
        );
        
        const results = await Promise.all(promises);
        
        // Filter out failed requests and return array of {radarCode, cog}
        return results
            .map((cog, index) => ({ radarCode: radarCodes[index], cog }))
            .filter(item => item.cog !== null);
    },
    
    /**
     * Get colormap for a product
     */
    async getColormap(productKey) {
        return this.get(`/products/${productKey}/colormap`);
    },
    
    /**
     * Get tile URL for a COG
     */
    getTileUrl(cogId) {
        return `${API_BASE}/tiles/${cogId}/{z}/{x}/{y}.png`;
    },
};
