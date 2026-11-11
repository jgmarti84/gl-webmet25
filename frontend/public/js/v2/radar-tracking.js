/**
 * Storm tracking tool of the single-radar view (radar.html).
 *
 * A switchable overlay on top of what the view already shows. It owns its
 * panel (#panel-tracking), its requests and its layer; radar-app.js only:
 *   - calls initRadarTracking() once the view is allowed and ready,
 *   - calls tool.showAt(i) from the animator's frame hook,
 *   - calls tool.onFramesChanged() whenever the frame grid is rebuilt
 *     (new window, live refresh).
 *
 * What it tracks: the newest N volumes (3 / 5 / 10) of the view's window. Each
 * tracking frame is drawn on the grid slot of its volume, so only the last N
 * frames of the animation carry tracking.
 *
 * Costs nothing until used: the drawing module (shared/tracking.js) is loaded
 * the first time the panel opens, and no tracking request is made while the
 * switch is off. Where the tracking service is not deployed the button stays
 * hidden.
 */
import { authFetch } from '../auth-api.js';
import { canUseTracking } from '../shared/tracking-access.js';
import {
    LAST_N_CHOICES,
    restoreLastN,
    restoreLeads,
    trackingRequest,
} from '../shared/tracking-prefs.js';
import { buildTrackingSlotMap } from './radar-utils.js';

const KEY_ENABLED = 'webmet25_tracking_enabled';
const KEY_LAST_N = 'webmet25_tracking_last_n';
const KEY_LEADS = 'webmet25_tracking_leads';
const KEY_TRAILS = 'webmet25_tracking_trails';
// Shared with the standalone /tracking page: the same four settings.
const PARAMS_KEY = 'webmet25_tracking_params';

const PARAM_DEFAULTS = { cappi_height_m: 2500, dbz_threshold: 35, min_area_km2: 50, apply_scale: true };
const PARAM_INPUTS = { cappi_height_m: 'trk-param-cappi', dbz_threshold: 'trk-param-dbz', min_area_km2: 'trk-param-area' };
const PARAM_SWITCHES = { apply_scale: 'trk-param-scale' };

const APPLY_LABEL = 'Recalcular seguimiento';
const APPLY_LABEL_DIRTY = 'Recalcular seguimiento (cambios sin aplicar)';

/** Grid rebuilds come in bursts (one per field layer); act once they settle. */
const FRAMES_SETTLE_MS = 400;

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
    apply_scale: 'Crecimiento en pronósticos',
    forecast_scale_max: 'Escala máx. del pronóstico (×)',
    solo_c2: 'Sólo criterio C2',
};

const el = id => document.getElementById(id);

/** The radar's cube coverage and the service's limits, or null when the
 *  tracking service does not answer (not deployed: 502/404). */
async function fetchRadarAvailability(radar) {
    try {
        const res = await authFetch(`api/tracking/radars/${encodeURIComponent(radar)}/availability`);
        if (!res.ok) return null;
        return await res.json();
    } catch {
        return null;
    }
}

/**
 * Set up the tool, or return null when this user/radar/deployment has none.
 *
 * @param {object} opts
 * @param {string} opts.radarCode
 * @param {L.Map}  opts.map
 * @param {object} opts.permissions      body of GET /permissions/me
 * @param {function(): {start: Date|null, end: Date|null}} opts.getWindow
 * @param {function(): Array} opts.getGridFrames      state.frames
 * @param {function(): number} opts.getCurrentFrame   index on screen
 */
export async function initRadarTracking(opts) {
    const button = el('btn-tracking');
    if (!button || !canUseTracking(opts.radarCode, opts.permissions)) return null;

    const info = await fetchRadarAvailability(opts.radarCode);
    if (!info) return null;   // service not deployed: no button at all

    button.style.display = '';
    if (!info.count) {
        button.disabled = true;
        button.title = 'Sin datos de seguimiento para este radar';
        button.setAttribute('aria-label', button.title);
        return null;
    }
    return new RadarTrackingTool(opts, info);
}

class RadarTrackingTool {
    constructor(opts, info) {
        this._opts = opts;
        this._maxLastN = info.max_last_n || Math.max(...LAST_N_CHOICES);

        this._module = null;        // shared/tracking.js, once loaded
        this._layer = null;         // TrackingLayer
        this._loading = null;       // Promise while the module loads

        this._enabled = localStorage.getItem(KEY_ENABLED) === '1';
        this._lastN = restoreLastN(localStorage.getItem(KEY_LAST_N), this._maxLastN);
        this._frames = [];
        this._slotMap = new Map();
        this._seq = 0;              // bumped by every request; older ones stop
        this._runParams = null;     // settings of the run on screen (for the "unapplied" flag)
        this._settleTimer = null;

        // Opening the panel the first time loads the drawing module and builds
        // the controls that depend on it. A saved "on" also loads it straight away.
        el('btn-tracking').addEventListener('click', () => this._ensureLoaded());
        if (this._enabled) this._ensureLoaded().then(() => this._run());
        this._updateBadge();
    }

    // ------------------------------------------------------------ public API

