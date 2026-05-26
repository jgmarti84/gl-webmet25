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

// Available basemap options
const BASEMAPS = {
    'argenmap': {
        name:        'IGN Argenmap',
        url:         'https://wms.ign.gob.ar/geoserver/gwc/service/tms/1.0.0/capabaseargenmap@EPSG%3A3857@png/{z}/{x}/{-y}.png',
        attribution: '© <a href="https://www.ign.gob.ar/" target="_blank">Instituto Geográfico Nacional</a>',
        maxZoom:     18,
    },
    'argenmap_gris': {
        name:        'IGN Argenmap Gris',
        url:         'https://wms.ign.gob.ar/geoserver/gwc/service/tms/1.0.0/mapabase_gris@EPSG%3A3857@png/{z}/{x}/{-y}.png',
        attribution: '© <a href="https://www.ign.gob.ar/" target="_blank">Instituto Geográfico Nacional</a>',
        maxZoom:     18,
    },
    'argenmap_topo': {
        name:        'IGN Argenmap Topo',
        url:         'https://wms.ign.gob.ar/geoserver/gwc/service/tms/1.0.0/mapabase_topo@EPSG%3A3857@png/{z}/{x}/{-y}.png',
        attribution: '© <a href="https://www.ign.gob.ar/" target="_blank">Instituto Geográfico Nacional</a>',
        maxZoom:     18,
    },
    'osm': {
        name:        'OpenStreetMap',
        url:         '/osm-tiles/{z}/{x}/{y}.png',
        attribution: '© OpenStreetMap contributors',
        maxZoom:     19,
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
        this._currentBasemap = 'argenmap';
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

        // Coverage mask state — SVG element appended directly to the map
        // container (outside Leaflet panes) to avoid pane CSS transforms.
        this._coverageSvgEl = null;
        this._coverageOpacity = parseFloat(
            localStorage.getItem('webmet25_coverage_opacity')
        ) || 0.4;
        // Map of radarCode → { lat, lng, radius_m }
        this._activeRadarCoverages = new Map();
    }

    // =========================================================================
    // Initialisation
    // =========================================================================

    /**
     * Initialise the Leaflet map.  Called once on page load.
     * @returns {L.Map}
     */
    init() {
        this._map = L.map(this._mapElementId, { zoomControl: false }).setView(DEFAULT_CENTER, DEFAULT_ZOOM);

        // Radar coverage mask pane — kept for z-index ordering, the SVG
        // is NOT placed inside this pane (panes are transformed by Leaflet
        // during pan/zoom which would misalign the circles). The SVG is
        // appended directly to the map container instead.
        this._map.createPane('coverageMaskPane');
        this._map.getPane('coverageMaskPane').style.zIndex = 300;
        this._map.getPane('coverageMaskPane').style.pointerEvents = 'none';

        this._initCoverageMask();

        // Redraw on every pan and zoom event (not just *end) so circles
        // track the viewport smoothly during drags and pinch-zoom.
        this._map.on('move zoom moveend zoomend resize', () => {
            this._updateCoverageMask();
        });

        this.setBasemap(localStorage.getItem('webmet25_selected_basemap') || this._currentBasemap);
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
        localStorage.setItem('webmet25_selected_basemap', basemapKey);
        const basemapSelect = document.getElementById('basemap-select');
        if (basemapSelect && basemapSelect.value !== basemapKey) basemapSelect.value = basemapKey;
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
        if (params.smooth)                              qs.set('smooth', 'true');
        if (params.smooth && params.smoothSigma != null) qs.set('smooth_sigma', params.smoothSigma);
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

        // Apply crisp nearest-neighbor rendering so discrete measurement
        // cells render as sharp pixel squares rather than a blurred gradient.
        const el = overlay.getElement();
        if (el) {
            el.classList.add('radar-image-overlay');
        }

        // TODO Phase: zoom-adaptive rendering
        // When implemented, pass ?zoom=N to the /frames/ endpoint so the backend
        // selects the appropriate COG overview level (native ~473x473 at zoom 9+,
        // overview 2x at zoom 8, 4x at zoom 7, etc.).
        // Cache key for frames will need to include zoom tier (e.g. frame:{id}:{tier}:{params}).
        // On map 'zoomend', if zoom crosses a tier boundary, invalidate preloaded
        // object URLs and trigger a re-fetch cycle while holding last frame (LOCF).

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
    // Coverage mask helpers
    // =========================================================================

    /**
     * Create the full-map SVG overlay mask once, at map init.
     * The mask starts with no cutout circles; call addRadarCoverage() to add them.
     */
    _initCoverageMask() {
        const svgNS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(svgNS, 'svg');
        svg.setAttribute('xmlns', svgNS);
        // Cover the entire map container. Positioned outside all Leaflet panes
        // so pan/zoom CSS transforms on panes do NOT shift this element.
        // Width/height attributes must be set (not just CSS) so the SVG has
        // an intrinsic viewport for resolving percentage/coordinate values.
        // We keep them in sync with the container in _updateCoverageMask().
        const mapSize = this._map.getSize();
        svg.setAttribute('width', String(mapSize.x));
        svg.setAttribute('height', String(mapSize.y));
        svg.style.cssText = [
            'position:absolute',
            'top:0',
            'left:0',
            'pointer-events:none',
            // Above overlayPane (400) and markerPane (600) so the mask always
            // sits on top of all map content.
            'z-index:650',
        ].join(';');

        // <defs> with mask
        const defs = document.createElementNS(svgNS, 'defs');
        const mask = document.createElementNS(svgNS, 'mask');
        mask.setAttribute('id', 'radar-coverage-mask');
        // Use userSpaceOnUse so all coordinates are in plain SVG pixels —
        // no ambiguity from objectBoundingBox percentage resolution.
        mask.setAttribute('maskUnits', 'userSpaceOnUse');
        mask.setAttribute('maskContentUnits', 'userSpaceOnUse');
        // Cover entire SVG with huge rect — updated each frame via viewBox
        // so there is no chance of a gap if the map is larger than expected.
        mask.setAttribute('x', '-9999');
        mask.setAttribute('y', '-9999');
        mask.setAttribute('width', '99999');
        mask.setAttribute('height', '99999');

        // White base rect = show everything by default.
        // Use large absolute values — safe regardless of zoom/pan.
        const maskBase = document.createElementNS(svgNS, 'rect');
        maskBase.setAttribute('x', '-9999');
        maskBase.setAttribute('y', '-9999');
        maskBase.setAttribute('width', '99999');
        maskBase.setAttribute('height', '99999');
        maskBase.setAttribute('fill', 'white');
        mask.appendChild(maskBase);

        defs.appendChild(mask);
        svg.appendChild(defs);

        // Dark overlay rect — covers the entire SVG canvas.
        // Black circles punched into the mask make coverage areas transparent.
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

        // Append directly to the map container (not a pane) so the SVG
        // is never subject to Leaflet's pane CSS transforms.
        const mapContainer = this._map.getContainer();
        if (getComputedStyle(mapContainer).position === 'static') {
            mapContainer.style.position = 'relative';
        }
        mapContainer.appendChild(svg);
    }

    /**
     * Redraw the SVG mask circles to match the current map viewport.
     * Must be called after every pan/zoom and after coverage set changes.
     */
    _updateCoverageMask() {
        if (!this._coverageSvgEl) return;

        // Keep SVG dimensions matching the map container so latLngToContainerPoint
        // coordinates fall within the SVG's rendered area after resize.
        const mapSize = this._map.getSize();
        this._coverageSvgEl.setAttribute('width', String(mapSize.x));
        this._coverageSvgEl.setAttribute('height', String(mapSize.y));

        const svgNS = 'http://www.w3.org/2000/svg';
        const mask = this._coverageSvgEl.querySelector('#radar-coverage-mask');
        if (!mask) return;

        // Remove all existing cutout circles (keep the white base rect)
        mask.querySelectorAll('circle').forEach(c => c.remove());

        // Add one black circle per active radar coverage area.
        // Black in SVG mask = fully transparent in the masked element.
        // Overlapping black circles merge automatically (union).
        //
        // The Mercator projection is conformal: at any single point, the N-S
        // and E-W scales are both sec(lat), so a geodetic circle of radius R
        // centred at the radar projects to a circle in Mercator pixel-space to
        // first order.  _metersToPixels computes that pixel radius by measuring
        // the E-W Mercator pixel distance for R metres, which is correct.
        for (const [, coverage] of this._activeRadarCoverages) {
            const point = this._map.latLngToContainerPoint(
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

        // Sync opacity on the overlay rect
        const overlayRect = this._coverageSvgEl.querySelector(
            '#radar-coverage-overlay-rect'
        );
        if (overlayRect) {
            overlayRect.setAttribute('opacity', String(this._coverageOpacity));
        }
    }

    /**
     * Convert a ground radius in meters to SVG layer pixels
     * at the given latitude and the current map zoom.
     * @param {number} lat
     * @param {number} radiusMeters
     * @returns {number}
     */
    _metersToPixels(lat, radiusMeters) {
        // Compute pixel radius using the same container-point projection
        // used in _updateCoverageMask so units are consistent with the viewBox.
        const metersPerDegLng = 111320 * Math.cos(lat * Math.PI / 180);
        const offsetLng = radiusMeters / metersPerDegLng;
        const centerPx = this._map.latLngToContainerPoint(L.latLng(lat, 0));
        const edgePx   = this._map.latLngToContainerPoint(L.latLng(lat, offsetLng));
        return Math.abs(edgePx.x - centerPx.x);
    }

    /**
     * Register a radar's coverage area in the mask.
     * @param {string} radarCode
     * @param {number} lat     Center latitude (WGS84)
     * @param {number} lng     Center longitude (WGS84)
     * @param {number} radius_m Coverage radius in meters
     */
    addRadarCoverage(radarCode, lat, lng, radius_m) {
        this._activeRadarCoverages.set(radarCode, { lat, lng, radius_m });
        this._updateCoverageMask();
    }

    /**
     * Remove a radar's coverage area from the mask.
     * @param {string} radarCode
     */
    removeRadarCoverage(radarCode) {
        this._activeRadarCoverages.delete(radarCode);
        this._updateCoverageMask();
    }

    /**
     * Update the opacity of the shaded region outside coverage areas.
     * Coverage circles themselves remain fully transparent.
     * @param {number} opacity  0.0 – 1.0
     */
    setCoverageOpacity(opacity) {
        this._coverageOpacity = opacity;
        this._updateCoverageMask();
    }

    // =========================================================================
    // Map accessor
    // =========================================================================

    getMap() { return this._map; }
}
