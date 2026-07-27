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
 * - applyColormapChange() updates the legend only; image reload for all
 *   changes (field, colormap, range filter) goes through _loadFramesWithContinuity()
 *   which uses updateParams() for an atomic background swap without stopping animation.
 * - loadLatestCogs() builds a single-frame cogsByFrame and calls loadFrames().
 * - AnimationController v2 takes mapManager in the constructor and wires
 *   controls via initControls().
 */

import { api } from '../shared/api.js';
import { MapManager } from './map.js';
import { AnimationController, formatTimestamp } from './animation.js';
import { UIControls } from '../shared/controls.js';
import { LegendRenderer } from '../shared/legend.js';
import { TopsCoresLayer } from '../shared/tops-cores.js';
import { 
    waitForLeaflet, 
    buildCogsByFrameMap, 
    groupCogsByTimestamp, 
    getCogBucketKey, 
    getAvailableProductKeys,
    selectDefaultProduct,
    baseFieldKey,
    fieldHasBothVariants,
    fieldVariantKey,
    getActiveCoverageMode,
    debounce,
    haversineKm,
    getBrowserGeolocation,
    getIPGeolocation,
    _updateFieldBadge,
    _updateRadarBadge,
    updateLiveIndicator,
    _hideFieldLoadingBadge,
    isTopsCoresAvailableForField
} from './radar-utils.js';

import { 
    COVERAGE_MODES, 
    DEFAULT_TIME_WINDOW_HOURS,
    DEFAULT_RADAR_STATUS_REFRESH_INTERVAL_MS,
    DEFAULT_LIVE_REFRESH_INTERVAL_MS,
    GEOLOCATION_AUTO_SELECT_COUNT,
    GEOLOCATION_AUTO_PRODUCT,
    GEOLOCATION_AUTO_LOAD_HOURS,
    DEFAULT_FIELD_OPACITY,
    MS_PER_HOUR,
    LIVE_REFRESH_MAX_COGS
} from './constants.js';

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
    topsCoresLayer: null,
    topsCoresVisible: false,
    topsCoresPointSize: 4,
    smoothingEnabled: false,
    smoothingSigma: 0.8,
    coverageModeId: 'cd',
    // Set when the animation was torn down because the last radar was removed,
    // so re-selecting a radar resumes the same field + time window (see #1).
    resumePending: false,
};

// =============================================================================
// SETTINGS HELPERS (localStorage) — identical to app.js
// =============================================================================

const SETTINGS_KEY_SHOW_INACTIVE      = 'webmet25_show_inactive_radars';
const SETTINGS_KEY_SHOW_FILTERED      = 'webmet25_show_filtered_fields';
const SETTINGS_KEY_COVERAGE_VISIBLE   = 'webmet25_coverage_visible';
const SETTINGS_KEY_COVERAGE_OPACITY   = 'webmet25_coverage_opacity';
const SETTINGS_KEY_COVERAGE_MODE      = 'webmet25_coverage_mode';
const SETTINGS_KEY_TOPS_CORES_VISIBLE = 'webmet25_tops_cores_visible';
const SETTINGS_KEY_TOPS_CORES_SIZE    = 'webmet25_tops_cores_size';
const SETTINGS_KEY_ACTIVE_ONLY_LEGACY = 'webmet25_active_only';
const SETTINGS_KEY_SMOOTH_ENABLED     = 'webmet25_smooth_enabled';
const SETTINGS_KEY_SMOOTH_SIGMA       = 'webmet25_smooth_sigma';

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
    return DEFAULT_RADAR_STATUS_REFRESH_INTERVAL_MS;
}

function getLiveRefreshIntervalMs() {
    return DEFAULT_LIVE_REFRESH_INTERVAL_MS;
}

// =============================================================================
// SNAPSHOT OVERLAY HELPERS
// Each function draws one element onto an existing canvas context.
// They are intentionally standalone so any can be commented out in
// captureMapSnapshot() without touching the others.
// =============================================================================

/**
 * Draw the OHMC logo onto the canvas (top-left corner).
 * The source asset is a @3x PNG, so we render it at its CSS display size.
 */
async function snapshotOverlayLogo(ctx) {
    const img = document.querySelector('#logo-container img');
    if (!img || !img.complete || img.naturalWidth === 0) return;
    // Respect the 65 px CSS height; derive width proportionally.
    const displayH = 75;
    const displayW = Math.round(img.naturalWidth * (displayH / img.naturalHeight));
    ctx.save();
    ctx.globalAlpha = 1;
    ctx.drawImage(img, 16, 16, displayW, displayH);
    ctx.restore();
}

/**
 * Draw a vertical colormap legend (bottom-left).
 * Draws: product title → gradient bar with tick marks → unit label.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {HTMLCanvasElement}        canvas
 * @param {object|null}              colormapData  - LegendRenderer.currentColormap
 */
function snapshotOverlayVerticalLegend(ctx, canvas, colormapData) {
    if (!colormapData?.colors?.length) return;

    const cm        = colormapData;
    const BAR_W     = 18; // gradient bar width
    const BAR_H     = 180; // gradient bar height
    const TICK_LEN  = 6; // tick mark length
    const LABEL_SZ  = 11; // tick value font size
    const TITLE_SZ  = 14; // product title font size
    const PAD       = 12; // inner padding of the background box
    const marginL   = 16;
    // Reserve space for title above and unit below the bar
    const totalH    = TITLE_SZ + 6 + BAR_H + 18;
    const x0        = marginL;
    const y0        = canvas.height - totalH - 20;

    const vmin        = cm.vmin ?? 0;
    const vmax        = cm.vmax ?? 100;
    const range       = vmax - vmin;
    const decimals    = range >= 10 ? 0 : range >= 1 ? 1 : 2;
    const labelColW   = 42; // estimated max label width
    const bgW         = PAD + BAR_W + TICK_LEN + 4 + labelColW + PAD;
    const bgH         = totalH + PAD;

    ctx.save();

    // Semi-transparent background panel
    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    _snapshotRoundRect(ctx, x0 - PAD, y0 - PAD, bgW, bgH, 6);
    ctx.fill();

    // Title
    ctx.fillStyle   = '#ffffff';
    ctx.font        = `bold ${TITLE_SZ}px "Inter", sans-serif`;
    ctx.textAlign   = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(cm.product_title || cm.product_key || '', x0, y0);

    const barY = y0 + TITLE_SZ + 6;

    // Gradient bar (bottom → top = vmin → vmax)
    const grad = ctx.createLinearGradient(0, barY + BAR_H, 0, barY);
    const SAMPLES = 64;
    for (let i = 0; i < SAMPLES; i++) {
        const t   = i / (SAMPLES - 1);
        const idx = Math.round(t * (cm.colors.length - 1));
        grad.addColorStop(t, cm.colors[idx]);
    }
    ctx.fillStyle = grad;
    ctx.fillRect(x0, barY, BAR_W, BAR_H);

    // Tick marks + labels
    const tickVals = (cm.ticks?.length)
        ? cm.ticks.map(t => t.value).filter(v => v >= vmin && v <= vmax)
        : Array.from({ length: 5 }, (_, i) => vmin + (i / 4) * range);

    ctx.font        = `${LABEL_SZ}px "Inter", monospace`;
    ctx.fillStyle   = '#ffffff';
    ctx.strokeStyle = 'rgba(255,255,255,0.8)';
    ctx.lineWidth   = 1;
    ctx.textBaseline = 'middle';
    tickVals.forEach(v => {
        const frac = range > 0 ? (v - vmin) / range : 0;
        const ty   = barY + BAR_H - frac * BAR_H;
        ctx.beginPath();
        ctx.moveTo(x0 + BAR_W, ty);
        ctx.lineTo(x0 + BAR_W + TICK_LEN, ty);
        ctx.stroke();
        ctx.fillText(v.toFixed(decimals), x0 + BAR_W + TICK_LEN + 4, ty);
    });

    // Unit label
    ctx.font        = `${LABEL_SZ}px "Inter", sans-serif`;
    ctx.textBaseline = 'top';
    ctx.fillText(cm.unit?.trim() || '', x0, barY + BAR_H + 4);

    ctx.restore();
}

/**
 * Draw an info panel (bottom-right) showing the selected field and current
 * frame datetime.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {HTMLCanvasElement}        canvas
 * @param {string}                   fieldLabel
 * @param {string}                   timeText
 */
