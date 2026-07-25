/**
 * tops-cores.js — Leaflet layer for convective cores and storm tops.
 *
 * Fetches TopsAndCores records and their GeoJSON features from the API,
 * then renders them as Markers on the Leaflet map using a custom SVG icon.
 *
 * Usage:
 *   import { TopsCoresLayer } from '../shared/tops-cores.js';
 *   const layer = new TopsCoresLayer(map);
 *   layer.setVisible(true);
 *   layer.updateFrame(frame);   // fire-and-forget
 */

const API_BASE = '/api/v1';

// Default time window on each side of the frame timestamp (ms)
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

        // Track the timestamp of the last completed updateFrame so that slow
        // responses from older frames do not overwrite a newer render.
        this._lastRenderedTimestamp = null;

        // Abort controller for in-flight requests
        this._abortController = null;
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
     * Fire-and-forget frame update.  Called by the animation loop on each
     * frame advance.  Does not block the animation.
     *
     * @param {Object} frame  Animation frame object: { timestamp, cogsByRadar }
     */
    updateFrame(frame) {
        if (!this._visible) return;
        if (!frame) return;

        const ts = frame.timestamp || frame.observation_time;
        if (!ts) return;

        const radarCodes = Object.keys(frame.cogsByRadar || {});
        if (radarCodes.length === 0) {
            this.clear();
            return;
        }

        // Cancel any in-flight request from a previous frame
        if (this._abortController) {
            this._abortController.abort();
        }
        this._abortController = new AbortController();
        const { signal } = this._abortController;
        const renderTimestamp = ts;

        // Time window
        const center = new Date(ts).getTime();
        const timeFrom = new Date(center - TIME_WINDOW_MS).toISOString();
        const timeTo   = new Date(center + TIME_WINDOW_MS).toISOString();

        // Build query string with multiple radar_codes
        const params = new URLSearchParams({ time_from: timeFrom, time_to: timeTo });
        radarCodes.forEach(code => params.append('radar_codes', code));
        const metaUrl = `${API_BASE}/tops-cores?${params.toString()}`;

        // Kick off async work — never awaited by the caller
        (async () => {
            console.log('[T+C] fetch-start for', ts);
            try {
                // Step 1: fetch metadata records
                const metaResp = await fetch(metaUrl, { signal });
                if (!metaResp.ok) {
                    console.warn(`[TopsCoresLayer] metadata fetch failed: ${metaResp.status}`);
                    this.clear();
                    return;
                }
                const records = await metaResp.json();

                if (!records || records.length === 0) {
                    this.clear();
                    return;
                }

                // Step 2: fetch GeoJSON features for all records concurrently
                const featureResults = await Promise.all(
                    records.map(rec =>
                        fetch(`${API_BASE}/tops-cores/${rec.id}/features`, { signal })
                            .then(r => {
                                if (!r.ok) return null;
                                return r.json();
                            })
                            .catch(err => {
                                if (err.name !== 'AbortError') {
                                    console.warn(`[TopsCoresLayer] features fetch failed for id=${rec.id}:`, err);
                                }
                                return null;
                            })
                    )
                );

                // If a newer frame has already started rendering, drop this response
                console.log('[T+C] render-check for', renderTimestamp,
                    '| signal.aborted:', signal.aborted,
                    '| lastRendered:', this._lastRenderedTimestamp);
                if (signal.aborted) return;
                if (renderTimestamp !== ts && this._lastRenderedTimestamp !== null &&
                    new Date(renderTimestamp) < new Date(this._lastRenderedTimestamp)) {
                    return;
                }

                // Step 3: clear old markers and render new ones
                this.clear();

                featureResults.forEach(geojson => {
                    if (!geojson || !Array.isArray(geojson.features)) return;
                    this._renderFeatureCollection(geojson.features);
                });

                console.log('[T+C] RENDERED for', renderTimestamp);
                this._lastRenderedTimestamp = renderTimestamp;

            } catch (err) {
                if (err.name === 'AbortError') return; // expected — new frame started
                console.warn('[TopsCoresLayer] updateFrame error:', err);
                this.clear();
            }
        })();
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
        if (this._abortController) {
            this._abortController.abort();
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
            iconUrl: ICON_URL,
            iconSize: [sizePx, sizePx],
            iconAnchor: [sizePx / 2, sizePx / 2],
        });
    }

    /**
     * Render all features in a FeatureCollection, showing only core markers.
     * Each core tooltip includes the altitude from its spatially nearest top.
     * @param {Object[]} features  Array of GeoJSON Feature objects
     */
    _renderFeatureCollection(features) {
        const cores = features.filter(f => f?.geometry?.type === 'Point' && f?.properties?.type === 'core');
        const tops  = features.filter(f => f?.geometry?.type === 'Point' && f?.properties?.type === 'top');

        cores.forEach(core => {
            const [coreLon, coreLat] = core.geometry.coordinates;

            // Find the nearest top by squared Euclidean distance in geographic coords
            let nearestAltitude = null;
            let minDist = Infinity;
            tops.forEach(top => {
                const [topLon, topLat] = top.geometry.coordinates;
                const dist = (topLon - coreLon) ** 2 + (topLat - coreLat) ** 2;
                if (dist < minDist) {
                    minDist = dist;
                    nearestAltitude = top.properties?.altitude_m ?? null;
                }
            });

            const marker = L.marker([coreLat, coreLon], {
                icon: this._coreIcon(this._iconSize),
                pane: this._pane,
            });
            const dbz = core.properties?.intensity_dbz != null ? `${core.properties.intensity_dbz} dBZ` : '—';
            const alt = nearestAltitude != null ? `${nearestAltitude} m` : '—';
            marker.bindTooltip(`Core — ${dbz}<br>Top — ${alt}`, { sticky: true });
            marker.addTo(this._layerGroup);
        });
    }
}
