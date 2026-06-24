import { api }                 from '../shared/api.js';
import { MapManager }          from './map.js';
import { AnimationController } from './animation.js';
import { UIControls }          from '../shared/controls.js';
import { 
    waitForLeaflet, 
    updateRadarHeader,
    fitMapToRadar,
    groupCogsByTimestamp,
    buildCogsByFrameMap
}      from './radar-utils.js';

import {
    MS_PER_HOUR,
    DEFAULT_FIELD_OPACITY,
    DEFAULT_TIME_WINDOW_HOURS,
    DEFAULT_LIVE_REFRESH_INTERVAL_MS,
    COVERAGE_MODES,
} from './constants.js';

const LIVE_REFRESH_INTERVAL_MS = DEFAULT_LIVE_REFRESH_INTERVAL_MS;
const CD_MODE = COVERAGE_MODES.find(m => m.id === 'cd');

const SETTINGS_KEY_BASEMAP          = 'webmet25_selected_basemap';
const SETTINGS_KEY_COVERAGE_OPACITY = 'webmet25_coverage_opacity';
const SETTINGS_KEY_TIME_HOURS        = 'webmet25_time_window_hours';

// ─── URL param ───────────────────────────────────────────────────────────────

const urlParams   = new URLSearchParams(window.location.search);
const RADAR_CODE  = urlParams.get('code');
const INITIAL_FIELD = urlParams.get('field') || null;

if (!RADAR_CODE) window.location.href = 'index.html';

// ─── Page state ──────────────────────────────────────────────────────────────

const state = {
    radarCode:        RADAR_CODE,
    radar:            null,
    mapManager:       null,
    animator:         null,
    ui:               null,
    products:         [],
    frames:           [],
    liveHours:        null,
    liveRefreshTimer: null,
    animationMode:    null,
    layers:           [],
    nextLayerId:      1,
    pickerContext:    null,
};

function updateTimeBadge(hours) {
    const badge = document.getElementById('badge-module-c');
    if (badge) badge.textContent = hours ? `${hours}h` : '—';
}

function updateTimeWindowLabel(hours) {
    const label = document.getElementById('time-window-label');
    if (label) label.textContent = hours ? `Last ${hours} hrs` : '—';
}

function updateFieldBadge() {
    const badge   = document.getElementById('badge-module-b');
    if (!badge) return;
    const visible = state.layers.filter(l => l.visible);
    badge.textContent = visible.length
        ? visible.map(l => l.productKey).join(', ')
        : '—';
}

function setLayerOpacity(layerId, opacity) {
    const layer = state.layers.find(l => l.id === layerId);
    if (!layer) return;
    layer.opacity = opacity;
    // Apply immediately to the current frame
    const key     = `${state.radarCode}__${layer.productKey}`;
    const overlay = state.mapManager._overlays.get(key);
    if (overlay && layer.visible) {
        overlay.setOpacity(opacity);
    }
}


function setLayerVisible(layerId, visible) {
    const layer = state.layers.find(l => l.id === layerId);
    if (!layer) return;
    layer.visible = visible;

    // Apply immediately
    const key     = `${state.radarCode}__${layer.productKey}`;
    const overlay = state.mapManager._overlays.get(key);
    if (overlay) {
        overlay.setOpacity(visible ? layer.opacity : 0);
    }

    updateFieldBadge();
    renderLayerList();
}

function reorderLayers(fromIdx, toIdx) {
    if (fromIdx === toIdx) return;
    const moved = state.layers.splice(fromIdx, 1)[0];
    state.layers.splice(toIdx, 0, moved);
    state.layers.forEach((l, i) => { l.zIndex = i; });
    renderLayerList();
    updateFieldBadge();
}


// ─── Colormap strip ───────────────────────────────────────────────────────────

function buildHorizontalGradient(colors) {
    const SAMPLES = 32;
    const stops   = [];
    for (let i = 0; i < SAMPLES; i++) {
        const idx = Math.round((i / (SAMPLES - 1)) * (colors.length - 1));
        const pct = ((i / (SAMPLES - 1)) * 100).toFixed(1);
        stops.push(`${colors[idx]} ${pct}%`);
    }
    return `linear-gradient(to right, ${stops.join(', ')})`;
}

