/**
 * map-v2.js — Canvas-based MapManager using L.imageOverlay
 *
 * Instead of creating ~10 tile layers per COG (as v1 does with L.tileLayer),
 * this manager fetches each COG as a single georeferenced PNG from the
 * /api/v1/frames/{id}/image.png endpoint and positions it with L.imageOverlay.
 *
 * This reduces ~1800 HTTP requests per session to ~180 (10× reduction).
 *
 * Key design decisions
 * --------------------
 * - All overlay keys use the format `${radarCode}__${productKey}` (double
 *   underscore) so the structure is multi-field-ready from day one.
 * - L.imageOverlay instances are created once in loadFrames() and reused
 *   throughout the session. No DOM creation during animation playback.
 * - Image pixels are fetched via fetch() (not new Image(src)) so that the
 *   X-Bbox-* response headers can be read.
 * - Object URLs are tracked and revoked when frames are removed to prevent
 *   memory leaks.
 * - The _frameImages array is kept in sync with app.js's state.cogs array.
 *   When app-v2.js inserts/removes frames from state.cogs it must call
 *   addFrame()/removeFrame() with the same index so MapManager stays aligned.
 */

const DEFAULT_CENTER = [-34.0, -64.0];
const DEFAULT_ZOOM   = 5;
const DEFAULT_OPACITY = 0.7;

// A 1×1 transparent PNG used as the initial source for overlays before the
// first real image is loaded.  We need an actual URL (not '') because some
// Leaflet versions emit console warnings on empty src.
const BLANK_PNG =
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAA' +
    'DUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';

// Available basemap options — identical to v1
const BASEMAPS = {
    'dark': {
        name:        'Dark',
        url:         'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
        attribution: '© OpenStreetMap contributors, © CARTO',
        maxZoom:     18,
    },
    'light': {
        name:        'Light',
        url:         'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
        attribution: '© OpenStreetMap contributors, © CARTO',
        maxZoom:     18,
    },
    'osm': {
        name:        'OpenStreetMap',
        url:         '/osm-tiles/{z}/{x}/{y}.png',
        attribution: '© OpenStreetMap contributors',
        maxZoom:     19,
    },
    'satellite': {
        name:        'Satellite',
        url:         'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attribution: 'Tiles © Esri',
        maxZoom:     18,
    },
    'terrain': {
        name:        'Terrain',
        url:         'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
        attribution: 'Map data: © OpenStreetMap contributors, SRTM | Map style: © OpenTopoMap',
        maxZoom:     17,
    },
};

export class MapManager {
    /**
     * @param {string} mapElementId - ID of the DOM element to render the map into.
     */
    constructor(mapElementId = 'map') {
        this._mapElementId  = mapElementId;
        this._map           = null;
        this._baseLayer     = null;
        this._currentBasemap = 'dark';
        this._currentOpacity = DEFAULT_OPACITY;

        // -----------------------------------------------------------------------
        // Frame image storage.
        //
        // _frameImages is an Array that mirrors app-v2.js's state.cogs array.
        // Each element is a Map<overlayKey, ImageEntry> where:
        //   overlayKey = `${radarCode}__${productKey}`
        //   ImageEntry = { img: HTMLImageElement, loaded: boolean,
        //                  url: string, objectUrl: string }
        //
        // _frameImages[i] corresponds exactly to state.cogs[i].
        // addFrame() splices into this array; removeFrame() splices out.
        // -----------------------------------------------------------------------
        this._frameImages = [];

        // One persistent L.imageOverlay per (radarCode, productKey) combination.
        // Created when the bbox for a key is first seen; reused forever.
        this._overlays = new Map(); // overlayKey → L.imageOverlay

        // Bbox per overlay key — populated from X-Bbox-* response headers.
        this._bboxes = new Map(); // overlayKey → {west, south, east, north}

        // Index of the frame currently shown (-1 = none shown yet).
        this._currentFrameIndex = -1;

        // True while loadFrames() / updateParams() is in progress.
        // app-v2.js checks this before attempting incremental updates.
        this._loadInProgress = false;

        // Radar coverage circles (L.circle), keyed by radar code.
        this._coverageCircles = {};
    }

    // =========================================================================
    // Initialisation
    // =========================================================================

    /**
     * Initialise the Leaflet map.  Called once on page load.
     * @returns {L.Map}
     */
    init() {
        this._map = L.map(this._mapElementId).setView(DEFAULT_CENTER, DEFAULT_ZOOM);

        // Create coverage pane below tile pane but above the basemap.
        // Same z-index design as v1 map.js.
        this._map.createPane('coveragePane');
        this._map.getPane('coveragePane').style.zIndex = 350;

        this.setBasemap(this._currentBasemap);
        return this._map;
    }

