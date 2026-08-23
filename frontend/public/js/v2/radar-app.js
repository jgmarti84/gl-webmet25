import { api }                 from '../shared/api.js';
import { MapManager }          from './map.js';
import { AnimationController } from './animation.js';
import { UIControls }          from '../shared/controls.js';
import {
    waitForLeaflet,
    updateRadarHeader,
    fitMapToRadar,
    buildGridFrames,
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
const CD_MODE      = COVERAGE_MODES.find(m => m.id === 'cd');
const GRID_STEP_MS = 10 * 60 * 1000;

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
    pickerContext:        null,
    pickerShowFiltered:   false,
};

function updateTimeBadge(hours) {
    const badge = document.getElementById('badge-module-c');
    if (badge) badge.textContent = hours ? `${hours}h` : '—';
}

function updateTimeWindowLabel(hours) {
    const label = document.getElementById('time-window-label');
    if (label) label.textContent = hours ? `Últimas ${hours} hrs` : '—';
}

function updateFieldBadge() {
    const badge  = document.getElementById('badge-module-b');
    const btn    = document.getElementById('btn-module-b');
    if (!badge) return;
    const visible = state.layers.filter(l => l.visible);
    badge.textContent = visible.length ? String(visible.length) : '—';
    if (btn) {
        btn.title = visible.length
            ? `Campos activos: ${visible.map(l => l.productKey).join(', ')}`
            : 'Selección de campo';
    }
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

function buildColormapHticks(colormap) {
    if (!colormap?.colors?.length) return null;

    const vmin  = colormap.vmin ?? 0;
    const vmax  = colormap.vmax ?? 100;
    const range = vmax - vmin;
    const MAX_TICKS = 5;

    let tickValues = [];

    if (colormap.ticks?.length > 0) {
        const raw = colormap.ticks
            .map(t => t.value)
            .filter(v => v >= vmin && v <= vmax)
            .sort((a, b) => a - b);
        if (raw.length === 0 || raw[0] > vmin)               raw.unshift(vmin);
        if (raw[raw.length - 1] < vmax)                       raw.push(vmax);
        if (raw.length <= MAX_TICKS) {
            tickValues = raw;
        } else {
            tickValues = Array.from({ length: MAX_TICKS },
                (_, i) => raw[Math.round(i * (raw.length - 1) / (MAX_TICKS - 1))]);
        }
    } else {
        for (let i = 0; i < MAX_TICKS; i++) {
            tickValues.push(vmin + (i / (MAX_TICKS - 1)) * range);
        }
    }

    const absRange = Math.abs(range);
    const decimals = absRange >= 10 ? 0 : absRange >= 1 ? 1 : 2;

    const container = document.createElement('div');
    container.className = 'layer-colormap-hticks';

    tickValues.forEach(value => {
        const leftPct = range > 0 ? ((value - vmin) / range) * 100 : 0;

        const tick = document.createElement('div');
        tick.className = 'layer-htick';
        tick.style.left = `${leftPct.toFixed(2)}%`;

        const line = document.createElement('div');
        line.className = 'layer-htick-line';

        const label = document.createElement('span');
        label.className = 'layer-htick-label';
        label.textContent = value.toFixed(decimals);

        tick.appendChild(line);
        tick.appendChild(label);
        container.appendChild(tick);
    });

    return container;
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

        // ── Header row: drag | eye | name | remove ──
        const header     = document.createElement('div');
        header.className = 'layer-row-header';

        const eyeBtn       = document.createElement('button');
        eyeBtn.className   = `layer-eye-btn${layer.visible ? '' : ' hidden-layer'}`;
        eyeBtn.textContent = layer.visible ? '👁' : '🚫';
        eyeBtn.title       = layer.visible ? 'Ocultar capa' : 'Mostrar capa';
        eyeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            setLayerVisible(layer.id, !layer.visible);
        });

        const nameEl       = document.createElement('div');
        nameEl.className   = 'layer-field-name';
        nameEl.textContent = layer.productKey;
        nameEl.title       = layer.productTitle;
        nameEl.addEventListener('click', (e) => {
            e.stopPropagation();
            openFieldPicker(layer.id);
        });

        const removeBtn       = document.createElement('button');
        removeBtn.className   = 'layer-remove-btn';
        removeBtn.textContent = '✕';
        removeBtn.title       = 'Quitar capa';
        removeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            removeLayer(layer.id);
        });

        header.appendChild(handle);
        header.appendChild(eyeBtn);
        header.appendChild(nameEl);
        header.appendChild(removeBtn);

        // ── Body: colormap strip + ticks + slider ──
        const body     = document.createElement('div');
        body.className = 'layer-row-body';

        const cmapWrapper     = document.createElement('div');
        cmapWrapper.className = 'layer-cmap-wrapper';

        const strip     = document.createElement('div');
        strip.className = 'layer-colormap-strip';
        if (layer.colormap?.colors?.length) {
            strip.style.background = buildHorizontalGradient(layer.colormap.colors);
        } else {
            strip.style.background = 'rgba(255,255,255,0.15)';
        }

        cmapWrapper.appendChild(strip);
        const hticks = buildColormapHticks(layer.colormap);
        if (hticks) cmapWrapper.appendChild(hticks);

        // ── Opacity % label (declared before slider so slider's input handler can reference it) ──
        const pctLabel       = document.createElement('span');
        pctLabel.className   = 'layer-opacity-pct';
        pctLabel.textContent = `${Math.round(layer.opacity * 100)}%`;

        const sliderRow     = document.createElement('div');
        sliderRow.className = 'layer-slider-row';

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
            const val = parseFloat(e.target.value);
            pctLabel.textContent = `${Math.round(val * 100)}%`;
            setLayerOpacity(layer.id, val);
        });

        sliderRow.appendChild(slider);
        sliderRow.appendChild(pctLabel);

        body.appendChild(cmapWrapper);
        body.appendChild(sliderRow);

        // ── Settings toggle ──
        const settingsToggle     = document.createElement('button');
        settingsToggle.className = 'layer-settings-toggle';
        settingsToggle.textContent = (layer.settingsExpanded ? '▾' : '▸') + ' Ajustes';

        // ── Settings body: colormap / range / smoothing ──
        const settingsBody     = document.createElement('div');
        settingsBody.className = 'layer-settings-body';
        settingsBody.style.display = layer.settingsExpanded ? 'flex' : 'none';

        // — Colormap select —
        const cmapSetRow     = document.createElement('div');
        cmapSetRow.className = 'layer-setting-row';
        const cmapSetLabel       = document.createElement('span');
        cmapSetLabel.className   = 'layer-setting-label';
        cmapSetLabel.textContent = 'Colormap';
        const cmapSetSel     = document.createElement('select');
        cmapSetSel.className = 'layer-setting-select';
        const availCmaps    = layer.colormap?.available_colormaps || [];
        const defaultCmName = layer.colormap?.colormap || null;
        if (defaultCmName) {
            const grp = document.createElement('optgroup');
            grp.label = 'Default';
            const opt = document.createElement('option');
            opt.value = defaultCmName; opt.textContent = defaultCmName;
            grp.appendChild(opt);
            cmapSetSel.appendChild(grp);
        }
        const otherCmaps = availCmaps.filter(c => c !== defaultCmName).sort();
        if (otherCmaps.length > 0) {
            const grp = document.createElement('optgroup');
            grp.label = 'Otros';
            otherCmaps.forEach(name => {
                const opt = document.createElement('option');
                opt.value = name; opt.textContent = name;
                grp.appendChild(opt);
            });
            cmapSetSel.appendChild(grp);
        }
        cmapSetSel.value = layer.selectedColormap || defaultCmName || '';
        cmapSetSel.addEventListener('mousedown', e => e.stopPropagation());
        cmapSetSel.addEventListener('change', async (e) => {
            e.stopPropagation();
            await setLayerColormap(layer.id, e.target.value);
        });
        cmapSetRow.appendChild(cmapSetLabel);
        cmapSetRow.appendChild(cmapSetSel);

        // — Range filter —
        const rangeSetRow     = document.createElement('div');
        rangeSetRow.className = 'layer-setting-row';
        const rangeSetLabel       = document.createElement('span');
        rangeSetLabel.className   = 'layer-setting-label';
        rangeSetLabel.textContent = 'Rango';
        const vminInp       = document.createElement('input');
        vminInp.type        = 'number';
        vminInp.className   = 'layer-setting-range-input';
        vminInp.placeholder = 'mín';
        vminInp.step        = 'any';
        vminInp.value       = layer.vmin != null ? String(layer.vmin)
            : (layer.colormap?.vmin != null ? String(layer.colormap.vmin) : '');
        vminInp.addEventListener('mousedown', e => e.stopPropagation());
        const vmaxInp       = document.createElement('input');
        vmaxInp.type        = 'number';
        vmaxInp.className   = 'layer-setting-range-input';
        vmaxInp.placeholder = 'máx';
        vmaxInp.step        = 'any';
        vmaxInp.value       = layer.vmax != null ? String(layer.vmax)
            : (layer.colormap?.vmax != null ? String(layer.colormap.vmax) : '');
        vmaxInp.addEventListener('mousedown', e => e.stopPropagation());
        const rangeApplyBtn       = document.createElement('button');
        rangeApplyBtn.className   = 'layer-setting-apply-btn';
        rangeApplyBtn.textContent = 'Aplicar';
        rangeApplyBtn.addEventListener('mousedown', e => e.stopPropagation());
        rangeApplyBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            layer.vmin = vminInp.value !== '' ? parseFloat(vminInp.value) : null;
            layer.vmax = vmaxInp.value !== '' ? parseFloat(vmaxInp.value) : null;
            await reloadLayerWithNewParams(layer);
        });
        rangeSetRow.appendChild(rangeSetLabel);
        rangeSetRow.appendChild(vminInp);
        rangeSetRow.appendChild(vmaxInp);
        rangeSetRow.appendChild(rangeApplyBtn);

        // — Gaussian smoothing —
        const smoothSetRow     = document.createElement('div');
        smoothSetRow.className = 'layer-setting-row';
        const smoothSetLabel       = document.createElement('span');
        smoothSetLabel.className   = 'layer-setting-label';
        smoothSetLabel.textContent = 'Suavizado';
        const smoothChk     = document.createElement('input');
        smoothChk.type      = 'checkbox';
        smoothChk.className = 'layer-setting-smooth-toggle';
        smoothChk.checked   = layer.smoothingEnabled;
        const smoothSlider     = document.createElement('input');
        smoothSlider.type      = 'range';
        smoothSlider.className = 'layer-setting-sigma-slider';
        smoothSlider.min       = '0.3';
        smoothSlider.max       = '3.0';
        smoothSlider.step      = '0.1';
        smoothSlider.value     = String(layer.smoothingSigma);
        smoothSlider.disabled  = !layer.smoothingEnabled;
        const smoothSigmaLbl       = document.createElement('span');
        smoothSigmaLbl.className   = 'layer-setting-sigma-val';
        smoothSigmaLbl.textContent = layer.smoothingSigma.toFixed(1);
        let _sigmaTimer = null;
        smoothChk.addEventListener('mousedown', e => e.stopPropagation());
        smoothChk.addEventListener('change', async (e) => {
            e.stopPropagation();
            layer.smoothingEnabled = e.target.checked;
            smoothSlider.disabled  = !layer.smoothingEnabled;
            await reloadLayerWithNewParams(layer);
        });
        smoothSlider.addEventListener('mousedown', e => e.stopPropagation());
        smoothSlider.addEventListener('input', (e) => {
            e.stopPropagation();
            const val = parseFloat(e.target.value);
            layer.smoothingSigma   = val;
            smoothSigmaLbl.textContent = val.toFixed(1);
            if (_sigmaTimer) clearTimeout(_sigmaTimer);
            if (layer.smoothingEnabled) {
                _sigmaTimer = setTimeout(async () => {
                    await reloadLayerWithNewParams(layer);
                }, 400);
            }
        });
        smoothSetRow.appendChild(smoothSetLabel);
        smoothSetRow.appendChild(smoothChk);
        smoothSetRow.appendChild(smoothSlider);
        smoothSetRow.appendChild(smoothSigmaLbl);

        settingsBody.appendChild(cmapSetRow);
        settingsBody.appendChild(rangeSetRow);
        settingsBody.appendChild(smoothSetRow);

        settingsToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            layer.settingsExpanded     = !layer.settingsExpanded;
            settingsBody.style.display = layer.settingsExpanded ? 'flex' : 'none';
            settingsToggle.textContent = (layer.settingsExpanded ? '▾' : '▸') + ' Ajustes';
        });

        body.appendChild(settingsToggle);
        body.appendChild(settingsBody);

        row.appendChild(header);
        row.appendChild(body);
        container.appendChild(row);
    });

    renderFieldPickerDropdown();
}

