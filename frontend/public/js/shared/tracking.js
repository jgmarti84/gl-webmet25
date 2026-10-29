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

import { authFetch } from '../auth-api.js';

const TRACKING_BASE = '/api/tracking';

/**
 * Styling. Everything is drawn over COLMAX, whose colormap spans greens,
 * yellows, reds and magentas — so no single line colour is safe. Every line is
 * drawn twice: a dark halo underneath and a light line on top, which reads on
 * any background. System interiors use SVG hatch patterns (see _ensurePatterns)
 * so the reflectivity stays visible between the stripes.
 *
 * Non-convective systems are detected but rejected by the filter — shown,
 * but clearly secondary, since "detected but rejected" and "nothing there" are
 * different states.
 */
const HATCH_CONV  = 'trk-hatch-conv';
const HATCH_PLAIN = 'trk-hatch-plain';
const HALO = { color: '#000000', opacity: 0.55, fill: false, dashArray: null, lineCap: 'round', lineJoin: 'round' };

const STYLE_CONVECTIVE = { color: '#ffffff', weight: 2.5, opacity: 1, fillColor: `url(#${HATCH_CONV})`, fillOpacity: 1 };
const STYLE_PLAIN      = { color: '#d9d9d9', weight: 1.8, opacity: 0.95, dashArray: '6,4', fillColor: `url(#${HATCH_PLAIN})`, fillOpacity: 1 };
const STYLE_FORECAST   = { color: '#ffd54f', weight: 2, opacity: 1, dashArray: '5,5', fill: false };
const STYLE_ARROW      = { color: '#ffd54f', weight: 2.5, opacity: 1, fill: false };
const STYLE_TRACK      = { color: '#4dd0e1', weight: 2.5, opacity: 1, fill: false };

