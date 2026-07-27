/**
 * tops-cores.js — Leaflet layer for convective cores and storm tops.
 *
 * Data is pre-fetched at load time for all animation frames via loadForFrames(),
 * then displayed synchronously on each frame advance via showFrame().
 * This eliminates the async race between the GeoTIFF layer (synchronous) and
 * the tops/cores markers that existed with the old per-frame fetch approach.
 *
 * Usage:
 *   import { TopsCoresLayer } from '../shared/tops-cores.js';
 *   const layer = new TopsCoresLayer(map);
 *   layer.setVisible(true);
 *   layer.loadForFrames(frames);   // fire-and-forget at load time
 *   layer.showFrame(frameIndex);   // synchronous, called from animation loop
 */

const API_BASE = '/api/v1';

// Time window on each side of a frame timestamp used to match tops/cores records (ms)
const TIME_WINDOW_MS = 2.5 * 60 * 1000;

// SVG icon for core markers
const ICON_URL = '/img/alert-icon.svg';

// Default icon size in pixels (slider default 4 × scale factor 4)
const DEFAULT_ICON_SIZE = 16;

/**
 * Manages the Tops & Cores Leaflet overlay.
 */
export class TopsCoresLayer {
    /**
     * @param {L.Map} map  Leaflet map instance
     */
    constructor(map) {
        this._map = map;
        this._visible = false;
        this._pane = 'topsCoresPane';

        // Dedicated pane above overlayPane (200) so markers always sit on top
        // of L.imageOverlay radar images regardless of DOM insertion order.
        if (!map.getPane(this._pane)) {
            map.createPane(this._pane);
            map.getPane(this._pane).style.zIndex = 450;
        }

        // L.LayerGroup that holds all markers for the current frame
        this._layerGroup = L.layerGroup().addTo(map);

        // Current icon size in pixels (updated by setPointSize)
        this._iconSize = DEFAULT_ICON_SIZE;

        // Pre-loaded marker data indexed by frame index.
        // Each element is an array of { lat, lon, dbz, alt } plain objects.
        this._frameData = [];

        // Last frameIndex passed to showFrame() — used to re-paint when
        // loadForFrames() completes while the animation is paused.
        this._lastShownFrameIndex = null;

        // Abort controller for any in-flight loadForFrames() call.
        this._loadAbortController = null;
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /**
     * Show or hide the entire layer group.
     * @param {boolean} visible
     */
    setVisible(visible) {
        this._visible = visible;
        if (visible) {
            if (!this._map.hasLayer(this._layerGroup)) {
                this._layerGroup.addTo(this._map);
            }
        } else {
            this._layerGroup.remove();
        }
    }

    /**
     * Update the icon size of all existing markers and store for new ones.
     * The raw slider value (2–10) is scaled ×4 to produce a usable pixel size.
     * @param {number} radiusPx  Value from the size slider (2–10)
     */
    setPointSize(radiusPx) {
        this._iconSize = Math.round(radiusPx * 4);
        const icon = this._coreIcon(this._iconSize);
        this._layerGroup.eachLayer(layer => {
            if (layer.setIcon) {
                layer.setIcon(icon);
            }
        });
    }

    /**
     * Pre-fetch all tops/cores data for a full set of animation frames.
     *
     * Issues a single broad metadata query covering the entire time range,
     * fetches per-record GeoJSON features concurrently, then distributes the
     * results into per-frame marker-data arrays keyed by frame index.
     *
     * Call this fire-and-forget from app.js after frames are loaded. When it
     * completes it will re-paint the last shown frame if the animation is paused.
     *
     * @param {Array} frames  groupedFrames: [{timestamp, cogsByRadar}, …]
     */
    async loadForFrames(frames) {
        if (!frames || frames.length === 0) {
            this._frameData = [];
            return;
        }

        // Cancel any previous load still in flight
        if (this._loadAbortController) {
            this._loadAbortController.abort();
        }
        this._loadAbortController = new AbortController();
        const { signal } = this._loadAbortController;

        // Compute a single time range covering all frames ± the window
        const timestamps = frames.map(f => new Date(f.timestamp || f.observation_time).getTime());
        const overallStart = new Date(Math.min(...timestamps) - TIME_WINDOW_MS);
        const overallEnd   = new Date(Math.max(...timestamps) + TIME_WINDOW_MS);

        // Collect all unique radar codes used across all frames
        const radarCodesSet = new Set();
        frames.forEach(f => Object.keys(f.cogsByRadar || {}).forEach(c => radarCodesSet.add(c)));
        const radarCodes = [...radarCodesSet];

        if (radarCodes.length === 0) {
            this._frameData = frames.map(() => []);
            return;
        }

        try {
            // Step 1: one metadata query for the full time range
            const params = new URLSearchParams({
                time_from: overallStart.toISOString(),
                time_to:   overallEnd.toISOString(),
            });
            radarCodes.forEach(code => params.append('radar_codes', code));

            const metaResp = await fetch(`${API_BASE}/tops-cores?${params}`, { signal });
            if (!metaResp.ok) {
                console.warn(`[TopsCoresLayer] loadForFrames metadata failed: ${metaResp.status}`);
                this._frameData = frames.map(() => []);
                return;
            }
            const records = await metaResp.json();

            if (signal.aborted) return;

            if (!records || records.length === 0) {
                this._frameData = frames.map(() => []);
                if (this._visible && this._lastShownFrameIndex !== null) {
                    this.showFrame(this._lastShownFrameIndex);
                }
                return;
            }

            // Step 2: fetch GeoJSON features for all records concurrently
            const featureResults = await Promise.all(
                records.map(rec =>
                    fetch(`${API_BASE}/tops-cores/${rec.id}/features`, { signal })
                        .then(r => r.ok ? r.json() : null)
                        .catch(err => {
                            if (err.name !== 'AbortError') {
                                console.warn(`[TopsCoresLayer] features fetch failed for id=${rec.id}:`, err);
                            }
                            return null;
                        })
                )
            );

            if (signal.aborted) return;

            // Step 3: extract plain marker-data objects from each record's features
            const recordMarkerData = featureResults.map(geojson => {
                if (!geojson || !Array.isArray(geojson.features)) return [];
                return this._extractMarkerData(geojson.features);
            });

            // Step 4: distribute records to frames by ±TIME_WINDOW_MS
            this._frameData = frames.map(frame => {
                const frameMs = new Date(frame.timestamp || frame.observation_time).getTime();
                const data = [];
                records.forEach((rec, i) => {
                    const recMs = new Date(rec.observation_time).getTime();
                    if (Math.abs(recMs - frameMs) <= TIME_WINDOW_MS) {
                        data.push(...recordMarkerData[i]);
                    }
                });
                return data;
            });

            // Re-paint the paused frame now that data is ready
            if (this._visible && this._lastShownFrameIndex !== null) {
                this.showFrame(this._lastShownFrameIndex);
            }

        } catch (err) {
            if (err.name === 'AbortError') return;
            console.warn('[TopsCoresLayer] loadForFrames error:', err);
            this._frameData = frames.map(() => []);
        }
    }

    /**
     * Synchronously display the pre-loaded markers for the given frame index.
     * Called on every frame advance from the animation loop — must not block.
     * @param {number} frameIndex
     */
    showFrame(frameIndex) {
        this._lastShownFrameIndex = frameIndex;
        this._layerGroup.clearLayers();
        if (!this._visible) return;

        const data = this._frameData[frameIndex];
        if (!data || data.length === 0) return;

        const icon = this._coreIcon(this._iconSize);
        data.forEach(({ lat, lon, dbz, alt }) => {
            const dbzText = dbz != null ? `${dbz} dBZ` : '—';
            const altText = alt != null ? `${alt} m` : '—';
            const marker = L.marker([lat, lon], { icon, pane: this._pane });
            marker.bindTooltip(`Core — ${dbzText}<br>Top — ${altText}`, { sticky: true });
            marker.addTo(this._layerGroup);
        });
    }

    /**
     * Remove all markers from the layer group.
     */
    clear() {
        this._layerGroup.clearLayers();
    }

    /**
     * Remove the layer group from the map entirely.
     */
    destroy() {
        if (this._loadAbortController) {
            this._loadAbortController.abort();
        }
        this._layerGroup.remove();
    }

    // -------------------------------------------------------------------------
    // Internal
    // -------------------------------------------------------------------------

    /**
     * Build a Leaflet icon for core markers at the given pixel size.
     * @param {number} sizePx
     * @returns {L.Icon}
     */
    _coreIcon(sizePx) {
        return L.icon({
            iconUrl:    ICON_URL,
            iconSize:   [sizePx, sizePx],
            iconAnchor: [sizePx / 2, sizePx / 2],
        });
    }

    /**
     * Extract plain marker-data objects from a GeoJSON feature array.
     * Each core gets the altitude of its spatially nearest top.
     * @param {Object[]} features  GeoJSON Feature objects
     * @returns {{ lat: number, lon: number, dbz: number|null, alt: number|null }[]}
     */
    _extractMarkerData(features) {
        const cores = features.filter(f => f?.geometry?.type === 'Point' && f?.properties?.type === 'core');
        const tops  = features.filter(f => f?.geometry?.type === 'Point' && f?.properties?.type === 'top');

        return cores.map(core => {
            const [lon, lat] = core.geometry.coordinates;

            // Find the nearest top by squared Euclidean distance in geographic coords
            let alt = null;
            let minDist = Infinity;
            tops.forEach(top => {
                const [tlon, tlat] = top.geometry.coordinates;
                const dist = (tlon - lon) ** 2 + (tlat - lat) ** 2;
                if (dist < minDist) {
                    minDist = dist;
                    alt = top.properties?.altitude_m ?? null;
                }
            });

            return { lat, lon, dbz: core.properties?.intensity_dbz ?? null, alt };
        });
    }
}