function renderLayerList() {
    const container = document.getElementById('layer-list');
    if (!container) return;
    container.innerHTML = '';

    state.layers.forEach((layer, idx) => {
        const row        = document.createElement('div');
        row.className    = 'layer-row';
        row.dataset.idx  = String(idx);
        // Do NOT set draggable on the row itself — only the handle triggers drag

        // ── Drag handle ──
        const handle = document.createElement('span');
        handle.className   = 'layer-drag-handle';
        handle.textContent = '⠿';
        handle.title       = 'Drag to reorder';

        // Make ONLY the handle initiate drag
        handle.addEventListener('mousedown', () => {
            row.draggable = true;
        });
        handle.addEventListener('mouseleave', () => {
            // Will be reset after dragend anyway, but clean up eagerly
        });

        row.addEventListener('dragstart', (e) => {
            e.dataTransfer.setData('text/plain', String(idx));
            row.style.opacity = '0.5';
        });
        row.addEventListener('dragend', () => {
            row.style.opacity  = '';
            row.draggable      = false; // reset until handle is pressed again
            container.querySelectorAll('.layer-row')
                .forEach(r => r.classList.remove('drag-over'));
        });
        row.addEventListener('dragover', (e) => {
            e.preventDefault();
            container.querySelectorAll('.layer-row')
                .forEach(r => r.classList.remove('drag-over'));
            row.classList.add('drag-over');
        });
        row.addEventListener('drop', (e) => {
            e.preventDefault();
            const fromIdx = parseInt(e.dataTransfer.getData('text/plain'), 10);
            row.classList.remove('drag-over');
            reorderLayers(fromIdx, idx);
        });

        // ── Eye toggle ──
        const eyeBtn       = document.createElement('button');
        eyeBtn.className   = `layer-eye-btn${layer.visible ? '' : ' hidden-layer'}`;
        eyeBtn.textContent = layer.visible ? '👁' : '🚫';
        eyeBtn.title       = layer.visible ? 'Hide layer' : 'Show layer';
        eyeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            setLayerVisible(layer.id, !layer.visible);
        });

        // ── Center column ──
        const center     = document.createElement('div');
        center.className = 'layer-center';

        const nameEl       = document.createElement('div');
        nameEl.className   = 'layer-field-name';
        nameEl.textContent = layer.productKey;
        nameEl.title       = layer.productTitle;
        nameEl.addEventListener('click', (e) => {
            e.stopPropagation();
            openFieldPicker(layer.id);
        });

        const strip     = document.createElement('div');
        strip.className = 'layer-colormap-strip';
        strip.title     = 'Colormap editor — coming soon';
        if (layer.colormap?.colors?.length) {
            strip.style.background = buildHorizontalGradient(layer.colormap.colors);
        } else {
            strip.style.background = 'rgba(255,255,255,0.15)';
        }

        const slider     = document.createElement('input');
        slider.type      = 'range';
        slider.className = 'layer-opacity-slider';
        slider.min       = '0';
        slider.max       = '1';
        slider.step      = '0.05';
        slider.value     = String(layer.opacity);
        slider.addEventListener('mousedown', e => e.stopPropagation());
        slider.addEventListener('input', (e) => {
            e.stopPropagation();
            const val        = parseFloat(e.target.value);
            pctLabel.textContent = `${Math.round(val * 100)}%`;
            setLayerOpacity(layer.id, val);
        });

        center.appendChild(nameEl);
        center.appendChild(strip);
        center.appendChild(slider);

        // ── Opacity % label ──
        const pctLabel       = document.createElement('span');
        pctLabel.className   = 'layer-opacity-pct';
        pctLabel.textContent = `${Math.round(layer.opacity * 100)}%`;

        // ── Remove ──
        const removeBtn       = document.createElement('button');
        removeBtn.className   = 'layer-remove-btn';
        removeBtn.textContent = '✕';
        removeBtn.title       = 'Remove layer';
        removeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            removeLayer(layer.id);
        });

        row.appendChild(handle);
        row.appendChild(eyeBtn);
        row.appendChild(center);
        row.appendChild(pctLabel);
        row.appendChild(removeBtn);
        container.appendChild(row);
    });
}

