/**
 * app-v2.js — v2 frontend orchestrator.
 *
 * Mirrors app.js exactly except for the MapManager integration:
 *   v1: L.tileLayer via preloadFrames / cachedFrameLayers
 *   v2: L.imageOverlay via loadFrames / _frameImages
 *
 * Key behavioral changes
 * ----------------------
 * - getTileParams() returns { colormap, vmin, vmax } (not { cmap, vmin, vmax })
 *   because the /frames/ endpoint uses `colormap` as the query-param name.
 * - loadTimeRangeCogs() calls mapManager.loadFrames() instead of preloadFrames().
 * - onFrameChange() calls mapManager.showFrame() instead of showCachedFrame().
 * - addRadarIncremental() calls mapManager.addRadarToFrame() / addFrame().
 * - removeRadarIncremental() calls mapManager.removeFrame() / removeFrameSlot().
 * - refreshLiveWindow() uses the same MapManager v2 API for incremental diffs.
 * - applyColormapChange() uses mapManager.updateParams() instead of
 *   preloadFramesBackground / commitPendingFrames.
 * - loadLatestCogs() builds a single-frame cogsByFrame and calls loadFrames().
 * - AnimationController v2 takes mapManager in the constructor and wires
 *   controls via initControls().
 */

import { api } from './api.js';
import { MapManager } from './map-v2.js';
import { AnimationController } from './animation-v2.js';
import { UIControls } from './controls.js';
import { LegendRenderer } from './legend.js';

// =============================================================================
// CONSTANTS (identical to app.js)
// =============================================================================

const MS_PER_HOUR = 3600 * 1000;
const BUCKET_TOLERANCE_MINUTES = 5;
const DEFAULT_LIVE_REFRESH_INTERVAL_MS = 5 * 60 * 1000;
const DEFAULT_RADAR_STATUS_REFRESH_INTERVAL_MS = 10 * 60 * 1000;
const LIVE_REFRESH_MAX_COGS = 200;
const GEOLOCATION_AUTO_SELECT_COUNT = 3;
const GEOLOCATION_AUTO_LOAD_HOURS = 3;
const GEOLOCATION_AUTO_PRODUCT = 'DBZHo';
const DEFAULT_TIME_WINDOW_HOURS = 3;
const DEFAULT_FIELD_OPACITY = 0.7;
const DEFAULT_COVERAGE_OPACITY = 0.1;

// =============================================================================
// APPLICATION STATE
// =============================================================================

const state = {
    radars: [],
    products: [],
    cogs: [],
    selectedRadars: [],
    selectedProduct: null,
    showUnfilteredProducts: false,
    showInactiveRadars: false,
    activeTimeWindowHours: DEFAULT_TIME_WINDOW_HOURS,
    selectedColormap: null,
    currentVmin: null,
    currentVmax: null,
    fieldOpacity: {},
    mapManager: null,
    animator: null,
    ui: null,
    legend: null,
    hasZoomedToBounds: false,
    animationMode: null,
    liveHours: null,
    liveRefreshInterval: null,
    radarStatusRefreshInterval: null,
    coverageVisible: false,
    coverageOpacity: DEFAULT_COVERAGE_OPACITY,
};

// =============================================================================
// HELPERS
// =============================================================================

function getCogBucketKey(timestamp) {
    const bucketMs = BUCKET_TOLERANCE_MINUTES * 60 * 1000;
    const t = new Date(timestamp).getTime();
    return Math.round(t / bucketMs) * bucketMs;
}

function groupCogsByTimestamp(cogs, toleranceMinutes = BUCKET_TOLERANCE_MINUTES) {
    const bucketMs = toleranceMinutes * 60 * 1000;
    const buckets = new Map();
    cogs.forEach(cog => {
        const t = new Date(cog.observation_time).getTime();
        const key = Math.round(t / bucketMs) * bucketMs;
        if (!buckets.has(key)) {
            buckets.set(key, { timestamp: cog.observation_time, cogsByRadar: {} });
        }
        const frame = buckets.get(key);
        if (!frame.cogsByRadar[cog.radar_code]) {
            frame.cogsByRadar[cog.radar_code] = cog;
        }
    });
    return Array.from(buckets.entries())
        .sort((a, b) => a[0] - b[0])
        .map(([, frame]) => frame);
}

/**
 * Convert a groupedFrames array (app.js state.cogs format) to the
 * Map<frameIndex, Map<radarCode, cogObject>> format expected by MapManager.loadFrames().
 *
 * @param {Array} groupedFrames  [{timestamp, cogsByRadar: {code: cog}}, …]
 * @returns {Map<number, Map<string, Object>>}
 */
function buildCogsByFrameMap(groupedFrames) {
    const cogsByFrame = new Map();
    groupedFrames.forEach((frame, idx) => {
        const radarMap = new Map();
        Object.entries(frame.cogsByRadar).forEach(([code, cog]) => radarMap.set(code, cog));
        cogsByFrame.set(idx, radarMap);
    });
    return cogsByFrame;
}

// =============================================================================
// SETTINGS HELPERS (localStorage) — identical to app.js
// =============================================================================

const SETTINGS_KEY_SHOW_INACTIVE      = 'webmet25_show_inactive_radars';
const SETTINGS_KEY_SHOW_FILTERED      = 'webmet25_show_filtered_fields';
const SETTINGS_KEY_REFRESH_INTERVAL   = 'webmet25_radar_refresh_interval_min';
const SETTINGS_KEY_LIVE_REFRESH_INTERVAL = 'webmet25_live_refresh_interval_ms';
const SETTINGS_KEY_COVERAGE_VISIBLE   = 'webmet25_coverage_visible';
const SETTINGS_KEY_COVERAGE_OPACITY   = 'webmet25_coverage_opacity';
const SETTINGS_KEY_ACTIVE_ONLY_LEGACY = 'webmet25_active_only';

function getSettingShowInactive() {
    const stored = localStorage.getItem(SETTINGS_KEY_SHOW_INACTIVE);
    if (stored !== null) return stored === 'true';
    const legacy = localStorage.getItem(SETTINGS_KEY_ACTIVE_ONLY_LEGACY);
    if (legacy !== null) {
        const showInactive = legacy === 'false';
        localStorage.setItem(SETTINGS_KEY_SHOW_INACTIVE, String(showInactive));
        return showInactive;
    }
    return false;
}

function getSettingShowFiltered() {
    const stored = localStorage.getItem(SETTINGS_KEY_SHOW_FILTERED);
    return stored === 'true';
}

function getSettingRefreshIntervalMs() {
    const stored = localStorage.getItem(SETTINGS_KEY_REFRESH_INTERVAL);
    if (stored === null) return DEFAULT_RADAR_STATUS_REFRESH_INTERVAL_MS;
    const minutes = parseFloat(stored);
    if (isNaN(minutes) || minutes <= 0) return DEFAULT_RADAR_STATUS_REFRESH_INTERVAL_MS;
    return Math.min(minutes, 60) * 60 * 1000;
}

function setSettingRefreshIntervalMin(minutes) {
    localStorage.setItem(SETTINGS_KEY_REFRESH_INTERVAL, String(minutes));
}

