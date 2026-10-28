/**
 * Storm tracking page controller.
 *
 * A thin host around shared pieces, so the page behaves like the single-radar
 * view:
 *  - TrackingLayer (js/shared/tracking.js) draws systems, forecasts and trails;
 *  - MapManager (v2/map.js) owns the map and the COLMAX underlay: every frame's
 *    image is preloaded and swapped on one persistent overlay, so playback
 *    never blanks between frames;
 *  - AnimationController (v2/animation.js) owns playback, the slider, speed and
 *    the buttons of the #animation-controls panel (same panel as radar.html).
 * Live windows ("last N hours") re-anchor to the newest cube every minute,
 * exactly like the single-radar view's live mode.
 */

import { TrackingLayer } from './shared/tracking.js';
import { authFetch } from './auth-api.js';
import { indexCogsByMinute, closestCog } from './shared/colmax-match.js';
import { MapManager } from './v2/map.js';
import { AnimationController } from './v2/animation.js';
import { updateLiveIndicator, wireAnimationPanel } from './v2/radar-utils.js';
import { MS_PER_HOUR, DEFAULT_LIVE_REFRESH_INTERVAL_MS } from './v2/constants.js';

const API_V1 = '/api/v1';
const COLMAX = 'COLMAX';

const el = id => document.getElementById(id);

const state = {
    map: null,
    mapManager: null,
    animator: null,
    layer: null,
    availability: new Map(),
    frames: [],
    radar: null,
    windowEnd: null,       // Date of the newest cube in the loaded window
    liveHours: null,       // number while a live window is active, else null
    liveTimer: null,
    loading: false,
};

// ---------------------------------------------------------------- bootstrap

async function init() {
    state.mapManager = new MapManager('map');
    state.mapManager.init();
    // Grey basemap: neutral under the coloured system polygons.
    state.mapManager.setBasemap('argenmap_gris');
    state.map = state.mapManager.getMap();

    state.layer = new TrackingLayer(state.map);

    // AnimationController drives "the map" through showFrame(); this view
    // object forwards each frame to MapManager (COLMAX) and TrackingLayer.
    state.animator = new AnimationController({ showFrame: renderFrame });
    state.animator.initControls(null);
    state.animator.setOnLockChange(locked => {
        if (state.liveHours !== null) updateLiveIndicator(state.liveHours, locked);
    });
    wireAnimationPanel();

    el('btn-back').addEventListener('click', () => { window.location.href = '/'; });
    el('radar-select').addEventListener('change', () => { stopLive(); onRadarChange(); });
    el('window-select').addEventListener('change', onWindowChange);
    el('btn-run').addEventListener('click', run);
    el('btn-cog-refresh-now').addEventListener('click', () => refreshLive({ manual: true }));
    el('toggle-forecasts').addEventListener('change', e => state.layer.setShowForecasts(e.target.checked));
    el('toggle-trails').addEventListener('change', e => state.layer.setShowTrails(e.target.checked));
    el('toggle-colmax').addEventListener('change', rerenderCurrentFrame);
    document.addEventListener('keydown', onKey);

    onWindowChange();
    await loadRadars();
}

/** Radar list comes from cube availability, not the radar registry: a radar
 *  without cubes cannot be tracked, so offering it would only produce an
 *  empty result. */
async function loadRadars() {
    let radars = [];
    try {
        radars = await TrackingLayer.availability();
    } catch (err) {
        status(`No se pudo consultar la disponibilidad: ${err.message}`, true);
        return;
    }

    const select = el('radar-select');
    select.innerHTML = '';

    if (!radars.length) {
        select.innerHTML = '<option>— sin volúmenes indexados —</option>';
        el('btn-run').disabled = true;
        status('Ningún radar tiene cubos NetCDF indexados todavía.', true);
        return;
    }

    state.availability = new Map(radars.map(r => [r.radar_code, r]));
    for (const r of radars) {
        const opt = document.createElement('option');
        opt.value = r.radar_code;
        opt.textContent = `${r.radar_code} (${r.count})`;
        select.appendChild(opt);
    }
    onRadarChange();
}

/** Clamp the pickers to what actually exists. Retention prunes cubes, so the
 *  oldest available volume is a hard floor on how far back tracking can go. */