async function removeLayer(layerId) {
    const idx = state.layers.findIndex(l => l.id === layerId);
    if (idx === -1) return;
    const layer = state.layers[idx];

    // Remove this layer's overlays from MapManager
    const keysToRemove = [];
    state.mapManager._overlays.forEach((_, key) => {
        if (key.startsWith(`${state.radarCode}__${layer.productKey}`)) {
            keysToRemove.push(key);
        }
    });
    keysToRemove.forEach(key => {
        const overlay = state.mapManager._overlays.get(key);
        if (overlay && state.mapManager._map.hasLayer(overlay)) {
            state.mapManager._map.removeLayer(overlay);
        }
        state.mapManager._overlays.delete(key);
        state.mapManager._bboxes.delete(key);
    });
    // Remove from frameImages
    state.mapManager._frameImages.forEach(frameMap => {
        const key = `${state.radarCode}__${layer.productKey}`;
        const entry = frameMap?.get(key);
        if (entry?.objectUrl) URL.revokeObjectURL(entry.objectUrl);
        frameMap?.delete(key);
    });

    state.layers.splice(idx, 1);
    state.layers.forEach((l, i) => { l.zIndex = i; });

    if (state.layers.length === 0) {
        state.mapManager._clearAllOverlays();
        state.frames = [];
        state.animator.updateFrames([], null);
        state.ui.enableAnimationControls(false);
        state.ui.enableNavButtons(false);
    } else {
        // Refresh display
        const ci = state.mapManager._currentFrameIndex;
        if (ci >= 0) showAllLayersAtFrame(ci);
    }

    renderLayerList();
    updateFieldBadge();
}

/**
 * First-load wrapper: anchors to the latest available data for the given
 * layer, then delegates to loadLayerFramesForRange.
 */
async function loadLayerFrames(layer, hours) {
    const timeRange = state.ui.getTimeRangeValues();
    if (timeRange.start && timeRange.end) {
        await loadLayerFramesForRange(layer, timeRange.start, timeRange.end);
        return;
    }

    const latestItems = await api.getLatestCogsForRadars(
        [state.radarCode], layer.productKey, CD_MODE.volNrs, CD_MODE.strategy
    );
    if (!latestItems.length) {
        state.ui.setStatus(`⚠️ Sin datos para ${layer.productKey}`, 'error');
        return;
    }
    const endTime   = new Date(latestItems[0].cog.observation_time);
    const startTime = new Date(endTime.getTime() - hours * MS_PER_HOUR);
    state.ui.setTimeRangeValues(startTime, endTime);

    await loadLayerFramesForRange(layer, startTime, endTime);
}


// ─── Per-layer frame loading ──────────────────────────────────────────────────
/**
 * Load COGs for a single layer into the shared MapManager frame structure,
 * for an EXPLICIT time range. Used by both initial load and live refresh.
 */
async function loadLayerFramesForRange(layer, startTime, endTime) {
    state.ui.setStatus(`Cargando ${layer.productKey}…`, 'loading');

    try {
        const cogs = await api.getCogsForTimeRange(
            [state.radarCode], layer.productKey,
            startTime, endTime, 100, CD_MODE.volNrs, CD_MODE.strategy
        );

        if (!cogs.length) {
            state.ui.setStatus(`⚠️ Sin datos para ${layer.productKey}`, 'error');
            return;
        }

        const newFrames = groupCogsByTimestamp(cogs);

        if (state.frames.length === 0) {
            state.frames = newFrames;
            state.mapManager._frameImages = state.frames.map(() => new Map());
        }

        const existingBuckets = new Map(
            state.frames.map((f, i) => [
                Math.round(new Date(f.timestamp).getTime() / 60000) * 60000,
                i,
            ])
        );

        const loadPromises = newFrames.map(async (frame) => {
            const bucket = Math.round(
                new Date(frame.timestamp).getTime() / 60000
            ) * 60000;
            const frameIdx = existingBuckets.get(bucket);
            if (frameIdx === undefined) return;

            const cog = frame.cogsByRadar[state.radarCode];
            if (!cog) return;

            const key = `${state.radarCode}__${layer.productKey}`;
            const url = state.mapManager._buildFrameUrl(cog.id, layer.productKey, {});

            try {
                const { img, bbox, objectUrl } = await state.mapManager._loadImage(url);
                if (!state.mapManager._frameImages[frameIdx]) {
                    state.mapManager._frameImages[frameIdx] = new Map();
                }
                state.mapManager._frameImages[frameIdx].set(key, {
                    img, loaded: true, url, objectUrl,
                });
                if (!state.mapManager._bboxes.has(key)) {
                    state.mapManager._bboxes.set(key, bbox);
                    state.mapManager._createOverlay(key, bbox);
                    const overlay = state.mapManager._overlays.get(key);
                    if (overlay) overlay.setOpacity(0);
                }
            } catch (err) {
                console.warn(`loadLayerFramesForRange: failed ${key} frame ${frameIdx}:`, err);
            }
        });

        await Promise.all(loadPromises);

        const firstVisible = state.layers.find(l => l.visible);
        if (firstVisible) {
            state.animator.updateFrames(
                state.frames, firstVisible.productKey,
                state.frames.length - 1
            );
        }

        state.ui.enableAnimationControls(true);
        state.ui.enableNavButtons(true);
        state.animationMode = 'timerange';

        showAllLayersAtFrame(state.frames.length - 1);
        state.mapManager._currentFrameIndex = state.frames.length - 1;

        state.ui.setStatus(
            `✓ ${layer.productKey} cargado — ${state.frames.length} fotogramas`,
            'success'
        );

    } catch (err) {
        console.error('loadLayerFramesForRange error:', err);
        state.ui.setStatus(`Error cargando ${layer.productKey}: ${err.message}`, 'error');
    }
}