function getLiveRefreshIntervalMs() {
    const stored = localStorage.getItem(SETTINGS_KEY_LIVE_REFRESH_INTERVAL);
    if (stored === null) return DEFAULT_LIVE_REFRESH_INTERVAL_MS;
    const ms = parseInt(stored, 10);
    if (isNaN(ms) || ms <= 0) return DEFAULT_LIVE_REFRESH_INTERVAL_MS;
    return Math.min(Math.max(ms, 60 * 1000), 30 * 60 * 1000);
}

function setLiveRefreshIntervalMs(ms) {
    localStorage.setItem(SETTINGS_KEY_LIVE_REFRESH_INTERVAL, String(ms));
}

// =============================================================================
// GEOLOCATION HELPERS (identical to app.js)
// =============================================================================

function haversineKm(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2 +
              Math.cos(lat1 * Math.PI / 180) *
              Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function getBrowserGeolocation() {
    return new Promise((resolve, reject) => {
        if (!navigator.geolocation) { reject(new Error('Geolocation not supported')); return; }
        navigator.geolocation.getCurrentPosition(
            pos => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
            err => reject(err),
            { timeout: 8000, maximumAge: 60000 }
        );
    });
}

async function getIPGeolocation() {
    const resp = await fetch('https://ipapi.co/json/', { signal: AbortSignal.timeout(6000) });
    if (!resp.ok) throw new Error(`IP geo failed: ${resp.status}`);
    const data = await resp.json();
    if (!data.latitude || !data.longitude) throw new Error('No coordinates in IP geo response');
    return { lat: data.latitude, lon: data.longitude };
}

// =============================================================================
// MAIN APPLICATION
// =============================================================================

const app = {
    async init() {
        state.ui = new UIControls();
        state.ui.setStatus('Initializing...', 'loading');

        state.showInactiveRadars    = getSettingShowInactive();
        state.showUnfilteredProducts = getSettingShowFiltered();

        const storedCoverageVisible = localStorage.getItem(SETTINGS_KEY_COVERAGE_VISIBLE);
        state.coverageVisible = storedCoverageVisible === 'true';
        const storedCoverageOpacity = localStorage.getItem(SETTINGS_KEY_COVERAGE_OPACITY);
        state.coverageOpacity = storedCoverageOpacity !== null
            ? parseFloat(storedCoverageOpacity)
            : DEFAULT_COVERAGE_OPACITY;

        try {
            await this.waitForLeaflet();

            // v2: MapManager takes the element ID
            state.mapManager = new MapManager('map');
            state.mapManager.init();

            // v2: AnimationController takes mapManager
            state.animator = new AnimationController(state.mapManager);
            state.animator.setOnFrameChange((index, frame) => {
                this.onFrameChange(index, frame);
            });

            state.legend = new LegendRenderer('legend-container');

            await this.loadInitialData();
            this.setupEventListeners();
            this.initSettingsPanel();

            // v2: wire animation DOM controls now that ui and animator exist
            state.animator.initControls(state.ui);

            state.ui.enableAnimationControls(false);
            state.ui.enableNavButtons(false);

            state.ui.setStatus('Ready', 'success');
            this.startRadarStatusRefresh();
            this.tryGeolocationAutoInit();

        } catch (error) {
            console.error('Init error:', error);
            state.ui.setStatus(`Error: ${error.message}`, 'error');
        }
    },

    async waitForLeaflet(maxWait = 5000) {
        const startTime = Date.now();
        while (typeof L === 'undefined') {
            if (Date.now() - startTime > maxWait) {
                throw new Error('Leaflet library failed to load. Please check your internet connection.');
            }
            await new Promise(resolve => setTimeout(resolve, 100));
        }
    },

    async loadInitialData() {
        state.radars = await api.getRadars(!state.showInactiveRadars);
        state.ui.populateRadarCheckboxes(state.radars, state.showInactiveRadars);
        this.updateActiveOnlyToggle();
        state.products = await api.getProducts();
        state.ui.populateProductSelect(state.products, state.showUnfilteredProducts);
        state.ui.updateFilterToggle(state.showUnfilteredProducts);
    },

    updateActiveOnlyToggle() {
        const toggle = document.getElementById('toggle-show-inactive');
        if (toggle) toggle.checked = state.showInactiveRadars;
    },

    async refreshRadarList() {
        try {
            const prevSelected = new Set(state.ui.getSelectedRadars());
            state.radars = await api.getRadars(!state.showInactiveRadars);
            state.ui.populateRadarCheckboxes(state.radars, state.showInactiveRadars);
            prevSelected.forEach(code => {
                const cb = document.getElementById(`radar-${code}`);
                if (cb) cb.checked = true;
            });
        } catch (err) {
            console.warn('Failed to refresh radar list:', err);
        }
    },

    startRadarStatusRefresh() {
        if (state.radarStatusRefreshInterval !== null) {
            clearInterval(state.radarStatusRefreshInterval);
        }
        const intervalMs = getSettingRefreshIntervalMs();
        state.radarStatusRefreshInterval = setInterval(() => {
            this.refreshRadarList();
        }, intervalMs);
    },

    initSettingsPanel() {
        const intervalInput = document.getElementById('settings-refresh-interval');
        if (intervalInput) {
            const stored = localStorage.getItem(SETTINGS_KEY_REFRESH_INTERVAL);
            intervalInput.value = stored !== null
                ? stored
                : String(DEFAULT_RADAR_STATUS_REFRESH_INTERVAL_MS / 60000);
        }
        const liveIntervalInput = document.getElementById('settings-live-refresh-interval');
        if (liveIntervalInput) {
            const stored = localStorage.getItem(SETTINGS_KEY_LIVE_REFRESH_INTERVAL);
            liveIntervalInput.value = stored !== null
                ? String(parseInt(stored, 10) / 60000)
                : String(DEFAULT_LIVE_REFRESH_INTERVAL_MS / 60000);
        }
        const coverageToggle = document.getElementById('toggle-coverage');
        if (coverageToggle) {
            const visible = localStorage.getItem(SETTINGS_KEY_COVERAGE_VISIBLE) === 'true';
            coverageToggle.checked = visible;
            state.coverageVisible = visible;
            const opacityGroup = document.getElementById('coverage-opacity-group');
            if (opacityGroup) opacityGroup.style.display = visible ? 'block' : 'none';
        }
        const coverageOpacitySlider = document.getElementById('coverage-opacity-slider');
        if (coverageOpacitySlider) {
            const stored = localStorage.getItem(SETTINGS_KEY_COVERAGE_OPACITY);
            const opacity = stored !== null ? parseFloat(stored) : DEFAULT_COVERAGE_OPACITY;
            coverageOpacitySlider.value = opacity;
            state.coverageOpacity = opacity;
            const display = document.getElementById('coverage-opacity-value');
            if (display) display.textContent = `${Math.round(opacity * 100)}%`;
        }
        const speedSlider = document.getElementById('speed-slider');
        const speedValue  = document.getElementById('speed-value');
        if (speedSlider && speedValue) {
            const s = state.animator ? state.animator.getSpeed() : 1.0;
            speedSlider.value = s;
            speedValue.textContent = `${s.toFixed(1)}x`;
        }
        this._syncFieldOpacitySlider();
    },

    async tryGeolocationAutoInit() {
        let location = null;
        try {
            location = await getBrowserGeolocation();
        } catch (e) {
            console.log('Geolocation: browser denied, trying IP…');
        }
        if (!location) {
            try {
                location = await getIPGeolocation();
            } catch (e) {
                console.log('Geolocation: IP lookup failed:', e.message);
            }
        }
        if (!location) {
            state.ui.setStatus('Select radar(s) and product to start', '');
            return;
        }
        await this.runGeolocationAutoInit(location.lat, location.lon);
    },

    async runGeolocationAutoInit(userLat, userLon) {
        try {
            const activeRadars = await api.getRadars(true);
            if (!activeRadars.length) return;

            const sorted = activeRadars.map(r => ({
                radar: r,
                dist: haversineKm(userLat, userLon, r.center_lat, r.center_long),
            })).sort((a, b) => a.dist - b.dist);

            const closest = sorted.slice(0, GEOLOCATION_AUTO_SELECT_COUNT).map(x => x.radar);
            closest.forEach(r => {
                const cb = document.getElementById(`radar-${r.code}`);
                if (cb) cb.checked = true;
            });
            this.onRadarSelectionChange();

            const preferredProducts = [GEOLOCATION_AUTO_PRODUCT, 'DBZH'];
            let selectedProduct = null;
            for (const key of preferredProducts) {
                if (state.products.find(p => p.product_key === key)) {
                    selectedProduct = key;
                    break;
                }
            }
            if (!selectedProduct) return;

            const isUnfiltered = /o$/.test(selectedProduct);
            if (isUnfiltered !== state.showUnfilteredProducts) {
                state.showUnfilteredProducts = isUnfiltered;
                state.ui.populateProductSelect(state.products, state.showUnfilteredProducts);
                state.ui.updateFilterToggle(state.showUnfilteredProducts);
            }

            const productSelect = document.getElementById('product-select');
            if (productSelect) productSelect.value = selectedProduct;
            state.selectedProduct = selectedProduct;
            await this.loadColormapOptions();

            await this.loadLastNHours(GEOLOCATION_AUTO_LOAD_HOURS);
            if (state.animator.getFrameCount() > 1) {
                state.animator.play();
                state.ui.updatePlayButton(true);
            }
        } catch (err) {
            console.warn('Geolocation auto-init failed:', err);
        }
    },

    setupEventListeners() {
        const PANEL_MAP = {
            'btn-module-a': 'panel-module-a',
            'btn-module-b': 'panel-module-b',
            'btn-module-c': 'panel-module-c',
            'btn-settings':  'settings-panel',
        };
        Object.entries(PANEL_MAP).forEach(([btnId, panelId]) => {
            const btn = document.getElementById(btnId);
            if (!btn) return;
            btn.addEventListener('click', () => this.togglePanel(panelId));
        });

        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('panel-close')) {
                const panelId = e.target.dataset.close;
                if (panelId) this.closePanel(panelId);
            }
        });

        const snapshotBtn = document.getElementById('btn-snapshot');
        if (snapshotBtn) {
            snapshotBtn.addEventListener('click', () => this.captureMapSnapshot());
        }

        const basemapSelect = document.getElementById('basemap-select');
        if (basemapSelect) {
            basemapSelect.addEventListener('change', (e) => {
                state.mapManager.setBasemap(e.target.value);
            });
        }

        const refreshIntervalInput = document.getElementById('settings-refresh-interval');
        const refreshIntervalSave  = document.getElementById('settings-refresh-save');
        if (refreshIntervalInput && refreshIntervalSave) {
            refreshIntervalSave.addEventListener('click', () => {
                const minutes = Math.min(parseFloat(refreshIntervalInput.value), 60);
                if (!isNaN(minutes) && minutes > 0) {
                    setSettingRefreshIntervalMin(minutes);
                    this.startRadarStatusRefresh();
                    state.ui.setStatus(`Radar refresh interval set to ${minutes} min`, 'success');
                }
            });
        }

        const liveRefreshInput = document.getElementById('settings-live-refresh-interval');
        const liveRefreshSave  = document.getElementById('settings-live-refresh-save');
        if (liveRefreshInput && liveRefreshSave) {
            liveRefreshSave.addEventListener('click', () => {
                const minutes = parseFloat(liveRefreshInput.value);
                if (!isNaN(minutes) && minutes >= 1 && minutes <= 30) {
                    const ms = Math.round(minutes * 60 * 1000);
                    setLiveRefreshIntervalMs(ms);
                    if (state.liveHours !== null) this.startLiveRefresh(state.liveHours);
                    state.ui.setStatus(`Live refresh interval set to ${minutes} min`, 'success');
                } else {
                    state.ui.setStatus('Live refresh: enter a value between 1 and 30 min', 'error');
                }
            });
        }

        const coverageToggle = document.getElementById('toggle-coverage');
        if (coverageToggle) {
            coverageToggle.addEventListener('change', (e) => {
                state.coverageVisible = e.target.checked;
                localStorage.setItem(SETTINGS_KEY_COVERAGE_VISIBLE, String(state.coverageVisible));
                const opacityGroup = document.getElementById('coverage-opacity-group');
                if (opacityGroup) opacityGroup.style.display = state.coverageVisible ? 'block' : 'none';
                if (state.coverageVisible) {
                    state.selectedRadars.forEach(code => {
                        const radar = state.radars.find(r => r.code === code);
                        if (radar) state.mapManager.addCoverageCircle(radar, state.coverageOpacity);
                    });
                } else {
                    state.mapManager.clearCoverageCircles();
                }
            });
        }

        const coverageOpacitySlider = document.getElementById('coverage-opacity-slider');
        if (coverageOpacitySlider) {
            coverageOpacitySlider.addEventListener('input', (e) => {
                const opacity = parseFloat(e.target.value);
                state.coverageOpacity = opacity;
                localStorage.setItem(SETTINGS_KEY_COVERAGE_OPACITY, String(opacity));
                state.mapManager.updateCoverageOpacity(opacity);
                const display = document.getElementById('coverage-opacity-value');
                if (display) display.textContent = `${Math.round(opacity * 100)}%`;
            });
        }

        const showInactiveToggle = document.getElementById('toggle-show-inactive');
        if (showInactiveToggle) {
            showInactiveToggle.addEventListener('change', async (e) => {
                state.showInactiveRadars = e.target.checked;
                localStorage.setItem(SETTINGS_KEY_SHOW_INACTIVE, String(state.showInactiveRadars));
                await this.refreshRadarList();
            });
        }

        const showFilteredToggle = document.getElementById('toggle-show-filtered');
        if (showFilteredToggle) {
            showFilteredToggle.addEventListener('change', (e) => {
                state.showUnfilteredProducts = e.target.checked;
                localStorage.setItem(SETTINGS_KEY_SHOW_FILTERED, String(state.showUnfilteredProducts));
                state.ui.populateProductSelect(state.products, state.showUnfilteredProducts);
                state.ui.updateFilterToggle(state.showUnfilteredProducts);
            });
        }

        const radarCheckboxes = document.getElementById('radar-checkboxes');
        if (radarCheckboxes) {
            radarCheckboxes.addEventListener('change', () => this.onRadarCheckboxChange());
        }

        const productSelect = document.getElementById('product-select');
        if (productSelect) {
            productSelect.addEventListener('change', async (e) => {
                state.selectedProduct = e.target.value || null;
                state.selectedColormap = null;
                state.currentVmin = null;
                state.currentVmax = null;
                await this.loadColormapOptions();
                this.onTimeRangeChange();
            });
        }

        const loadBtn = document.getElementById('load-time-range-btn');
        if (loadBtn) {
            loadBtn.addEventListener('click', () => this.loadTimeRangeCogs());
        }

        const loadLatestBtn = document.getElementById('load-latest-btn');
        if (loadLatestBtn) {
            loadLatestBtn.addEventListener('click', () => this.loadLatestCogs());
        }

        // Preset time-window buttons
        document.querySelectorAll('[data-hours]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const hours = parseFloat(e.currentTarget.dataset.hours);
                if (!isNaN(hours)) {
                    state.activeTimeWindowHours = hours;
                    document.querySelectorAll('[data-hours]').forEach(b =>
                        b.classList.toggle('active', b === e.currentTarget)
                    );
                    this.loadLastNHours(hours);
                }
            });
        });

        const startInput = document.getElementById('start-time');
        const endInput   = document.getElementById('end-time');
        if (startInput) startInput.addEventListener('change', () => this.onTimeRangeChange());
        if (endInput)   endInput.addEventListener('change',   () => this.onTimeRangeChange());

        // Colormap
        const colormapSelect = document.getElementById('colormap-select');
        if (colormapSelect) {
            colormapSelect.addEventListener('change', (e) => {
                state.selectedColormap = e.target.value || null;
            });
        }

        const applyColormapBtn = document.getElementById('btn-apply-range');
        if (applyColormapBtn) {
            applyColormapBtn.addEventListener('click', () => this.applyColormapChange());
        }

        const vminInput = document.getElementById('vmin-input');
        const vmaxInput = document.getElementById('vmax-input');
        if (vminInput) {
            vminInput.addEventListener('change', (e) => {
                const v = parseFloat(e.target.value);
                state.currentVmin = isNaN(v) ? null : v;
            });
        }
        if (vmaxInput) {
            vmaxInput.addEventListener('change', (e) => {
                const v = parseFloat(e.target.value);
                state.currentVmax = isNaN(v) ? null : v;
            });
        }

        const resetRangeBtn = document.getElementById('reset-range-btn');
        if (resetRangeBtn) {
            resetRangeBtn.addEventListener('click', async () => {
                state.currentVmin = null;
                state.currentVmax = null;
                await this.loadColormapOptions();
            });
        }

        // Field opacity
        const fieldOpacitySlider = document.getElementById('field-opacity-slider');
        if (fieldOpacitySlider) {
            fieldOpacitySlider.addEventListener('input', (e) => {
                const opacity = parseFloat(e.target.value);
                if (state.selectedProduct) {
                    state.fieldOpacity[state.selectedProduct] = opacity;
                }
                state.mapManager.setOpacity(opacity);
                const display = document.getElementById('field-opacity-value');
                if (display) display.textContent = `${Math.round(opacity * 100)}%`;
            });
        }

        // Speed slider is wired by AnimationController.initControls() — do not
        // duplicate it here, or two listeners would fire on every input event.

        // Snapshot keyboard shortcut
        document.addEventListener('keydown', (e) => {
            if (e.key === 's' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                this.captureMapSnapshot();
            }
        });

        // Live refresh manual trigger
        const cogRefreshNowBtn = document.getElementById('btn-cog-refresh-now');
        if (cogRefreshNowBtn) {
            cogRefreshNowBtn.addEventListener('click', () => {
                if (state.liveHours !== null) this.refreshLiveWindow();
            });
        }
    },

    // =========================================================================
    // Radar selection change
    // =========================================================================

    onRadarCheckboxChange() {
        const newSelection = state.ui.getSelectedRadars();
        const added   = newSelection.filter(c => !state.selectedRadars.includes(c));
        const removed = state.selectedRadars.filter(c => !newSelection.includes(c));

        state.selectedRadars = newSelection;

        // Update coverage circles
        if (state.coverageVisible) {
            added.forEach(code => {
                const radar = state.radars.find(r => r.code === code);
                if (radar) state.mapManager.addCoverageCircle(radar, state.coverageOpacity);
            });
            removed.forEach(code => state.mapManager.removeCoverageCircle(code));
        }

        // Incremental add/remove while animation is running
        if (state.animationMode === 'timerange') {
            added.forEach(code => this.addRadarIncremental(code));
            removed.forEach(code => this.removeRadarIncremental(code));
        }
    },

    onRadarSelectionChange() {
        state.selectedRadars = state.ui.getSelectedRadars();
    },

    // =========================================================================
    // Incremental radar add / remove
    // =========================================================================

    async addRadarIncremental(radarCode) {
        if (state.animationMode !== 'timerange' || !state.cogs || state.cogs.length === 0) return;

        const timeRange = state.ui.getTimeRangeValues();
        if (!timeRange.start || !timeRange.end) return;

        state.ui.setStatus(`Adding ${radarCode.toUpperCase()} to animation…`, 'loading');

        try {
            const newCogs = await api.getCogsForTimeRange(
                [radarCode], state.selectedProduct, timeRange.start, timeRange.end, 100
            );

            if (newCogs.length === 0) {
                state.ui.setStatus(
                    `⚠️ No data for ${radarCode.toUpperCase()} in current time range`, 'error'
                );
                return;
            }

            const params = this.getTileParams();
            const existingBucketToIdx = new Map();
            state.cogs.forEach((frame, idx) => {
                existingBucketToIdx.set(getCogBucketKey(frame.timestamp), idx);
            });

            const newBucketToCog = new Map();
            newCogs.forEach(cog => {
                const key = getCogBucketKey(cog.observation_time);
                if (!newBucketToCog.has(key)) newBucketToCog.set(key, cog);
            });
            const sortedNewBuckets = Array.from(newBucketToCog.entries()).reverse(); // oldest-first

            const toInsert = [];
            const mergePromises = [];
            for (const [key, cog] of sortedNewBuckets) {
                if (existingBucketToIdx.has(key)) {
                    const frameIdx = existingBucketToIdx.get(key);
                    state.cogs[frameIdx].cogsByRadar[radarCode] = cog;
                    // v2: load the image into the existing frame slot
                    mergePromises.push(
                        state.mapManager.addRadarToFrame(frameIdx, radarCode, state.selectedProduct, cog, params)
                    );
                } else {
                    toInsert.push({ key, cog });
                }
            }

            const currentIndex = state.animator.getCurrentIndex();
            let indexAdjustment = 0;
            const insertPromises = [];

            for (const { key, cog } of toInsert) {
                let lo = 0, hi = state.cogs.length;
                while (lo < hi) {
                    const mid = (lo + hi) >>> 1;
                    if (getCogBucketKey(state.cogs[mid].timestamp) < key) lo = mid + 1;
                    else hi = mid;
                }
                const insertIdx = lo;

                const newFrame = { timestamp: cog.observation_time, cogsByRadar: { [radarCode]: cog } };
                state.cogs.splice(insertIdx, 0, newFrame);

                // v2: addFrame() will splice _frameImages at insertIdx
                insertPromises.push(
                    state.mapManager.addFrame(insertIdx, radarCode, state.selectedProduct, cog, params)
                );

                if (insertIdx <= currentIndex + indexAdjustment) {
                    indexAdjustment++;
                }
            }

            await Promise.all([...mergePromises, ...insertPromises]);

            const newCurrentIndex = Math.min(currentIndex + indexAdjustment, state.cogs.length - 1);
            state.animator.updateFrames(state.cogs, state.selectedProduct, newCurrentIndex);
            // Show the new current frame immediately
            state.animator.goToFrame(newCurrentIndex);

            state.ui.updateFrameCounter(newCurrentIndex, state.cogs.length);
            state.ui.updateAnimationSlider(newCurrentIndex, state.cogs.length);
            state.ui.setStatus(`✓ Added ${radarCode.toUpperCase()} — ${state.cogs.length} frames`, 'success');

        } catch (err) {
            console.error('addRadarIncremental error:', err);
            state.ui.setStatus(`Error adding ${radarCode.toUpperCase()}: ${err.message}`, 'error');
        }
    },

    removeRadarIncremental(radarCode) {
        if (state.animationMode !== 'timerange' || !state.cogs || state.cogs.length === 0) return;

        // Process frames in REVERSE index order so each splice on _frameImages
        // does not shift the indices of frames we have not processed yet.
        for (let i = state.cogs.length - 1; i >= 0; i--) {
            const frame = state.cogs[i];
            delete frame.cogsByRadar[radarCode];

            if (Object.keys(frame.cogsByRadar).length === 0) {
                // Frame is now empty: splice it out of both arrays.
                // removeFrameSlot adjusts mapManager.currentFrameIndex internally.
                state.mapManager.removeFrameSlot(i);
            } else {
                // Frame still has other radars: remove only this radar's image entry.
                // removeFrame() will NOT splice the slot (frame is non-empty after removal).
                state.mapManager.removeFrame(i, radarCode, state.selectedProduct);
            }
        }

        // Compact state.cogs to match the new _frameImages length
        const newFrames = state.cogs.filter(f => Object.keys(f.cogsByRadar).length > 0);
        state.cogs = newFrames;

        if (newFrames.length === 0) {
            state.animator.updateFrames([], null);
            state.animationMode = null;
            state.ui.enableAnimationControls(false);
            state.ui.enableNavButtons(false);
            state.ui.setStatus(`All frames empty after removing ${radarCode.toUpperCase()}`, 'error');
            return;
        }

        // Use MapManager's updated pointer as the new current index
        const newCurrentIndex = Math.max(
            0,
            Math.min(state.mapManager.currentFrameIndex, newFrames.length - 1)
        );

        state.animator.updateFrames(newFrames, state.selectedProduct, newCurrentIndex);
        state.animator.goToFrame(newCurrentIndex);

        state.ui.updateFrameCounter(newCurrentIndex, newFrames.length);
        state.ui.updateAnimationSlider(newCurrentIndex, newFrames.length);
        state.ui.setTimeDisplay(newFrames[newCurrentIndex].timestamp);
        state.ui.setStatus(`✓ Removed ${radarCode.toUpperCase()} from animation`, 'success');
    },

    // =========================================================================
    // Load latest COGs
    // =========================================================================

    async loadLatestCogs() {
        if (state.selectedRadars.length === 0 || !state.selectedProduct) {
            state.ui.setStatus('Select radar(s) and product', 'error');
            return;
        }
        state.ui.setStatus('Loading latest images...', 'loading');
        state.animator.stop();
        state.ui.updatePlayButton(false);

        try {
            const latestCogs = await api.getLatestCogsForRadars(state.selectedRadars, state.selectedProduct);
            const radarCodesWithData    = latestCogs.map(item => item.radarCode);
            const radarCodesWithoutData = state.selectedRadars.filter(c => !radarCodesWithData.includes(c));

            if (latestCogs.length === 0) {
                const radarList   = state.selectedRadars.join(', ').toUpperCase();
                const productName = state.products.find(p => p.product_key === state.selectedProduct)?.product_title || state.selectedProduct;
                state.ui.setStatus(
                    `⚠️ No data available for ${radarList} with product "${productName}". Try a different product or radar.`,
                    'error'
                );
                return;
            }

            let colormap = null;
            try {
                colormap = await api.getColormapInfo(state.selectedProduct, state.selectedColormap);
            } catch (e) {
                try { colormap = await api.getColormap(state.selectedProduct); } catch (e2) { /* ignore */ }
            }

            // v2: build a single-frame cogsByFrame Map
            const singleFrameRadarMap = new Map();
            let firstCog = null;
            latestCogs.forEach(({ radarCode, cog }) => {
                if (!cog) return;
                singleFrameRadarMap.set(radarCode, cog);
                if (!firstCog) firstCog = cog;
            });
            const cogsByFrame = new Map([[0, singleFrameRadarMap]]);

            state.mapManager._clearAllOverlays();
            state.hasZoomedToBounds = false;
            state.animationMode = 'latest';

            const params = this.getTileParams();
            state.ui.setStatus('Loading frame image…', 'loading');
            await state.mapManager.loadFrames(cogsByFrame, state.selectedProduct, params, null);

            // Zoom to first radar bounds
            if (firstCog && !state.hasZoomedToBounds) {
                const radar = state.radars.find(r => r.code === firstCog.radar_code);
                if (radar?.extent) {
                    const ext = radar.extent;
                    state.mapManager.getMap().fitBounds([
                        [ext.lat_min, ext.lon_min],
                        [ext.lat_max, ext.lon_max],
                    ]);
                }
                state.hasZoomedToBounds = true;
            }

            // Show single frame
            state.mapManager.showFrame(0, Array.from(singleFrameRadarMap.keys()), state.selectedProduct);

            if (firstCog) state.ui.setTimeDisplay(firstCog.observation_time);

            if (colormap) {
                if (state.currentVmin !== null) colormap.vmin = state.currentVmin;
                if (state.currentVmax !== null) colormap.vmax = state.currentVmax;
                state.legend.render(colormap);
                state.legend.show();
            }

            const loadedRadars = latestCogs.map(item => item.radarCode.toUpperCase()).join(', ');
            const radarText    = latestCogs.length === 1 ? 'radar' : 'radars';
            let msg = `✓ Showing latest from ${latestCogs.length} ${radarText}: ${loadedRadars}`;
            if (radarCodesWithoutData.length > 0) {
                msg += ` (${radarCodesWithoutData.map(c => c.toUpperCase()).join(', ')} has no data)`;
            }
            state.ui.setStatus(msg, 'success');

        } catch (error) {
            console.error('Load error:', error);
            state.ui.setStatus(`Error: ${error.message}`, 'error');
        }
    },

    // =========================================================================
    // Load COGs for a time range
    // =========================================================================

    async loadTimeRangeCogs() {
        if (state.selectedRadars.length === 0 || !state.selectedProduct) {
            state.ui.setStatus('Select radar(s) and product', 'error');
            return;
        }
        const timeRange = state.ui.getTimeRangeValues();
        if (!timeRange.start || !timeRange.end) {
            state.ui.setStatus('Select valid time range', 'error');
            return;
        }
        if (timeRange.start >= timeRange.end) {
            state.ui.setStatus('Start time must be before end time', 'error');
            return;
        }

        state.ui.setStatus('Loading time range data...', 'loading');

        try {
            const cogs = await api.getCogsForTimeRange(
                state.selectedRadars, state.selectedProduct,
                timeRange.start, timeRange.end, 100
            );

            if (cogs.length === 0) {
                const radarList   = state.selectedRadars.join(', ').toUpperCase();
                const productName = state.products.find(p => p.product_key === state.selectedProduct)?.product_title || state.selectedProduct;
                state.ui.setStatus(
                    `⚠️ No data available for ${radarList} with product "${productName}" in selected time range.`,
                    'error'
                );
                return;
            }

            const groupedFrames = groupCogsByTimestamp(cogs);

            let colormap = null;
            try {
                colormap = await api.getColormapInfo(state.selectedProduct, state.selectedColormap);
            } catch (e) {
                try { colormap = await api.getColormap(state.selectedProduct); } catch (e2) { /* ignore */ }
            }

            // v2: clear overlays, not tileLayer cache
            state.mapManager._clearAllOverlays();
            state.animator.stop();
            state.ui.updatePlayButton(false);
            state.hasZoomedToBounds = false;
            state.animationMode = 'timerange';

            const params      = this.getTileParams();
            const cogsByFrame = buildCogsByFrameMap(groupedFrames);

            // v2: loadFrames fetches full-COG PNGs with progress callback
            await state.mapManager.loadFrames(cogsByFrame, state.selectedProduct, params,
                (loaded, total) => {
                    state.ui.setStatus(
                        `Loading frames… ${loaded} / ${total} (${Math.round(loaded / total * 100)}%)`,
                        'loading'
                    );
                }
            );

            // Zoom to first frame's first radar bounds
            const anyRadarCode = Object.keys(groupedFrames[0].cogsByRadar)[0];
            if (anyRadarCode && !state.hasZoomedToBounds) {
                const radar = state.radars.find(r => r.code === anyRadarCode);
                if (radar?.extent) {
                    const ext = radar.extent;
                    state.mapManager.getMap().fitBounds([
                        [ext.lat_min, ext.lon_min],
                        [ext.lat_max, ext.lon_max],
                    ]);
                }
                state.hasZoomedToBounds = true;
            }

            state.cogs = groupedFrames;

            // v2: updateFrames takes (frames, productKey, currentIndex)
            state.animator.updateFrames(groupedFrames, state.selectedProduct, 0);
            state.animator.goToFrame(0);

            if (colormap) {
                if (state.currentVmin !== null) colormap.vmin = state.currentVmin;
                if (state.currentVmax !== null) colormap.vmax = state.currentVmax;
                state.legend.render(colormap);
                state.legend.show();
            }

            if (groupedFrames.length > 1) {
                state.ui.enableAnimationControls(true);
                state.ui.enableNavButtons(true);
                state.ui.updateFrameCounter(0, groupedFrames.length);
                state.ui.updateAnimationSlider(0, groupedFrames.length);
            }

            const radarCodes  = [...new Set(groupedFrames.flatMap(f => Object.keys(f.cogsByRadar)))];
            const loadedRadars = radarCodes.map(c => c.toUpperCase()).join(', ');
            const radarText    = radarCodes.length === 1 ? 'radar' : 'radars';

            let liveNote = '';
            if (state.liveHours !== null && groupedFrames.length > 0) {
                const oldestFrameTime  = new Date(groupedFrames[0].timestamp);
                const newestFrameTime  = new Date(groupedFrames[groupedFrames.length - 1].timestamp);
                const requestedStart   = state.ui.getTimeRangeValues().start;
                if (requestedStart) {
                    const gapHours = (oldestFrameTime - requestedStart) / MS_PER_HOUR;
                    if (gapHours > 0.5) {
                        const availableHours = ((newestFrameTime - oldestFrameTime) / MS_PER_HOUR).toFixed(1);
                        liveNote = ` ⚠️ Only ${availableHours}h of data available (${state.liveHours}h requested)`;
                    }
                }
            }

            state.ui.setStatus(
                `✓ Loaded ${groupedFrames.length} frames from ${radarCodes.length} ${radarText}: ${loadedRadars}${liveNote}`,
                'success'
            );

        } catch (error) {
            console.error('Load time range error:', error);
            state.ui.setStatus(`Error: ${error.message}`, 'error');
        }
    },

    // =========================================================================
    // Load last N hours
    // =========================================================================

    async loadLastNHours(hours) {
        if (state.selectedRadars.length === 0 || !state.selectedProduct) {
            state.ui.setStatus('Select radar(s) and product first', 'error');
            return;
        }
        this.stopLiveRefresh();
        state.ui.setStatus('Finding latest data…', 'loading');

        try {
            const latestItems = await api.getLatestCogsForRadars(
                state.selectedRadars, state.selectedProduct
            );

            if (latestItems.length === 0) {
                const radarList   = state.selectedRadars.join(', ').toUpperCase();
                const productName = state.products.find(p => p.product_key === state.selectedProduct)?.product_title || state.selectedProduct;
                state.ui.setStatus(
                    `⚠️ No data available for ${radarList} with product "${productName}". Try a different product or radar.`,
                    'error'
                );
                return;
            }

            const endTime = latestItems.reduce((max, { cog }) => {
                const t = new Date(cog.observation_time);
                return t > max ? t : max;
            }, new Date(0));
            const startTime = new Date(endTime.getTime() - hours * MS_PER_HOUR);

            state.ui.setTimeRangeValues(startTime, endTime);
            this.onTimeRangeChange();
            state.liveHours = hours;

            await this.loadTimeRangeCogs();

            if (state.liveHours !== null) {
                this.startLiveRefresh(hours);
            }
        } catch (err) {
            console.error('loadLastNHours error:', err);
            state.ui.setStatus(`Error: ${err.message}`, 'error');
            state.liveHours = null;
        }
    },

    startLiveRefresh(hours) {
        this.stopLiveRefresh();
        state.liveHours = hours;
        const intervalMs = getLiveRefreshIntervalMs();
        state.liveRefreshInterval = setInterval(() => {
            this.refreshLiveWindow();
        }, intervalMs);
        this.updateLiveIndicator();
    },

    stopLiveRefresh() {
        if (state.liveRefreshInterval !== null) {
            clearInterval(state.liveRefreshInterval);
            state.liveRefreshInterval = null;
        }
        state.liveHours = null;
        this.updateLiveIndicator();
    },

    // =========================================================================
    // Live refresh (full-window diff)
    // =========================================================================

    async refreshLiveWindow() {
        if (!state.liveHours || !state.selectedRadars.length || !state.selectedProduct) return;
        if (state.animationMode !== 'timerange' || !state.cogs || state.cogs.length === 0) return;

        try {
            const hours = state.liveHours;

            const latestItems = await api.getLatestCogsForRadars(
                state.selectedRadars, state.selectedProduct
            );
            if (!latestItems.length) return;

            const newEndTime = latestItems.reduce((max, { cog }) => {
                const t = new Date(cog.observation_time);
                return t > max ? t : max;
            }, new Date(0));
            const newStartTime = new Date(newEndTime.getTime() - hours * MS_PER_HOUR);

            const allCogs = await api.getCogsForTimeRange(
                state.selectedRadars, state.selectedProduct,
                newStartTime, newEndTime, LIVE_REFRESH_MAX_COGS
            );

            const cachedCogIds = new Set();
            state.cogs.forEach(frame => {
                Object.values(frame.cogsByRadar).forEach(cog => cachedCogIds.add(cog.id));
            });

            const cogsToAdd = allCogs.filter(c => !cachedCogIds.has(c.id));

            const newStartMs = newStartTime.getTime();
            const currentIndex = state.animator.getCurrentIndex();
            const params       = this.getTileParams();

            let removedBeforeCurrent = 0;
            const expiredIndices = [];
            state.cogs.forEach((frame, i) => {
                if (new Date(frame.timestamp).getTime() < newStartMs) {
                    expiredIndices.push(i);
                    if (i < currentIndex) removedBeforeCurrent++;
                }
            });

            // Remove expired frames in reverse order
            for (let i = expiredIndices.length - 1; i >= 0; i--) {
                const idx = expiredIndices[i];
                state.cogs.splice(idx, 1);
                // v2: removeFrameSlot splices _frameImages
                state.mapManager.removeFrameSlot(idx);
            }

            let indexAfterExpiry = Math.max(0, currentIndex - removedBeforeCurrent);

            // Add new / recovered COGs
            let insertionAdjustment = 0;
            const addPromises = [];

            if (cogsToAdd.length > 0) {
                const existingBucketToIdx = new Map();
                state.cogs.forEach((frame, idx) => {
                    existingBucketToIdx.set(getCogBucketKey(frame.timestamp), idx);
                });

                const newBucketMap = new Map();
                cogsToAdd.forEach(cog => {
                    const key = getCogBucketKey(cog.observation_time);
                    if (!newBucketMap.has(key)) newBucketMap.set(key, {});
                    const byRadar = newBucketMap.get(key);
                    if (!byRadar[cog.radar_code]) byRadar[cog.radar_code] = cog;
                });

                const sortedBuckets = Array.from(newBucketMap.entries()).sort((a, b) => a[0] - b[0]);

                for (const [key, cogsByRadar] of sortedBuckets) {
                    if (existingBucketToIdx.has(key)) {
                        const frameIdx = existingBucketToIdx.get(key);
                        Object.entries(cogsByRadar).forEach(([radarCode, cog]) => {
                            state.cogs[frameIdx].cogsByRadar[radarCode] = cog;
                            addPromises.push(
                                state.mapManager.addRadarToFrame(
                                    frameIdx, radarCode, state.selectedProduct, cog, params
                                )
                            );
                        });
                    } else {
                        let lo = 0, hi = state.cogs.length;
                        while (lo < hi) {
                            const mid = Math.floor((lo + hi) / 2);
                            if (getCogBucketKey(state.cogs[mid].timestamp) < key) lo = mid + 1;
                            else hi = mid;
                        }
                        const insertIdx = lo;
                        const representativeCog = Object.values(cogsByRadar)[0];
                        const newFrame  = { timestamp: representativeCog.observation_time, cogsByRadar };
                        state.cogs.splice(insertIdx, 0, newFrame);

                        // v2: insert each radar for this new frame
                        Object.entries(cogsByRadar).forEach(([radarCode, cog], i) => {
                            if (i === 0) {
                                // First radar splices the frame slot
                                addPromises.push(
                                    state.mapManager.addFrame(
                                        insertIdx, radarCode, state.selectedProduct, cog, params
                                    )
                                );
                            } else {
                                // Subsequent radars merge into existing slot
                                addPromises.push(
                                    state.mapManager.addRadarToFrame(
                                        insertIdx, radarCode, state.selectedProduct, cog, params
                                    )
                                );
                            }
                        });

                        if (insertIdx <= indexAfterExpiry + insertionAdjustment) {
                            insertionAdjustment++;
                        }

                        existingBucketToIdx.forEach((idx, k) => {
                            if (idx >= insertIdx) existingBucketToIdx.set(k, idx + 1);
                        });
                        existingBucketToIdx.set(key, insertIdx);
                    }
                }
            }

            await Promise.all(addPromises);

            state.ui.setTimeRangeValues(newStartTime, newEndTime);
            this.onTimeRangeChange();
            state.liveHours = hours;

            const newLength = state.cogs.length;
            if (newLength === 0) return;

            const newCurrentIndex = Math.min(
                indexAfterExpiry + insertionAdjustment,
                newLength - 1
            );

            state.animator.updateFrames(state.cogs, state.selectedProduct, newCurrentIndex);

            state.ui.updateFrameCounter(newCurrentIndex, newLength);
            state.ui.updateAnimationSlider(newCurrentIndex, newLength);
            this.updateTimeWindowLabel();

            console.log(
                `Live refresh: +${cogsToAdd.length} new/recovered COGs, ` +
                `-${expiredIndices.length} expired frames, ${newLength} total frames`
            );
        } catch (err) {
            console.warn('Live refresh error (will retry next cycle):', err);
        }
    },

    // =========================================================================
    // Frame change callback (from AnimationController)
    // =========================================================================

    onFrameChange(index, frame) {
        if (!frame) return;
        this.updateTimeWindowLabel();

        if (frame.cogsByRadar) {
            // v2: showFrame is called by AnimationController._showCurrentFrame()
            // so we only need to update the UI here
            state.ui.setTimeDisplay(frame.timestamp);
            state.ui.updateFrameCounter(index, state.animator.getFrameCount());
            state.ui.updateAnimationSlider(index, state.animator.getFrameCount());
            return;
        }

        // Legacy single-COG fallback
        if (frame.observation_time) {
            state.ui.setTimeDisplay(frame.observation_time);
            state.ui.updateFrameCounter(index, state.animator.getFrameCount());
            state.ui.updateAnimationSlider(index, state.animator.getFrameCount());
        }
    },

    updateTimeWindowLabel() {
        const label = document.getElementById('time-window-label');
        if (!label) return;
        if (state.liveHours !== null) {
            label.textContent = `Last ${state.liveHours} hrs`;
        } else if (state.animationMode === 'timerange') {
            const range = state.ui.getTimeRangeValues();
            if (range.start && range.end) {
                const fmt = (d) => {
                    const dd = String(d.getDate()).padStart(2, '0');
                    const mo = String(d.getMonth() + 1).padStart(2, '0');
                    const hh = String(d.getHours()).padStart(2, '0');
                    const mi = String(d.getMinutes()).padStart(2, '0');
                    return `${dd}/${mo} ${hh}:${mi}`;
                };
                label.textContent = `${fmt(range.start)} → ${fmt(range.end)}`;
            } else {
                label.textContent = 'Custom range';
            }
        } else {
            label.textContent = '—';
        }
        const badgeC = document.getElementById('badge-module-c');
        if (badgeC) badgeC.textContent = state.liveHours !== null ? `${state.liveHours}h` : '—';
    },

    // =========================================================================
    // Colormap / range
    // =========================================================================

    async loadColormapOptions() {
        if (!state.selectedProduct) {
            document.getElementById('colormap-group').style.display = 'none';
            document.getElementById('range-group').style.display = 'none';
            document.getElementById('field-opacity-group').style.display = 'none';
            return;
        }
        try {
            const info = await api.getColormapInfo(state.selectedProduct);
            const defaultCmap = info.colormap;
            const options     = (info.available_colormaps || []).slice();

            const select = document.getElementById('colormap-select');
            select.innerHTML = '';

            const grpDefault = document.createElement('optgroup');
            grpDefault.label = 'Default';
            const defaultOpt = document.createElement('option');
            defaultOpt.value = defaultCmap; defaultOpt.textContent = defaultCmap;
            grpDefault.appendChild(defaultOpt);
            select.appendChild(grpDefault);

            const others = options.filter(c => c !== defaultCmap).sort();
            if (others.length > 0) {
                const grpOther = document.createElement('optgroup');
                grpOther.label = 'Other';
                others.forEach(cmap => {
                    const opt = document.createElement('option');
                    opt.value = cmap; opt.textContent = cmap;
                    grpOther.appendChild(opt);
                });
                select.appendChild(grpOther);
            }

            if (state.selectedColormap && options.includes(state.selectedColormap)) {
                select.value = state.selectedColormap;
            } else if (defaultCmap) {
                state.selectedColormap = defaultCmap;
                select.value = defaultCmap;
            }

            if (state.currentVmin === null) {
                document.getElementById('vmin-input').value = info.vmin ?? '';
            }
            if (state.currentVmax === null) {
                document.getElementById('vmax-input').value = info.vmax ?? '';
            }

            document.getElementById('colormap-group').style.display = 'block';
            document.getElementById('range-group').style.display = 'block';
            document.getElementById('field-opacity-group').style.display = 'block';
            this._syncFieldOpacitySlider();
        } catch (err) {
            console.warn('Failed to load colormap options:', err);
        }
    },

    async applyColormapChange() {
        if (!state.animationMode) return;

        if (state.animationMode === 'latest') {
            await this.loadLatestCogs();
            return;
        }

        if (!state.cogs || !state.cogs.length) {
            await this.loadTimeRangeCogs();
            return;
        }

        const cogsByFrame = buildCogsByFrameMap(state.cogs);
        const params      = this.getTileParams();

        state.ui.showMapOverlay('Applying colormap\u2026');

        try {
            const colormap = await api.getColormapInfo(state.selectedProduct, state.selectedColormap);
            if (colormap) {
                if (state.currentVmin !== null) colormap.vmin = state.currentVmin;
                if (state.currentVmax !== null) colormap.vmax = state.currentVmax;
                state.legend.render(colormap);
            }
        } catch (e) {
            console.warn('Failed to update legend during colormap change:', e);
        }

        const prevIndex   = state.animator.getCurrentIndex();
        const wasPlaying  = state.animator.getIsPlaying();
        state.animator.stop();

        // v2: updateParams reloads all images with new params, swaps atomically
        await state.mapManager.updateParams(
            cogsByFrame, state.selectedProduct, params,
            (loaded, total) => {
                state.ui.updateMapOverlay(`Applying colormap\u2026 ${loaded}\u00a0/\u00a0${total}`);
            }
        );

        state.animator.updateFrames(state.cogs, state.selectedProduct, prevIndex);
        state.animator.goToFrame(prevIndex);
        state.ui.hideMapOverlay();
        state.ui.setStatus('Colormap updated \u2713', 'success');
        if (wasPlaying) state.animator.play();
    },

    /**
     * v2 key difference: returns `colormap` (not `cmap`) to match the
     * /api/v1/frames/{id}/image.png query-parameter name.
     */
    getTileParams() {
        return {
            colormap: state.selectedColormap || null,
            vmin:     state.currentVmin,
            vmax:     state.currentVmax,
        };
    },

    _syncFieldOpacitySlider() {
        const slider  = document.getElementById('field-opacity-slider');
        const display = document.getElementById('field-opacity-value');
        if (!slider) return;
        const opacity = state.fieldOpacity[state.selectedProduct] ?? DEFAULT_FIELD_OPACITY;
        slider.value = opacity;
        if (display) display.textContent = `${Math.round(opacity * 100)}%`;
        if (state.mapManager) state.mapManager.setOpacity(opacity);
    },

    updateLiveIndicator() {
        const el = document.getElementById('live-indicator');
        if (!el) return;
        if (state.liveHours !== null) {
            el.textContent = '● LIVE';
            el.className = 'live-indicator live-on';
        } else {
            el.textContent = '○ Live';
            el.className = 'live-indicator live-off';
        }
        const cogRefreshBtn = document.getElementById('btn-cog-refresh-now');
        if (cogRefreshBtn) cogRefreshBtn.disabled = state.liveHours === null;
    },

    // =========================================================================
    // Panel helpers
    // =========================================================================

    _panelButtonMap: {
        'panel-module-a': 'btn-module-a',
        'panel-module-b': 'btn-module-b',
        'panel-module-c': 'btn-module-c',
        'settings-panel': 'btn-settings',
    },

    togglePanel(panelId) {
        const ALL_PANELS = ['panel-module-a', 'panel-module-b', 'panel-module-c', 'settings-panel'];
        ALL_PANELS.forEach(id => {
            const panel = document.getElementById(id);
            const btnId = this._panelButtonMap[id];
            const btn   = btnId ? document.getElementById(btnId) : null;
            if (id === panelId) {
                const isOpen = panel && panel.style.display !== 'none';
                if (panel) panel.style.display = isOpen ? 'none' : 'block';
                if (btn)   btn.classList.toggle('is-active', !isOpen);
            } else {
                if (panel) panel.style.display = 'none';
                if (btn)   btn.classList.remove('is-active');
            }
        });
    },

    closePanel(panelId) {
        const panel = document.getElementById(panelId);
        if (panel) panel.style.display = 'none';
        const btnId = this._panelButtonMap[panelId];
        const btn   = btnId ? document.getElementById(btnId) : null;
        if (btn) btn.classList.remove('is-active');
    },

    // =========================================================================
    // Time range helpers
    // =========================================================================

    onTimeRangeChange() {
        // Deactivate live preset buttons if the user manually changed the range.
        // (kept for UI consistency; actual live state is tracked via state.liveHours)
    },

    // =========================================================================
    // Snapshot
    // =========================================================================

    async captureMapSnapshot() {
        try {
            const canvas = document.createElement('canvas');
            const mapEl  = document.getElementById('map');
            canvas.width  = mapEl.offsetWidth;
            canvas.height = mapEl.offsetHeight;
            const ctx = canvas.getContext('2d');

            // Collect all visible images: basemap tiles + overlay pane imgs
            const imgs = Array.from(
                document.querySelectorAll('.leaflet-tile-pane img, .leaflet-overlay-pane img')
            );
            for (const img of imgs) {
                if (!img.complete || img.naturalWidth === 0) continue;
                const rect = img.getBoundingClientRect();
                const mapRect = mapEl.getBoundingClientRect();
                ctx.globalAlpha = parseFloat(img.style.opacity || '1');
                ctx.drawImage(img, rect.left - mapRect.left, rect.top - mapRect.top,
                    rect.width, rect.height);
            }
            ctx.globalAlpha = 1;

            const link = document.createElement('a');
            link.download = `radar-snapshot-${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
            link.href = canvas.toDataURL('image/png');
            link.click();
        } catch (err) {
            console.warn('Snapshot failed:', err);
            state.ui.setStatus('Snapshot failed: ' + err.message, 'error');
        }
    },
};

// =============================================================================
// START APPLICATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    app.init();
});
