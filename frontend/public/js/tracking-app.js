/**
 * Storm tracking page controller.
 *
 * A thin host: it wires DOM controls to TrackingLayer (js/shared/tracking.js)
 * and to the existing COG frames API for the COLMAX underlay. All the layer
 * behaviour lives in the module so it can later be mounted inside radar.html
 * without a rewrite.
 */

import { TrackingLayer } from './shared/tracking.js';

const API_V1 = '/api/v1';

const el = id => document.getElementById(id);

const state = {
    map: null,
    layer: null,
    colmax: null,          // L.layerGroup of imageOverlays, one per frame
    colmaxByTime: new Map(),
    frames: [],
    index: 0,
    playing: false,
    timer: null,
};

// ---------------------------------------------------------------- bootstrap

async function init() {
    state.map = L.map('map', { center: [-31.42, -64.18], zoom: 7, zoomControl: true });

    // ESRI light canvas: neutral under coloured polygons, and no API key.
    L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
        { maxZoom: 16, attribution: 'Esri' }
    ).addTo(state.map);

    state.layer = new TrackingLayer(state.map);
    state.colmax = L.layerGroup().addTo(state.map);

    el('btn-back').addEventListener('click', () => { window.location.href = '/'; });
    el('radar-select').addEventListener('change', onRadarChange);
    el('btn-run').addEventListener('click', run);
    el('toggle-forecasts').addEventListener('change', e => state.layer.setShowForecasts(e.target.checked));
    el('toggle-trails').addEventListener('change', e => state.layer.setShowTrails(e.target.checked));
    el('toggle-colmax').addEventListener('change', () => showFrame(state.index));
    el('frame-slider').addEventListener('input', e => { pause(); showFrame(+e.target.value); });
    el('btn-first').addEventListener('click', () => { pause(); showFrame(0); });
    el('btn-prev').addEventListener('click', () => { pause(); showFrame(state.index - 1); });
    el('btn-next').addEventListener('click', () => { pause(); showFrame(state.index + 1); });
    el('btn-last').addEventListener('click', () => { pause(); showFrame(state.frames.length - 1); });
    el('btn-play').addEventListener('click', togglePlay);
    document.addEventListener('keydown', onKey);

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
    // Default to the last two hours of what exists — long enough for tracks to
    // form, short enough to come back quickly.
    const start = new Date(Math.max(min.getTime(), max.getTime() - 2 * 3600 * 1000));
    el('start-input').value = toLocalInput(start);
    el('end-input').value = toLocalInput(max);
}

// ------------------------------------------------------------------- run

async function run() {
    const radar = el('radar-select').value;
    const start = fromLocalInput(el('start-input').value);
    const end = fromLocalInput(el('end-input').value);

    if (!start || !end || start >= end) {
        status('Rango de tiempo inválido.', true);
        return;
    }

    el('btn-run').disabled = true;
    state.layer.clear();
    state.colmax.clearLayers();
    state.colmaxByTime = new Map();
    el('frame-controls').classList.add('hidden');
    status('Enviando…');

    try {
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

        state.frames = result.frames || [];
        renderConfig(result.config_in_force);

        if (!state.frames.length) {
            status('No hay volúmenes en ese rango.', true);
            return;
        }

        state.layer.setFrames(state.frames);
        await loadColmax(radar, start, end);

        el('frame-slider').max = String(state.frames.length - 1);
        el('frame-controls').classList.remove('hidden');
        showFrame(0);

        // The map opens on Córdoba, but the selected radar may be anywhere.
        // Without this the storms land off-screen and the run looks empty.
        const extent = state.layer.bounds();
        if (extent) state.map.fitBounds(extent, { padding: [80, 80], maxZoom: 9 });

        const withData = state.frames.filter(f => f.features?.features?.length).length;
        const tracks = countTracks(state.frames);
        status(
            `${state.frames.length} volúmenes · ${withData} con sistemas · ` +
            `${tracks.total} tramas, ${tracks.multi} seguidas` +
            (result.cached ? ' · (cacheado)' : '')
        );
    } catch (err) {
        status(err.message, true);
    } finally {
        el('btn-run').disabled = false;
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

// ---------------------------------------------------------------- COLMAX

/**
 * Fetch COLMAX COGs for the window and index them by observation time.
 *
 * Reuses the existing COG/frames API — radarlib already produces COLMAX, so
 * this needs no new backend. Failure is non-fatal: the tracking layer is the
 * point of the page and an absent underlay should not break it.
 */
async function loadColmax(radar, start, end) {
    try {
        const params = new URLSearchParams({
            radar_codes: radar, product: 'COLMAX',
            time_from: start, time_to: end, limit: '500',
        });
        const res = await fetch(`${API_V1}/cogs?${params}`);
        if (!res.ok) return;
        const cogs = (await res.json()).cogs || [];
        for (const cog of cogs) {
            if (!cog.bbox) continue;
            state.colmaxByTime.set(isoMinute(cog.observation_time), cog);
        }
    } catch {
        /* underlay is optional */
    }
}

function showColmaxFor(frame) {
    state.colmax.clearLayers();
    if (!el('toggle-colmax').checked || !frame) return;
    const cog = state.colmaxByTime.get(isoMinute(frame.timestamp));
    if (!cog?.bbox) return;
    const b = cog.bbox;
    L.imageOverlay(
        `${API_V1}/frames/${cog.id}/image.png`,
        [[b.min_lat, b.min_lon], [b.max_lat, b.max_lon]],
        { opacity: 0.75 }
    ).addTo(state.colmax);
}

// ----------------------------------------------------------------- frames

function showFrame(index) {
    if (!state.frames.length) return;
    index = Math.max(0, Math.min(index, state.frames.length - 1));
    state.index = index;

    const frame = state.layer.showFrame(index);
    showColmaxFor(frame);

    el('frame-slider').value = String(index);
    el('frame-counter').textContent = `${index + 1} / ${state.frames.length}`;
    el('frame-time').textContent = fmt(frame.timestamp);

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

function togglePlay() {
    state.playing ? pause() : play();
}

function play() {
    if (!state.frames.length) return;
    state.playing = true;
    el('btn-play').textContent = '⏸';
    state.timer = setInterval(() => {
        showFrame(state.index >= state.frames.length - 1 ? 0 : state.index + 1);
    }, 700);
}

function pause() {
    state.playing = false;
    el('btn-play').textContent = '▶';
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
}

function onKey(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
    else if (e.code === 'ArrowLeft') { pause(); showFrame(state.index - 1); }
    else if (e.code === 'ArrowRight') { pause(); showFrame(state.index + 1); }
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
/** COG and cube timestamps come from the same volume but may differ in
 *  sub-minute precision, so match at minute resolution. */
const isoMinute = iso => String(iso).slice(0, 16);
const toLocalInput = d => new Date(d.getTime() - d.getTimezoneOffset() * 0).toISOString().slice(0, 16);
const fromLocalInput = v => (v ? `${v}:00Z` : null);

init();
