/**
 * Map Module - Handles map initialization and layer management
 */

const DEFAULT_CENTER = [-34.0, -64.0];
const DEFAULT_ZOOM = 5;
const DEFAULT_OPACITY = 0.7;

// Tile layer z-index values – ensures radar always renders above basemap
const ZINDEX_BASEMAP = 1;
const ZINDEX_RADAR   = 2;

// Frame pre-loading tuning
const PRELOAD_BATCH_SIZE  = 20;  // was 5
const PRELOAD_BATCH_DELAY = 50;  // was 100ms

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
        url: '/osm-tiles/{z}/{x}/{y}.png',
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
        // Background preload state (used for colormap-change UX)
        this._cancelBackgroundPreload = null;
        // True while the initial batch preload started by preloadFrames() is still running
        this._preloadInProgress = false;
        // Coverage mask state — SVG element appended directly to the map
        // container (outside Leaflet panes) to avoid pane CSS transforms.
        this._coverageSvgEl = null;
        this._coverageOpacity = parseFloat(
            localStorage.getItem('webmet25_coverage_opacity')
        ) || 0.4;
        // Map of radarCode → { lat, lng, radius_m }
        this._activeRadarCoverages = new Map();
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

        // Radar coverage mask pane — kept for z-index ordering. The SVG is
        // appended directly to the map container (not inside this pane) so
        // Leaflet's pan/zoom CSS transforms never misalign the circles.
        this.map.createPane('coverageMaskPane');
        this.map.getPane('coverageMaskPane').style.zIndex = 300;
        this.map.getPane('coverageMaskPane').style.pointerEvents = 'none';

        this._initCoverageMask();

        // Redraw circles on every pan, zoom, and resize.
        this.map.on('move zoom moveend zoomend resize', () => {
            this._updateCoverageMask();
        });
        
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
        
        // Add new base layer (zIndex: ZINDEX_BASEMAP keeps it below radar layers)
        const basemap = BASEMAPS[basemapKey];
        this.baseLayer = L.tileLayer(basemap.url, {
            attribution: basemap.attribution,
            maxZoom: basemap.maxZoom,
            zIndex: ZINDEX_BASEMAP,
            crossOrigin: 'anonymous', // required for canvas snapshot (Change 3)
        }).addTo(this.map);
        
        this.currentBasemap = basemapKey;
    }
    
    /**
     * Set radar layer on the map (supports multiple radars)
     */
    setRadarLayer(radarCode, cogId, bounds = null, opacity = null, tileParams = {}) {
        if (!cogId) return;
        
        // Use provided opacity or current opacity
        const layerOpacity = opacity !== null ? opacity : this.currentOpacity;
        
        // Remove existing layer for this radar if it exists
        if (this.radarLayers[radarCode]) {
            this.map.removeLayer(this.radarLayers[radarCode]);
        }
        
        // Build tile URL with optional colormap/vmin/vmax params
        const queryParams = new URLSearchParams();
        if (tileParams.cmap) queryParams.append('colormap', tileParams.cmap);
        if (tileParams.vmin !== null && tileParams.vmin !== undefined) queryParams.append('vmin', tileParams.vmin);
        if (tileParams.vmax !== null && tileParams.vmax !== undefined) queryParams.append('vmax', tileParams.vmax);
        const queryStr = queryParams.toString();
        const tileUrl = queryStr
            ? `/api/v1/tiles/${cogId}/{z}/{x}/{y}.png?${queryStr}`
            : `/api/v1/tiles/${cogId}/{z}/{x}/{y}.png`;
        
        this.radarLayers[radarCode] = L.tileLayer(tileUrl, {
            opacity: layerOpacity,
            maxZoom: 18,
            tms: false,
            zIndex: ZINDEX_RADAR,
            crossOrigin: 'anonymous', // required for canvas snapshot (Change 3)
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
     * Frames are loaded in small batches with a brief delay between batches to
     * avoid saturating the server/browser with simultaneous tile requests.
     *
     * @param {Array}    groupedFrames - Array of {timestamp, cogsByRadar: {radarCode: cog}}
     * @param {Function} onLayerLoaded - Optional callback fired each time a layer finishes loading its tiles
     * @param {Object}   tileParams    - Optional {cmap, vmin, vmax} for tile URL
     */
    preloadFrames(groupedFrames, onLayerLoaded = null, tileParams = {}) {
        this._preloadInProgress = true;
        this.clearCachedFrames();

        // Pre-size the array so indices stay stable while batches fill in
        this.cachedFrameLayers = new Array(groupedFrames.length).fill(null);

        const BATCH_SIZE  = PRELOAD_BATCH_SIZE;
        const BATCH_DELAY = PRELOAD_BATCH_DELAY;

        const loadBatch = (startIdx) => {
            if (startIdx >= groupedFrames.length) return;
            const endIdx = Math.min(startIdx + BATCH_SIZE, groupedFrames.length);

            for (let i = startIdx; i < endIdx; i++) {
                const frame = groupedFrames[i];
                const layerMap = {};
                Object.entries(frame.cogsByRadar).forEach(([radarCode, cog]) => {
                    const queryParams = new URLSearchParams();
                    if (tileParams.cmap) queryParams.append('colormap', tileParams.cmap);
                    if (tileParams.vmin !== null && tileParams.vmin !== undefined) queryParams.append('vmin', tileParams.vmin);
                    if (tileParams.vmax !== null && tileParams.vmax !== undefined) queryParams.append('vmax', tileParams.vmax);
                    const queryStr = queryParams.toString();
                    const tileUrl = queryStr
                        ? `/api/v1/tiles/${cog.id}/{z}/{x}/{y}.png?${queryStr}`
                        : `/api/v1/tiles/${cog.id}/{z}/{x}/{y}.png`;
                    const layer = L.tileLayer(tileUrl, {
                        opacity: 0, // hidden until this frame is active
                        maxZoom: 18,
                        tms: false,
                        keepBuffer: 2,
                        zIndex: ZINDEX_RADAR,
                        crossOrigin: 'anonymous', // required for canvas snapshot (Change 3)
                    });
                    if (onLayerLoaded) {
                        layer.once('load', onLayerLoaded);
                    }
                    layer.addTo(this.map);
                    layerMap[radarCode] = layer;
                });
                this.cachedFrameLayers[i] = layerMap;
            }

            if (endIdx < groupedFrames.length) {
                setTimeout(() => loadBatch(endIdx), BATCH_DELAY);
            } else {
                this._preloadInProgress = false;
            }
        };

        loadBatch(0);
    }

    /**
     * Pre-load new frame layers in the background WITHOUT clearing the current
     * visible layers.  Used for colormap-change UX: the current animation
     * keeps playing while the new tiles are fetched, then `commitPendingFrames`
     * is called to do a seamless swap.
     *
     * Cancels any previous background preload that has not yet completed.
     *
     * @param {Array}    groupedFrames - Same structure as accepted by preloadFrames
     * @param {Function} onProgress   - Called with (loadedCount, totalLayers) on each layer load
     * @param {Function} onComplete   - Called with (pendingLayers) when all layers have loaded
     * @param {Object}   tileParams   - Optional {cmap, vmin, vmax} for tile URL
     * @returns {Function} cancel     - Call to abort the background preload
     */
    preloadFramesBackground(groupedFrames, onProgress, onComplete, tileParams = {}) {
        // Cancel any previous in-flight background preload
        if (this._cancelBackgroundPreload) {
            this._cancelBackgroundPreload();
            this._cancelBackgroundPreload = null;
        }

        if (!groupedFrames.length) {
            if (onComplete) onComplete([]);
            return () => {};
        }

        let cancelled = false;
        const pendingLayers = new Array(groupedFrames.length).fill(null);

        const totalLayers = groupedFrames.reduce(
            (sum, f) => sum + Object.keys(f.cogsByRadar).length, 0
        );

        if (totalLayers === 0) {
            if (onComplete) setTimeout(() => onComplete(pendingLayers), 0);
            return () => {};
        }

        let loadedCount = 0;

        const checkComplete = () => {
            if (loadedCount >= totalLayers && onComplete && !cancelled) {
                onComplete(pendingLayers);
            }
        };

        const loadBatch = (startIdx) => {
            if (cancelled || startIdx >= groupedFrames.length) return;
            const endIdx = Math.min(startIdx + PRELOAD_BATCH_SIZE, groupedFrames.length);

            for (let i = startIdx; i < endIdx; i++) {
                if (cancelled) return;
                const frame = groupedFrames[i];
                const layerMap = {};
                Object.entries(frame.cogsByRadar).forEach(([radarCode, cog]) => {
                    const queryParams = new URLSearchParams();
                    if (tileParams.cmap) queryParams.append('colormap', tileParams.cmap);
                    if (tileParams.vmin !== null && tileParams.vmin !== undefined) queryParams.append('vmin', tileParams.vmin);
                    if (tileParams.vmax !== null && tileParams.vmax !== undefined) queryParams.append('vmax', tileParams.vmax);
                    const queryStr = queryParams.toString();
                    const tileUrl = queryStr
                        ? `/api/v1/tiles/${cog.id}/{z}/{x}/{y}.png?${queryStr}`
                        : `/api/v1/tiles/${cog.id}/{z}/{x}/{y}.png`;
                    const layer = L.tileLayer(tileUrl, {
                        opacity: 0,
                        maxZoom: 18,
                        tms: false,
                        keepBuffer: 2,
                        zIndex: ZINDEX_RADAR,
                        crossOrigin: 'anonymous', // required for canvas snapshot (Change 3)
                    });
                    layer.once('load', () => {
                        if (cancelled) return;
                        loadedCount++;
                        if (onProgress) onProgress(loadedCount, totalLayers);
                        checkComplete();
                    });
                    layer.addTo(this.map);
                    layerMap[radarCode] = layer;
                });
                pendingLayers[i] = layerMap;
            }

            if (endIdx < groupedFrames.length) {
                setTimeout(() => loadBatch(endIdx), PRELOAD_BATCH_DELAY);
            }
        };

        loadBatch(0);

        const cancel = () => {
            cancelled = true;
            pendingLayers.forEach(frameLayerMap => {
                if (frameLayerMap) {
                    Object.values(frameLayerMap).forEach(layer => {
                        if (this.map && this.map.hasLayer(layer)) {
                            this.map.removeLayer(layer);
                        }
                    });
                }
            });
        };

        this._cancelBackgroundPreload = cancel;
        return cancel;
    }

    /**
     * Swap the current cached frame layers for the pending layers produced by
     * `preloadFramesBackground`.  The old layers are removed from the map.
     * The caller is responsible for showing the correct frame afterwards
     * (e.g. via `showCachedFrame`).
     *
     * @param {Array} pendingLayers - Array produced by preloadFramesBackground
     */
    commitPendingFrames(pendingLayers) {
        this._cancelBackgroundPreload = null;
        // Clear old layers; resets currentCachedFrameIndex to -1
        this.clearCachedFrames();
        this.cachedFrameLayers = pendingLayers;
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
        this._preloadInProgress = false;
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
     * Create a tile layer for the given COG, add it to the map at opacity 0,
     * and return it.  Used for incremental radar add and live window updates.
     *
     * @param {number|string} cogId      - COG ID
     * @param {Object}        tileParams - Optional {cmap, vmin, vmax}
     * @returns {L.TileLayer}
     */
    createHiddenTileLayer(cogId, tileParams = {}) {
        const queryParams = new URLSearchParams();
        if (tileParams.cmap) queryParams.append('colormap', tileParams.cmap);
        if (tileParams.vmin !== null && tileParams.vmin !== undefined) queryParams.append('vmin', tileParams.vmin);
        if (tileParams.vmax !== null && tileParams.vmax !== undefined) queryParams.append('vmax', tileParams.vmax);
        const queryStr = queryParams.toString();
        const tileUrl = queryStr
            ? `/api/v1/tiles/${cogId}/{z}/{x}/{y}.png?${queryStr}`
            : `/api/v1/tiles/${cogId}/{z}/{x}/{y}.png`;
        const layer = L.tileLayer(tileUrl, {
            opacity: 0,
            maxZoom: 18,
            tms: false,
            keepBuffer: 2,
            zIndex: ZINDEX_RADAR,
            crossOrigin: 'anonymous', // required for canvas snapshot (Change 3)
        });
        layer.addTo(this.map);
        return layer;
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
    
    // =========================================================================
    // Coverage mask helpers
    // =========================================================================

    _initCoverageMask() {
        const svgNS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(svgNS, 'svg');
        svg.setAttribute('xmlns', svgNS);
        const mapSize = this.map.getSize();
        svg.setAttribute('width', String(mapSize.x));
        svg.setAttribute('height', String(mapSize.y));
        svg.style.cssText = [
            'position:absolute',
            'top:0',
            'left:0',
            'pointer-events:none',
            'z-index:650',
        ].join(';');

        const defs = document.createElementNS(svgNS, 'defs');
        const mask = document.createElementNS(svgNS, 'mask');
        mask.setAttribute('id', 'radar-coverage-mask');
        mask.setAttribute('maskUnits', 'userSpaceOnUse');
        mask.setAttribute('maskContentUnits', 'userSpaceOnUse');
        mask.setAttribute('x', '-9999');
        mask.setAttribute('y', '-9999');
        mask.setAttribute('width', '99999');
        mask.setAttribute('height', '99999');

        const maskBase = document.createElementNS(svgNS, 'rect');
        maskBase.setAttribute('x', '-9999');
        maskBase.setAttribute('y', '-9999');
        maskBase.setAttribute('width', '99999');
        maskBase.setAttribute('height', '99999');
        maskBase.setAttribute('fill', 'white');
        mask.appendChild(maskBase);
        defs.appendChild(mask);
        svg.appendChild(defs);

        const overlay = document.createElementNS(svgNS, 'rect');
        overlay.setAttribute('id', 'radar-coverage-overlay-rect');
        overlay.setAttribute('x', '-9999');
        overlay.setAttribute('y', '-9999');
        overlay.setAttribute('width', '99999');
        overlay.setAttribute('height', '99999');
        overlay.setAttribute('fill', '#000000');
        overlay.setAttribute('opacity', String(this._coverageOpacity));
        overlay.setAttribute('mask', 'url(#radar-coverage-mask)');
        svg.appendChild(overlay);

        this._coverageSvgEl = svg;

        const mapContainer = this.map.getContainer();
        if (getComputedStyle(mapContainer).position === 'static') {
            mapContainer.style.position = 'relative';
        }
        mapContainer.appendChild(svg);
    }

    _updateCoverageMask() {
        if (!this._coverageSvgEl) return;

        const mapSize = this.map.getSize();
        this._coverageSvgEl.setAttribute('width', String(mapSize.x));
        this._coverageSvgEl.setAttribute('height', String(mapSize.y));

        const svgNS = 'http://www.w3.org/2000/svg';
        const mask = this._coverageSvgEl.querySelector('#radar-coverage-mask');
        if (!mask) return;

        mask.querySelectorAll('circle').forEach(c => c.remove());

        for (const [, coverage] of this._activeRadarCoverages) {
            const point = this.map.latLngToContainerPoint(
                L.latLng(coverage.lat, coverage.lng)
            );
            const radiusPx = this._metersToPixels(coverage.lat, coverage.radius_m);

            const circle = document.createElementNS(svgNS, 'circle');
            circle.setAttribute('cx', String(point.x));
            circle.setAttribute('cy', String(point.y));
            circle.setAttribute('r', String(radiusPx));
            circle.setAttribute('fill', 'black');
            mask.appendChild(circle);
        }

        const overlayRect = this._coverageSvgEl.querySelector('#radar-coverage-overlay-rect');
        if (overlayRect) {
            overlayRect.setAttribute('opacity', String(this._coverageOpacity));
        }
    }

    _metersToPixels(lat, radiusMeters) {
        const metersPerDegLng = 111320 * Math.cos(lat * Math.PI / 180);
        const offsetLng = radiusMeters / metersPerDegLng;
        const centerPx = this.map.latLngToContainerPoint(L.latLng(lat, 0));
        const edgePx   = this.map.latLngToContainerPoint(L.latLng(lat, offsetLng));
        return Math.abs(edgePx.x - centerPx.x);
    }

    addRadarCoverage(radarCode, lat, lng, radius_m) {
        this._activeRadarCoverages.set(radarCode, { lat, lng, radius_m });
        this._updateCoverageMask();
    }

    removeRadarCoverage(radarCode) {
        this._activeRadarCoverages.delete(radarCode);
        this._updateCoverageMask();
    }

    setCoverageOpacity(opacity) {
        this._coverageOpacity = opacity;
        this._updateCoverageMask();
    }

    /**
     * Get map instance
     */
    getMap() {
        return this.map;
    }
}