function onRadarChange() {
    const info = state.availability.get(el('radar-select').value);
    if (!info) return;

    el('radar-header-code').textContent = info.radar_code;
    el('coverage-note').textContent =
        `${info.count} volúmenes · ${fmt(info.min_time)} → ${fmt(info.max_time)}`;

    const min = new Date(info.min_time);
    const max = new Date(info.max_time);
    for (const id of ['start-input', 'end-input']) {
        el(id).min = toLocalInput(min);
        el(id).max = toLocalInput(max);
    }
    // Custom range default: the last two hours of what exists.
    const start = new Date(Math.max(min.getTime(), max.getTime() - 2 * MS_PER_HOUR));
    el('start-input').value = toLocalInput(start);
    el('end-input').value = toLocalInput(max);
}

/** "last N hours" windows are live; the custom range is a fixed window. */
function selectedHours() {
    const v = el('window-select').value;
    return v === 'custom' ? null : parseFloat(v);
}

function onWindowChange() {
    el('custom-range').classList.toggle('hidden', selectedHours() !== null);
    // A different window needs a new run; don't keep refreshing the old one.
    stopLive();
}

// ------------------------------------------------------------------- run

async function run() {
    const radar = el('radar-select').value;
    const hours = selectedHours();
    stopLive();

    let start, end;
    if (hours !== null) {
        const info = await latestAvailability(radar);
        if (!info) { status('No hay volúmenes para ese radar.', true); return; }
        ({ start, end } = liveWindow(info, hours));
    } else {
        start = fromLocalInput(el('start-input').value);
        end = fromLocalInput(el('end-input').value);
        if (!start || !end || start >= end) {
            status('Rango de tiempo inválido.', true);
            return;
        }
    }

    // Fresh start: clear the previous run before loading the new one.
    state.animator.pause();
    state.animator.updateFrames([], COLMAX);
    state.layer.clear();
    state.mapManager._clearAllOverlays();
    el('animation-controls').classList.add('hidden');

    el('btn-run').disabled = true;
    const ok = await loadWindow(radar, start, end, { fit: true, hours });
    el('btn-run').disabled = false;

    if (ok && hours !== null) startLive(hours);
}

/**
 * Run tracking for [start, end], preload the COLMAX underlay for every frame,
 * then hand the frames to the animator in one step (old frames keep playing
 * until the new ones are ready).
 */
async function loadWindow(radar, start, end, { fit = false, hours = null } = {}) {
    if (state.loading) return false;
    state.loading = true;
    try {
        status('Enviando…');
        const result = await TrackingLayer.run(
            { radar, start, end },
            s => {
                const p = s.progress || {};
                if (s.status === 'running' && p.volumes_total) {
                    status(`Procesando ${p.volumes_done}/${p.volumes_total} volúmenes…`);
                } else if (s.status === 'pending') {
                    status('En cola…');
                }
            }
        );

        const frames = result.frames || [];
        if (!frames.length) {
            status('No hay volúmenes en ese rango.', true);
            return false;
        }

        // Pair each frame with its volume's COLMAX and preload every image
        // (MapManager), the same way the single-radar view loads its frames.
        const index = await loadColmaxIndex(radar, start, end);
        const cogsByFrame = new Map();
        frames.forEach((frame, i) => {
            const cog = closestCog(index, frame.timestamp);
            frame.cogsByRadar = cog ? { [radar]: cog } : {};
            if (cog) cogsByFrame.set(i, new Map([[radar, cog]]));
        });
        if (cogsByFrame.size) {
            await state.mapManager.loadFrames(cogsByFrame, COLMAX, {}, (done, total) => {
                status(`Cargando COLMAX ${done}/${total}…`);
            });
        } else {
            state.mapManager._clearAllOverlays();
        }

        state.radar = radar;
        state.frames = frames;
        state.windowEnd = new Date(frames[frames.length - 1].timestamp);
        state.layer.setFrames(frames);
        renderConfig(result.config_in_force);

        el('time-window-label').textContent = hours !== null
            ? `Últimas ${fmtHours(hours)} h`
            : 'Rango personalizado';
        el('animation-controls').classList.remove('hidden');

        // Same as the single-radar view: (re)load lands on the newest frame.
        state.animator.updateFrames(frames, COLMAX, frames.length - 1);

        if (fit) {
            // The map opens on Córdoba, but the selected radar may be anywhere.
            // Without this the storms land off-screen and the run looks empty.
            const extent = state.layer.bounds();
            if (extent) state.map.fitBounds(extent, { padding: [80, 80], maxZoom: 9 });
        }

        const withData = frames.filter(f => f.features?.features?.length).length;
        const tracks = countTracks(frames);
        status(
            `${frames.length} volúmenes · ${withData} con sistemas · ` +
            `${tracks.total} tramas, ${tracks.multi} seguidas` +
            (cogsByFrame.size < frames.length ? ` · COLMAX en ${cogsByFrame.size}/${frames.length}` : '') +
            (result.cached ? ' · (cacheado)' : '')
        );
        return true;
    } catch (err) {
        status(err.message, true);
        return false;
    } finally {
        state.loading = false;
    }
}