function renderFieldPickerDropdown() {
    const list = document.getElementById('field-picker-list');
    if (!list) return;

    const activeKeys = new Set(state.layers.map(l => l.productKey));
    const visible    = state.products.filter(p =>
        state.pickerShowFiltered
            ? !p.product_key.endsWith('o')
            :  p.product_key.endsWith('o')
    );

    list.innerHTML = '';
    visible.forEach(product => {
        const item = document.createElement('div');
        item.className = 'radar-checkbox-item';

        const cbId = `field-picker-cb-${product.product_key}`;
        const cb   = document.createElement('input');
        cb.type    = 'checkbox';
        cb.id      = cbId;
        cb.checked = activeKeys.has(product.product_key);

        cb.addEventListener('change', async () => {
            if (cb.checked) {
                await addLayer(product.product_key);
            } else {
                const layer = state.layers.find(l => l.productKey === product.product_key);
                if (layer) await removeLayer(layer.id);
            }
        });

        const label      = document.createElement('label');
        label.htmlFor    = cbId;
        label.textContent = product.product_key;
        label.title       = product.product_title;

        item.appendChild(cb);
        item.appendChild(label);
        list.appendChild(item);
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
    updateCoverageRadius();

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
        [state.radarCode], layer.productKey, CD_MODE.include
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
            startTime, endTime, 100, CD_MODE.include
        );

        if (!cogs.length) {
            state.ui.setStatus(`⚠️ Sin datos para ${layer.productKey}`, 'error');
            return;
        }

        // Store actual COG-derived coverage radius when the tag is present.
        // Layers without it stay null and updateCoverageRadius treats them as full-range.
        const coverageM = cogs.find(c => c.radar_coverage_m != null)?.radar_coverage_m ?? null;
        if (coverageM !== null) layer.coverageRadius = coverageM;

        const newFrames = buildGridFrames(cogs, 10, startTime, endTime);

        if (state.frames.length === 0) {
            state.frames = newFrames;
            state.mapManager._frameImages = state.frames.map(() => new Map());
        }

        // displayTimestamp (slot boundary) → frame index in the shared grid
        const slotToFrameIdx = new Map(
            state.frames.map((f, i) => [new Date(f.displayTimestamp).getTime(), i])
        );

        // Assign each COG for this radar to its nearest slot; latest obs_time wins per slot
        layer.cogsByFrame = new Map();
        cogs.forEach(cog => {
            if (cog.radar_code !== state.radarCode) return;
            const t    = new Date(cog.observation_time).getTime();
            const slot = Math.round(t / GRID_STEP_MS) * GRID_STEP_MS;
            const frameIdx = slotToFrameIdx.get(slot);
            if (frameIdx === undefined) return;
            const prev = layer.cogsByFrame.get(frameIdx);
            if (!prev || t > new Date(prev.observation_time).getTime()) {
                layer.cogsByFrame.set(frameIdx, cog);
            }
        });

        const key = `${state.radarCode}__${layer.productKey}`;
        const loadPromises = Array.from(layer.cogsByFrame.entries()).map(async ([frameIdx, cog]) => {
            const url = state.mapManager._buildFrameUrl(cog.id, layer.productKey, getTileParamsForLayer(layer));

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

        updateCoverageRadius();

    } catch (err) {
        console.error('loadLayerFramesForRange error:', err);
        state.ui.setStatus(`Error cargando ${layer.productKey}: ${err.message}`, 'error');
    }
}

/**
 * Recompute and apply the coverage mask + ring lines.
 * For every active layer: use its COG-derived radius when known, otherwise
 * treat it as full-range (img_radio).
 * - The mask cutout uses the largest radius (union of all coverage areas).
 * - A visible ring is drawn for each unique radius; the smallest ring gets
 *   heavier styling since it lies inside the lit coverage area.
 */
function updateCoverageRadius() {
    if (!state.radar || !state.mapManager) return;
    const fullRange = state.radar.img_radio * 1000;

    // Collect unique {radius_m, productKey} pairs from active layers.
    // When no layers are active, show no rings but keep the mask at full range.
    let uniqueRings = [];
    if (state.layers.length > 0) {
        const seen = new Set();
        for (const l of state.layers) {
            const r = l.coverageRadius ?? fullRange;
            if (!seen.has(r)) {
                seen.add(r);
                uniqueRings.push({ radius_m: r, productKey: l.productKey });
            }
        }
    }

    const maxRadius = uniqueRings.length > 0
        ? Math.max(...uniqueRings.map(r => r.radius_m))
        : fullRange;
    state.mapManager.addRadarCoverage(
        state.radar.code,
        state.radar.center_lat,
        state.radar.center_long,
        maxRadius,
    );
    state.mapManager.setRadarCoverageRings(
        state.radar.code,
        state.radar.center_lat,
        state.radar.center_long,
        uniqueRings,
    );
}

// ─── Per-layer render params ──────────────────────────────────────────────────

function getTileParamsForLayer(layer) {
    return {
        colormap:    layer.selectedColormap || null,
        vmin:        layer.vmin,
        vmax:        layer.vmax,
        smooth:      layer.smoothingEnabled,
        smoothSigma: layer.smoothingSigma,
    };
}

/**
 * Re-fetch frame images for one layer using its current render params,
 * replacing cached entries in-place. Leaves all other layers untouched.
 */
async function reloadLayerWithNewParams(layer) {
    if (!state.frames.length) return;
    state.ui.setStatus(`Actualizando ${layer.productKey}…`, 'loading');
    const key    = `${state.radarCode}__${layer.productKey}`;
    const params = getTileParamsForLayer(layer);

    const promises = state.frames.map(async (frame, frameIdx) => {
        const cog = layer.cogsByFrame?.get(frameIdx);
        if (!cog) return;
        const url = state.mapManager._buildFrameUrl(cog.id, layer.productKey, params);
        try {
            const { img, objectUrl } = await state.mapManager._loadImage(url);
            if (!state.mapManager._frameImages[frameIdx]) {
                state.mapManager._frameImages[frameIdx] = new Map();
            }
            const old = state.mapManager._frameImages[frameIdx].get(key);
            if (old?.objectUrl) URL.revokeObjectURL(old.objectUrl);
            state.mapManager._frameImages[frameIdx].set(key, { img, loaded: true, url, objectUrl });
        } catch (err) {
            console.warn(`reloadLayerWithNewParams: failed ${key} frame ${frameIdx}:`, err);
        }
    });

    await Promise.all(promises);

    const ci = state.mapManager._currentFrameIndex;
    if (ci >= 0) showAllLayersAtFrame(ci);
    state.ui.setStatus(`✓ ${layer.productKey} actualizado`, 'success');
}

/**
 * Change the colormap for a layer: fetch new colormap info, update the strip,
 * re-render the layer list, then reload frame images.
 */
async function setLayerColormap(layerId, colormapName) {
    const layer = state.layers.find(l => l.id === layerId);
    if (!layer) return;
    layer.selectedColormap = colormapName;
    try {
        const info = await api.getColormapInfo(layer.productKey, colormapName);
        layer.colormap = info;
    } catch (err) {
        console.warn('setLayerColormap: could not fetch colormap info:', err);
    }
    renderLayerList();
    await reloadLayerWithNewParams(layer);
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
        id:             state.nextLayerId++,
        productKey,
        productTitle:   product.product_title,
        opacity:        state.layers.length === 0 ? 1.0 : DEFAULT_FIELD_OPACITY,
        visible:        true,
        colormap,
        zIndex:         state.layers.length,
        coverageRadius:   null,
        selectedColormap: colormap?.colormap || null,
        vmin:             null,
        vmax:             null,
        smoothingEnabled: false,
        smoothingSigma:   0.8,
        settingsExpanded: false,
        cogsByFrame:      new Map(),
    };
    state.layers.push(layer);
    updateCoverageRadius(); // immediate update: new layer contributes full-range until COGs load

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

    layer.productKey       = newProductKey;
    layer.productTitle     = product.product_title;
    layer.colormap         = colormap;
    layer.coverageRadius   = null;
    layer.selectedColormap = colormap?.colormap || null;
    layer.vmin             = null;
    layer.vmax             = null;
    updateCoverageRadius();

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
            [state.radarCode], anchorLayer.productKey, CD_MODE.include
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

    const btnSnapshot = document.getElementById('btn-snapshot');
    if (btnSnapshot) {
        btnSnapshot.addEventListener('click', () => captureMapSnapshot());
    }

    // ── Animation controls: collapse toggle ──
    const btnCollapse = document.getElementById('btn-collapse-controls');
    const animPanel   = document.getElementById('animation-controls');
    if (btnCollapse && animPanel) {
        btnCollapse.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            e.preventDefault();
            animPanel.classList.toggle('collapsed');
        });
    }

    // ── Animation controls: draggable ──
    const animHandle = animPanel?.querySelector('.animation-info-row');
    if (animPanel && animHandle) {
        let dragging = false;
        let offsetX  = 0;
        let offsetY  = 0;

        animHandle.addEventListener('mousedown', (e) => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON') return;
            const rect = animPanel.getBoundingClientRect();
            animPanel.style.right  = 'auto';
            animPanel.style.bottom = 'auto';
            animPanel.style.left   = `${rect.left}px`;
            animPanel.style.top    = `${rect.top}px`;
            dragging = true;
            offsetX  = e.clientX - rect.left;
            offsetY  = e.clientY - rect.top;
            animHandle.classList.add('dragging');
            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (!dragging) return;
            const maxX = window.innerWidth  - animPanel.offsetWidth;
            const maxY = window.innerHeight - animPanel.offsetHeight;
            animPanel.style.left = `${Math.max(0, Math.min(e.clientX - offsetX, maxX))}px`;
            animPanel.style.top  = `${Math.max(0, Math.min(e.clientY - offsetY, maxY))}px`;
        });

        const endDrag = () => {
            if (!dragging) return;
            dragging = false;
            animHandle.classList.remove('dragging');
        };
        document.addEventListener('mouseup',    endDrag);
        document.addEventListener('mouseleave', endDrag);
    }

    // ── Section-add-field: collapsible dropdown with checkbox list ──
    const sectionAddField = document.getElementById('section-add-field');
    if (sectionAddField) {
        const sectionHeader = sectionAddField.querySelector('.field-section-header');
        if (sectionHeader) {
            sectionHeader.addEventListener('click', () => {
                const isOpen = sectionAddField.classList.toggle('open');
                sectionHeader.setAttribute('aria-expanded', String(isOpen));
                if (isOpen) renderFieldPickerDropdown();
            });
        }
    }

    const togglePickerFiltered = document.getElementById('toggle-field-picker-filtered');
    if (togglePickerFiltered) {
        togglePickerFiltered.addEventListener('change', () => {
            state.pickerShowFiltered = togglePickerFiltered.checked;
            renderFieldPickerDropdown();
        });
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

// =============================================================================
// SNAPSHOT
// =============================================================================

async function captureMapSnapshot() {
    try {
        const mapEl = document.getElementById('map');

        // Step 1: draw geo content (basemap + radar overlays + SVG mask) on full canvas
        const full    = document.createElement('canvas');
        full.width    = mapEl.offsetWidth;
        full.height   = mapEl.offsetHeight;
        const fullCtx = full.getContext('2d');

        // Basemap tiles + radar overlay images
        const imgs = Array.from(
            document.querySelectorAll('.leaflet-tile-pane img, .leaflet-overlay-pane img')
        );
        for (const img of imgs) {
            if (!img.complete || img.naturalWidth === 0) continue;
            const rect    = img.getBoundingClientRect();
            const mapRect = mapEl.getBoundingClientRect();
            fullCtx.globalAlpha = parseFloat(img.style.opacity || '1');
            fullCtx.drawImage(img, rect.left - mapRect.left, rect.top - mapRect.top,
                rect.width, rect.height);
        }
        fullCtx.globalAlpha = 1;

        // Coverage SVG mask
        const coverageSvg = state.mapManager?._coverageSvgEl;
        if (coverageSvg) {
            try {
                const svgData = new XMLSerializer().serializeToString(coverageSvg);
                const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
                const svgUrl  = URL.createObjectURL(svgBlob);
                await new Promise((resolve) => {
                    const svgImg = new Image();
                    svgImg.onload = () => {
                        fullCtx.drawImage(svgImg, 0, 0, full.width, full.height);
                        URL.revokeObjectURL(svgUrl);
                        resolve();
                    };
                    svgImg.onerror = () => { URL.revokeObjectURL(svgUrl); resolve(); };
                    svgImg.src = svgUrl;
                });
            } catch (_) { /* best-effort */ }
        }

        // Step 2: crop to centered rect. SNAPSHOT_ASPECT = cropW / cropH.
        // 1.0 = square, 1.2 = a bit wider, 1.5 = 3:2, etc.
        const SNAPSHOT_ASPECT = 1.3;
        const cropH  = Math.min(full.width, full.height);
        const cropW  = Math.min(Math.round(cropH * SNAPSHOT_ASPECT), full.width);
        const cropX  = Math.round((full.width  - cropW) / 2);
        const cropY  = Math.round((full.height - cropH) / 2);
        const canvas = document.createElement('canvas');
        canvas.width  = cropW;
        canvas.height = cropH;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(full, cropX, cropY, cropW, cropH, 0, 0, cropW, cropH);

        // Step 3: draw annotation overlays on the cropped canvas
        // Comment out any line to disable that overlay element.
        const timeText = document.getElementById('time-display')?.textContent?.trim() || '';
        await radarSnapshotOverlayLogo(ctx);
        radarSnapshotOverlayHeader(ctx, canvas);
        radarSnapshotOverlayLayerLegends(ctx, canvas, timeText);
        radarSnapshotOverlayInfoPanel(ctx, canvas, timeText);

        const link = document.createElement('a');
        const code = state.radarCode || 'radar';
        link.download = `${code}-snapshot-${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
        link.href = canvas.toDataURL('image/png');
        link.click();
    } catch (err) {
        console.warn('Snapshot failed:', err);
        if (state.ui) state.ui.setStatus('Error al capturar la imagen: ' + err.message, 'error');
    }
}

/** Draw the OHMC logo (top-left). */
async function radarSnapshotOverlayLogo(ctx) {
    const img = document.querySelector('#logo-container img');
    if (!img || !img.complete || img.naturalWidth === 0) return;
    const displayH =75;
    const displayW = Math.round(img.naturalWidth * (displayH / img.naturalHeight));
    ctx.save();
    ctx.globalAlpha = 1;
    ctx.drawImage(img, 16, 16, displayW, displayH);
    ctx.restore();
}

/**
 * Draw a panel showing the radar code + title (top-center, below the
 * on-screen radar header bar).
 */
function radarSnapshotOverlayHeader(ctx, canvas) {
    if (!state.radar) return;
    const text = `${state.radar.code}  —  ${state.radar.title}`;
    const FONT_SZ = 16;
    const PAD     = 10;
    ctx.save();
    ctx.font        = `bold ${FONT_SZ}px "Inter", sans-serif`;
    ctx.textBaseline = 'top';
    ctx.textAlign   = 'center';
    const textW = ctx.measureText(text).width;
    const boxW  = textW + PAD * 2;
    const boxH  = FONT_SZ + PAD * 2;
    const x     = (canvas.width - boxW) / 2;
    const y     = 16;
    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    _radarSnapshotRoundRect(ctx, x, y, boxW, boxH, 6);
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.fillText(text, canvas.width / 2, y + PAD);
    ctx.restore();
}

/**
 * Draw compact horizontal colormap strips for every active layer (bottom-left).
 * Each row: [field name] [gradient strip] — mirroring the layer list in the panel.
 * The current frame datetime appears above the strip stack.
 */
function radarSnapshotOverlayLayerLegends(ctx, canvas, timeText) {
    const visibleLayers = state.layers.filter(l => l.visible && l.colormap?.colors?.length);
    if (!visibleLayers.length) return;

    const LABEL_W      = 90;
    const STRIP_W      = 170;
    const STRIP_H      = 14;
    const TICK_LINE_H  = 4;
    const TICK_LABEL_H = 9;
    const TICK_FONT_SZ = 8;
    const MAX_TICKS    = 5;
    const ROW_GAP      = 8;
    const FONT_SZ      = 16;
    const TIME_SZ      = 16;
    const PAD          = 12;
    const SAMPLES      = 64;

    const rowH  = STRIP_H + TICK_LINE_H + TICK_LABEL_H + ROW_GAP;
    const timeH = timeText && timeText !== '—' ? TIME_SZ + 6 : 0;
    const totalH = timeH + visibleLayers.length * rowH - ROW_GAP + PAD * 2;
    const totalW = PAD + LABEL_W + 6 + STRIP_W + PAD;
    const x0 = 16;
    const y0 = canvas.height - totalH - 16;

    ctx.save();

    // Background panel
    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    _radarSnapshotRoundRect(ctx, x0, y0, totalW, totalH, 6);
    ctx.fill();

    let curY = y0 + PAD;

    // Datetime line above the layer rows
    if (timeH) {
        ctx.font        = `${TIME_SZ}px "Inter", monospace`;
        ctx.fillStyle   = 'rgba(255,255,255,0.75)';
        ctx.textBaseline = 'top';
        ctx.textAlign   = 'left';
        ctx.fillText(timeText, x0 + PAD, curY);
        curY += timeH;
    }

    visibleLayers.forEach(layer => {
        const cm    = layer.colormap;
        const vmin  = cm.vmin ?? 0;
        const vmax  = cm.vmax ?? 100;
        const range = vmax - vmin;

        // Field name label (truncated to fit LABEL_W)
        ctx.font        = `bold ${FONT_SZ}px "Inter", sans-serif`;
        ctx.fillStyle   = '#ffffff';
        ctx.textBaseline = 'middle';
        ctx.textAlign   = 'left';
        let label = layer.productKey;
        while (label.length > 1 && ctx.measureText(label).width > LABEL_W) {
            label = label.slice(0, -1);
        }
        ctx.fillText(label, x0 + PAD, curY + STRIP_H / 2);

        // Horizontal gradient strip
        const stripX = x0 + PAD + LABEL_W + 6;
        const grad   = ctx.createLinearGradient(stripX, 0, stripX + STRIP_W, 0);
        for (let i = 0; i < SAMPLES; i++) {
            const t   = i / (SAMPLES - 1);
            const idx = Math.round(t * (cm.colors.length - 1));
            grad.addColorStop(t, cm.colors[idx]);
        }
        ctx.fillStyle = grad;
        ctx.fillRect(stripX, curY, STRIP_W, STRIP_H);

        // Opacity indicator: dim unfilled bar portion if opacity < 1
        if (layer.opacity < 1) {
            ctx.fillStyle = `rgba(0,0,0,${1 - layer.opacity})`;
            ctx.fillRect(stripX, curY, STRIP_W, STRIP_H);
        }

        // Tick marks + labels (same logic as buildColormapHticks)
        let tickValues = [];
        if (cm.ticks?.length > 0) {
            const raw = cm.ticks
                .map(t => t.value)
                .filter(v => v >= vmin && v <= vmax)
                .sort((a, b) => a - b);
            if (raw.length === 0 || raw[0] > vmin) raw.unshift(vmin);
            if (raw[raw.length - 1] < vmax)        raw.push(vmax);
            tickValues = raw.length <= MAX_TICKS
                ? raw
                : Array.from({ length: MAX_TICKS },
                    (_, i) => raw[Math.round(i * (raw.length - 1) / (MAX_TICKS - 1))]);
        } else {
            tickValues = Array.from({ length: MAX_TICKS },
                (_, i) => vmin + (i / (MAX_TICKS - 1)) * range);
        }
        const absRange = Math.abs(range);
        const decimals = absRange >= 10 ? 0 : absRange >= 1 ? 1 : 2;

        const tickY = curY + STRIP_H;
        ctx.font        = `${TICK_FONT_SZ}px "Inter", monospace`;
        ctx.textBaseline = 'top';
        ctx.textAlign   = 'center';
        tickValues.forEach(value => {
            const leftPct = range !== 0 ? (value - vmin) / range : 0;
            const tx      = stripX + leftPct * STRIP_W;
            ctx.fillStyle = 'rgba(255,255,255,0.6)';
            ctx.fillRect(Math.round(tx), tickY, 1, TICK_LINE_H);
            ctx.fillStyle = 'rgba(255,255,255,0.85)';
            ctx.fillText(value.toFixed(decimals), tx, tickY + TICK_LINE_H + 1);
        });

        curY += rowH;
    });

    ctx.restore();
}

/**
 * Draw the current frame datetime in a small panel (bottom-right) when there
 * is only one layer or when the layer legends panel is absent.
 * Skipped if the layer legends panel already shows the time.
 */
function radarSnapshotOverlayInfoPanel(ctx, canvas, timeText) {
    // If there are visible layers the legends panel already shows the time.
    const hasLegends = state.layers.some(l => l.visible && l.colormap?.colors?.length);
    if (hasLegends) return;
    if (!timeText || timeText === '—') return;

    const FONT_SZ = 16;
    const PAD     = 12;
    ctx.save();
    ctx.font        = `${FONT_SZ}px "Inter", monospace`;
    ctx.textBaseline = 'top';
    const textW = ctx.measureText(timeText).width;
    const boxW  = textW + PAD * 2;
    const boxH  = FONT_SZ + PAD * 2;
    const x = canvas.width  - boxW - 16;
    const y = canvas.height - boxH - 16;
    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    _radarSnapshotRoundRect(ctx, x, y, boxW, boxH, 6);
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.fillText(timeText, x + PAD, y + PAD);
    ctx.restore();
}

/** Helper: filled rounded rectangle path. */
function _radarSnapshotRoundRect(ctx, x, y, w, h, r) {
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
    // ─── Initialization ───────────────────────────────────────────────────────────────
    async init() {

        try {
            await waitForLeaflet();
            
            state.ui = new UIControls();
            state.mapManager = new MapManager('map', {minZoom: 7.2});
            state.mapManager.init();
            state.animator   = new AnimationController(state.mapManager);
            window.__radarMapManager = state.mapManager; // exposed for e2e/debug

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
                api.getProducts(CD_MODE.include),
            ]);

            state.radar    = radars.find(r => r.code === RADAR_CODE) || null;
            state.products = products;

            if (!state.radar || !state.radar.detail_view_enabled) {
                const overlay = document.getElementById('radar-unavailable');
                const counter = document.getElementById('redirect-countdown');
                overlay.style.display = 'flex';
                let secs = 5;
                const tick = setInterval(() => {
                    secs -= 1;
                    counter.textContent = secs;
                    if (secs <= 0) {
                        clearInterval(tick);
                        window.location.replace('index.html');
                    }
                }, 1000);
                return;
            }

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