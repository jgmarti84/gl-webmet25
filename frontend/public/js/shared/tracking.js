/**
 * Storm tracking layer.
 *
 * Renders the output of the tracking sidecar (/api/tracking) on a Leaflet map:
 * convective system polygons, their forecast polygons, and the centroid
 * trajectory of each track.
 *
 * Written as a self-contained module rather than page code on purpose. v1 lives
 * on its own page, but the intent is to fold tracking into radar.html as a
 * toggleable layer later — which is cheap wiring only if the layer owns its own
 * fetch, render and frame-sync, exactly as tops-cores.js does.
 *
 * Tracking is single-radar by nature and this layer assumes it: every cube is
 * gridded through one radar's geometry, and a storm in the overlap between two
 * radars is tracked twice under different ids.
 */

const TRACKING_BASE = '/api/tracking';

/** Styling by convective verdict. Non-convective systems are detected but
 *  rejected by the filter — worth showing faintly rather than hiding, since
 *  "detected but rejected" and "nothing there" are different states. */
const STYLE_CONVECTIVE = { color: '#ff3b30', weight: 2, fillColor: '#ff3b30', fillOpacity: 0.18 };
const STYLE_PLAIN      = { color: '#9e9e9e', weight: 1, fillColor: '#9e9e9e', fillOpacity: 0.08, dashArray: '4,3' };
const STYLE_FORECAST   = { color: '#4fc3f7', weight: 1, fill: false, dashArray: '3,4', opacity: 0.75 };
const STYLE_TRACK      = { color: '#ffb300', weight: 2, opacity: 0.9 };

export class TrackingLayer {
    /** @param {L.Map} map */
    constructor(map) {
        this._map = map;
        this._visible = true;

        // Dedicated pane above the radar imagery, so polygons are never hidden
        // behind an L.imageOverlay regardless of DOM insertion order.
        this._pane = 'trackingPane';
        if (!map.getPane(this._pane)) {
            map.createPane(this._pane);
            map.getPane(this._pane).style.zIndex = 460;
        }

        this._systems = L.layerGroup().addTo(map);
        this._forecasts = L.layerGroup().addTo(map);
        this._tracks = L.layerGroup().addTo(map);

        /** @type {Array} frames from the job result, in time order */
        this._frames = [];
        /** @type {Map<string, Array<[number,number]>>} track id -> centroid path */
        this._paths = new Map();

        this._showForecasts = true;
        this._showTrails = true;
        this._currentIndex = null;
    }

    // ---------------------------------------------------------------- state

    /** Frames from a completed job, in time order. */
    setFrames(frames) {
        this._frames = Array.isArray(frames) ? frames : [];
        this._buildPaths();
        this._currentIndex = null;
        return this._frames.length;
    }

    get frames() { return this._frames; }
    get frameCount() { return this._frames.length; }

    /**
     * Centroid trajectory per track id, accumulated across all frames.
     *
     * Track identity is the `name` property: a UUID inherited at each
     * successful match, so systems sharing it across frames are one storm.
     * Note these ids are generated fresh per tracking run — stable within one
     * result set, not across runs.
     */
    _buildPaths() {
        this._paths = new Map();
        for (const frame of this._frames) {
            for (const feature of frame.features?.features || []) {
                const props = feature.properties || {};
                if (props.kind !== 'system') continue;
                const centre = centroidOf(feature.geometry);
                if (!centre) continue;
                if (!this._paths.has(props.name)) this._paths.set(props.name, []);
                this._paths.get(props.name).push(centre);
            }
        }
    }

    // --------------------------------------------------------------- render

    /** Render the frame at `index`. Out-of-range clears the map. */
    showFrame(index) {
        this._currentIndex = index;
        this._systems.clearLayers();
        this._forecasts.clearLayers();
        this._tracks.clearLayers();

        const frame = this._frames[index];
        if (!frame) return null;

        const live = new Set();

        for (const feature of frame.features?.features || []) {
            const props = feature.properties || {};

            if (props.kind === 'system') {
                live.add(props.name);
                const convective = props.is_convective === true;
                L.geoJSON(feature, {
                    pane: this._pane,
                    style: convective ? STYLE_CONVECTIVE : STYLE_PLAIN,
                })
                    .bindPopup(() => popupHtml(props))
                    .addTo(this._systems);
            } else if (props.kind === 'forecast' && this._showForecasts) {
                L.geoJSON(feature, { pane: this._pane, style: STYLE_FORECAST })
                    .bindTooltip(`+${props.lead_min} min`, { sticky: true })
                    .addTo(this._forecasts);
            }
        }

        // Trails for the tracks alive in this frame only — drawing every path
        // at once turns a busy day into an unreadable tangle.
        if (this._showTrails) {
            for (const name of live) {
                const path = this._paths.get(name);
                if (path && path.length > 1) {
                    L.polyline(path, { pane: this._pane, ...STYLE_TRACK }).addTo(this._tracks);
                }
            }
        }

        return frame;
    }

    setVisible(visible) {
        this._visible = visible;
        for (const group of [this._systems, this._forecasts, this._tracks]) {
            if (visible) group.addTo(this._map); else group.remove();
        }
    }

    setShowForecasts(show) {
        this._showForecasts = show;
        if (this._currentIndex !== null) this.showFrame(this._currentIndex);
    }