async function addLayer(productKey) {
    const product = state.products.find(p => p.product_key === productKey);
    if (!product) return;

    // Fetch colormap
    let colormap = null;
    try {
        colormap = await api.getColormapInfo(productKey);
    } catch (e) {
        try { colormap = await api.getColormap(productKey); } catch (_) {}
    }

    const layer = {
        id:           state.nextLayerId++,
        productKey,
        productTitle: product.product_title,
        opacity:      state.layers.length === 0 ? 1.0 : DEFAULT_FIELD_OPACITY,
        visible:      true,
        colormap,
        zIndex:       state.layers.length,
    };
    state.layers.push(layer);

    // Load frames for this new layer into the existing frame structure
    const storedHours = parseFloat(
        localStorage.getItem(SETTINGS_KEY_TIME_HOURS)
    ) || DEFAULT_TIME_WINDOW_HOURS;

    await loadLayerFrames(layer, storedHours);

    renderLayerList();
    updateFieldBadge();
}

async function swapLayerField(layerId, newProductKey) {
    const layer   = state.layers.find(l => l.id === layerId);
    if (!layer) return;
    const product = state.products.find(p => p.product_key === newProductKey);
    if (!product) return;

    // Remove old overlays
    const oldKey = `${state.radarCode}__${layer.productKey}`;
    state.mapManager._frameImages.forEach(frameMap => {
        const entry = frameMap?.get(oldKey);
        if (entry?.objectUrl) URL.revokeObjectURL(entry.objectUrl);
        frameMap?.delete(oldKey);
    });
    const oldOverlay = state.mapManager._overlays.get(oldKey);
    if (oldOverlay && state.mapManager._map.hasLayer(oldOverlay)) {
        state.mapManager._map.removeLayer(oldOverlay);
    }
    state.mapManager._overlays.delete(oldKey);
    state.mapManager._bboxes.delete(oldKey);

    // Fetch new colormap
    let colormap = null;
    try {
        colormap = await api.getColormapInfo(newProductKey);
    } catch (e) {
        try { colormap = await api.getColormap(newProductKey); } catch (_) {}
    }

    layer.productKey   = newProductKey;
    layer.productTitle = product.product_title;
    layer.colormap     = colormap;

    const storedHours = parseFloat(
        localStorage.getItem(SETTINGS_KEY_TIME_HOURS)
    ) || DEFAULT_TIME_WINDOW_HOURS;
    await loadLayerFrames(layer, storedHours);

    renderLayerList();
    updateFieldBadge();
}

/**
 * Show the current frame for all visible layers in sequence.
 * Called on every animation tick and whenever visibility/opacity changes.
 */