    /** Draw the tracking frame of grid slot `frameIndex` (or nothing). */
    showAt(frameIndex) {
        if (!this._layer || !this._enabled) return;
        const index = this._slotMap.get(frameIndex);
        this._layer.showFrame(index === undefined ? -1 : index);
    }

    /** The view rebuilt its frame grid: re-map, then re-ask for its window. */
    onFramesChanged() {
        if (!this._enabled) return;
        this._remap();
        clearTimeout(this._settleTimer);
        this._settleTimer = setTimeout(() => this._run(), FRAMES_SETTLE_MS);
    }

    // ---------------------------------------------------------------- setup

    _ensureLoaded() {
        if (!this._loading) {
            this._loading = import('../shared/tracking.js').then(module => {
                this._module = module;
                this._layer = new module.TrackingLayer(this._opts.map);
                this._buildControls();
            }).catch(err => {
                console.error('tracking module failed to load:', err);
                this._status('No se pudo cargar el seguimiento.', true);
                this._loading = null;
            });
        }
        return this._loading;
    }

    _buildControls() {
        const { FORECAST_LEADS, DEFAULT_FORECAST_LEADS, FORECAST_COLORS } = this._module;

        // On/off
        const toggle = el('toggle-tracking');
        toggle.checked = this._enabled;
        toggle.addEventListener('change', () => this._setEnabled(toggle.checked));

        // Last N volumes (choices above the service's cap are disabled)
        document.querySelectorAll('.trk-lastn-btn').forEach(btn => {
            const n = Number(btn.dataset.n);
            btn.disabled = n > this._maxLastN;
            btn.classList.toggle('active', n === this._lastN);
            btn.addEventListener('click', () => {
                if (n === this._lastN) return;
                this._lastN = n;
                localStorage.setItem(KEY_LAST_N, String(n));
                document.querySelectorAll('.trk-lastn-btn')
                    .forEach(b => b.classList.toggle('active', Number(b.dataset.n) === n));
                this._run();
            });
        });

        // Forecast leads: one checkbox per lead, its swatch in the lead's colour
        const leads = restoreLeads(localStorage.getItem(KEY_LEADS), FORECAST_LEADS, DEFAULT_FORECAST_LEADS);
        const box = el('trk-leads');
        box.innerHTML = '';
        for (const lead of FORECAST_LEADS) {
            const label = document.createElement('label');
            label.className = 'trk-lead';
            label.innerHTML =
                `<input type="checkbox" data-lead="${lead}"${leads.includes(lead) ? ' checked' : ''}>` +
                `<span class="trk-swatch" style="background:${FORECAST_COLORS[lead]}"></span>` +
                `<span>+${lead} min</span>`;
            box.appendChild(label);
        }
        box.addEventListener('change', () => {
            const chosen = [...box.querySelectorAll('input[data-lead]:checked')].map(i => Number(i.dataset.lead));
            localStorage.setItem(KEY_LEADS, JSON.stringify(chosen));
            this._layer.setForecastLeads(chosen);
        });
        this._layer.setForecastLeads(leads);

        // Trails
        const trails = el('toggle-trk-trails');
        trails.checked = localStorage.getItem(KEY_TRAILS) !== '0';
        this._layer.setShowTrails(trails.checked);
        trails.addEventListener('change', () => {
            localStorage.setItem(KEY_TRAILS, trails.checked ? '1' : '0');
            this._layer.setShowTrails(trails.checked);
        });

        // Tracking settings: applied only with "Recalcular seguimiento" (saved, then
        // used by every run from then on), never on a keystroke. Edits that differ
        // from the run on screen flag the button, as on the /tracking page.
        this._writeParams(this._restoreParams());
        el('btn-trk-apply').addEventListener('click', () => {
            const params = this._readParams();
            if (!params) return;
            localStorage.setItem(PARAMS_KEY, JSON.stringify(params));
            this._run();
            this._updateDirty();
        });
        el('btn-trk-reset').addEventListener('click', () => {
            this._writeParams(PARAM_DEFAULTS);
            this._updateDirty();
        });
        for (const id of [...Object.values(PARAM_INPUTS), ...Object.values(PARAM_SWITCHES)]) {
            el(id).addEventListener('input', () => this._updateDirty());
            el(id).addEventListener('change', () => this._updateDirty());
        }

        this._status(this._enabled ? '' : 'Activá el seguimiento para calcularlo sobre la ventana actual.');
    }

    // ---------------------------------------------------------------- state

    _setEnabled(on) {
        this._enabled = on;
        localStorage.setItem(KEY_ENABLED, on ? '1' : '0');
        this._updateBadge();
        if (on) {
            this._run();
        } else {
            this._seq++;                 // stop any pending request
            clearTimeout(this._settleTimer);
            this._frames = [];
            this._slotMap = new Map();
            this._runParams = null;
            this._updateDirty();
            this._layer?.clear();
            this._renderConfig(null);
            this._status('Activá el seguimiento para calcularlo sobre la ventana actual.');
        }
    }

    _updateBadge() {
        el('btn-tracking')?.classList.toggle('is-on', this._enabled);
    }

