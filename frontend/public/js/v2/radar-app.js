/**
 * radar-app.js — Single-radar detail page orchestrator
 *
 * Step 5 fixes:
 * - Drag only from handle element
 * - Multi-layer loadFrames: each layer loads independently with its own productKey
 * - Eye toggle and opacity work during animation
 * - showFrame called per visible layer in sequence
 * - Play button SVG swap via .playing class
 * - Legend hidden (future step)
 */

import { api }                 from '../shared/api.js';
import { MapManager }          from './map.js';
import { AnimationController } from './animation.js';
import { UIControls }          from '../shared/controls.js';

// ─── URL param ───────────────────────────────────────────────────────────────

const urlParams  = new URLSearchParams(window.location.search);
const RADAR_CODE = urlParams.get('code');
if (!RADAR_CODE) window.location.href = 'index.html';

// ─── Constants ───────────────────────────────────────────────────────────────

const MS_PER_HOUR                   = 3_600_000;
const DEFAULT_HOURS                 = 1.5;
const DEFAULT_LAYER_OPACITY         = 0.7;
const SETTINGS_KEY_BASEMAP          = 'webmet25_selected_basemap';
const SETTINGS_KEY_COVERAGE_OPACITY = 'webmet25_coverage_opacity';
const SETTINGS_KEY_TIME_HOURS       = 'webmet25_radar_time_hours';
const LIVE_REFRESH_INTERVAL_MS      = 5 * 60 * 1000;

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

// ─── Utility ─────────────────────────────────────────────────────────────────

function waitForLeaflet(timeout = 10000) {
    return new Promise((resolve, reject) => {
        if (window.L) { resolve(); return; }
        const start = Date.now();
        const iv = setInterval(() => {
            if (window.L) { clearInterval(iv); resolve(); }
            else if (Date.now() - start > timeout) {
                clearInterval(iv); reject(new Error('Leaflet failed to load'));
            }
        }, 50);
    });
}

function updateRadarHeader(radar) {
    const codeEl  = document.getElementById('radar-header-code');
    const titleEl = document.getElementById('radar-header-title');
    if (codeEl)  codeEl.textContent  = radar.code;
    if (titleEl) titleEl.textContent = radar.title;
    document.title = `${radar.code} — WebMet25`;
}

function fitMapToRadar(radar) {
    if (!radar.extent) return;
    const { lat_min, lat_max, lon_min, lon_max } = radar.extent;
    state.mapManager.getMap().fitBounds([
        [lat_min, lon_min],
        [lat_max, lon_max],
    ]);
}

function groupCogsByTimestamp(cogs) {
    const buckets = new Map();
    cogs.forEach(cog => {
        const key = Math.round(
            new Date(cog.observation_time).getTime() / 60000
        ) * 60000;
        if (!buckets.has(key)) {
            buckets.set(key, { timestamp: cog.observation_time, cogsByRadar: {} });
        }
        buckets.get(key).cogsByRadar[cog.radar_code] = cog;
    });
    return Array.from(buckets.values())
        .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
}

function buildCogsByFrameMap(frames) {
    const result = new Map();
    frames.forEach((frame, i) => {
        result.set(i, new Map(Object.entries(frame.cogsByRadar)));
    });
    return result;
}

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

// ─── Multi-layer map rendering ────────────────────────────────────────────────

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

// ─── Layer management ─────────────────────────────────────────────────────────

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
        opacity:      state.layers.length === 0 ? 1.0 : DEFAULT_LAYER_OPACITY,
        visible:      true,
        colormap,
        zIndex:       state.layers.length,
    };
    state.layers.push(layer);

    // Load frames for this new layer into the existing frame structure
    const storedHours = parseFloat(
        localStorage.getItem(SETTINGS_KEY_TIME_HOURS)
    ) || DEFAULT_HOURS;

    await loadLayerFrames(layer, storedHours);

    renderLayerList();
    updateFieldBadge();
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
    ) || DEFAULT_HOURS;
    await loadLayerFrames(layer, storedHours);

    renderLayerList();
    updateFieldBadge();
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

// ─── Per-layer frame loading ──────────────────────────────────────────────────

/**
 * Load COGs for a single layer into the shared MapManager frame structure.
 * Uses the existing time window (startTime/endTime from the time inputs).
 * If no time range is set yet, uses the last N hours default.
 */