function showAllLayersAtFrame(frameIndex) {
    // First hide everything
    state.mapManager._overlays.forEach(overlay => overlay.setOpacity(0));

    // Then show each visible layer with its own opacity
    state.layers.forEach(layer => {
        if (!layer.visible) return;
        const frameMap = state.mapManager._frameImages[frameIndex];
        if (!frameMap) return;
        const key     = `${state.radarCode}__${layer.productKey}`;
        const entry   = frameMap.get(key);
        const overlay = state.mapManager._overlays.get(key);
        if (entry && overlay && entry.loaded) {
            overlay.setUrl(entry.img.src);
            overlay.setOpacity(layer.opacity);
        }
    });
}

// ─── Live refresh ─────────────────────────────────────────────────────────────

function startLiveRefresh(hours) {
    stopLiveRefresh();
    state.liveHours        = hours;
    state.liveRefreshTimer = setInterval(() => {
        refreshLiveWindow();
    }, LIVE_REFRESH_INTERVAL_MS);

    const indicator = document.getElementById('live-indicator');
    if (indicator) {
        indicator.className   = 'live-indicator live-on';
        indicator.textContent = '● Live';
    }
}

function stopLiveRefresh() {
    if (state.liveRefreshTimer) {
        clearInterval(state.liveRefreshTimer);
        state.liveRefreshTimer = null;
    }
    state.liveHours = null;
    const indicator = document.getElementById('live-indicator');
    if (indicator) {
        indicator.className   = 'live-indicator live-off';
        indicator.textContent = '○ Live';
    }
}

/**
 * Recompute the time window anchored to the latest available data for
 * EACH active layer, then reload all layers. Always recalculates the
 * window — never trusts the existing start/end inputs — so the window
 * actually slides forward over time like the main page does.
 */
async function refreshLiveWindow() {
    if (!state.liveHours || !state.layers.length) return;

    try {
        const hours = state.liveHours;

        // Anchor to the latest COG across all active layers (use the first
        // layer as the canonical anchor — matches main page behavior of
        // anchoring to the latest available data for the selected field set)
        const anchorLayer  = state.layers[0];
        const latestItems  = await api.getLatestCogsForRadars(
            [state.radarCode], anchorLayer.productKey, CD_MODE.volNrs, CD_MODE.strategy
        );
        if (!latestItems.length) return;

        const newEndTime   = new Date(latestItems[0].cog.observation_time);
        const newStartTime = new Date(newEndTime.getTime() - hours * MS_PER_HOUR);

        state.ui.setTimeRangeValues(newStartTime, newEndTime);
        updateTimeWindowLabel(hours);

        // Reset frame structure and reload every active layer into the
        // newly anchored window
        state.frames = [];
        state.mapManager._clearAllOverlays();
        state.mapManager._frameImages = [];

        for (const layer of state.layers) {
            await loadLayerFramesForRange(layer, newStartTime, newEndTime);
        }

        state.liveHours = hours; // re-affirm (loadLayerFrames doesn't touch this)

    } catch (err) {
        console.warn('Live refresh error (will retry next cycle):', err);
    }
}

// ─── Field picker modal ───────────────────────────────────────────────────────

function openFieldPicker(context) {

    state.pickerContext = context;
    const modal = document.getElementById('field-picker-modal');
    const grid  = document.getElementById('field-picker-grid');
    if (!modal || !grid) return;
    
    const activeKeys = new Set(state.layers.map(l => l.productKey));
    grid.innerHTML   = '';
    
    state.products.forEach(product => {
        const btn       = document.createElement('button');
        btn.className   = 'field-picker-btn';
        btn.textContent = product.product_key;
        btn.title       = product.product_title;
        btn.disabled    = activeKeys.has(product.product_key) && context === 'add';

        btn.addEventListener('click', async () => {
            closeFieldPicker();
            if (context === 'add') {
                await addLayer(product.product_key);
            } else {
                await swapLayerField(context, product.product_key);
            }
        });
        grid.appendChild(btn);
    });

    modal.style.display = 'flex';
}

function closeFieldPicker() {
    const modal = document.getElementById('field-picker-modal');
    if (modal) modal.style.display = 'none';
    state.pickerContext = null;
}

// ─── Time window controls ─────────────────────────────────────────────────────