function snapshotOverlayInfoPanel(ctx, canvas, fieldLabel, timeText) {
    const lines = [fieldLabel, timeText].filter(s => s && s !== '—');
    if (!lines.length) return;

    const FONT_SZ  = 15; // font size for info panel
    const LINE_H   = FONT_SZ + 6;
    const PAD      = 10;
    const boxW     = 260;
    const boxH     = lines.length * LINE_H + PAD * 2;
    const x        = canvas.width  - boxW - 16;
    const y        = canvas.height - boxH - 16;

    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    _snapshotRoundRect(ctx, x, y, boxW, boxH, 6);
    ctx.fill();

    ctx.fillStyle   = '#ffffff';
    ctx.textAlign   = 'left';
    ctx.textBaseline = 'top';
    lines.forEach((line, i) => {
        const isFirst = i === 0;
        ctx.font = isFirst
            ? `bold ${FONT_SZ}px "Inter", sans-serif`
            : `${FONT_SZ}px "Inter", sans-serif`;
        ctx.fillText(line, x + PAD, y + PAD + i * LINE_H);
    });
    ctx.restore();
}

/** Helper: draw a filled rounded rectangle path (Canvas 2D). */
function _snapshotRoundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
}

// =============================================================================
// MAIN APPLICATION
// =============================================================================

