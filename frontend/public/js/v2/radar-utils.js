import { 
    COVERAGE_MODES, 
} from './constants.js';

// =============================================================================
// HELPERS
// =============================================================================

export function getCogBucketKey(timestamp, toleranceMinutes = 10) {
    const bucketMs = toleranceMinutes * 60 * 1000;
    const t = new Date(timestamp).getTime();
    return Math.round(t / bucketMs) * bucketMs;
}

export function groupCogsByTimestamp(cogs, toleranceMinutes = 5) {
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
// function groupCogsByTimestamp(cogs) {
//     const buckets = new Map();
//     cogs.forEach(cog => {
//         const key = Math.round(
//             new Date(cog.observation_time).getTime() / 60000
//         ) * 60000;
//         if (!buckets.has(key)) {
//             buckets.set(key, { timestamp: cog.observation_time, cogsByRadar: {} });
//         }
//         buckets.get(key).cogsByRadar[cog.radar_code] = cog;
//     });
//     return Array.from(buckets.values())
//         .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
// }
/**
 * Build animation frames on a fixed grid (default 10 min), assigning each COG
 * to the next grid boundary at or after its observation time (ceiling assignment).
 *
 * When multiple COGs from the same radar map to the same slot, the one with the
 * latest observation time wins (freshest data closest to the slot boundary).
 *
 * frame.displayTimestamp — the grid boundary ISO string, used for the time display.
 * frame.timestamp        — actual obs_dt of the first assigned COG, used for
 *                          TOPS_CORES matching (exact obs time, not the display slot).
 *
 * @param {Array}  cogs         Flat COG list from the API
 * @param {number} stepMinutes  Display grid interval (default 10)
 * @returns {Array}             [{displayTimestamp, timestamp, cogsByRadar}, …]
 */
export function buildGridFrames(cogs, stepMinutes = 10) {
    if (!cogs || cogs.length === 0) return [];

    const stepMs = stepMinutes * 60 * 1000;

    // slot (ms) → radar_code → { cog, t }  — latest obs_time wins per radar per slot
    const bySlot = {};
    cogs.forEach(cog => {
        const t    = new Date(cog.observation_time).getTime();
        const slot = Math.ceil(t / stepMs) * stepMs;
        if (!bySlot[slot]) bySlot[slot] = {};
        const prev = bySlot[slot][cog.radar_code];
        if (!prev || t > prev.t) {
            bySlot[slot][cog.radar_code] = { cog, t };
        }
    });

    return Object.keys(bySlot)
        .map(Number)
        .sort((a, b) => a - b)
        .map(slotMs => {
            const cogsByRadar = {};
            Object.values(bySlot[slotMs]).forEach(({ cog }) => {
                cogsByRadar[cog.radar_code] = cog;
            });
            const firstCog = Object.values(cogsByRadar)[0];
            return {
                displayTimestamp: new Date(slotMs).toISOString(),
                timestamp:        firstCog.observation_time,
                cogsByRadar,
            };
        });
}

export function getAvailableProductKeys(products, showUnfilteredProducts) {
    return products
        .map(product => product.product_key)
        .filter(productKey => {
            const isUnfiltered = /o$/.test(productKey);
            return showUnfilteredProducts ? isUnfiltered : !isUnfiltered;
        });
}

export function selectDefaultProduct(availableProductKeys) {
    const preferredKeys = ['COLMAX', 'DBZH', 'DBZHo'];
    return preferredKeys.find(key => availableProductKeys.includes(key))
        || availableProductKeys[0]
        || null;
}

// Field-key helpers. Convention: a trailing 'o' marks the UNFILTERED variant
// (e.g. COLMAXo); no suffix is the filtered/polarimetric variant (COLMAX).
export function baseFieldKey(productKey) {
    return (productKey || '').replace(/o$/, '');
}

// Does the product list contain BOTH the filtered and unfiltered variant of the
// field that `productKey` belongs to? (i.e. can the Filtered switch toggle it?)
export function fieldHasBothVariants(products, productKey) {
    const base = baseFieldKey(productKey);
    const keys = products.map(p => p.product_key);
    return keys.includes(base) && keys.includes(`${base}o`);
}

// The key for the requested variant of a field, or null if it isn't available.
export function fieldVariantKey(products, productKey, unfiltered) {
    const target = unfiltered ? `${baseFieldKey(productKey)}o` : baseFieldKey(productKey);
    return products.some(p => p.product_key === target) ? target : null;
}

/**
 * Convert a groupedFrames array (app.js state.cogs format) to the
 * Map<frameIndex, Map<radarCode, cogObject>> format expected by MapManager.loadFrames().
 *
 * @param {Array} groupedFrames  [{timestamp, cogsByRadar: {code: cog}}, …]
 * @returns {Map<number, Map<string, Object>>}
 */
export function buildCogsByFrameMap(groupedFrames) {
    const cogsByFrame = new Map();
    groupedFrames.forEach((frame, idx) => {
        const radarMap = new Map();
        Object.entries(frame.cogsByRadar).forEach(([code, cog]) => radarMap.set(code, cog));
        cogsByFrame.set(idx, radarMap);
    });
    return cogsByFrame;
}

export async function waitForLeaflet(maxWait = 5000) {
    const startTime = Date.now();
    while (typeof L === 'undefined') {
        if (Date.now() - startTime > maxWait) {
            throw new Error('Leaflet library failed to load. Please check your internet connection.');
        }
        await new Promise(resolve => setTimeout(resolve, 100));
    }
}

/**
 * Returns the COVERAGE_MODES entry that matches state.coverageModeId.
 * Falls back to the first entry if the stored id is somehow unknown.
 */
export function getActiveCoverageMode(coverageModeId) {
    return COVERAGE_MODES.find(m => m.id === coverageModeId) || COVERAGE_MODES[0];
}

export function updateRadarHeader(radar) {
    const codeEl  = document.getElementById('radar-header-code');
    const titleEl = document.getElementById('radar-header-title');
    if (codeEl)  codeEl.textContent  = radar.code;
    if (titleEl) titleEl.textContent = radar.title;
    document.title = `${radar.code} — WebMet25`;
}

export function fitMapToRadar(radar, mapManager) {
    if (!radar.extent) return;
    const { lat_min, lat_max, lon_min, lon_max } = radar.extent;
    mapManager.getMap().fitBounds([
        [lat_min, lon_min],
        [lat_max, lon_max],
    ]);
}

/** Update badge-module-b with the currently selected product key. */
export function _updateFieldBadge(selectedProduct) {
    const badge = document.getElementById('badge-module-b');
    if (!badge) return;
    const key = selectedProduct || '';
    badge.textContent = key ? key.toUpperCase() : '';
    badge.style.display = key ? 'inline-flex' : 'none';
}

/** Update badge-module-a with the number of selected radars. */
export function _updateRadarBadge(selectedRadars) {
    const badge = document.getElementById('badge-module-a');
    if (!badge) return;
    const count = (selectedRadars || []).length;
    badge.textContent = count > 0 ? String(count) : '';
    badge.style.display = count > 0 ? 'inline-flex' : 'none';
}

export function updateLiveIndicator(liveHours) {
    const el = document.getElementById('live-indicator');
    if (!el) return;
    if (liveHours !== null) {
        el.textContent = '● EN VIVO';
        el.className = 'live-indicator live-on';
    } else {
        el.textContent = '○ En vivo';
        el.className = 'live-indicator live-off';
    }
    const cogRefreshBtn = document.getElementById('btn-cog-refresh-now');
    if (cogRefreshBtn) cogRefreshBtn.disabled = liveHours === null;
}

export function _hideFieldLoadingBadge() {
    const badge = document.getElementById('field-loading-badge');
    if (badge) badge.classList.remove('visible');
}

export function isTopsCoresAvailableForField(productKey) {
    const baseProductKey = (productKey || '').replace(/o$/, '');
    return baseProductKey === 'COLMAX';
}

// =============================================================================
// GEOLOCATION HELPERS (identical to app.js)
// =============================================================================

/**
 * Returns a debounced version of *fn* that only fires after *ms* milliseconds
 * of inactivity. Useful for sliders whose `input` events fire at high frequency.
 *
 * @param {Function} fn
 * @param {number}   ms
 * @returns {Function}
 */
export function debounce(fn, ms) {
    let timer = null;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), ms);
    };
}

export function haversineKm(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2 +
              Math.cos(lat1 * Math.PI / 180) *
              Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function getBrowserGeolocation() {
    return new Promise((resolve, reject) => {
        if (!navigator.geolocation) { reject(new Error('Geolocation not supported')); return; }
        navigator.geolocation.getCurrentPosition(
            pos => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
            err => reject(err),
            { timeout: 8000, maximumAge: 60000 }
        );
    });
}

export async function getIPGeolocation() {
    const resp = await fetch('https://ipapi.co/json/', { signal: AbortSignal.timeout(6000) });
    if (!resp.ok) throw new Error(`IP geo failed: ${resp.status}`);
    const data = await resp.json();
    if (!data.latitude || !data.longitude) throw new Error('No coordinates in IP geo response');
    return { lat: data.latitude, lon: data.longitude };
}