async function loadLayerFrames(layer, hours) {
    state.ui.setStatus(`Cargando ${layer.productKey}…`, 'loading');

    try {
        // Determine time range
        const timeRange = state.ui.getTimeRangeValues();
        let startTime   = timeRange.start;
        let endTime     = timeRange.end;

        if (!startTime || !endTime) {
            const latestItems = await api.getLatestCogsForRadars(
                [state.radarCode], layer.productKey
            );
            if (!latestItems.length) {
                state.ui.setStatus(
                    `⚠️ Sin datos para ${layer.productKey}`, 'error'
                );
                return;
            }
            endTime   = new Date(latestItems[0].cog.observation_time);
            startTime = new Date(endTime.getTime() - hours * MS_PER_HOUR);
            state.ui.setTimeRangeValues(startTime, endTime);
        }

        const cogs = await api.getCogsForTimeRange(
            [state.radarCode], layer.productKey,
            startTime, endTime, 100
        );

        if (!cogs.length) {
            state.ui.setStatus(
                `⚠️ Sin datos para ${layer.productKey} en el rango seleccionado`,
                'error'
            );
            return;
        }

        // Group into frames — merge with existing frame structure
        const newFrames = groupCogsByTimestamp(cogs);

        // If no frames exist yet, initialise from this layer
        if (state.frames.length === 0) {
            state.frames = newFrames;
            // Pre-size _frameImages
            state.mapManager._frameImages = state.frames.map(() => new Map());
        }

        // Load images for this layer into existing frame slots
        // Match by minute-bucket timestamp
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
            if (frameIdx === undefined) return; // no matching slot

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
                    // Set initial opacity
                    const overlay = state.mapManager._overlays.get(key);
                    if (overlay) overlay.setOpacity(0);
                }
            } catch (err) {
                console.warn(`loadLayerFrames: failed ${key} frame ${frameIdx}:`, err);
            }
        });

        await Promise.all(loadPromises);

        // Wire animator to the shared frames using the FIRST visible layer's
        // productKey — animator.updateFrames drives the frame index only;
        // actual rendering is overridden via onFrameChange below
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

        // Show latest frame for all layers
        showAllLayersAtFrame(state.frames.length - 1);
        state.mapManager._currentFrameIndex = state.frames.length - 1;

        state.ui.setStatus(
            `✓ ${layer.productKey} cargado — ${state.frames.length} fotogramas`,
            'success'
        );

    } catch (err) {
        console.error('loadLayerFrames error:', err);
        state.ui.setStatus(`Error cargando ${layer.productKey}: ${err.message}`, 'error');
    }
}

// ─── Live refresh ─────────────────────────────────────────────────────────────

function startLiveRefresh(hours) {
    stopLiveRefresh();
    state.liveHours        = hours;
    state.liveRefreshTimer = setInterval(async () => {
        if (!state.liveHours || !state.layers.length) return;
        try {
            for (const layer of state.layers) {
                await loadLayerFrames(layer, hours);
            }
        } catch (err) {
            console.warn('Live refresh error:', err);
        }
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

// ─── Layer list renderer ──────────────────────────────────────────────────────

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
        });
    }

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

// ─── Bootstrap ───────────────────────────────────────────────────────────────

async function init() {
    try {
        await waitForLeaflet();

        state.ui         = new UIControls();
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
            api.getProducts(),
        ]);

        state.radar    = radars.find(r => r.code === RADAR_CODE) || null;
        state.products = products;

        if (!state.radar) {
            state.ui.setStatus(`Radar '${RADAR_CODE}' no encontrado`, 'error');
            document.getElementById('radar-header-title').textContent = 'Radar not found';
            return;
        }

        state.mapManager.addRadarCoverage(
            state.radar.code,
            state.radar.center_lat,
            state.radar.center_long,
            state.radar.img_radio * 1000,
        );

        updateRadarHeader(state.radar);
        fitMapToRadar(state.radar);

        const storedHours = parseFloat(
            localStorage.getItem(SETTINGS_KEY_TIME_HOURS)
        ) || DEFAULT_HOURS;
        document.querySelectorAll('.time-window-btn').forEach(btn => {
            btn.classList.toggle(
                'active', parseFloat(btn.dataset.hours) === storedHours
            );
        });
        updateTimeBadge(storedHours);
        updateTimeWindowLabel(storedHours);

        state.ui.setStatus('Seleccione un campo para comenzar →  ⊞', 'success');

    } catch (err) {
        console.error('radar-app init error:', err);
        if (state.ui) state.ui.setStatus(`Error: ${err.message}`, 'error');
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}