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
     * Get latest COG for a radar/product
     */
    async getLatestCog(radarCode, productKey) {
        return this.get(`/cogs/latest?radar_code=${radarCode}&product_key=${productKey}`);
    },
    
    /**
     * Get latest COGs for multiple radars and a product
     * Returns array of {radarCode, cog} objects
     */
    async getLatestCogsForRadars(radarCodes, productKey) {
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
     * Get COGs for multiple radars within a time range
     * Returns array of COG objects sorted by observation_time descending (newest first)
     */
    async getCogsForTimeRange(radarCodes, productKey, startTime, endTime, limit = 100) {
        // Build query parameters
        const params = new URLSearchParams({
            product_key: productKey,
            page_size: limit,
        });
        
        if (startTime) {
            params.append('start_time', startTime.toISOString());
        }
        
        if (endTime) {
            params.append('end_time', endTime.toISOString());
        }
        
        // Fetch COGs for each radar
        const promises = radarCodes.map(radarCode => {
            const radarParams = new URLSearchParams(params);
            radarParams.append('radar_code', radarCode);
            
            return this.get(`/cogs?${radarParams}`)
                .then(data => ({
                    radarCode,
                    cogs: data.cogs || []
                }))
                .catch(err => {
                    console.warn(`Failed to get COGs for ${radarCode}:`, err);
                    return { radarCode, cogs: [] };
                });
        });
        
        const results = await Promise.all(promises);
        
        // Merge all COGs from all radars into a single array
        const allCogs = results.flatMap(result => 
            result.cogs.map(cog => ({
                ...cog,
                radar_code: result.radarCode
            }))
        );
        
        // Sort by observation_time descending (newest first)
        allCogs.sort((a, b) => 
            new Date(b.observation_time) - new Date(a.observation_time)
        );
        
        return allCogs;
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