/** Distinct tracks, and how many span more than one frame — the second number
 *  is the one that says tracking actually associated anything. */
function countTracks(frames) {
    const seen = new Map();
    for (const f of frames) {
        for (const x of f.features?.features || []) {
            if (x.properties?.kind !== 'system') continue;
            seen.set(x.properties.name, (seen.get(x.properties.name) || 0) + 1);
        }
    }
    return { total: seen.size, multi: [...seen.values()].filter(n => n > 1).length };
}

// ------------------------------------------------------------------ live

async function latestAvailability(radar) {
    try {
        const radars = await TrackingLayer.availability(radar);
        return radars.find(r => r.radar_code === radar) || null;
    } catch (err) {
        console.warn('Tracking availability failed:', err);
        return null;
    }
}

/** [newest cube − hours, newest cube], clamped to the oldest cube. */
function liveWindow(info, hours) {
    const max = new Date(info.max_time);
    const min = new Date(info.min_time);
    // +1 s so the newest cube is inside the window whatever its sub-second part.
    const end = new Date(max.getTime() + 1000);
    const start = new Date(Math.max(min.getTime(), max.getTime() - hours * MS_PER_HOUR));
    return { start: toIsoSeconds(start), end: toIsoSeconds(end) };
}

function startLive(hours) {
    stopLive();
    state.liveHours = hours;
    state.liveTimer = setInterval(() => refreshLive(), DEFAULT_LIVE_REFRESH_INTERVAL_MS);
    updateLiveIndicator(hours, state.animator.isLockedToLatest());
}

function stopLive() {
    if (state.liveTimer) clearInterval(state.liveTimer);
    state.liveTimer = null;
    state.liveHours = null;
    updateLiveIndicator(null);
}

/**
 * Slide the live window forward when a newer cube exists. Called every
 * minute, and by the ↻ button (manual) to check right away.
 */
async function refreshLive({ manual = false } = {}) {
    if (state.liveHours === null || state.loading || !state.radar) return;
    const hours = state.liveHours;
    const info = await latestAvailability(state.radar);
    if (!info) return;
    if (state.windowEnd && new Date(info.max_time) <= state.windowEnd) {
        if (manual) status('Sin volúmenes nuevos todavía.');
        return;
    }
    const { start, end } = liveWindow(info, hours);
    await loadWindow(state.radar, start, end, { hours });
}

// ---------------------------------------------------------------- COLMAX

/** /api/v1/cogs caps page_size at 200; a long window needs several pages. */
const COGS_PAGE_SIZE = 200;
const COGS_MAX_PAGES = 20;

/**
 * COLMAX COGs for the window, bucketed by minute (colmax-match.js). Several
 * volumes can have a COLMAX in the same minute; closestCog picks the cube's own.
 *
 * Failure is non-fatal — the tracking layer is the point of the page — but it
 * is logged, so a broken underlay is visible in the console instead of silent.
 */
async function loadColmaxIndex(radar, start, end) {
    const index = new Map();
    try {
        for (let page = 1; page <= COGS_MAX_PAGES; page++) {
            const params = new URLSearchParams({
                radar_code: radar, product_key: COLMAX,
                start_time: start, end_time: end,
                page: String(page), page_size: String(COGS_PAGE_SIZE),
            });
            const res = await authFetch(`${API_V1}/cogs?${params}`);
            if (!res.ok) {
                console.warn(`COLMAX underlay: /cogs returned ${res.status}`);
                return index;
            }
            const body = await res.json();
            const cogs = body.cogs || [];
            indexCogsByMinute(index, cogs);
            if (cogs.length < COGS_PAGE_SIZE || page * COGS_PAGE_SIZE >= (body.total ?? 0)) return index;
        }
        console.warn(`COLMAX underlay: window has more than ${COGS_MAX_PAGES * COGS_PAGE_SIZE} COGs; showing the newest only`);
    } catch (err) {
        console.warn('COLMAX underlay: failed to load', err);
    }
    return index;
}

