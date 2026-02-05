/**
 * Map Module - Handles map initialization and layer management
 */

const DEFAULT_CENTER = [-34.0, -64.0];
const DEFAULT_ZOOM = 5;
const DEFAULT_OPACITY = 0.7;

// Available basemap options
const BASEMAPS = {
    'dark': {
        name: 'Dark',
        url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
        attribution: '© OpenStreetMap contributors, © CARTO',
        maxZoom: 18
    },
    'light': {
        name: 'Light',
        url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
        attribution: '© OpenStreetMap contributors, © CARTO',
        maxZoom: 18
    },
    'osm': {
        name: 'OpenStreetMap',
        url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    },
    'satellite': {
        name: 'Satellite',
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attribution: 'Tiles © Esri',
        maxZoom: 18
    },
    'terrain': {
        name: 'Terrain',
        url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
        attribution: 'Map data: © OpenStreetMap contributors, SRTM | Map style: © OpenTopoMap',
        maxZoom: 17
    }
};

export class MapManager {
    constructor() {
        this.map = null;
        this.baseLayer = null;
        this.radarLayers = {}; // Support multiple radar layers
        this.currentOpacity = DEFAULT_OPACITY;
        this.currentBasemap = 'dark';
    }
    
    /**
     * Get available basemaps
     */
    getBasemaps() {
        return BASEMAPS;
    }
    
    /**
     * Initialize the Leaflet map
     */
    init(containerId = 'map', basemapKey = 'dark') {
        // Create map
        this.map = L.map(containerId).setView(DEFAULT_CENTER, DEFAULT_ZOOM);
        
        // Add initial basemap
        this.setBasemap(basemapKey);
        
        return this.map;
    }
    
    /**
     * Change basemap
     */
    setBasemap(basemapKey) {
        if (!BASEMAPS[basemapKey]) {
            console.warn(`Unknown basemap: ${basemapKey}`);
            return;
        }
        
        // Remove existing base layer
        if (this.baseLayer) {
            this.map.removeLayer(this.baseLayer);
        }
        
        // Add new base layer
        const basemap = BASEMAPS[basemapKey];
        this.baseLayer = L.tileLayer(basemap.url, {
            attribution: basemap.attribution,
            maxZoom: basemap.maxZoom,
        }).addTo(this.map);
        
        this.currentBasemap = basemapKey;
    }
    
    /**
     * Set radar layer on the map (supports multiple radars)
     */
    setRadarLayer(radarCode, cogId, bounds = null, opacity = null) {
        if (!cogId) return;
        
        // Use provided opacity or current opacity
        const layerOpacity = opacity !== null ? opacity : this.currentOpacity;
        
        // Remove existing layer for this radar if it exists
        if (this.radarLayers[radarCode]) {
            this.map.removeLayer(this.radarLayers[radarCode]);
        }
        
        // Add new radar layer
        const tileUrl = `/api/v1/tiles/${cogId}/{z}/{x}/{y}.png`;
        
        this.radarLayers[radarCode] = L.tileLayer(tileUrl, {
            opacity: layerOpacity,
            maxZoom: 18,
            tms: false,
        }).addTo(this.map);
        
        // Fit to bounds if provided (only once for the first radar)
        if (bounds && bounds.lat_min && bounds.lat_max && Object.keys(this.radarLayers).length === 1) {
            this.map.fitBounds([
                [bounds.lat_min, bounds.lon_min],
                [bounds.lat_max, bounds.lon_max],
            ]);
        }
        
        return this.radarLayers[radarCode];
    }
    
    /**
     * Update radar layer opacity for all layers
     */
    setOpacity(opacity) {
        this.currentOpacity = opacity;
        Object.values(this.radarLayers).forEach(layer => {
            layer.setOpacity(opacity);
        });
    }
    
    /**
     * Get current opacity
     */
    getOpacity() {
        return this.currentOpacity;
    }
    
    /**
     * Remove specific radar layer
     */
    clearRadarLayer(radarCode = null) {
        if (radarCode) {
            // Remove specific radar layer
            if (this.radarLayers[radarCode]) {
                this.map.removeLayer(this.radarLayers[radarCode]);
                delete this.radarLayers[radarCode];
            }
        } else {
            // Remove all radar layers
            Object.values(this.radarLayers).forEach(layer => {
                this.map.removeLayer(layer);
            });
            this.radarLayers = {};
        }
    }
    
    /**
     * Get active radar codes
     */
    getActiveRadars() {
        return Object.keys(this.radarLayers);
    }
    
    /**
     * Get map instance
     */
    getMap() {
        return this.map;
    }
}