    _remap() {
        this._slotMap = buildTrackingSlotMap(this._frames, this._opts.getGridFrames());
        this.showAt(this._opts.getCurrentFrame());
    }

    /**
     * Ask for the current window. The overlay on screen stays until the new
     * result arrives (animation continuity); a newer request supersedes this one.
     */
    async _run() {
        if (!this._enabled) return;
        await this._ensureLoaded();
        if (!this._layer || !this._enabled) return;

        // The applied settings, not whatever is typed in the panel right now.
        const params = this._restoreParams();
        const request = trackingRequest(this._opts.radarCode, this._opts.getWindow(), this._lastN, params);
        if (!request) {
            this._status('Esperando la ventana de tiempo…');
            return;
        }

        const seq = ++this._seq;
        const isCancelled = () => seq !== this._seq || !this._enabled;
        if (!this._frames.length) this._status('Calculando seguimiento…');

        try {
            const result = await this._module.TrackingLayer.runForRadar(request, state => {
                const p = state.progress || {};
                if (state.status !== 'done' && p.volumes_total) {
                    this._status(`Procesando ${p.volumes_done}/${p.volumes_total} volúmenes…`);
                }
            }, { isCancelled });
            if (!result || isCancelled()) return;

            this._runParams = params;
            this._updateDirty();
            this._frames = result.frames || [];
            this._layer.setFrames(this._frames);
            this._remap();
            this._renderConfig(result.config_in_force);
            this._status(this._summary());
        } catch (err) {
            if (isCancelled()) return;
            console.warn('tracking run failed:', err);
            this._status('No se pudo calcular el seguimiento. Se reintentará con la próxima actualización.', true);
        }
    }

    _summary() {
        const n = this._frames.length;
        if (!n) return 'No hay volúmenes con datos de seguimiento en la ventana seleccionada.';
        const shown = new Set(this._slotMap.values()).size;
        const last = this._frames[n - 1].timestamp;
        const hhmm = new Date(last).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hour12: false });
        let text = `Seguimiento sobre ${n} ${n === 1 ? 'volumen' : 'volúmenes'} (último ${hhmm}).`;
        if (n < this._lastN) text += ` Sólo hay ${n} en la ventana.`;
        if (shown < n) text += ` ${n - shown} no coincide${n - shown === 1 ? '' : 'n'} con cuadros de la animación.`;
        return text;
    }

    // ------------------------------------------------------------ settings

    /** Flag the button while the panel's settings differ from the run on screen. */
    _updateDirty() {
        const button = el('btn-trk-apply');
        if (!button) return;
        const panel = this._readParams({ report: false });
        const dirty = !!this._runParams &&
            (!panel || Object.keys(PARAM_DEFAULTS).some(k => panel[k] !== this._runParams[k]));
        button.classList.toggle('dirty', dirty);
        button.textContent = dirty ? APPLY_LABEL_DIRTY : APPLY_LABEL;
    }

    _restoreParams() {
        let saved = {};
        try { saved = JSON.parse(localStorage.getItem(PARAMS_KEY)) || {}; } catch { /* defaults */ }
        const params = { ...PARAM_DEFAULTS };
        for (const [key, id] of Object.entries(PARAM_INPUTS)) {
            const v = Number(saved[key]);
            const input = el(id);
            if (saved[key] != null && Number.isFinite(v) && input) {
                params[key] = Math.min(Math.max(v, Number(input.min)), Number(input.max));
            }
        }
        for (const key of Object.keys(PARAM_SWITCHES)) {
            if (typeof saved[key] === 'boolean') params[key] = saved[key];
        }
        return params;
    }

    _writeParams(params) {
        for (const [key, id] of Object.entries(PARAM_INPUTS)) el(id).value = params[key];
        for (const [key, id] of Object.entries(PARAM_SWITCHES)) el(id).checked = !!params[key];
    }

    /** The settings in the panel, or null (with the browser's hint) if one is invalid. */
    _readParams({ report = true } = {}) {
        const params = {};
        for (const [key, id] of Object.entries(PARAM_INPUTS)) {
            const input = el(id);
            if (!input || input.value === '' || !input.checkValidity()) {
                if (report && input) input.reportValidity();
                return null;
            }
            params[key] = input.valueAsNumber;
        }
        for (const [key, id] of Object.entries(PARAM_SWITCHES)) params[key] = el(id).checked;
        return params;
    }

    // -------------------------------------------------------------- output

    _renderConfig(cfg) {
        const table = el('trk-config-table');
        if (!table) return;
        table.innerHTML = '';
        if (!cfg) return;
        for (const [key, label] of Object.entries(CONFIG_LABELS)) {
            if (cfg[key] === undefined || cfg[key] === null) continue;
            const row = table.insertRow();
            row.insertCell().textContent = label;
            const v = cfg[key];
            row.insertCell().textContent =
                Array.isArray(v) ? v.join(', ') : typeof v === 'boolean' ? (v ? 'sí' : 'no') : String(v);
        }
    }

    _status(message, isError = false) {
        const node = el('trk-status');
        if (!node) return;
        node.textContent = message;
        node.classList.toggle('error', !!isError);
    }
}
