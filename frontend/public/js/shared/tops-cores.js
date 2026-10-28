/**
 * tops-cores.js — Leaflet layer for convective cores and storm tops.
 *
 * Marker data is pre-fetched for the COGs displayed in the animation frames via
 * loadForFrames() and cached by COG identity (radar|strategy|vol|observation_time),
 * then displayed synchronously on each frame advance via showFrame(). Lookups never
 * depend on frame positions, so changing the frame list (radar toggling, live
 * refresh) cannot pair a frame with another scan's markers.
 *
 * Usage:
 *   import { TopsCoresLayer } from '../shared/tops-cores.js';
 *   const layer = new TopsCoresLayer(map);
 *   layer.setVisible(true);
 *   layer.loadForFrames(frames);   // fire-and-forget at load time
 *   layer.showFrame(frame, prevFrame, holdRadarCodes);  // synchronous, from animation loop
 */

import { authFetch } from '../auth-api.js';
import {
    cogTimeSpan,
    collectDisplayedCogs,
    markersForFrame,
    recordKey,
    selectWantedRecords,
} from './tops-cores-match.js';

const API_BASE = '/api/v1';

// Margin around the first/last displayed COG time in the metadata query (ms).
// Records are matched to COGs by exact observation_time; this only guards
// against sub-second serialisation differences at the range edges.
const QUERY_MARGIN_MS = 1000;

// SVG icon for core markers
const ICON_URL = '/img/code-purple.svg';

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

        // Marker data per tops/cores record, keyed by COG identity
        // (radar|strategy|vol|observation_time) — independent of frame positions.
        this._markersByKey = new Map();

        // Frame context of the last showFrame() call — used to re-paint when
        // loadForFrames() completes while the animation is paused.
        this._lastContext = null;

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
     * Pre-fetch the tops/cores markers of every COG displayed in the frames.
     *
     * Only COGs whose markers are not cached yet are requested: one metadata
     * query spanning them, then the per-record GeoJSON features concurrently.
     * Results are stored by COG identity, so a result is valid whatever the
     * frame list looks like when it arrives. The cache is pruned to the COGs
     * currently displayed.
     *
     * Call this fire-and-forget from app.js whenever the frame list changes.
     * When it completes it re-paints the last shown frame.
     *
     * @param {Array} frames  [{cogsByRadar}, …] — the animation frames
     */
    async loadForFrames(frames) {
        // Cancel any previous load still in flight (its COGs are re-requested if still needed)
        if (this._loadAbortController) {
            this._loadAbortController.abort();
        }
        this._loadAbortController = new AbortController();
        const { signal } = this._loadAbortController;

        const displayed = collectDisplayedCogs(frames);

        // Drop cached markers of COGs no longer displayed
        for (const key of [...this._markersByKey.keys()]) {
            if (!displayed.has(key)) this._markersByKey.delete(key);
        }

        const missing = new Map([...displayed].filter(([key]) => !this._markersByKey.has(key)));
        if (missing.size === 0) {
            this._repaint();
            return;
        }

        const span = cogTimeSpan(missing.values());
        const radarCodes = [...new Set([...missing.values()].map(c => c.radar_code))].filter(Boolean);
        if (!span || radarCodes.length === 0) {
            this._repaint();
            return;
        }

        try {
            // Step 1: one metadata query spanning the missing COGs
            const params = new URLSearchParams({
                time_from: new Date(span.from.getTime() - QUERY_MARGIN_MS).toISOString(),
                time_to:   new Date(span.to.getTime() + QUERY_MARGIN_MS).toISOString(),
            });
            radarCodes.forEach(code => params.append('radar_codes', code));

            const metaResp = await authFetch(`${API_BASE}/tops-cores?${params}`, { signal });
            if (!metaResp.ok) {
                console.warn(`[TopsCoresLayer] loadForFrames metadata failed: ${metaResp.status}`);
                return;
            }
            const records = selectWantedRecords(await metaResp.json() || [], missing);
            if (signal.aborted) return;

            // Step 2: fetch GeoJSON features for the wanted records concurrently
            const results = await Promise.all(
                records.map(rec =>
                    authFetch(`${API_BASE}/tops-cores/${rec.id}/features`, { signal })
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

            // Step 3: cache by COG identity (failed fetches stay uncached and are retried next load)
            records.forEach((rec, i) => {
                const geojson = results[i];
                if (!geojson || !Array.isArray(geojson.features)) return;
                this._markersByKey.set(
                    recordKey(rec.radar_code, rec.strategy, rec.vol_nr, rec.observation_time),
                    this._extractMarkerData(geojson.features)
                );
            });

            this._repaint();

        } catch (err) {
            if (err.name === 'AbortError') return;
            console.warn('[TopsCoresLayer] loadForFrames error:', err);
        }
    }

    /**
     * Synchronously display the markers of the COGs shown by the given frame.
     * Called on every frame advance from the animation loop — must not block.
     *
     * @param {{cogsByRadar: object}} frame  the frame being displayed
     * @param {{cogsByRadar: object}|null} [prevFrame]  previous frame (source of held images)
     * @param {string[]} [holdRadarCodes]  radars whose image is held from prevFrame
     */
    showFrame(frame, prevFrame = null, holdRadarCodes = []) {
        this._lastContext = { frame, prevFrame, holdRadarCodes };
        this._layerGroup.clearLayers();
        if (!this._visible) return;

        const markers = markersForFrame(frame, prevFrame, holdRadarCodes, this._markersByKey);
        if (markers.length === 0) return;

        const icon = this._coreIcon(this._iconSize);
        markers.forEach(({ lat, lon, dbz, alt }) => {
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
     * Re-draw the last shown frame (after data finished loading).
     */
    _repaint() {
        if (this._visible && this._lastContext) {
            const { frame, prevFrame, holdRadarCodes } = this._lastContext;
            this.showFrame(frame, prevFrame, holdRadarCodes);
        }
    }

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
     * Extract marker-data objects from a GeoJSON feature array.
     * Each core gets the altitude of its spatially nearest top.
     * @param {Object[]} features  GeoJSON Feature objects
     * @returns {{lat,lon,dbz,alt}[]}
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
