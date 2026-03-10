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
        // Pre-cached layers for smooth animation
        this.cachedFrameLayers = []; // Array of {radarCode: L.tileLayer}
        this.currentCachedFrameIndex = -1;
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
     * Pre-create all tile layers for animation frames so tiles are loaded in
     * the background and frame transitions don't have to wait for network requests.
     *
     * @param {Array}    groupedFrames - Array of {timestamp, cogsByRadar: {radarCode: cog}}
     * @param {Function} onLayerLoaded - Optional callback fired each time a layer finishes loading its tiles
     */
    preloadFrames(groupedFrames, onLayerLoaded = null) {
        this.clearCachedFrames();

        this.cachedFrameLayers = groupedFrames.map((frame) => {
            const layerMap = {};
            Object.entries(frame.cogsByRadar).forEach(([radarCode, cog]) => {
                const tileUrl = `/api/v1/tiles/${cog.id}/{z}/{x}/{y}.png`;
                const layer = L.tileLayer(tileUrl, {
                    opacity: 0, // hidden until this frame is active
                    maxZoom: 18,
                    tms: false,
                    keepBuffer: 4,
                });
                if (onLayerLoaded) {
                    layer.once('load', onLayerLoaded);
                }
                layer.addTo(this.map);
                layerMap[radarCode] = layer;
            });
            return layerMap;
        });
    }

    /**
     * Show a specific pre-cached frame, hiding the previous one.
     * All radars for that frame are made visible simultaneously.
     *
     * @param {number} frameIndex
     */
    showCachedFrame(frameIndex) {
        const opacity = this.currentOpacity;

        // Hide previous frame's layers
        if (
            this.currentCachedFrameIndex >= 0 &&
            this.cachedFrameLayers[this.currentCachedFrameIndex]
        ) {
            Object.values(this.cachedFrameLayers[this.currentCachedFrameIndex]).forEach(layer => {
                layer.setOpacity(0);
            });
        }

        // Show new frame's layers
        if (frameIndex >= 0 && this.cachedFrameLayers[frameIndex]) {
            Object.values(this.cachedFrameLayers[frameIndex]).forEach(layer => {
                layer.setOpacity(opacity);
            });
        }

        this.currentCachedFrameIndex = frameIndex;
    }

    /**
     * Remove all pre-cached animation layers from the map and reset state.
     */
    clearCachedFrames() {
        this.cachedFrameLayers.forEach(frameLayerMap => {
            if (frameLayerMap) {
                Object.values(frameLayerMap).forEach(layer => {
                    if (this.map && this.map.hasLayer(layer)) {
                        this.map.removeLayer(layer);
                    }
                });
            }
        });
        this.cachedFrameLayers = [];
        this.currentCachedFrameIndex = -1;
    }

    /**
     * Update radar layer opacity for all layers
     */
    setOpacity(opacity) {
        this.currentOpacity = opacity;
        // Update "latest" mode layers
        Object.values(this.radarLayers).forEach(layer => {
            layer.setOpacity(opacity);
        });
        // Update currently-visible cached frame layers
        if (
            this.currentCachedFrameIndex >= 0 &&
            this.cachedFrameLayers[this.currentCachedFrameIndex]
        ) {
            Object.values(this.cachedFrameLayers[this.currentCachedFrameIndex]).forEach(layer => {
                layer.setOpacity(opacity);
            });
        }
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