/** Forecast leads (min) drawn as outlines, besides the furthest one. */
const FORECAST_OUTLINE_LEADS = [18, 36];

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
        // Own SVG renderer, so the hatch patterns can live in its <defs>.
        this._renderer = L.svg({ pane: this._pane });

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
     * Centroid trajectory per track id, accumulated across all frames, with the
     * frame index of each point so a frame only draws the path up to itself.
     *
     * Track identity is the `name` property: a UUID inherited at each
     * successful match, so systems sharing it across frames are one storm.
     * Note these ids are generated fresh per tracking run — stable within one
     * result set, not across runs.
     */
    _buildPaths() {
        this._paths = new Map();
        for (const [frameIndex, frame] of this._frames.entries()) {
            // A split gives several systems the parent's name in one frame;
            // keep the one continuing the path so the trail doesn't zig-zag.
            const byName = new Map();
            for (const feature of frame.features?.features || []) {
                const props = feature.properties || {};
                if (props.kind !== 'system') continue;
                const centre = centroidOf(feature.geometry);
                if (!centre) continue;
                if (!byName.has(props.name)) byName.set(props.name, []);
                byName.get(props.name).push(centre);
            }
            for (const [name, centres] of byName) {
                if (!this._paths.has(name)) this._paths.set(name, []);
                const path = this._paths.get(name);
                const last = path.length ? path[path.length - 1].latlng : null;
                const centre = last ? nearest(centres, last) : centres[0];
                path.push({ frame: frameIndex, latlng: centre });
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

        const systems = [];
        const live = new Map();        // track id -> centroids in this frame (a split shares a name)
        const forecasts = new Map();   // track id -> forecast features

        for (const feature of frame.features?.features || []) {
            const props = feature.properties || {};
            if (props.kind === 'system') {
                systems.push(feature);
                if (!live.has(props.name)) live.set(props.name, []);
                live.get(props.name).push(centroidOf(feature.geometry));
            } else if (props.kind === 'forecast') {
                if (!forecasts.has(props.name)) forecasts.set(props.name, []);
                forecasts.get(props.name).push(feature);
            }
        }

        // Drawing order = stacking order in the shared SVG: forecast areas, then
        // systems, then trails and forecast arrows. A system under a forecast
        // area still gets its click (popup); the area gets the hover elsewhere.
        const chains = this._showForecasts
            ? [...forecasts].flatMap(([name, features]) => forecastChains(live.get(name) || [], features))
                .map(chain => ({ origin: chain.origin, leads: leadsOf(chain.features) }))
                .filter(chain => chain.leads.length)
            : [];
        for (const chain of chains) this._drawForecastAreas(chain.leads);

        for (const feature of systems) {
            const props = feature.properties;
            const style = props.is_convective === true ? STYLE_CONVECTIVE : STYLE_PLAIN;
            this._halo(feature, style.weight).addTo(this._systems);
            L.geoJSON(feature, { pane: this._pane, renderer: this._renderer, style })
                .bindPopup(() => popupHtml(props))
                .addTo(this._systems);
        }

        // Trails: the path of each storm alive in this frame, up to this frame
        // only — drawing every path, or a storm's future positions, turns a busy
        // animation into an unreadable tangle.
        if (this._showTrails) {
            for (const name of live.keys()) {
                const path = (this._paths.get(name) || []).filter(p => p.frame <= index).map(p => p.latlng);
                if (path.length < 2) continue;
                this._line(path, STYLE_TRACK, this._tracks);
                for (const point of path.slice(0, -1)) {
                    L.circleMarker(point, { pane: this._pane, renderer: this._renderer, radius: 2.5,
                        color: '#000', weight: 1, opacity: 0.6, fillColor: STYLE_TRACK.color, fillOpacity: 1 })
                        .addTo(this._tracks);
                }
            }
        }

        for (const chain of chains) this._drawForecastArrow(chain.origin, chain.leads);

        this._ensurePatterns();
        return frame;
    }

    /**
     * One storm's forecast areas: the outlines of a few leads
     * (FORECAST_OUTLINE_LEADS + the furthest), fainter the further ahead.
     * Every lead's outline at once was unreadable. Lead times show on hover
     * only, so a busy frame isn't covered in labels.
     */
    _drawForecastAreas(leads) {
        const last = leads[leads.length - 1];
        const outlined = leads.filter(x => x === last || FORECAST_OUTLINE_LEADS.includes(x.lead));
        // Furthest first: nearer outlines end up on top and win the hover.
        for (let i = outlined.length - 1; i >= 0; i--) {
            const x = outlined[i];
            const fade = outlined.length > 1 ? i / (outlined.length - 1) : 0;  // 0 nearest .. 1 furthest
            const style = {
                ...STYLE_FORECAST,
                opacity: 1 - 0.4 * fade,
                weight: STYLE_FORECAST.weight - 0.6 * fade,
                // Transparent fill so the whole area (not just the line) takes the hover.
                fill: true, fillColor: STYLE_FORECAST.color, fillOpacity: 0,
            };
            this._halo(x.feature, style.weight).addTo(this._forecasts);
            const area = L.geoJSON(x.feature, { pane: this._pane, renderer: this._renderer, style })
                .bindTooltip(`Pronóstico +${x.lead} min`, { sticky: true });
            area.on('mouseover', () => area.setStyle({ fillOpacity: 0.15 }))
                .on('mouseout', () => area.setStyle({ fillOpacity: 0 }))
                .addTo(this._forecasts);
        }
    }

    /** The motion arrow: from the storm through every lead's centroid, a dot
     *  per lead (hover: lead time) and an arrowhead at the furthest. */
    _drawForecastArrow(origin, leads) {
        const last = leads[leads.length - 1];
        const path = (origin ? [origin] : []).concat(leads.map(x => x.centre));
        if (path.length >= 2) this._line(path, STYLE_ARROW, this._forecasts);
        for (const x of leads.slice(0, -1)) {
            L.circleMarker(x.centre, { pane: this._pane, renderer: this._renderer, radius: 3,
                color: '#000', weight: 1, opacity: 0.6, fillColor: STYLE_ARROW.color, fillOpacity: 1 })
                .bindTooltip(`Pronóstico +${x.lead} min`)
                .addTo(this._forecasts);
        }
        const from = path.length >= 2 ? path[path.length - 2] : null;
        L.marker(last.centre, {
            pane: this._pane,
            interactive: false,
            icon: L.divIcon({
                className: 'trk-arrow-tip',
                html: `<span class="trk-arrowhead" style="transform:rotate(${from ? bearingDeg(from, last.centre) : 90}deg)"></span>`,
                iconSize: [0, 0],
            }),
        }).addTo(this._forecasts);
    }

    /** Dark under-stroke for a geometry, so the line on top reads on any colour. */
    _halo(feature, weight) {
        return L.geoJSON(feature, {
            pane: this._pane, renderer: this._renderer, interactive: false,
            style: { ...HALO, weight: weight + 3 },
        });
    }

    /** A polyline with its halo. */
    _line(latlngs, style, group) {
        L.polyline(latlngs, { pane: this._pane, renderer: this._renderer, interactive: false,
            ...HALO, weight: style.weight + 3 }).addTo(group);
        L.polyline(latlngs, { pane: this._pane, renderer: this._renderer, interactive: false, ...style }).addTo(group);
    }

    /** Hatch patterns for system interiors, defined once in the layer's SVG. */
    _ensurePatterns() {
        const svg = this._renderer._container;
        if (!svg || svg.querySelector(`#${HATCH_CONV}`)) return;
        const ns = 'http://www.w3.org/2000/svg';
        const defs = svg.querySelector('defs') || svg.insertBefore(document.createElementNS(ns, 'defs'), svg.firstChild);
        const pattern = (id, size, angle, stripe, width, opacity, tint) => {
            const p = document.createElementNS(ns, 'pattern');
            p.setAttribute('id', id);
            p.setAttribute('patternUnits', 'userSpaceOnUse');
            p.setAttribute('width', size);
            p.setAttribute('height', size);
            p.setAttribute('patternTransform', `rotate(${angle})`);
            if (tint) {
                const bg = document.createElementNS(ns, 'rect');
                bg.setAttribute('width', size);
                bg.setAttribute('height', size);
                bg.setAttribute('fill', tint);
                p.appendChild(bg);
            }
            const line = document.createElementNS(ns, 'line');
            line.setAttribute('x1', 0); line.setAttribute('y1', 0);
            line.setAttribute('x2', 0); line.setAttribute('y2', size);
            line.setAttribute('stroke', stripe);
            line.setAttribute('stroke-width', width);
            line.setAttribute('stroke-opacity', opacity);
            p.appendChild(line);
            defs.appendChild(p);
        };
        // Convective: dense white stripes over a light dark tint (reads on bright echoes).
        pattern(HATCH_CONV, 7, 45, '#ffffff', 2.2, 0.8, 'rgba(0,0,0,0.15)');
        // Non-convective: sparse, thin, opposite angle.
        pattern(HATCH_PLAIN, 11, -45, '#d9d9d9', 1.2, 0.6, null);
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
        for (const path of this._paths.values()) points.push(...path.map(p => p.latlng));
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
        const res = await authFetch(`${TRACKING_BASE}/availability${q}`);
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
        const res = await authFetch(`${TRACKING_BASE}/jobs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ radar, start, end, config }),
        });
        if (!res.ok) throw new Error(`submit failed: ${res.status} ${await res.text()}`);
        const job = await res.json();

        for (;;) {
            const poll = await authFetch(`${TRACKING_BASE}/jobs/${job.job_id}`);
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

/** The point of `points` closest to `to` (all [lat, lon]). */
function nearest(points, to) {
    const d = p => (p[0] - to[0]) ** 2 + ((p[1] - to[1]) * Math.cos(to[0] * Math.PI / 180)) ** 2;
    return points.reduce((best, p) => (d(p) < d(best) ? p : best));
}

/**
 * Split one track name's forecast features into one chain per system. Usually
 * a name has one system and this is a no-op; after a split, several systems
 * share the parent's name, and drawing their forecasts as one path would
 * zig-zag between them. Each lead's polygons are attached to the nearest chain
 * end (starting from the systems' centroids).
 */
function forecastChains(origins, features) {
    const byLead = new Map();
    for (const f of features) {
        const lead = f.properties?.lead_min;
        const centre = centroidOf(f.geometry);
        if (lead == null || !centre) continue;
        if (!byLead.has(lead)) byLead.set(lead, []);
        byLead.get(lead).push({ feature: f, centre });
    }
    const leads = [...byLead.keys()].sort((a, b) => a - b);
    const chains = origins.filter(Boolean).map(origin => ({ origin, end: origin, features: [] }));
    if (!chains.length) chains.push({ origin: null, end: null, features: [] });
    for (const lead of leads) {
        const free = [...chains];
        for (const item of byLead.get(lead)) {
            const pool = free.length ? free : chains;
            const chain = pool[0].end
                ? pool.reduce((best, c) => (c.end && dist2(c.end, item.centre) < dist2(best.end, item.centre) ? c : best))
                : pool[0];
            chain.features.push(item.feature);
            chain.end = item.centre;
            free.splice(free.indexOf(chain), 1);
        }
    }
    return chains.filter(c => c.features.length);
}

/** Forecast features -> [{lead, centre, feature}] sorted by lead, unusable ones dropped. */
function leadsOf(features) {
    return features
        .map(f => ({ lead: f.properties?.lead_min, centre: centroidOf(f.geometry), feature: f }))
        .filter(x => x.centre && x.lead != null)
        .sort((a, b) => a.lead - b.lead);
}

function dist2(a, b) {
    return (a[0] - b[0]) ** 2 + ((a[1] - b[1]) * Math.cos(a[0] * Math.PI / 180)) ** 2;
}

/** Screen bearing (degrees clockwise from east) from a to b, for the arrowhead.
 *  Web Mercator is conformal, so scaling longitude by cos(lat) is enough. */
function bearingDeg(a, b) {
    const k = Math.cos(((a[0] + b[0]) / 2) * Math.PI / 180);
    return Math.atan2(-(b[0] - a[0]), (b[1] - a[1]) * k) * 180 / Math.PI;
}

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