function initTimeWindowControls() {
    document.querySelectorAll('.time-window-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            document.querySelectorAll('.time-window-btn')
                .forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const hours = parseFloat(btn.dataset.hours);
            localStorage.setItem(SETTINGS_KEY_TIME_HOURS, String(hours));
            updateTimeBadge(hours);
            updateTimeWindowLabel(hours);
            stopLiveRefresh();

            // Reload all active layers for the new time window
            if (state.layers.length) {
                // Reset frame structure
                state.frames = [];
                state.mapManager._clearAllOverlays();
                state.mapManager._frameImages = [];
                // Clear time range inputs so loadLayerFrames re-anchors
                state.ui.setTimeRangeValues(null, null);

                for (const layer of state.layers) {
                    await loadLayerFrames(layer, hours);
                }
                startLiveRefresh(hours);
            }
        });
    });

    const btnCustomRange     = document.getElementById('btn-custom-range');
    const timerangeContainer = document.getElementById('timerange-container');
    if (btnCustomRange && timerangeContainer) {
        btnCustomRange.addEventListener('click', () => {
            const hidden = timerangeContainer.style.display === 'none'
                        || timerangeContainer.style.display === '';
            timerangeContainer.style.display = hidden ? 'block' : 'none';
            if (hidden) {
                document.querySelectorAll('.time-window-btn')
                    .forEach(b => b.classList.remove('active'));
                // Wheels must be visible before they can be positioned
                state.ui.refreshTimeWheels();
            }
        });
    }

    // iOS-style time wheels (same pattern as main page)
    state.ui.initTimeWheels();

    const startInput = document.getElementById('start-date');
    const endInput   = document.getElementById('end-date');
    const loadBtn    = document.getElementById('btn-load-timerange');

    const checkRangeInputs = () => {
        if (loadBtn) loadBtn.disabled = !(startInput?.value && endInput?.value);
    };
    if (startInput) startInput.addEventListener('change', checkRangeInputs);
    if (endInput)   endInput.addEventListener('change', checkRangeInputs);

    if (loadBtn) {
        loadBtn.addEventListener('click', async () => {
            const start = startInput?.value ? new Date(startInput.value) : null;
            const end   = endInput?.value   ? new Date(endInput.value)   : null;
            if (!start || !end || start >= end) {
                state.ui.setStatus('Rango de tiempo inválido', 'error');
                return;
            }
            stopLiveRefresh();
            document.querySelectorAll('.time-window-btn')
                .forEach(b => b.classList.remove('active'));
            updateTimeBadge(null);
            updateTimeWindowLabel(null);

            if (state.layers.length) {
                state.frames = [];
                state.mapManager._clearAllOverlays();
                state.mapManager._frameImages = [];
                for (const layer of state.layers) {
                    await loadLayerFrames(layer, null);
                }
            }
        });
    }
}

// ─── Settings panel ──────────────────────────────────────────────────────────

function initSettingsPanel() {
    const basemapSelect = document.getElementById('basemap-select');
    if (basemapSelect) {
        const stored = localStorage.getItem(SETTINGS_KEY_BASEMAP) || 'argenmap';
        basemapSelect.value = stored;
        basemapSelect.addEventListener('change', (e) => {
            state.mapManager.setBasemap(e.target.value);
        });
    }

    const coverageOpacitySlider = document.getElementById('coverage-opacity');
    if (coverageOpacitySlider) {
        const stored = parseFloat(
            localStorage.getItem(SETTINGS_KEY_COVERAGE_OPACITY)
        ) || 0.4;
        coverageOpacitySlider.value = stored;
        coverageOpacitySlider.addEventListener('input', (e) => {
            const val = parseFloat(e.target.value);
            localStorage.setItem(SETTINGS_KEY_COVERAGE_OPACITY, String(val));
            state.mapManager.setCoverageOpacity(val);
        });
    }
}

// ─── Panel controls ───────────────────────────────────────────────────────────