    // =========================================================================
    // Basemap helpers — identical to v1
    // =========================================================================

    getBasemaps() { return BASEMAPS; }

    setBasemap(basemapKey) {
        if (!BASEMAPS[basemapKey]) {
            console.warn(`Unknown basemap: ${basemapKey}`);
            return;
        }
        if (this._baseLayer) {
            this._map.removeLayer(this._baseLayer);
        }
        const basemap = BASEMAPS[basemapKey];
        this._baseLayer = L.tileLayer(basemap.url, {
            attribution: basemap.attribution,
            maxZoom:     basemap.maxZoom,
            zIndex:      1,
            crossOrigin: 'anonymous',
        }).addTo(this._map);
        this._currentBasemap = basemapKey;
    }

    // =========================================================================
    // Opacity helpers
    // =========================================================================

    getOpacity() { return this._currentOpacity; }

    /**
     * Update overlay opacity.  Affects the currently visible overlays immediately.
     * @param {number} opacity
     */
    setOpacity(opacity) {
        this._currentOpacity = opacity;
        // Update all currently visible overlays
        if (this._currentFrameIndex >= 0) {
            const frameMap = this._frameImages[this._currentFrameIndex];
            if (frameMap) {
                frameMap.forEach((entry, key) => {
                    const overlay = this._overlays.get(key);
                    if (overlay && entry.loaded) {
                        overlay.setOpacity(opacity);
                    }
                });
            }
        }
    }

    // =========================================================================
    // Internal helpers
    // =========================================================================

    /**
     * Build the /frames/ URL for a given COG.
     * @param {number} cogId
     * @param {string} productKey  (unused in URL but kept for future multi-field support)
     * @param {Object} params      {colormap, vmin, vmax}
     * @returns {string}
     */
    _buildFrameUrl(cogId, productKey, params = {}) {
        const base = `/api/v1/frames/${cogId}/image.png`;
        const qs   = new URLSearchParams();
        if (params.colormap)                            qs.set('colormap', params.colormap);
        if (params.vmin !== undefined && params.vmin !== null) qs.set('vmin', params.vmin);
        if (params.vmax !== undefined && params.vmax !== null) qs.set('vmax', params.vmax);
        const str = qs.toString();
        return str ? `${base}?${str}` : base;
    }

