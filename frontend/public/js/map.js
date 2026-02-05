/**
 * Map Module - Handles map initialization and layer management
 */

const DEFAULT_CENTER = [-34.0, -64.0];
const DEFAULT_ZOOM = 5;
const DEFAULT_OPACITY = 0.7;

export class MapManager {
    constructor() {
        this.map = null;
        this.radarLayer = null;
        this.currentOpacity = DEFAULT_OPACITY;
    }
    
    /**
     * Initialize the Leaflet map
     */
    init(containerId = 'map') {
        // Create map
        this.map = L.map(containerId).setView(DEFAULT_CENTER, DEFAULT_ZOOM);
        
        // Add dark base layer (matches webmet.ohmc.ar aesthetic)
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '© OpenStreetMap contributors, © CARTO',
            maxZoom: 18,
        }).addTo(this.map);
        
        return this.map;
    }
    
    /**
     * Set radar layer on the map
     */
    setRadarLayer(cogId, bounds = null, opacity = null) {
        // Remove existing radar layer
        this.clearRadarLayer();
        
        if (!cogId) return;
        
        // Use provided opacity or current opacity
        const layerOpacity = opacity !== null ? opacity : this.currentOpacity;
        
        // Add new radar layer
        const tileUrl = `/api/v1/tiles/${cogId}/{z}/{x}/{y}.png`;
        
        this.radarLayer = L.tileLayer(tileUrl, {
            opacity: layerOpacity,
            maxZoom: 18,
            tms: false,
        }).addTo(this.map);
        
        // Fit to bounds if provided (only once)
        if (bounds && bounds.lat_min && bounds.lat_max) {
            this.map.fitBounds([
                [bounds.lat_min, bounds.lon_min],
                [bounds.lat_max, bounds.lon_max],
            ]);
        }
        
        return this.radarLayer;
    }
    
    /**
     * Update radar layer opacity
     */
    setOpacity(opacity) {
        this.currentOpacity = opacity;
        if (this.radarLayer) {
            this.radarLayer.setOpacity(opacity);
        }
    }
    
    /**
     * Get current opacity
     */
    getOpacity() {
        return this.currentOpacity;
    }
    
    /**
     * Remove radar layer
     */
    clearRadarLayer() {
        if (this.radarLayer) {
            this.map.removeLayer(this.radarLayer);
            this.radarLayer = null;
        }
    }
    
    /**
     * Get map instance
     */
    getMap() {
        return this.map;
    }
}
