/**
 * tops-cores.js — Leaflet layer for convective cores and storm tops.
 *
 * Fetches TopsAndCores records and their GeoJSON features from the API,
 * then renders them as CircleMarkers on the Leaflet map.
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

// Default CircleMarker radius in pixels
const DEFAULT_RADIUS = 8;

// CircleMarker style for cores
const CORE_STYLE = {
    fillColor: '#3b82f6',  // blue
    color: '#000',
    weight: 1,
    fillOpacity: 0.9,
};

// CircleMarker style for tops
const TOP_STYLE = {
    fillColor: '#ef4444',  // red
    color: '#000',
    weight: 1,
    fillOpacity: 0.9,
};

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
        this._radius = DEFAULT_RADIUS;

        // L.LayerGroup that holds all CircleMarkers for the current frame
        this._layerGroup = L.layerGroup().addTo(map);

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
     * Update the radius of all existing markers and store for new ones.
     * @param {number} radiusPx
     */
    setPointSize(radiusPx) {
        this._radius = radiusPx;
        this._layerGroup.eachLayer(layer => {
            if (layer.setRadius) {
                layer.setRadius(radiusPx);
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
                if (signal.aborted) return;
                if (renderTimestamp !== ts && this._lastRenderedTimestamp !== null &&
                    new Date(renderTimestamp) < new Date(this._lastRenderedTimestamp)) {
                    return;
                }

                // Step 3: clear old markers and render new ones
                this.clear();

                featureResults.forEach(geojson => {
                    if (!geojson || !Array.isArray(geojson.features)) return;
                    geojson.features.forEach(feature => {
                        this._renderFeature(feature);
                    });
                });

                this._lastRenderedTimestamp = renderTimestamp;

            } catch (err) {
                if (err.name === 'AbortError') return; // expected — new frame started
                console.warn('[TopsCoresLayer] updateFrame error:', err);
                this.clear();
            }
        })();
    }

    /**
     * Remove all CircleMarkers from the layer group.
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
     * Render a single GeoJSON feature as a CircleMarker.
     * @param {Object} feature  GeoJSON Feature (Point)
     */
    _renderFeature(feature) {
        if (!feature || feature.geometry?.type !== 'Point') return;

        const coords = feature.geometry.coordinates; // [lon, lat]
        if (!coords || coords.length < 2) return;

        const props = feature.properties || {};
        const type  = props.type;

        if (type === 'core') {
            const marker = L.circleMarker([coords[1], coords[0]], {
                ...CORE_STYLE,
                radius: this._radius,
            });
            const dbz = props.intensity_dbz != null ? `${props.intensity_dbz} dBZ` : '—';
            marker.bindTooltip(`Core — ${dbz}`, { sticky: true });
            marker.addTo(this._layerGroup);

        } else if (type === 'top') {
            const marker = L.circleMarker([coords[1], coords[0]], {
                ...TOP_STYLE,
                radius: this._radius,
            });
            const alt = props.altitude_m != null ? `${props.altitude_m} m` : '—';
            marker.bindTooltip(`Top — ${alt}`, { sticky: true });
            marker.addTo(this._layerGroup);
        }
        // Unknown feature types are silently ignored
    }
}