function initPanelControls() {
    const panelMap = {
        'btn-module-b': 'panel-module-b',
        'btn-module-c': 'panel-module-c',
        'btn-settings': 'settings-panel',
    };

    Object.entries(panelMap).forEach(([btnId, panelId]) => {
        const btn = document.getElementById(btnId);
        if (!btn) return;
        btn.addEventListener('click', () => {
            const panel    = document.getElementById(panelId);
            if (!panel) return;
            const isHidden = panel.style.display === 'none'
                          || panel.style.display === '';
            document.querySelectorAll('.floating-panel')
                .forEach(p => { p.style.display = 'none'; });
            if (isHidden) panel.style.display = 'block';
        });
    });

    document.querySelectorAll('.panel-close').forEach(btn => {
        btn.addEventListener('click', () => {
            const panel = document.getElementById(btn.getAttribute('data-close'));
            if (panel) panel.style.display = 'none';
        });
    });

    const btnBack = document.getElementById('btn-back');
    if (btnBack) {
        btnBack.addEventListener('click', () => {
            window.location.href = 'index.html';
        });
    }

    const btnAddField = document.getElementById('btn-add-field');
    if (btnAddField) {
        console.log('btnAddField:', btnAddField);
        btnAddField.addEventListener('click', () => openFieldPicker('add'));
    }

    const btnCloseFieldPicker = document.getElementById('btn-close-field-picker');
    if (btnCloseFieldPicker) {
        btnCloseFieldPicker.addEventListener('click', closeFieldPicker);
    }

    const modal = document.getElementById('field-picker-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeFieldPicker();
        });
    }
}

// =============================================================================
// MAIN APPLICATION
// =============================================================================

const app = {
    // ─── Initialization ───────────────────────────────────────────────────────────────
    async init() {

        try {
            await waitForLeaflet();
            
            state.ui = new UIControls();
            state.mapManager = new MapManager('map');
            state.mapManager.init();
            state.animator   = new AnimationController(state.mapManager);

            // Override the animator's _showCurrentFrame to call our multi-layer renderer
            state.animator._showCurrentFrame = function () {
                const frame = this._frames[this._currentFrame];
                if (!frame) return;
                showAllLayersAtFrame(this._currentFrame);
                state.mapManager._currentFrameIndex = this._currentFrame;
                if (this._onFrameChange) {
                    this._onFrameChange(this._currentFrame, frame);
                }
            };

            state.animator.initControls(state.ui);

            state.ui.enableAnimationControls(false);
            state.ui.enableNavButtons(false);

            initPanelControls();
            initSettingsPanel();
            initTimeWindowControls();

            const [radars, products] = await Promise.all([
                api.getRadars(false),
                // Always fetch cd-mode (Conventional + Doppler) products only
                api.getProducts(CD_MODE.volNrs, CD_MODE.strategy),
            ]);

            state.radar    = radars.find(r => r.code === RADAR_CODE) || null;
            state.products = products;

            state.mapManager.addRadarCoverage(
                state.radar.code,
                state.radar.center_lat,
                state.radar.center_long,
                state.radar.img_radio * 1000,
            );

            updateRadarHeader(state.radar);
            fitMapToRadar(state.radar, state.mapManager);

            const storedHours = parseFloat(
                localStorage.getItem(SETTINGS_KEY_TIME_HOURS)
            ) || DEFAULT_TIME_WINDOW_HOURS;
            document.querySelectorAll('.time-window-btn').forEach(btn => {
                btn.classList.toggle(
                    'active', parseFloat(btn.dataset.hours) === storedHours
                );
            });
            updateTimeBadge(storedHours);
            updateTimeWindowLabel(storedHours);

            // Resolve the initial product: use the field passed from the main
            // page if it's a cd-mode product, otherwise fall back to DBZHo.
            const cdProductKeys = state.products.map(p => p.product_key);
            let initialProductKey = null;
            if (INITIAL_FIELD && cdProductKeys.includes(INITIAL_FIELD)) {
                initialProductKey = INITIAL_FIELD;
            } else {
                const fallbacks = ['DBZHo', 'COLMAXo'];
                initialProductKey = fallbacks.find(k => cdProductKeys.includes(k))
                    || cdProductKeys[0]
                    || null;
            }

            if (initialProductKey) {
                state.ui.setStatus('Cargando datos…', 'loading');
                await addLayer(initialProductKey);
                startLiveRefresh(storedHours);
                if (state.frames.length) state.animator.play();
            } else {
                state.ui.setStatus('Seleccione un campo para comenzar →  ⊞', 'success');
            }


        } catch (err) {
            console.error('radar-app init error:', err);
            if (state.ui) state.ui.setStatus(`Error: ${err.message}`, 'error');
        }
    }
};

// =============================================================================
// START APPLICATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    app.init();
});