    setShowTrails(show) {
        this._showTrails = show;
        if (this._currentIndex !== null) this.showFrame(this._currentIndex);
    }

    clear() {
        this._frames = [];
        this._paths = new Map();
        this._currentIndex = null;
        this._systems.clearLayers();
        this._forecasts.clearLayers();
        this._tracks.clearLayers();
    }

    /**
     * Extent of every system across all frames, or null if there are none.
     *
     * Needed because the map's default centre is not the selected radar —
     * tracking one radar while looking at another's region shows an empty map
     * and looks like a failure.
     */
    bounds() {
        const points = [];
        for (const path of this._paths.values()) points.push(...path);
        for (const frame of this._frames) {
            for (const feature of frame.features?.features || []) {
                if (feature.properties?.kind !== 'system') continue;
                const rings = feature.geometry?.type === 'Polygon'
                    ? [feature.geometry.coordinates[0]]
                    : feature.geometry?.type === 'MultiPolygon'
                        ? feature.geometry.coordinates.map(p => p[0]) : [];
                for (const ring of rings) {
                    for (const [lon, lat] of ring) points.push([lat, lon]);
                }
            }
        }
        return points.length ? L.latLngBounds(points) : null;
    }

    // ------------------------------------------------------------------ api

    /** Cube coverage per radar. `min_time` bounds how far back tracking can go. */
    static async availability(radar) {
        const q = radar ? `?radar=${encodeURIComponent(radar)}` : '';
        const res = await fetch(`${TRACKING_BASE}/availability${q}`);
        if (!res.ok) throw new Error(`availability failed: ${res.status}`);
        return (await res.json()).radars || [];
    }

    /**
     * Submit a run and poll until it finishes.
     *
     * Submit/poll rather than one call because a window is seconds of CPU. A
     * cached result comes back already complete, so the first poll resolves it.
     *
     * @param {function(object):void} onProgress called with each poll payload
     */
    static async run({ radar, start, end, config }, onProgress, pollMs = 1000) {
        const res = await fetch(`${TRACKING_BASE}/jobs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ radar, start, end, config }),
        });
        if (!res.ok) throw new Error(`submit failed: ${res.status} ${await res.text()}`);
        const job = await res.json();

        for (;;) {
            const poll = await fetch(`${TRACKING_BASE}/jobs/${job.job_id}`);
            if (poll.status === 404) {
                // In-memory store: a restart loses jobs. Resubmit, don't error.
                throw new Error('Job disappeared (service restarted). Try again.');
            }
            if (!poll.ok) throw new Error(`poll failed: ${poll.status}`);
            const state = await poll.json();
            if (onProgress) onProgress(state);
            if (state.status === 'done') return state;
            if (state.status === 'error') throw new Error(state.error || 'tracking failed');
            await new Promise(r => setTimeout(r, pollMs));
        }
    }
}

// -------------------------------------------------------------------- utils

/** Area-weighted-ish centroid: mean of the outer ring vertices. Good enough
 *  for a trail; the exact polygon centroid is not worth the arithmetic here. */
function centroidOf(geometry) {
    if (!geometry) return null;
    const rings = geometry.type === 'Polygon' ? [geometry.coordinates[0]]
        : geometry.type === 'MultiPolygon' ? geometry.coordinates.map(p => p[0])
            : null;
    if (!rings || !rings.length) return null;
    let x = 0, y = 0, n = 0;
    for (const ring of rings) {
        for (const [lon, lat] of ring) { x += lon; y += lat; n++; }
    }
    return n ? [y / n, x / n] : null;
}

const FIELD_LABELS = [
    ['core_max_dbz', 'Max dBZ núcleo', ' dBZ'],
    ['max', 'Max dBZ', ' dBZ'],
    ['core_area_km2', 'Área núcleo', ' km²'],
    ['echo_top_max_m', 'Tope de eco', ' m'],
    ['velocity', 'Velocidad', ' m/s'],
    ['direction', 'Dirección', '°'],
    ['dist_centroid_km', 'Distancia al radar', ' km'],
    ['h0_msnm', 'H0', ' m s.n.m.'],
];

function popupHtml(props) {
    const rows = FIELD_LABELS
        .filter(([key]) => props[key] !== undefined && props[key] !== null)
        .map(([key, label, unit]) => {
            const v = typeof props[key] === 'number' ? props[key].toFixed(1) : props[key];
            return `<tr><td style="padding-right:8px;opacity:.7">${label}</td><td><b>${v}${unit}</b></td></tr>`;
        })
        .join('');

    const verdict = props.is_convective === true
        ? '<span style="color:#ff3b30;font-weight:600">CONVECTIVO</span>'
        : '<span style="opacity:.6">no convectivo</span>';

    const lineage = (props.relationships || []).length
        ? `<div style="opacity:.6;font-size:.85em">deriva de ${props.relationships.length} sistema(s)</div>`
        : '';

    return `
        <div style="font-size:.9em;min-width:190px">
            <div style="margin-bottom:4px">${verdict} &middot; <code>${String(props.name).slice(0, 8)}</code></div>
            <div style="opacity:.7;font-size:.85em;margin-bottom:6px">${props.event || ''}</div>
            ${lineage}
            <table style="border-collapse:collapse">${rows}</table>
        </div>`;
}