    /**
     * Fetch a frame image from the /frames/ endpoint using the Fetch API so
     * that X-Bbox-* response headers are readable.
     *
     * Returns { img: HTMLImageElement, bbox, objectUrl } on success.
     * Throws on HTTP error or network failure.
     */
    async _loadImage(url) {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status} for ${url}`);
        }

        // Read bbox from response headers
        const bbox = {
            west:  parseFloat(response.headers.get('X-Bbox-West')),
            south: parseFloat(response.headers.get('X-Bbox-South')),
            east:  parseFloat(response.headers.get('X-Bbox-East')),
            north: parseFloat(response.headers.get('X-Bbox-North')),
        };

        // Convert PNG bytes to object URL
        const blob      = await response.blob();
        const objectUrl = URL.createObjectURL(blob);

        const img = new Image();
        await new Promise((resolve, reject) => {
            img.onload  = resolve;
            img.onerror = reject;
            img.src     = objectUrl;
        });

        return { img, bbox, objectUrl };
    }

    /**
     * Create one persistent L.imageOverlay for the given key.
     * Starts invisible (opacity 0) with a blank PNG placeholder.
     *
     * @param {string} key  `${radarCode}__${productKey}`
     * @param {Object} bbox {west, south, east, north}
     */
    _createOverlay(key, bbox) {
        const bounds = [
            [bbox.south, bbox.west],
            [bbox.north, bbox.east],
        ];
        const overlay = L.imageOverlay(BLANK_PNG, bounds, {
            opacity:     0,
            interactive: false,
            zIndex:      200,
        });
        overlay.addTo(this._map);
        this._overlays.set(key, overlay);
    }

    /**
     * Revoke all object URLs for a given frame map and clear the map.
     * @param {Map} frameMap
     */
    _revokeFrameMap(frameMap) {
        if (!frameMap) return;
        frameMap.forEach(entry => {
            if (entry.objectUrl) URL.revokeObjectURL(entry.objectUrl);
        });
        frameMap.clear();
    }

    /**
     * Remove all overlays from the map and reset internal state.
     */
    _clearAllOverlays() {
        this._overlays.forEach(overlay => {
            if (this._map && this._map.hasLayer(overlay)) {
                this._map.removeLayer(overlay);
            }
        });
        this._overlays.clear();
        this._bboxes.clear();
        this._frameImages.forEach(frameMap => this._revokeFrameMap(frameMap));
        this._frameImages = [];
        this._currentFrameIndex = -1;
    }

    // =========================================================================
    // Core public API
    // =========================================================================

    /**
     * Load all frame images for all active radars and the current field.
     *
     * @param {Map<number, Map<string, Object>>} cogsByFrame
     *   frameIndex → (radarCode → cogObject)
     * @param {string}   productKey  e.g. 'DBZH'
     * @param {Object}   params      {colormap, vmin, vmax}
     * @param {Function} onProgress  (loaded, total) → void
     * @returns {Promise<void>}
     */
    async loadFrames(cogsByFrame, productKey, params = {}, onProgress = null) {
        this._loadInProgress = true;
        try {
            this._clearAllOverlays();

            // Pre-size _frameImages to match the number of frames
            const maxIndex = cogsByFrame.size > 0 ? Math.max(...cogsByFrame.keys()) : -1;
            if (maxIndex >= 0) {
                this._frameImages = new Array(maxIndex + 1).fill(null).map(() => new Map());
            }

            let total  = 0;
            cogsByFrame.forEach(radarMap => { total += radarMap.size; });
            let loaded = 0;

            const loadPromises = [];

            cogsByFrame.forEach((radarMap, frameIndex) => {
                radarMap.forEach((cogObj, radarCode) => {
                    const key = `${radarCode}__${productKey}`;
                    const url = this._buildFrameUrl(cogObj.id, productKey, params);

                    const promise = this._loadImage(url)
                        .then(({ img, bbox, objectUrl }) => {
                            // Ensure slot exists (should be pre-allocated above)
                            if (!this._frameImages[frameIndex]) {
                                this._frameImages[frameIndex] = new Map();
                            }
                            this._frameImages[frameIndex].set(key, {
                                img, loaded: true, url, objectUrl,
                            });
                            // Create the overlay the first time we see this key
                            if (!this._bboxes.has(key)) {
                                this._bboxes.set(key, bbox);
                                this._createOverlay(key, bbox);
                            }
                            loaded++;
                            if (onProgress) onProgress(loaded, total);
                        })
                        .catch(err => {
                            console.warn(`loadFrames: failed frame ${frameIndex} ${key}:`, err);
                            loaded++;
                            if (onProgress) onProgress(loaded, total);
                        });

                    loadPromises.push(promise);
                });
            });

            await Promise.all(loadPromises);
        } finally {
            this._loadInProgress = false;
        }
    }

    /**
     * Show a specific frame.  Called by AnimationController on each tick.
     * This is the animation hot path — no fetches, no DOM creation.
     *
     * @param {number}   frameIndex
     * @param {string[]} radarCodes   Currently active radar codes
     * @param {string}   productKey   Current active product key
     */
    showFrame(frameIndex, radarCodes, productKey) {
        // Hide all overlays
        this._overlays.forEach(overlay => overlay.setOpacity(0));

        const frameMap = this._frameImages[frameIndex];
        if (!frameMap) return;

        radarCodes.forEach(radarCode => {
            const key     = `${radarCode}__${productKey}`;
            const entry   = frameMap.get(key);
            const overlay = this._overlays.get(key);
            if (entry && overlay && entry.loaded) {
                overlay.setUrl(entry.img.src);
                overlay.setOpacity(this._currentOpacity);
            }
        });

        this._currentFrameIndex = frameIndex;
    }

    /**
     * Add a single new frame — used by live refresh incremental update.
     * Splices a new slot into _frameImages at the given index (shifting
     * existing frames forward) then loads the image asynchronously.
     *
     * Does NOT interrupt animation — the rAF loop continues while the
     * image loads in the background.
     *
     * @param {number} frameIndex  Position in the (already-mutated) state.cogs
     * @param {string} radarCode
     * @param {string} productKey
     * @param {Object} cogObject   {id, ...}
     * @param {Object} params      {colormap, vmin, vmax}
     * @returns {Promise<void>}
     */
    async addFrame(frameIndex, radarCode, productKey, cogObject, params = {}) {
        // Insert a new empty slot at frameIndex, shifting later entries
        this._frameImages.splice(frameIndex, 0, new Map());

        // Adjust the visible-frame pointer if it was at or after the insertion
        if (this._currentFrameIndex >= frameIndex) {
            this._currentFrameIndex++;
        }

        const key = `${radarCode}__${productKey}`;
        const url = this._buildFrameUrl(cogObject.id, productKey, params);

        try {
            const { img, bbox, objectUrl } = await this._loadImage(url);
            // After the await, frameIndex may have shifted due to concurrent
            // operations.  However, addFrame callers (live refresh) are
            // sequential in app-v2.js so this is safe.
            const frameMap = this._frameImages[frameIndex];
            if (frameMap) {
                frameMap.set(key, { img, loaded: true, url, objectUrl });
            }
            if (!this._bboxes.has(key)) {
                this._bboxes.set(key, bbox);
                this._createOverlay(key, bbox);
            }
        } catch (err) {
            console.warn(`addFrame: failed to load ${radarCode}/${productKey}:`, err);
        }
    }

    /**
     * Add a radar to an existing frame (merge path for live refresh).
     * Unlike addFrame, this does NOT splice; it just adds a key to an
     * existing frame slot.
     *
     * @param {number} frameIndex  Existing frame index in _frameImages
     * @param {string} radarCode
     * @param {string} productKey
     * @param {Object} cogObject
     * @param {Object} params
     * @returns {Promise<void>}
     */
    async addRadarToFrame(frameIndex, radarCode, productKey, cogObject, params = {}) {
        if (!this._frameImages[frameIndex]) {
            this._frameImages[frameIndex] = new Map();
        }
        const key = `${radarCode}__${productKey}`;
        const url = this._buildFrameUrl(cogObject.id, productKey, params);

        try {
            const { img, bbox, objectUrl } = await this._loadImage(url);
            const frameMap = this._frameImages[frameIndex];
            if (frameMap) {
                frameMap.set(key, { img, loaded: true, url, objectUrl });
            }
            if (!this._bboxes.has(key)) {
                this._bboxes.set(key, bbox);
                this._createOverlay(key, bbox);
            }
        } catch (err) {
            console.warn(`addRadarToFrame: failed to load ${radarCode}/${productKey}:`, err);
        }
    }

    /**
     * Remove a radar from a frame.  If the frame becomes empty after removal,
     * the slot is spliced out of _frameImages.
     *
     * Revokes the object URL to prevent memory leaks.
     *
     * @param {number} frameIndex
     * @param {string} radarCode
     * @param {string} productKey
     * @returns {boolean} true if the frame slot was entirely removed (empty)
     */
    removeFrame(frameIndex, radarCode, productKey) {
        const frameMap = this._frameImages[frameIndex];
        if (!frameMap) return false;

        const key   = `${radarCode}__${productKey}`;
        const entry = frameMap.get(key);
        if (entry) {
            if (entry.objectUrl) URL.revokeObjectURL(entry.objectUrl);
            frameMap.delete(key);
        }

        // If frame is now empty, splice the slot out
        if (frameMap.size === 0) {
            this._frameImages.splice(frameIndex, 1);

            // Adjust visible-frame pointer
            if (this._currentFrameIndex > frameIndex) {
                this._currentFrameIndex--;
            } else if (this._currentFrameIndex === frameIndex) {
                this._currentFrameIndex = -1;
            }

            // Remove overlay if no other frame uses this key
            this._maybeRemoveOverlay(key);
            return true; // slot removed
        }

        // Slot still exists (other radars remain); check overlay
        this._maybeRemoveOverlay(key);
        return false;
    }

    /**
     * Remove a frame slot entirely (all radars gone), splicing out.
     * Used by live refresh expiry when removing all radars from a frame.
     */
    removeFrameSlot(frameIndex) {
        const frameMap = this._frameImages[frameIndex];
        if (!frameMap) return;

        frameMap.forEach((entry, key) => {
            if (entry.objectUrl) URL.revokeObjectURL(entry.objectUrl);
            this._maybeRemoveOverlay(key);
        });
        frameMap.clear();
        this._frameImages.splice(frameIndex, 1);

        if (this._currentFrameIndex > frameIndex) {
            this._currentFrameIndex--;
        } else if (this._currentFrameIndex === frameIndex) {
            this._currentFrameIndex = -1;
        }
    }

    /**
     * Remove an overlay from the map if no frame in _frameImages uses it.
     * @param {string} key
     */
    _maybeRemoveOverlay(key) {
        const stillUsed = this._frameImages.some(m => m && m.has(key));
        if (!stillUsed) {
            const overlay = this._overlays.get(key);
            if (overlay) {
                if (this._map && this._map.hasLayer(overlay)) {
                    this._map.removeLayer(overlay);
                }
                this._overlays.delete(key);
            }
            this._bboxes.delete(key);
        }
    }

    /**
     * Reload all images with new display params (colormap / vmin / vmax).
     * Used when the user changes colormap or filter values.
     * Preloads into a shadow array and swaps atomically to avoid flicker.
     *
     * @param {Map<number, Map<string, Object>>} cogsByFrame
     * @param {string}   productKey
     * @param {Object}   params
     * @param {Function} onProgress
     * @returns {Promise<void>}
     */
    async updateParams(cogsByFrame, productKey, params = {}, onProgress = null) {
        // Pre-load into a new structure, then swap
        const savedCurrent = this._currentFrameIndex;

        // We build a new MapManager-compatible structure in memory
        const newFrameImages = [];
        const newOverlays    = new Map();
        const newBboxes      = new Map();

        const maxIndex = cogsByFrame.size > 0 ? Math.max(...cogsByFrame.keys()) : -1;
        if (maxIndex >= 0) {
            for (let i = 0; i <= maxIndex; i++) {
                newFrameImages.push(new Map());
            }
        }

        let total  = 0;
        cogsByFrame.forEach(radarMap => { total += radarMap.size; });
        let loaded = 0;

        const promises = [];
        cogsByFrame.forEach((radarMap, frameIndex) => {
            radarMap.forEach((cogObj, radarCode) => {
                const key = `${radarCode}__${productKey}`;
                const url = this._buildFrameUrl(cogObj.id, productKey, params);

                const p = this._loadImage(url)
                    .then(({ img, bbox, objectUrl }) => {
                        if (newFrameImages[frameIndex]) {
                            newFrameImages[frameIndex].set(key, {
                                img, loaded: true, url, objectUrl,
                            });
                        }
                        if (!newBboxes.has(key)) {
                            newBboxes.set(key, bbox);
                        }
                        loaded++;
                        if (onProgress) onProgress(loaded, total);
                    })
                    .catch(err => {
                        console.warn(`updateParams: failed ${frameIndex} ${key}:`, err);
                        loaded++;
                        if (onProgress) onProgress(loaded, total);
                    });
                promises.push(p);
            });
        });

        await Promise.all(promises);

        // Swap — revoke old object URLs first
        this._frameImages.forEach(fm => this._revokeFrameMap(fm));

        // Update overlays bounds and remove stale ones
        this._overlays.forEach((overlay, key) => {
            if (!newBboxes.has(key)) {
                if (this._map && this._map.hasLayer(overlay)) {
                    this._map.removeLayer(overlay);
                }
                this._overlays.delete(key);
                this._bboxes.delete(key);
            }
        });

        // Add/update overlays for new keys
        newBboxes.forEach((bbox, key) => {
            if (!this._overlays.has(key)) {
                this._bboxes.set(key, bbox);
                this._createOverlay(key, bbox);
            }
        });

        this._frameImages       = newFrameImages;
        this._currentFrameIndex = savedCurrent;
    }

    // =========================================================================
    // Frame count
    // =========================================================================

    get frameCount() {
        return this._frameImages.length;
    }

    get currentFrameIndex() {
        return this._currentFrameIndex;
    }

    // =========================================================================
    // Coverage circle helpers — identical to v1
    // =========================================================================

    addCoverageCircle(radar, opacity = 0.1) {
        if (!radar || !radar.code) return;
        this.removeCoverageCircle(radar.code);
        if (!radar.center_lat || !radar.center_long || !radar.img_radio) return;

        const circle = L.circle(
            [radar.center_lat, radar.center_long],
            {
                radius:      radar.img_radio * 1000 * 1.01,
                fillColor:   '#000000',
                fillOpacity: opacity,
                stroke:      false,
                interactive: false,
                pane:        'coveragePane',
            }
        ).addTo(this._map);

        this._coverageCircles[radar.code] = circle;
    }

    removeCoverageCircle(radarCode) {
        const circle = this._coverageCircles[radarCode];
        if (circle) {
            if (this._map && this._map.hasLayer(circle)) {
                this._map.removeLayer(circle);
            }
            delete this._coverageCircles[radarCode];
        }
    }

    clearCoverageCircles() {
        Object.keys(this._coverageCircles).forEach(code => this.removeCoverageCircle(code));
    }

    updateCoverageOpacity(opacity) {
        Object.values(this._coverageCircles).forEach(circle => {
            circle.setStyle({ fillOpacity: opacity });
        });
    }

    setCoverageVisible(visible, opacity) {
        if (!visible) {
            this.clearCoverageCircles();
        }
        // Circles are re-added by app-v2.js when visible=true
    }

    // =========================================================================
    // Map accessor
    // =========================================================================

    getMap() { return this._map; }
}