// ----------------------------------------------------------------- frames

/**
 * Called by AnimationController for every frame shown (play, slider, buttons).
 * `radarCodes` / `holdCodes` come from each frame's cogsByRadar, so a frame
 * without its own COLMAX keeps showing the previous image (one-gap hold), as in
 * the single-radar view.
 */
function renderFrame(index, radarCodes = [], _productKey, holdCodes = []) {
    const showColmax = el('toggle-colmax').checked;
    state.mapManager.showFrame(index, showColmax ? radarCodes : [], COLMAX, showColmax ? holdCodes : []);
    const frame = state.layer.showFrame(index);
    renderFrameInfo(frame);
}

function rerenderCurrentFrame() {
    if (!state.frames.length) return;
    const index = state.animator.getCurrentIndex();
    const ctx = state.animator.getFrameContext(index);
    if (!ctx) return;
    const radarCodes = [...Object.keys(ctx.frame.cogsByRadar || {}), ...ctx.holdCodes];
    renderFrame(index, radarCodes, COLMAX, ctx.holdCodes);
}

function renderFrameInfo(frame) {
    if (!frame) return;
    const counts = frame.counts || {};
    const verdict = el('frame-verdict');
    if (frame.gate_passed) {
        verdict.textContent = '';
        el('frame-counts').textContent =
            `detectados ${counts.detected ?? 0} · convectivos ${counts.convective ?? 0} · seguidos ${counts.tracked ?? 0}`;
    } else {
        // A discarded volume is not missing data, and the numbers behind the
        // decision are the only way to explain later why nothing appeared.
        const g = frame.gate || {};
        verdict.textContent = 'VOLUMEN DESCARTADO';
        el('frame-counts').textContent = g.umbral_m != null
            ? `tope ${fmtNum(g.tope_max_m)} m < umbral ${fmtNum(g.umbral_m)} m (H0 ${fmtNum(g.h0_msnm)} m, ${g.h0_fuente || '—'})`
            : '';
    }
}

/** Keyboard shortcuts (tracking page only): Space plays/pauses, arrows step. */
function onKey(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    if (!state.frames.length) return;
    if (e.code === 'Space') { e.preventDefault(); state.animator.toggle(); }
    else if (e.code === 'ArrowLeft') { state.animator.pause(); state.animator.previous(); }
    else if (e.code === 'ArrowRight') { state.animator.pause(); state.animator.next(); }
}

// ------------------------------------------------------------------ misc

const CONFIG_LABELS = {
    cappi_height_m: 'CAPPI (m sobre antena)',
    dbz_threshold: 'Umbral de detección (dBZ)',
    min_area_km2: 'Área mínima (km²)',
    echotop_min_above_h0_m: 'Tope mínimo sobre H0 (m)',
    rhohv_qc_min: 'RHOHV mínimo (QC)',
    r_max_km: 'Radio máximo (km)',
    strategy: 'Estrategia de asociación',
    overlap: 'Solape mínimo',
    max_gap_tracking_min: 'Hueco máximo (min)',
    forecast_intervals: 'Pronósticos (min)',
    solo_c2: 'Sólo criterio C2',
};

function renderConfig(cfg) {
    const table = el('config-table');
    table.innerHTML = '';
    if (!cfg) return;
    for (const [key, label] of Object.entries(CONFIG_LABELS)) {
        if (cfg[key] === undefined) continue;
        const row = table.insertRow();
        row.insertCell().textContent = label;
        const cell = row.insertCell();
        cell.textContent = Array.isArray(cfg[key]) ? cfg[key].join(', ') : String(cfg[key]);
        cell.style.fontWeight = '600';
    }
}

function status(message, isError = false) {
    const node = el('run-status');
    node.textContent = message;
    node.classList.toggle('error', !!isError);
}

const fmt = iso => iso ? String(iso).replace('T', ' ').replace(/(\.\d+)?Z?$/, '') + ' UTC' : '—';
const fmtNum = v => (v == null ? '—' : Math.round(v));
const fmtHours = h => String(h).replace('.', ',');
const toIsoSeconds = d => d.toISOString().slice(0, 19) + 'Z';
const toLocalInput = d => new Date(d.getTime() - d.getTimezoneOffset() * 0).toISOString().slice(0, 16);
const fromLocalInput = v => (v ? `${v}:00Z` : null);

init();