const app = {
    async init() {
        state.ui = new UIControls();
        state.ui.setStatus('Inicializando...', 'loading');

        state.showInactiveRadars    = getSettingShowInactive();
        state.showUnfilteredProducts = getSettingShowFiltered();

        try {
            // await this.waitForLeaflet();
            await waitForLeaflet();

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
            _updateRadarBadge(state.selectedRadars);
            _updateFieldBadge(state.selectedProduct);

            // v2: wire animation DOM controls now that ui and animator exist
            state.animator.initControls(state.ui);

            // Make animation panel draggable via its info-row header
            this._initDraggablePanel();
            // Initialize TopsCoresLayer (but don't show it yet)
            state.topsCoresLayer = new TopsCoresLayer(state.mapManager._map);
            state.topsCoresLayer.setPointSize(state.topsCoresPointSize);
            if (state.topsCoresVisible) {
                state.topsCoresLayer.setVisible(true);
            } else {
                state.topsCoresLayer.setVisible(false);
            }

            state.ui.enableAnimationControls(false);
            state.ui.enableNavButtons(false);

            state.ui.setStatus('Listo', 'success');
            this.startRadarStatusRefresh();
            this.tryGeolocationAutoInit();

        } catch (error) {
            console.error('Init error:', error);
            state.ui.setStatus(`Error: ${error.message}`, 'error');
        }
    },

    async loadInitialData() {
        state.radars = await api.getRadars(!state.showInactiveRadars);
        state.ui.populateRadarCheckboxes(state.radars, state.showInactiveRadars);
        this.updateActiveOnlyToggle();

        // Restore coverage mode from localStorage before fetching products so
        // that only products belonging to the current mode's volumes are loaded.
        const storedMode = localStorage.getItem(SETTINGS_KEY_COVERAGE_MODE);
        if (storedMode && COVERAGE_MODES.find(m => m.id === storedMode)) {
            state.coverageModeId = storedMode;
        }
        const mode = getActiveCoverageMode(state.coverageModeId);

        // In VIG mode filtered fields are not available — force showUnfilteredProducts.
        if (!mode.filteredFieldsAvailable) {
            state.showUnfilteredProducts = true;
        }

        state.products = await api.getProducts(mode.volNrs, mode.strategy);
        state.ui.populateProductSelect(state.products, state.showUnfilteredProducts, mode.filteredFieldsAvailable);
        state.ui.updateFilterToggle(state.showUnfilteredProducts);
        state.ui.setFilterToggleEnabled(mode.filteredFieldsAvailable);

        const productSelect = document.getElementById('product-select');
        const availableKeys = getAvailableProductKeys(state.products, state.showUnfilteredProducts);
        const defaultProduct = selectDefaultProduct(availableKeys);

        state.selectedProduct = defaultProduct;
        if (productSelect) productSelect.value = defaultProduct || '';
        this._updateFilteredSwitchAvailability();
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
        const intervalDisplay = document.getElementById('settings-refresh-interval-display');
        if (intervalDisplay) {
            intervalDisplay.textContent = `${DEFAULT_RADAR_STATUS_REFRESH_INTERVAL_MS / 60000} min`;
        }
        const liveIntervalDisplay = document.getElementById('settings-live-refresh-interval-display');
        if (liveIntervalDisplay) {
            liveIntervalDisplay.textContent = `${DEFAULT_LIVE_REFRESH_INTERVAL_MS / 60000} min`;
        }
        // Sync coverage opacity slider with stored value
        const coverageOpacitySliderInit = document.getElementById('coverage-opacity');
        if (coverageOpacitySliderInit) {
            const storedOpacity = parseFloat(
                localStorage.getItem('webmet25_coverage_opacity')
            ) || 0.4;
            coverageOpacitySliderInit.value = storedOpacity;
        }
        // Sync tops & cores toggle and size slider with stored values
        const topsCoresToggle = document.getElementById('toggle-tops-cores');
        if (topsCoresToggle) {
            const stored = localStorage.getItem(SETTINGS_KEY_TOPS_CORES_VISIBLE);
            state.topsCoresVisible = stored === null
                ? isTopsCoresAvailableForField(state.selectedProduct)
                : stored === 'true';
            topsCoresToggle.checked = state.topsCoresVisible;
        }
        const topsCoresSizeSlider = document.getElementById('tops-cores-size');
        if (topsCoresSizeSlider) {
            // Slider range is 2–10 (step 0.5). Clamp any value persisted under the
            // old 4–20 range so the thumb stays inside the rescaled track.
            const stored = localStorage.getItem(SETTINGS_KEY_TOPS_CORES_SIZE);
            const parsed = stored !== null ? parseFloat(stored) : 4;
            state.topsCoresPointSize = Math.min(10, Math.max(2, isNaN(parsed) ? 4 : parsed));
            topsCoresSizeSlider.value = state.topsCoresPointSize;
        }
        // Smooth: restore from localStorage
        const smoothToggle = document.getElementById('toggle-smoothing');
        if (smoothToggle) {
            const stored = localStorage.getItem(SETTINGS_KEY_SMOOTH_ENABLED);
            state.smoothingEnabled = stored === 'true';
            smoothToggle.checked = state.smoothingEnabled;
        }
        const smoothSigmaSlider = document.getElementById('smoothing-sigma');
        const smoothSigmaValue  = document.getElementById('smoothing-sigma-value');
        if (smoothSigmaSlider) {
            const stored = localStorage.getItem(SETTINGS_KEY_SMOOTH_SIGMA);
            const sigma  = stored !== null ? parseFloat(stored) : 0.8;
            state.smoothingSigma = isNaN(sigma) ? 0.8 : Math.min(Math.max(sigma, 0.3), 3.0);
            smoothSigmaSlider.value = state.smoothingSigma;
            if (smoothSigmaValue) smoothSigmaValue.textContent = state.smoothingSigma.toFixed(1);
        }
        const speedSlider = document.getElementById('speed-slider');
        const speedValue  = document.getElementById('speed-value');
        if (speedSlider && speedValue) {
            const s = state.animator ? state.animator.getSpeed() : 1.0;
            speedSlider.value = s;
            speedValue.textContent = `${s.toFixed(1)}x`;
        }
        this._syncFieldOpacitySlider();
        this._updateTopsCoresUIVisibility();
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
            state.ui.setStatus('Seleccione radar(es) y campo para comenzar', '');
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
            this.onRadarCheckboxChange();

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
            _updateFieldBadge(selectedProduct);
            await this.loadColormapOptions();
            this._updateTopsCoresUIVisibility();
            this._updateFilteredSwitchAvailability();

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

        // Coverage mode toggle — cycles modes and reloads products / frames.
        // COVERAGE_MODES is defined at module level and is the single source
        // of truth for vol->mode mapping.
        const coverageToggleBtn = document.getElementById('coverage-toggle');
        if (coverageToggleBtn) {
            // Sync button label to current state (restored from localStorage in loadInitialData).
            coverageToggleBtn.textContent = getActiveCoverageMode(state.coverageModeId).label;

            // Disable the button while a switch is in flight so a quick second
            // click can't race the async product/frame reload of the first.
            let coverageSwitching = false;
            coverageToggleBtn.addEventListener('click', async () => {
                if (coverageSwitching) return;
                coverageSwitching = true;
                coverageToggleBtn.disabled = true;
                try {
                    const currentIdx = COVERAGE_MODES.findIndex(m => m.id === state.coverageModeId);
                    const nextMode   = COVERAGE_MODES[(currentIdx + 1) % COVERAGE_MODES.length];

                    state.coverageModeId = nextMode.id;
                    localStorage.setItem(SETTINGS_KEY_COVERAGE_MODE, nextMode.id);
                    coverageToggleBtn.textContent = nextMode.label;

                    // In VIG mode filtered fields don't exist — force raw/unfiltered.
                    if (!nextMode.filteredFieldsAvailable) {
                        state.showUnfilteredProducts = true;
                        localStorage.setItem(SETTINGS_KEY_SHOW_FILTERED, 'true');
                    }

                    // Re-fetch the product list for the new volumes.
                    state.products = await api.getProducts(nextMode.volNrs, nextMode.strategy);

                    // Field persistence (#10): keep the current field if the new
                    // mode has it (preferring the same filtered/unfiltered variant);
                    // otherwise fall back to the mode's default field
                    // (vig → DBZHo, cd → COLMAXo).
                    const keptVariant =
                        fieldVariantKey(state.products, state.selectedProduct, state.showUnfilteredProducts)
                        || state.products
                            .map(p => p.product_key)
                            .find(k => baseFieldKey(k) === baseFieldKey(state.selectedProduct));
                    if (keptVariant) {
                        state.selectedProduct = keptVariant;
                    } else {
                        const productKeys = state.products.map(p => p.product_key);
                        state.selectedProduct = productKeys.includes(nextMode.defaultProductKey)
                            ? nextMode.defaultProductKey
                            : (getAvailableProductKeys(state.products, state.showUnfilteredProducts)[0]
                                || productKeys[0] || null);
                        // Align the filtered view with the default field's variant
                        // so the dropdown actually shows the selected default.
                        if (state.selectedProduct && nextMode.filteredFieldsAvailable) {
                            state.showUnfilteredProducts = /o$/.test(state.selectedProduct);
                            localStorage.setItem(SETTINGS_KEY_SHOW_FILTERED, String(state.showUnfilteredProducts));
                        }
                    }

                    // Refresh the dropdown + filtered toggle for the resolved view.
                    state.ui.populateProductSelect(
                        state.products, state.showUnfilteredProducts, nextMode.filteredFieldsAvailable
                    );
                    state.ui.updateFilterToggle(state.showUnfilteredProducts);
                    const productSelect = document.getElementById('product-select');
                    if (productSelect && state.selectedProduct) productSelect.value = state.selectedProduct;

                    // Sync state.selectedProduct from the actual dropdown value.
                    // After populateProductSelect the browser may have reset to the
                    // placeholder if our computed value wasn't a valid option; reading
                    // back guarantees we use what the dropdown really shows.
                    const syncedProductSelect = document.getElementById('product-select');
                    if (syncedProductSelect) {
                        if (syncedProductSelect.value) {
                            state.selectedProduct = syncedProductSelect.value;
                        } else if (syncedProductSelect.options.length > 1) {
                            // Placeholder is index 0 — pick first real option.
                            syncedProductSelect.selectedIndex = 1;
                            state.selectedProduct = syncedProductSelect.value;
                        }
                    }
                    // Update colormap/badge/UI state for the new field.
                    state.selectedColormap = null;
                    state.currentVmin = null;
                    state.currentVmax = null;
                    this.onTimeRangeChange();
                    _updateFieldBadge(state.selectedProduct);
                    await this.loadColormapOptions();
                    this._updateTopsCoresUIVisibility();
                    this._updateFilteredSwitchAvailability();
                    if (state.selectedRadars.length > 0 && state.selectedProduct) {
                        const wasPlaying  = state.animator.getIsPlaying();
                        const cogsBefore  = state.cogs;
                        // Stop so loadLastNHours takes loadTimeRangeCogs (full visible reload).
                        if (wasPlaying) {
                            state.animator.stop();
                            state.ui.updatePlayButton(false);
                        }
                        await this.loadLastNHours(
                            state.activeTimeWindowHours ?? DEFAULT_TIME_WINDOW_HOURS
                        );
                        // Auto-resume if playback was active and new data was loaded.
                        if (wasPlaying && state.cogs !== cogsBefore && state.cogs && state.cogs.length > 0) {
                            state.animator.play();
                            state.ui.updatePlayButton(true);
                        }
                    }
                } finally {
                    coverageSwitching = false;
                    coverageToggleBtn.disabled = false;
                }
            });
        }

        const coverageOpacitySlider = document.getElementById('coverage-opacity');
        if (coverageOpacitySlider) {
            const storedOpacity = parseFloat(
                localStorage.getItem('webmet25_coverage_opacity')
            ) || 0.4;
            coverageOpacitySlider.value = storedOpacity;
            coverageOpacitySlider.addEventListener('input', (e) => {
                const val = parseFloat(e.target.value);
                localStorage.setItem('webmet25_coverage_opacity', JSON.stringify(val));
                state.mapManager.setCoverageOpacity(val);
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
            showFilteredToggle.addEventListener('change', async (e) => {
                // #2: the switch toggles the SELECTED field between its filtered
                // and unfiltered variant — it keeps the same field.
                // Toggle ON  → filtered variant (no 'o' suffix) → showUnfilteredProducts = false
                // Toggle OFF → unfiltered variant ('o' suffix)  → showUnfilteredProducts = true
                state.showUnfilteredProducts = !e.target.checked;
                localStorage.setItem(SETTINGS_KEY_SHOW_FILTERED, String(state.showUnfilteredProducts));
                const mode = getActiveCoverageMode(state.coverageModeId);

                // Remap the current field to the requested variant (if it exists),
                // keeping the field the same.
                const variant = fieldVariantKey(
                    state.products, state.selectedProduct, state.showUnfilteredProducts
                );
                if (variant) state.selectedProduct = variant;

                state.ui.populateProductSelect(state.products, state.showUnfilteredProducts, mode.filteredFieldsAvailable);
                state.ui.updateFilterToggle(state.showUnfilteredProducts);
                const productSelect = document.getElementById('product-select');
                if (productSelect && state.selectedProduct) productSelect.value = state.selectedProduct;

                if (variant) {
                    // Same field, different variant → reload colormap/range/frames.
                    await this._onProductChanged();
                }
            });
        }

        // Tops & Cores toggle
        const topsCoresToggle = document.getElementById('toggle-tops-cores');
        const topsCoresSizeRow = document.getElementById('tops-cores-size-row');
        if (topsCoresToggle) {
            topsCoresToggle.addEventListener('change', (e) => {
                state.topsCoresVisible = e.target.checked;
                localStorage.setItem(SETTINGS_KEY_TOPS_CORES_VISIBLE, String(state.topsCoresVisible));
                if (topsCoresSizeRow) {
                    topsCoresSizeRow.style.display = e.target.checked ? 'block' : 'none';
                }
                this._updateTopsCoresLayer();
            });
        }

        // Tops & Cores point size slider
        const topsCoresSizeSlider = document.getElementById('tops-cores-size');
        if (topsCoresSizeSlider) {
            topsCoresSizeSlider.addEventListener('input', (e) => {
                const size = parseFloat(e.target.value);
                if (!isNaN(size)) {
                    state.topsCoresPointSize = size;
                    localStorage.setItem(SETTINGS_KEY_TOPS_CORES_SIZE, String(size));
                    if (state.topsCoresLayer) {
                        state.topsCoresLayer.setPointSize(size);
                    }
                }
            });
        }

        // Gaussian smoothing toggle
        const smoothToggle = document.getElementById('toggle-smoothing');
        const smoothSigmaRow = document.getElementById('smoothing-sigma-row');
        if (smoothToggle) {
            smoothToggle.addEventListener('change', async (e) => {
                state.smoothingEnabled = e.target.checked;
                localStorage.setItem(SETTINGS_KEY_SMOOTH_ENABLED, String(state.smoothingEnabled));
                if (smoothSigmaRow) {
                    smoothSigmaRow.style.display = state.smoothingEnabled ? 'block' : 'none';
                }
                if (state.animationMode === 'timerange') {
                    await this._loadFramesWithContinuity(
                        () => this._fetchTimeRangeFrames(),
                        { showBadge: true, badgeText: 'Applying…' }
                    );
                } else if (state.animationMode === 'latest') {
                    await this.loadLatestCogs();
                }
            });
        }

        // Gaussian smoothing sigma slider (debounced 400 ms)
        const smoothSigmaSlider = document.getElementById('smoothing-sigma');
        const smoothSigmaValue  = document.getElementById('smoothing-sigma-value');
        if (smoothSigmaSlider) {
            const debouncedSigmaReload = debounce(async () => {
                if (state.animationMode === 'timerange') {
                    await this._loadFramesWithContinuity(
                        () => this._fetchTimeRangeFrames(),
                        { showBadge: false }
                    );
                } else if (state.animationMode === 'latest') {
                    await this.loadLatestCogs();
                }
            }, 400);

            smoothSigmaSlider.addEventListener('input', (e) => {
                const sigma = parseFloat(e.target.value);
                if (!isNaN(sigma)) {
                    state.smoothingSigma = sigma;
                    if (smoothSigmaValue) smoothSigmaValue.textContent = sigma.toFixed(1);
                    localStorage.setItem(SETTINGS_KEY_SMOOTH_SIGMA, String(sigma));
                    if (state.smoothingEnabled) debouncedSigmaReload();
                }
            });
        }

        // Field-menu accordion (#9): each section header toggles its body open/
        // closed. A section marked .disabled (e.g. Tops & Cores for a field that
        // doesn't support it) is grayed and does not expand.
        document.querySelectorAll('#panel-module-b .field-section-header').forEach(header => {
            header.addEventListener('click', () => {
                const section = header.closest('.field-section');
                if (!section || section.classList.contains('disabled')) return;
                const open = section.classList.toggle('open');
                header.setAttribute('aria-expanded', String(open));
            });
        });

        const radarCheckboxes = document.getElementById('radar-checkboxes');
        if (radarCheckboxes) {
            radarCheckboxes.addEventListener('change', () => this.onRadarCheckboxChange());
        }

        // All / None radar selection buttons
        const selectAllBtn = document.getElementById('btn-select-all-radars');
        if (selectAllBtn) {
            selectAllBtn.addEventListener('click', () => {
                document.querySelectorAll('#radar-checkboxes input[type="checkbox"]').forEach(cb => {
                    const item = cb.closest('.radar-checkbox-item');
                    if (item && !item.classList.contains('radar-inactive')) cb.checked = true;
                });
                this.onRadarCheckboxChange();
            });
        }
        const selectNoneBtn = document.getElementById('btn-clear-all-radars');
        if (selectNoneBtn) {
            selectNoneBtn.addEventListener('click', () => {
                const checkboxes = document.querySelectorAll('#radar-checkboxes input[type="checkbox"]');
                checkboxes.forEach(cb => { cb.checked = false; });
                this.onRadarCheckboxChange();
            });
        }

        const productSelect = document.getElementById('product-select');
        if (productSelect) {
            productSelect.addEventListener('change', async (e) => {
                state.selectedProduct = e.target.value || null;
                await this._onProductChanged();
            });
        }

        const loadBtn = document.getElementById('btn-load-timerange');
        if (loadBtn) {
            loadBtn.addEventListener('click', () => {
                this.stopLiveRefresh();
                this.loadTimeRangeCogs();
            });
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
                    const timerangeContainer = document.getElementById('timerange-container');
                    if (timerangeContainer) timerangeContainer.style.display = 'none';
                    this.loadLastNHours(hours);
                }
            });
        });

        const customRangeBtn = document.getElementById('btn-custom-range');
        if (customRangeBtn) {
            customRangeBtn.addEventListener('click', () => {
                const timerangeContainer = document.getElementById('timerange-container');
                if (!timerangeContainer) return;
                const isHidden = timerangeContainer.style.display === 'none' || !timerangeContainer.style.display;
                timerangeContainer.style.display = isHidden ? 'block' : 'none';
                if (isHidden) {
                    document.querySelectorAll('[data-hours]').forEach(b => b.classList.remove('active'));
                    state.activeTimeWindowHours = null;
                    // Wheels can only be positioned once visible — re-center now.
                    state.ui.refreshTimeWheels();
                }
            });
        }

        const startInput = document.getElementById('start-date');
        const endInput   = document.getElementById('end-date');
        if (startInput) startInput.addEventListener('change', () => this.onTimeRangeChange());
        if (endInput)   endInput.addEventListener('change',   () => this.onTimeRangeChange());

        // Build the iOS-style time wheels for the custom range.
        state.ui.initTimeWheels();

        // Colormap
        const colormapSelect = document.getElementById('colormap-select');
        if (colormapSelect) {
            colormapSelect.addEventListener('change', async (e) => {
                state.selectedColormap = e.target.value || null;
                // Update legend immediately with new colormap.
                await this.applyColormapChange();
                // Re-fetch frames in background with new colormap applied.
                // No badge — colormap re-fetch is fast (typically Redis-cached).
                if (state.animationMode === 'timerange') {
                    await this._loadFramesWithContinuity(
                        () => this._fetchTimeRangeFrames(),
                        { showBadge: false }
                    );
                } else if (state.animationMode === 'latest') {
                    await this.loadLatestCogs();
                }
            });
        }

        const applyColormapBtn = document.getElementById('btn-apply-range');
        if (applyColormapBtn) {
            applyColormapBtn.addEventListener('click', async () => {
                // Apply button handles range filter (vmin/vmax) only.
                // Re-fetch frames in background — animation keeps playing.
                if (state.animationMode === 'timerange') {
                    await this._loadFramesWithContinuity(
                        () => this._fetchTimeRangeFrames(),
                        { showBadge: true, badgeText: 'Applying…' }
                    );
                } else if (state.animationMode === 'latest') {
                    await this.loadLatestCogs();
                } else {
                    await this.applyColormapChange();
                }
            });
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

        // Live refresh manual trigger (main toolbar button)
        const cogRefreshNowBtn = document.getElementById('btn-cog-refresh-now');
        if (cogRefreshNowBtn) {
            cogRefreshNowBtn.addEventListener('click', () => {
                if (state.liveHours !== null) {
                    this.refreshLiveWindow(true);
                } else {
                    const badge = document.getElementById('field-loading-badge');
                    if (badge) {
                        badge.textContent = 'Solo disponible en modo en vivo.';
                        badge.classList.add('empty', 'visible');
                        badge.classList.remove('found');
                        setTimeout(() => badge.classList.remove('visible', 'empty'), 3000);
                    }
                }
            });
        }

        // Radar status refresh — settings panel "Refresh Now" button
        const radarRefreshNowBtn = document.getElementById('btn-radar-refresh-now');
        if (radarRefreshNowBtn) {
            radarRefreshNowBtn.addEventListener('click', () => this.refreshRadarList());
        }

        // Live window manual refresh — settings panel "Refresh Now" button
        const settingsCogRefreshBtn = document.getElementById('btn-settings-cog-refresh-now');
        if (settingsCogRefreshBtn) {
            settingsCogRefreshBtn.addEventListener('click', () => {
                if (state.liveHours !== null) this.refreshLiveWindow(true);
                else state.ui.setStatus('El modo en vivo no está activo', 'error');
            });
        }
    },

    // =========================================================================
    // Field change (shared by the product dropdown AND the coverage-mode switch)
    // =========================================================================

    /**
     * Apply all side effects of the selected field changing: reset the
     * colormap/range, refresh the field badge + colormap options + Tops&Cores
     * visibility, recompute the Filtered switch availability, then reload frames.
     * Both the product dropdown and the coverage-mode switch call this so the
     * two paths stay consistent — routing the mode switch through here is what
     * fixes its "needs two clicks to apply" behaviour (it previously did a
     * partial, out-of-order update that never reloaded the colormap).
     * Assumes state.selectedProduct is already set to the new field.
     */
    async _onProductChanged() {
        state.selectedColormap = null;
        state.currentVmin = null;
        state.currentVmax = null;
        this.onTimeRangeChange();
        _updateFieldBadge(state.selectedProduct);
        await this.loadColormapOptions();
        this._updateTopsCoresUIVisibility();
        this._updateFilteredSwitchAvailability();
        if (state.animationMode === 'timerange') {
            // Load new field frames in background — animation continues with the
            // old field until the new frames are ready.
            await this._loadFramesWithContinuity(
                () => this._fetchTimeRangeFrames(),
                { showBadge: true, badgeText: 'Cargando campo…' }
            );
        } else {
            await this.loadLatestCogs();
        }
    },

    /**
     * Enable/disable the Filtered switch based on whether the SELECTED field has
     * both a filtered and an unfiltered variant in the current product list (#2).
     * When it can't be toggled, a native tooltip explains why.
     */
    _updateFilteredSwitchAvailability() {
        const toggle = document.getElementById('toggle-show-filtered');
        if (!toggle) return;
        const mode = getActiveCoverageMode(state.coverageModeId);
        const hasBoth = !!state.selectedProduct
            && fieldHasBothVariants(state.products, state.selectedProduct);
        const enabled = mode.filteredFieldsAvailable && hasBoth;

        if (state.ui.setFilterToggleEnabled) {
            state.ui.setFilterToggleEnabled(enabled);
        } else {
            toggle.disabled = !enabled;
        }
        // Reflect the current field's variant on the switch (checked = filtered).
        toggle.checked = !state.showUnfilteredProducts;

        const wrapper = toggle.closest('.toggle-switch-wrapper') || toggle.parentElement;
        if (wrapper) {
            wrapper.title = enabled
                ? ''
                : 'No hay COGs filtrados para este campo';
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

        // Update coverage mask — always active, no visibility guard
        added.forEach(code => {
            const radar = state.radars.find(r => r.code === code);
            if (radar && radar.center_lat && radar.center_long && radar.img_radio) {
                state.mapManager.addRadarCoverage(
                    code, radar.center_lat, radar.center_long, radar.img_radio * 1000
                );
            }
        });
        removed.forEach(code => state.mapManager.removeRadarCoverage(code));

        const hasLiveFrames = state.animationMode === 'timerange'
            && Array.isArray(state.cogs) && state.cogs.length > 0;
        if (hasLiveFrames) {
            // Mid-animation: incremental add/remove keeps playback continuous.
            // (Removing the LAST radar tears the animation down and arms
            //  state.resumePending — see removeRadarIncremental.)
            added.forEach(code => this.addRadarIncremental(code));
            removed.forEach(code => this.removeRadarIncremental(code));
        } else if (state.resumePending && newSelection.length > 0 && state.selectedProduct) {
            // Resuming after a deselect-all teardown: there are no live frames to
            // merge into, so do a full load for the SAME field + the currently
            // selected time window, and start playback again (#1).
            this._resumeAnimationForSelection();
        }
        _updateRadarBadge(state.selectedRadars);
    },

    /**
     * Full reload + auto-play after the animation was torn down by clearing all
     * radars (#1). Uses whatever time window is currently selected — including a
     * different one chosen WHILE no radars were selected (the spec's exception),
     * because that choice already updated state.activeTimeWindowHours / the
     * custom-range inputs.
     */
    async _resumeAnimationForSelection() {
        state.resumePending = false;
        if (state.selectedRadars.length === 0 || !state.selectedProduct) return;
        if (state.activeTimeWindowHours != null) {
            await this.loadLastNHours(state.activeTimeWindowHours);
        } else {
            const tr = state.ui.getTimeRangeValues();
            if (tr.start && tr.end) await this.loadTimeRangeCogs();
            else await this.loadLastNHours(DEFAULT_TIME_WINDOW_HOURS);
        }
        if (state.animationMode === 'timerange'
            && Array.isArray(state.cogs) && state.cogs.length > 1) {
            state.animator.play();
            state.ui.updatePlayButton(true);
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

        state.ui.setStatus(`Agregando ${radarCode.toUpperCase()} a la animación…`, 'loading');

        try {
            const mode = getActiveCoverageMode(state.coverageModeId);
            const newCogs = await api.getCogsForTimeRange(
                [radarCode], state.selectedProduct, timeRange.start, timeRange.end, 100,
                mode.volNrs, mode.strategy
            );

            if (newCogs.length === 0) {
                state.ui.setStatus(
                    `⚠️ Sin datos para ${radarCode.toUpperCase()} en el rango de tiempo actual`, 'error'
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

            // Update coverage mask: use COG-based radius for the newly added radar
            this._updateCoverageFromCogs(newCogs);

            state.ui.updateFrameCounter(newCurrentIndex, state.cogs.length);
            state.ui.updateAnimationSlider(newCurrentIndex, state.cogs.length);
            state.ui.setStatus(`✓ Agregado ${radarCode.toUpperCase()} — ${state.cogs.length} fotogramas`, 'success');

        } catch (err) {
            console.error('addRadarIncremental error:', err);
            state.ui.setStatus(`Error al agregar ${radarCode.toUpperCase()}: ${err.message}`, 'error');
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
            // Remember that an animation was torn down by clearing radars, so
            // re-selecting a radar resumes the same field + window (#1).
            state.resumePending = true;
            state.ui.enableAnimationControls(false);
            state.ui.enableNavButtons(false);
            state.ui.setStatus(`No quedan fotogramas tras quitar ${radarCode.toUpperCase()}`, 'error');
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
        const _td1 = document.getElementById('time-display');
        if (_td1) _td1.textContent = formatTimestamp(newFrames[newCurrentIndex].timestamp);
        state.ui.setStatus(`✓ Quitado ${radarCode.toUpperCase()} de la animación`, 'success');
    },

    // =========================================================================
    // Load latest COGs
    // =========================================================================

    async loadLatestCogs() {
        if (state.selectedRadars.length === 0 || !state.selectedProduct) {
            state.ui.setStatus('Seleccione radar(es) y campo', 'error');
            return;
        }
        state.ui.setStatus('Cargando imágenes más recientes...', 'loading');
        state.animator.stop();
        state.ui.updatePlayButton(false);

        try {
            const mode = getActiveCoverageMode(state.coverageModeId);
            const latestCogs = await api.getLatestCogsForRadars(
                state.selectedRadars, state.selectedProduct, mode.volNrs, mode.strategy
            );
            const radarCodesWithData    = latestCogs.map(item => item.radarCode);
            const radarCodesWithoutData = state.selectedRadars.filter(c => !radarCodesWithData.includes(c));

            if (latestCogs.length === 0) {
                const radarList   = state.selectedRadars.join(', ').toUpperCase();
                const productName = state.products.find(p => p.product_key === state.selectedProduct)?.product_title || state.selectedProduct;
                state.ui.setStatus(
                    `⚠️ Sin datos para ${radarList} con el campo "${productName}". Pruebe con otro campo o radar.`,
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
            state.ui.setStatus('Cargando imagen del fotograma…', 'loading');
            await state.mapManager.loadFrames(cogsByFrame, state.selectedProduct, params, null);

            // Zoom to all selected radar bounds
            if (!state.hasZoomedToBounds) {
                const allBounds = this._getAllRadarsBounds();
                if (allBounds) {
                    state.mapManager.getMap().fitBounds(allBounds, {
                        padding: [32, 32],
                        maxZoom: 8,
                    });
                }
                state.hasZoomedToBounds = true;
            }

            // Show single frame
            state.mapManager.showFrame(0, Array.from(singleFrameRadarMap.keys()), state.selectedProduct);

            // Update coverage mask with actual COG coverage radius
            this._updateCoverageFromCogs(Array.from(singleFrameRadarMap.values()));

            if (firstCog) {
                const _td2 = document.getElementById('time-display');
                if (_td2) _td2.textContent = formatTimestamp(firstCog.observation_time);
            }

            if (colormap) {
                this._enrichColormapWithProduct(colormap);
                state.legend.render(colormap);
                state.legend.show();
            }

            const loadedRadars = latestCogs.map(item => item.radarCode.toUpperCase()).join(', ');
            const radarText    = latestCogs.length === 1 ? 'radar' : 'radares';
            let msg = `✓ Mostrando lo más reciente de ${latestCogs.length} ${radarText}: ${loadedRadars}`;
            if (radarCodesWithoutData.length > 0) {
                msg += ` (${radarCodesWithoutData.map(c => c.toUpperCase()).join(', ')} sin datos)`;
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
        this._showFieldLoadingBadge();
        try {
        if (state.selectedRadars.length === 0 || !state.selectedProduct) {
            state.ui.setStatus('Seleccione radar(es) y campo', 'error');
            return;
        }
        const timeRange = state.ui.getTimeRangeValues();
        if (!timeRange.start || !timeRange.end) {
            state.ui.setStatus('Seleccione un rango de tiempo válido', 'error');
            return;
        }
        if (timeRange.start >= timeRange.end) {
            state.ui.setStatus('La hora de inicio debe ser anterior a la de fin', 'error');
            return;
        }

        state.ui.setStatus('Cargando datos del rango de tiempo...', 'loading');

        try {
            const cogs = await api.getCogsForTimeRange(
                state.selectedRadars, state.selectedProduct,
                timeRange.start, timeRange.end, 100,
                getActiveCoverageMode(state.coverageModeId).volNrs, getActiveCoverageMode(state.coverageModeId).strategy
            );

            if (cogs.length === 0) {
                // finally runs first (hides the loading badge), then this re-shows it as empty state
                setTimeout(() => {
                    const badge = document.getElementById('field-loading-badge');
                    if (badge) {
                        badge.textContent = 'Sin datos para el rango seleccionado.';
                        badge.classList.add('empty', 'visible');
                        setTimeout(() => badge.classList.remove('visible', 'empty'), 4000);
                    }
                }, 0);
                return;
            }

            const groupedFrames = groupCogsByTimestamp(cogs, );

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
                        `Cargando fotogramas… ${loaded} / ${total} (${Math.round(loaded / total * 100)}%)`,
                        'loading'
                    );
                }
            );

            // Zoom to all selected radar bounds
            if (!state.hasZoomedToBounds) {
                const allBounds = this._getAllRadarsBounds();
                if (allBounds) {
                    state.mapManager.getMap().fitBounds(allBounds, {
                        padding: [32, 32],
                        maxZoom: 8,
                    });
                }
                state.hasZoomedToBounds = true;
            }

            state.cogs = groupedFrames;

            // Update coverage mask with actual per-product coverage radius from COGs
            const _allCogsTimeRange = groupedFrames.flatMap(f => Object.values(f.cogsByRadar));
            this._updateCoverageFromCogs(_allCogsTimeRange);

            // v2: updateFrames takes (frames, productKey, currentIndex)
            state.animator.updateFrames(groupedFrames, state.selectedProduct, 0);
            if (state.topsCoresLayer && isTopsCoresAvailableForField(state.selectedProduct)) {
                state.topsCoresLayer.loadForFrames(groupedFrames);
            }
            state.animator.goToFrame(0);

            if (colormap) {
                this._enrichColormapWithProduct(colormap);
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
            const radarText    = radarCodes.length === 1 ? 'radar' : 'radares';

            let liveNote = '';
            if (state.liveHours !== null && groupedFrames.length > 0) {
                const oldestFrameTime  = new Date(groupedFrames[0].timestamp);
                const newestFrameTime  = new Date(groupedFrames[groupedFrames.length - 1].timestamp);
                const requestedStart   = state.ui.getTimeRangeValues().start;
                if (requestedStart) {
                    const gapHours = (oldestFrameTime - requestedStart) / MS_PER_HOUR;
                    if (gapHours > 0.5) {
                        const availableHours = ((newestFrameTime - oldestFrameTime) / MS_PER_HOUR).toFixed(1);
                        liveNote = ` ⚠️ Solo ${availableHours}h de datos disponibles (${state.liveHours}h solicitadas)`;
                    }
                }
            }

            state.ui.setStatus(
                `✓ Cargados ${groupedFrames.length} fotogramas de ${radarCodes.length} ${radarText}: ${loadedRadars}${liveNote}`,
                'success'
            );

        } catch (error) {
            console.error('Load time range error:', error);
            state.ui.setStatus(`Error: ${error.message}`, 'error');
        }
        } finally {
            _hideFieldLoadingBadge();
        }
    },

    // =========================================================================
    // Load last N hours
    // =========================================================================

    async loadLastNHours(hours) {
        if (state.selectedRadars.length === 0 || !state.selectedProduct) {
            state.ui.setStatus('Primero seleccione radar(es) y campo', 'error');
            return;
        }
        this.stopLiveRefresh();
        state.ui.setStatus('Buscando los datos más recientes…', 'loading');

        try {
            const mode = getActiveCoverageMode(state.coverageModeId);
            const latestItems = await api.getLatestCogsForRadars(
                state.selectedRadars, state.selectedProduct, mode.volNrs, mode.strategy
            );

            if (latestItems.length === 0) {
                const radarList   = state.selectedRadars.join(', ').toUpperCase();
                const productName = state.products.find(p => p.product_key === state.selectedProduct)?.product_title || state.selectedProduct;
                state.ui.setStatus(
                    `⚠️ Sin datos para ${radarList} con el campo "${productName}". Pruebe con otro campo o radar.`,
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

            // If an animation is already running, reload the new window in the
            // background so playback is not interrupted. Otherwise do a full load
            // which also handles initial setup (zoom, enable controls, etc.).
            if (state.animationMode === 'timerange' && state.animator.getIsPlaying()) {
                await this._loadFramesWithContinuity(
                    () => this._fetchTimeRangeFrames(),
                    { showBadge: true, badgeText: 'Cargando…' }
                );
            } else {
                await this.loadTimeRangeCogs();
            }

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
        updateLiveIndicator(state.liveHours);
    },

    stopLiveRefresh() {
        if (state.liveRefreshInterval !== null) {
            clearInterval(state.liveRefreshInterval);
            state.liveRefreshInterval = null;
        }
        state.liveHours = null;
        updateLiveIndicator(state.liveHours);
    },

    // =========================================================================
    // Live refresh (full-window diff)
    // =========================================================================

    async refreshLiveWindow(showBadge = false) {
        if (!state.liveHours || !state.selectedRadars.length || !state.selectedProduct) {
            if (showBadge) _hideFieldLoadingBadge();
            return;
        }
        if (state.animationMode !== 'timerange' || !state.cogs || state.cogs.length === 0) {
            if (showBadge) {
                const badge = document.getElementById('field-loading-badge');
                if (badge) {
                    badge.textContent = 'Sin animación activa.';
                    badge.classList.add('empty', 'visible');
                    badge.classList.remove('found');
                    setTimeout(() => badge.classList.remove('visible', 'empty'), 3000);
                }
            }
            return;
        }

        if (showBadge) this._showFieldLoadingBadge('Buscando COGs más recientes ahora…');

        try {
            const hours = state.liveHours;

            const mode = getActiveCoverageMode(state.coverageModeId);
            const latestItems = await api.getLatestCogsForRadars(
                state.selectedRadars, state.selectedProduct, mode.volNrs, mode.strategy
            );
            if (!latestItems.length) {
                if (showBadge) _hideFieldLoadingBadge();
                return;
            }

            const newEndTime = latestItems.reduce((max, { cog }) => {
                const t = new Date(cog.observation_time);
                return t > max ? t : max;
            }, new Date(0));
            const newStartTime = new Date(newEndTime.getTime() - hours * MS_PER_HOUR);

            const allCogs = await api.getCogsForTimeRange(
                state.selectedRadars, state.selectedProduct,
                newStartTime, newEndTime, LIVE_REFRESH_MAX_COGS,
                mode.volNrs, mode.strategy
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
            if (newLength === 0) {
                if (showBadge) _hideFieldLoadingBadge();
                return;
            }

            const newCurrentIndex = Math.min(
                indexAfterExpiry + insertionAdjustment,
                newLength - 1
            );

            state.animator.updateFrames(state.cogs, state.selectedProduct, newCurrentIndex);
            if (state.topsCoresLayer && isTopsCoresAvailableForField(state.selectedProduct)) {
                state.topsCoresLayer.loadForFrames(state.cogs);
            }

            state.ui.updateFrameCounter(newCurrentIndex, newLength);
            state.ui.updateAnimationSlider(newCurrentIndex, newLength);
            this.updateTimeWindowLabel();

            console.log(
                `Live refresh: +${cogsToAdd.length} new/recovered COGs, ` +
                `-${expiredIndices.length} expired frames, ${newLength} total frames`
            );

            if (showBadge) {
                const badge = document.getElementById('field-loading-badge');
                if (badge) {
                    if (cogsToAdd.length > 0) {
                        const s = cogsToAdd.length === 1 ? '' : 's';
                        badge.textContent = `+${cogsToAdd.length} COG${s} nuevo${s}.`;
                        badge.classList.add('found', 'visible');
                        badge.classList.remove('empty');
                    } else {
                        badge.textContent = 'Sin COGs nuevos.';
                        badge.classList.add('empty', 'visible');
                        badge.classList.remove('found');
                    }
                    setTimeout(() => badge.classList.remove('visible', 'empty', 'found'), 4000);
                }
            }
        } catch (err) {
            console.warn('Live refresh error (will retry next cycle):', err);
            if (showBadge) _hideFieldLoadingBadge();
        }
    },

    // =========================================================================
    // Frame change callback (from AnimationController)
    // =========================================================================

    onFrameChange(index, frame) {
        if (!frame) return;
        this.updateTimeWindowLabel();

        const timeDisplay = document.getElementById('time-display');

        if (frame.cogsByRadar) {
            // v2: showFrame is called by AnimationController._showCurrentFrame()
            // so we only need to update the UI here
            if (timeDisplay) timeDisplay.textContent = formatTimestamp(frame.timestamp);
            state.ui.updateFrameCounter(index, state.animator.getFrameCount());
            state.ui.updateAnimationSlider(index, state.animator.getFrameCount());

            // Synchronous frame display — data was pre-loaded by loadForFrames()
            if (state.topsCoresLayer && state.topsCoresVisible) {
                state.topsCoresLayer.showFrame(index);
            }
            return;
        }

        // Legacy single-COG fallback
        if (frame.observation_time) {
            if (timeDisplay) timeDisplay.textContent = formatTimestamp(frame.observation_time);
            state.ui.updateFrameCounter(index, state.animator.getFrameCount());
            state.ui.updateAnimationSlider(index, state.animator.getFrameCount());
        }
    },

    updateTimeWindowLabel() {
        const label = document.getElementById('time-window-label');
        if (!label) return;
        if (state.liveHours !== null) {
            label.textContent = `Últimas ${state.liveHours} hrs`;
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
                label.textContent = 'Rango personalizado';
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
            const smoothToggleRowHide = document.getElementById('smoothing-toggle-row');
            const smoothSigmaRowHide  = document.getElementById('smoothing-sigma-row');
            if (smoothToggleRowHide) smoothToggleRowHide.style.display = 'none';
            if (smoothSigmaRowHide)  smoothSigmaRowHide.style.display  = 'none';
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
            // Reveal smoothing toggle; sigma slider follows current state
            const smoothToggleRow = document.getElementById('smoothing-toggle-row');
            const smoothSigmaRow  = document.getElementById('smoothing-sigma-row');
            if (smoothToggleRow) smoothToggleRow.style.display = 'flex';
            if (smoothSigmaRow) {
                smoothSigmaRow.style.display = state.smoothingEnabled ? 'block' : 'none';
            }
            this._syncFieldOpacitySlider();
        } catch (err) {
            console.warn('Failed to load colormap options:', err);
        }
    },

    async applyColormapChange() {
        if (!state.animationMode) return;
        // Update legend only — image reload is now handled by the
        // apply-button and colormap-dropdown handlers via _loadFramesWithContinuity.
        try {
            const colormap = await api.getColormapInfo(state.selectedProduct, state.selectedColormap);
            if (colormap) {
                this._enrichColormapWithProduct(colormap);
                state.legend.render(colormap);
                state.legend.show();
            }
        } catch (e) {
            console.warn('applyColormapChange: failed to update legend:', e);
        }
    },

    /**
     * Enrich a colormap object with product_title and unit from state.products.
     * Called just before legend.render() so the legend shows a human-readable
     * field name and the correct unit.  Mutates and returns the same object.
     *
     * @param {object} colormap - Colormap object returned by api.getColormapInfo()
     * @returns {object} The same colormap object, enriched in-place.
     */
    _enrichColormapWithProduct(colormap) {
        if (!colormap || !state.products) return colormap;
        const product = state.products.find(p => p.product_key === state.selectedProduct);
        if (product) {
            colormap.product_title = product.product_title || null;
            colormap.unit = product.unit !== undefined ? product.unit : null;
        }
        return colormap;
    },

    /**
     * v2 key difference: returns `colormap` (not `cmap`) to match the
     * /api/v1/frames/{id}/image.png query-parameter name.
     */
    getTileParams() {
        return {
            colormap:    state.selectedColormap || null,
            vmin:        state.currentVmin,
            vmax:        state.currentVmax,
            smooth:      state.smoothingEnabled,
            smoothSigma: state.smoothingSigma,
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

    _showFieldLoadingBadge(message = 'Cargando campo…') {
        const badge = document.getElementById('field-loading-badge');
        if (badge) {
            badge.textContent = message;
            badge.classList.add('visible');
        }
    },

    // _hideFieldLoadingBadge() {
    //     const badge = document.getElementById('field-loading-badge');
    //     if (badge) badge.classList.remove('visible');
    // },

    /**
     * Update the SVG coverage mask for each active radar using the actual
     * coverage radius stored in the COG metadata (radar_coverage_m).
     *
     * Accepts a flat array of COG objects (each with .radar_code and
     * .radar_coverage_m).  For each active radar the median coverage radius
     * across all provided COGs is used — this means that for products like
     * VRAD/WRAD (shorter range) the circle will automatically shrink.
     * Falls back to radar.img_radio (km → m) when no COG coverage is available.
     *
     * @param {Array} cogs  Flat array of COG response objects.
     */
    _updateCoverageFromCogs(cogs) {
        if (!cogs || cogs.length === 0) return;

        // Collect per-radar coverage samples from COG metadata
        const samplesByRadar = new Map();
        for (const cog of cogs) {
            if (cog.radar_coverage_m != null) {
                const code = cog.radar_code;
                if (!samplesByRadar.has(code)) samplesByRadar.set(code, []);
                samplesByRadar.get(code).push(cog.radar_coverage_m);
            }
        }

        for (const radarCode of state.selectedRadars) {
            const radar = state.radars.find(r => r.code === radarCode);
            if (!radar || !radar.center_lat || !radar.center_long) continue;

            const samples = samplesByRadar.get(radarCode);
            let radius_m;
            if (samples && samples.length > 0) {
                // Use median to be robust against outliers
                const sorted = samples.slice().sort((a, b) => a - b);
                radius_m = sorted[Math.floor(sorted.length / 2)];
            } else {
                // Fallback: img_radio is stored in km
                radius_m = radar.img_radio ? radar.img_radio * 1000 : null;
            }

            if (radius_m != null) {
                state.mapManager.addRadarCoverage(
                    radarCode, radar.center_lat, radar.center_long, radius_m
                );
            }
        }
    },

    /**
     * Compute the union LatLngBounds for all currently selected
     * and active radars, using center + img_radio radius.
     * Returns a Leaflet LatLngBounds or null if no radars found.
     */
    _getAllRadarsBounds() {
        if (!state.selectedRadars || state.selectedRadars.length === 0) {
            return null;
        }
        let bounds = null;
        for (const radarCode of state.selectedRadars) {
            const radar = state.radars.find(r => r.code === radarCode);
            if (!radar) continue;

            // Prefer explicit bounding box if available
            let radarBounds;
            if (radar.extent) {
                radarBounds = L.latLngBounds(
                    [radar.extent.lat_min, radar.extent.lon_min],
                    [radar.extent.lat_max, radar.extent.lon_max]
                );
            } else if (radar.center_lat && radar.center_long && radar.img_radio) {
                // Approximate from center + radius (img_radio is in km)
                const radiusDeg = radar.img_radio / 111.0;
                radarBounds = L.latLngBounds(
                    [radar.center_lat - radiusDeg, radar.center_long - radiusDeg],
                    [radar.center_lat + radiusDeg, radar.center_long + radiusDeg]
                );
            } else {
                continue;
            }

            if (!bounds) {
                bounds = radarBounds;
            } else {
                bounds.extend(radarBounds);
            }
        }
        return bounds;
    },

    /**
     * Fetch COGs for the current time-range selection and group them into frames.
     * Pure data function — no animation state mutation, no map layer teardown,
     * no animator.stop() calls.
     * Returns { groupedFrames, cogsByFrame } or null if no data available.
     */
    async _fetchTimeRangeFrames() {
        if (state.selectedRadars.length === 0 || !state.selectedProduct) return null;
        const timeRange = state.ui.getTimeRangeValues();
        if (!timeRange.start || !timeRange.end || timeRange.start >= timeRange.end) return null;

        const mode = getActiveCoverageMode(state.coverageModeId);
        const cogs = await api.getCogsForTimeRange(
            state.selectedRadars, state.selectedProduct,
            timeRange.start, timeRange.end, 100,
            mode.volNrs, mode.strategy
        );
        if (!cogs || cogs.length === 0) return null;

        const groupedFrames = groupCogsByTimestamp(cogs);
        const cogsByFrame   = buildCogsByFrameMap(groupedFrames);
        return { groupedFrames, cogsByFrame };
    },

    /**
     * Load new frames in the background without interrupting the current
     * animation. When loading completes, atomically swap the frame buffer:
     *   1. mapManager.updateParams() preloads images into a new buffer and
     *      swaps _frameImages — the RAF loop keeps reading old images throughout.
     *   2. animator.updateFrames() replaces the frames array — the RAF loop
     *      picks up new frames on the very next tick.
     *
     * If loadFn throws, the current animation continues unchanged.
     *
     * @param {Function} loadFn  - async () => { groupedFrames, cogsByFrame } | null
     * @param {object}   opts
     * @param {boolean}  opts.showBadge  - show loading badge during preload
     * @param {string}   opts.badgeText  - initial badge label
     */
    async _loadFramesWithContinuity(loadFn, { showBadge = true, badgeText = 'Cargando\u2026' } = {}) {
        if (showBadge) this._showFieldLoadingBadge(badgeText);
        try {
            const result = await loadFn();
            if (!result || !result.groupedFrames || result.groupedFrames.length === 0) {
                console.warn('[continuity] No frames returned \u2014 keeping current animation');
                return;
            }

            const { groupedFrames, cogsByFrame } = result;
            const params    = this.getTileParams();
            const prevIndex = state.animator.getCurrentIndex();

            // Stage 1: preload all frame images into a new buffer.
            // The animator keeps displaying old frames until the swap.
            await state.mapManager.updateParams(
                cogsByFrame, state.selectedProduct, params,
                (loaded, total) => {
                    if (showBadge) this._showFieldLoadingBadge(`${badgeText} ${loaded}\u00a0/\u00a0${total}`);
                }
            );

            // Stage 2: atomic frame-list swap \u2014 RAF picks up new frames next tick.
            state.cogs = groupedFrames;
            state.animator.updateFrames(
                groupedFrames, state.selectedProduct,
                Math.min(prevIndex, groupedFrames.length - 1)
            );
            if (state.topsCoresLayer && isTopsCoresAvailableForField(state.selectedProduct)) {
                state.topsCoresLayer.loadForFrames(groupedFrames);
            }

            // Update coverage mask to reflect potential coverage change (e.g. field switch)
            const _allCogsContinuity = groupedFrames.flatMap(f => Object.values(f.cogsByRadar));
            this._updateCoverageFromCogs(_allCogsContinuity);

            // Best-effort legend refresh after swap.
            try {
                const colormap = await api.getColormapInfo(state.selectedProduct, state.selectedColormap);
                if (colormap) {
                    this._enrichColormapWithProduct(colormap);
                    state.legend.render(colormap);
                    state.legend.show();
                }
            } catch (_) { /* legend update is best-effort */ }

            state.ui.setStatus('Actualizado \u2713', 'success');
        } catch (err) {
            console.error('[continuity] Background load failed:', err);
            // Animation continues unchanged \u2014 no error propagated to animator.
        } finally {
            if (showBadge) _hideFieldLoadingBadge();
        }
    },

    // updateLiveIndicator() {
    //     const el = document.getElementById('live-indicator');
    //     if (!el) return;
    //     if (state.liveHours !== null) {
    //         el.textContent = '● EN VIVO';
    //         el.className = 'live-indicator live-on';
    //     } else {
    //         el.textContent = '○ En vivo';
    //         el.className = 'live-indicator live-off';
    //     }
    //     const cogRefreshBtn = document.getElementById('btn-cog-refresh-now');
    //     if (cogRefreshBtn) cogRefreshBtn.disabled = state.liveHours === null;
    // },

    // /** Update badge-module-a with the number of selected radars. */
    // _updateRadarBadge() {
    //     const badge = document.getElementById('badge-module-a');
    //     if (!badge) return;
    //     const count = (state.selectedRadars || []).length;
    //     badge.textContent = count > 0 ? String(count) : '';
    //     badge.style.display = count > 0 ? 'inline-flex' : 'none';
    // },

    // /** Update badge-module-b with the currently selected product key. */
    // _updateFieldBadge() {
    //     const badge = document.getElementById('badge-module-b');
    //     if (!badge) return;
    //     const key = state.selectedProduct || '';
    //     badge.textContent = key ? key.toUpperCase() : '';
    //     badge.style.display = key ? 'inline-flex' : 'none';
    // },

    // isTopsCoresAvailableForField(productKey = state.selectedProduct) {
    //     const baseProductKey = (productKey || '').replace(/o$/, '');
    //     return baseProductKey === 'COLMAX';
    // },

    _updateTopsCoresUIVisibility() {
        const topsCoresToggle = document.getElementById('toggle-tops-cores');
        const topsCoresSizeRow = document.getElementById('tops-cores-size-row');
        if (!topsCoresToggle) return;

        const isAvailable = isTopsCoresAvailableForField(state.selectedProduct);

        // Accordion (#9): when Tops & Cores aren't available for the selected
        // field, gray the section header and make it non-expandable (collapse it)
        // rather than hiding it — so the option stays visible but evidently off.
        const section = document.getElementById('section-tops-cores');
        if (section) {
            section.classList.toggle('disabled', !isAvailable);
            const header = section.querySelector('.field-section-header');
            if (!isAvailable) {
                section.classList.remove('open');
                if (header) header.setAttribute('aria-expanded', 'false');
            }
            if (header) header.disabled = !isAvailable;
        }

        topsCoresToggle.disabled = !isAvailable;
        topsCoresToggle.checked = state.topsCoresVisible;

        if (topsCoresSizeRow) {
            topsCoresSizeRow.style.display = (isAvailable && state.topsCoresVisible) ? 'block' : 'none';
        }

        this._updateTopsCoresLayer();
    },

    _updateTopsCoresLayer() {
        if (!isTopsCoresAvailableForField(state.selectedProduct)) {
            if (state.topsCoresLayer) {
                state.topsCoresLayer.setVisible(false);
                state.topsCoresLayer.clear();
            }
            return;
        }

        if (state.topsCoresVisible) {
            if (!state.topsCoresLayer) {
                state.topsCoresLayer = new TopsCoresLayer(state.mapManager._map);
                state.topsCoresLayer.setPointSize(state.topsCoresPointSize);
            }
            state.topsCoresLayer.setVisible(true);
            // Show the current frame from pre-loaded data
            const currentIndex = state.animator ? state.animator.getCurrentIndex() : 0;
            state.topsCoresLayer.showFrame(currentIndex);
        } else {
            if (state.topsCoresLayer) {
                state.topsCoresLayer.setVisible(false);
                state.topsCoresLayer.clear();
            }
        }
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
        const timeRange = state.ui.getTimeRangeValues();
        const hasValidRange = timeRange.start && timeRange.end && timeRange.start < timeRange.end;
        const canLoad = state.selectedRadars.length > 0 && state.selectedProduct && hasValidRange;
        state.ui.enableLoadTimeRangeButton(canLoad);
    },

    /**
     * Route field/product changes to the appropriate load function based on
     * the current animation mode. Does NOT stop the animation before loading
     * so that existing frames continue to play while new data is fetched.
     */
    async onSelectionChange() {
        if (state.animationMode === 'timerange') {
            await this.loadTimeRangeCogs();
        } else if (state.animationMode === 'latest') {
            await this.loadLatestCogs();
        }
        // If no animation mode is active yet, nothing to reload.
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

            // Draw the coverage SVG mask layer (appended directly to the map
            // container, outside Leaflet panes, so not captured by the img loop above).
            const coverageSvg = state.mapManager && state.mapManager._coverageSvgEl;
            if (coverageSvg) {
                try {
                    const svgData = new XMLSerializer().serializeToString(coverageSvg);
                    const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
                    const svgUrl  = URL.createObjectURL(svgBlob);
                    await new Promise((resolve, reject) => {
                        const svgImg = new Image();
                        svgImg.onload = () => {
                            ctx.drawImage(svgImg, 0, 0, canvas.width, canvas.height);
                            URL.revokeObjectURL(svgUrl);
                            resolve();
                        };
                        svgImg.onerror = () => { URL.revokeObjectURL(svgUrl); resolve(); };
                        svgImg.src = svgUrl;
                    });
                } catch (_) { /* coverage overlay is best-effort */ }
            }

            // ── Modular overlays ─────────────────────────────────────────────────
            // Comment out any line to disable that overlay element.
            const colormapData = state.legend?.currentColormap || null;
            const fieldLabel   = colormapData?.product_title || colormapData?.product_key
                               || state.selectedProduct || '';
            const timeText     = document.getElementById('time-display')?.textContent?.trim() || '';

            await snapshotOverlayLogo(ctx);
            snapshotOverlayVerticalLegend(ctx, canvas, colormapData);
            snapshotOverlayInfoPanel(ctx, canvas, fieldLabel, timeText);
            // ────────────────────────────────────────────────────────────────────

            const link = document.createElement('a');
            link.download = `radar-snapshot-${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
            link.href = canvas.toDataURL('image/png');
            link.click();
        } catch (err) {
            console.warn('Snapshot failed:', err);
            state.ui.setStatus('Error al capturar la imagen: ' + err.message, 'error');
        }
    },

    /**
     * Make the animation panel draggable by its top info row (the drag handle).
     * Only mouse events are used — no HTML5 Drag API (which conflicts with Leaflet).
     * Position is NOT persisted to localStorage; page reload always resets to bottom-right.
     */
    _initDraggablePanel() {
        const panel  = document.getElementById('animation-controls');
        const handle = panel ? panel.querySelector('.animation-info-row') : null;
        if (!panel || !handle) return;

        let dragging = false;
        let offsetX  = 0;
        let offsetY  = 0;

        handle.addEventListener('mousedown', (e) => {
            // Only trigger on the handle itself or its direct label children,
            // not on interactive inputs inside the row.
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON') return;

            // Convert current CSS bottom/right to explicit left/top
            const rect = panel.getBoundingClientRect();
            panel.style.right  = 'auto';
            panel.style.bottom = 'auto';
            panel.style.left   = `${rect.left}px`;
            panel.style.top    = `${rect.top}px`;

            dragging = true;
            offsetX  = e.clientX - rect.left;
            offsetY  = e.clientY - rect.top;

            handle.classList.add('dragging');
            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (!dragging) return;
            const maxX = window.innerWidth  - panel.offsetWidth;
            const maxY = window.innerHeight - panel.offsetHeight;
            const x = Math.max(0, Math.min(e.clientX - offsetX, maxX));
            const y = Math.max(0, Math.min(e.clientY - offsetY, maxY));
            panel.style.left = `${x}px`;
            panel.style.top  = `${y}px`;
        });

        const endDrag = () => {
            if (!dragging) return;
            dragging = false;
            handle.classList.remove('dragging');
        };

        document.addEventListener('mouseup',    endDrag);
        document.addEventListener('mouseleave', endDrag);
    },
};

// =============================================================================
// START APPLICATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    app.init();
});
