/**
 * Radar Visualization App - Enhanced Version
 * 
 * Features:
 * - Modular architecture with separate concerns
 * - Animation controls with play/pause/speed
 * - Color legend with API integration
 * - Opacity slider
 * - Improved UI/UX matching webmet.ohmc.ar
 */

import { api } from './api.js';
import { MapManager } from './map.js';
import { AnimationController } from './animation.js';
import { UIControls } from './controls.js';
import { LegendRenderer } from './legend.js';

// =============================================================================
// CONSTANTS
// =============================================================================

const MS_PER_HOUR = 3600 * 1000;
const LIVE_REFRESH_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes
const BUCKET_TOLERANCE_MINUTES = 5; // COG grouping bucket size – must match groupCogsByTimestamp default

// =============================================================================
// APPLICATION STATE
// =============================================================================

const state = {
    // Data
    radars: [],
    products: [],
    cogs: [],
    
    // Selections
    selectedRadars: [], // Changed from selectedRadar to support multiple
    selectedProduct: null,
    showUnfilteredProducts: false, // Filter state for products

    // Colormap / range overrides (null = use server defaults)
    selectedColormap: null,
    currentVmin: null,
    currentVmax: null,
    
    // Module instances
    mapManager: null,
    animator: null,
    ui: null,
    legend: null,
    
    // Flags
    hasZoomedToBounds: false,
    animationMode: null, // 'latest' | 'timerange' | null

    // Live N-hours mode
    liveHours: null,             // N when a preset button was last used; null = not in live mode
    liveRefreshInterval: null,   // setInterval handle for 5-minute polling
};

// =============================================================================
// HELPERS
// =============================================================================

/**
 * Return the rounded-epoch bucket key for a COG timestamp using the same
 * bucket size as groupCogsByTimestamp.
 *
 * @param {string|Date} timestamp
 * @returns {number} bucket key (ms since epoch, rounded to BUCKET_TOLERANCE_MINUTES)
 */
function getCogBucketKey(timestamp) {
    const bucketMs = BUCKET_TOLERANCE_MINUTES * 60 * 1000;
    const t = new Date(timestamp).getTime();
    return Math.round(t / bucketMs) * bucketMs;
}

/**
 * Group a flat list of COGs (from multiple radars) into animation frames.
 *
 * COGs that fall within the same `toleranceMinutes` window are merged into one
 * frame so all selected radars are rendered simultaneously at each step.
 *
 * @param {Array}  cogs             - Raw COG objects (sorted newest-first)
 * @param {number} toleranceMinutes - Bucket size in minutes (default BUCKET_TOLERANCE_MINUTES)
 * @returns {Array} groupedFrames   - [{timestamp, cogsByRadar: {code: cog}}, …]
 *                                    sorted newest-first
 */
function groupCogsByTimestamp(cogs, toleranceMinutes = BUCKET_TOLERANCE_MINUTES) {
    const bucketMs = toleranceMinutes * 60 * 1000;

    const buckets = new Map(); // rounded-epoch → frame object

    cogs.forEach(cog => {
        const t = new Date(cog.observation_time).getTime();
        const key = Math.round(t / bucketMs) * bucketMs;

        if (!buckets.has(key)) {
            buckets.set(key, { timestamp: cog.observation_time, cogsByRadar: {} });
        }

        const frame = buckets.get(key);
        // Keep only one COG per radar per bucket (first encountered wins)
        if (!frame.cogsByRadar[cog.radar_code]) {
            frame.cogsByRadar[cog.radar_code] = cog;
        }
    });

    // Return sorted oldest-first so animation plays forward in time
    return Array.from(buckets.entries())
        .sort((a, b) => a[0] - b[0])
        .map(([, frame]) => frame);
}

// =============================================================================
// MAIN APPLICATION
// =============================================================================

const app = {
    /**
     * Initialize the application
     */
    async init() {
        // Initialize modules
        state.ui = new UIControls();
        state.ui.setStatus('Initializing...', 'loading');
        
        try {
            // Wait for Leaflet to be loaded
            await this.waitForLeaflet();
            
            // Initialize map
            state.mapManager = new MapManager();
            state.mapManager.init();
            
            // Initialize animation controller
            state.animator = new AnimationController();
            state.animator.setOnFrameChange((index, frame) => {
                this.onFrameChange(index, frame);
            });
            
            // Initialize legend
            state.legend = new LegendRenderer('legend-container');
            
            // Load initial data
            await this.loadInitialData();
            
            // Setup event listeners
            this.setupEventListeners();
            
            // Disable animation controls initially
            state.ui.enableAnimationControls(false);
            state.ui.enableNavButtons(false);
            
            state.ui.setStatus('Ready', 'success');
            
        } catch (error) {
            console.error('Init error:', error);
            state.ui.setStatus(`Error: ${error.message}`, 'error');
        }
    },
    
    /**
     * Wait for Leaflet library to be loaded
     */
    async waitForLeaflet(maxWait = 5000) {
        const startTime = Date.now();
        
        while (typeof L === 'undefined') {
            if (Date.now() - startTime > maxWait) {
                throw new Error('Leaflet library failed to load. Please check your internet connection.');
            }
            // Wait 100ms before checking again
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        
        console.log('Leaflet loaded successfully');
    },
    
    /**
     * Load radars and products from API
     */
    async loadInitialData() {
        // Load radars
        state.radars = await api.getRadars();
        state.ui.populateRadarCheckboxes(state.radars);
        
        // Load products
        state.products = await api.getProducts();
        // Populate with filtered products by default
        state.ui.populateProductSelect(state.products, state.showUnfilteredProducts);
        state.ui.updateFilterButton(state.showUnfilteredProducts);
    },
    
    /**
     * Setup all event listeners
     */
    setupEventListeners() {
        // Basemap selection
        document.getElementById('basemap-select').addEventListener('change', (e) => {
            state.mapManager.setBasemap(e.target.value);
        });
        
        // Radar checkboxes toggle
        document.getElementById('btn-toggle-radars').addEventListener('click', () => {
            const container = document.getElementById('radar-checkboxes');
            const btn = document.getElementById('btn-toggle-radars');
            // Check if hidden by inline style or initial CSS
            const isHidden = container.style.display === 'none' || 
                           window.getComputedStyle(container).display === 'none';
            
            if (isHidden) {
                container.style.display = 'block';
                btn.textContent = 'Hide Radars ▲';
            } else {
                container.style.display = 'none';
                btn.textContent = 'Show Radars ▼';
            }
        });
        
        // Select all radars
        document.getElementById('btn-select-all-radars').addEventListener('click', () => {
            state.ui.selectAllRadars();
            this.onRadarSelectionChange();
        });
        
        // Clear all radars
        document.getElementById('btn-clear-all-radars').addEventListener('click', () => {
            state.ui.clearAllRadars();
            this.onRadarSelectionChange();
        });
        
        // Radar checkbox changes
        document.addEventListener('change', (e) => {
            if (e.target.classList.contains('radar-checkbox')) {
                this.onRadarSelectionChange();
            }
        });
        
        // Product selection
        document.getElementById('product-select').addEventListener('change', (e) => {
            state.selectedProduct = e.target.value;
            // Reset colormap/range state when product changes
            state.selectedColormap = null;
            state.currentVmin = null;
            state.currentVmax = null;
            // Reset vmin/vmax inputs when product changes so loadColormapOptions
            // always fills them from the new product's defaults
            document.getElementById('vmin-input').value = '';
            document.getElementById('vmax-input').value = '';
            this.onSelectionChange();
        });
        
        // Product filter toggle
        document.getElementById('btn-toggle-filter').addEventListener('click', () => {
            state.showUnfilteredProducts = !state.showUnfilteredProducts;
            
            // Remember current selection
            const currentSelection = state.selectedProduct;
            
            // Update product list
            state.ui.populateProductSelect(state.products, state.showUnfilteredProducts);
            state.ui.updateFilterButton(state.showUnfilteredProducts);
            
            // Try to restore selection if it exists in the new list
            const productSelect = document.getElementById('product-select');
            if (currentSelection && productSelect) {
                const optionExists = Array.from(productSelect.options).some(opt => opt.value === currentSelection);
                if (optionExists) {
                    productSelect.value = currentSelection;
                } else {
                    // Clear selection if product not in new list
                    state.selectedProduct = null;
                    productSelect.value = ''; // Reset dropdown to placeholder
                    this.onSelectionChange();
                }
            }
        });
        
        // Time range toggle
        document.getElementById('btn-toggle-timerange').addEventListener('click', () => {
            const container = document.getElementById('timerange-container');
            const btn = document.getElementById('btn-toggle-timerange');
            // Check if hidden by inline style or initial CSS
            const isHidden = container.style.display === 'none' || 
                           window.getComputedStyle(container).display === 'none';
            
            if (isHidden) {
                container.style.display = 'block';
                btn.textContent = 'Hide Time Range ▲';
            } else {
                container.style.display = 'none';
                btn.textContent = 'Select Time Range ▼';
            }
        });
        
        // Time range preset buttons – anchor to the most recent available COG and start live mode
        document.querySelectorAll('.preset-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const hours = parseInt(e.target.dataset.hours);
                this.loadLastNHours(hours);
            });
        });
        
        // Time range inputs change
        document.getElementById('start-date').addEventListener('change', () => {
            this.onTimeRangeChange();
        });
        
        document.getElementById('end-date').addEventListener('change', () => {
            this.onTimeRangeChange();
        });
        
        // Load latest button
        document.getElementById('btn-load-latest').addEventListener('click', () => {
            this.stopLiveRefresh();
            this.loadLatestCogs();
        });
        
        // Load time range button
        document.getElementById('btn-load-timerange').addEventListener('click', () => {
            this.stopLiveRefresh();
            this.loadTimeRangeCogs();
        });
        
        // Navigation buttons
        document.getElementById('btn-prev').addEventListener('click', () => {
            state.animator.previous();
        });
        
        document.getElementById('btn-next').addEventListener('click', () => {
            state.animator.next();
        });
        
        document.getElementById('btn-latest').addEventListener('click', () => {
            state.animator.goToLatest();
        });
        
        // Animation controls
        document.getElementById('btn-play-pause').addEventListener('click', () => {
            state.animator.toggle();
            state.ui.updatePlayButton(state.animator.getIsPlaying());
        });
        
        document.getElementById('btn-speed').addEventListener('click', () => {
            this.cycleSpeed();
        });
        
        document.getElementById('animation-slider').addEventListener('input', (e) => {
            state.animator.goToFrame(parseInt(e.target.value));
        });
        
        // Opacity control
        document.getElementById('opacity-slider').addEventListener('input', (e) => {
            const opacity = parseFloat(e.target.value);
            state.mapManager.setOpacity(opacity);
            state.ui.updateOpacityDisplay(opacity);
        });

        // Colormap selection
        document.getElementById('colormap-select').addEventListener('change', (e) => {
            state.selectedColormap = e.target.value || null;
            this.applyColormapChange();
        });

        // vmin/vmax apply button
        document.getElementById('btn-apply-range').addEventListener('click', () => {
            const vminVal = parseFloat(document.getElementById('vmin-input').value);
            const vmaxVal = parseFloat(document.getElementById('vmax-input').value);
            if (!isNaN(vminVal) && !isNaN(vmaxVal) && isFinite(vminVal) && isFinite(vmaxVal) && vminVal < vmaxVal) {
                state.currentVmin = vminVal;
                state.currentVmax = vmaxVal;
                this.applyColormapChange();
            } else {
                state.ui.setStatus('Invalid range: min must be less than max', 'error');
            }
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ignore if user is typing in an input field
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') {
                return;
            }
            
            switch(e.key) {
                case ' ': // Space - play/pause
                    e.preventDefault();
                    if (state.animator.getFrameCount() > 1) {
                        state.animator.toggle();
                        state.ui.updatePlayButton(state.animator.getIsPlaying());
                    }
                    break;
                    
                case 'ArrowLeft': // Previous frame
                    e.preventDefault();
                    state.animator.previous();
                    break;
                    
                case 'ArrowRight': // Next frame
                    e.preventDefault();
                    state.animator.next();
                    break;
                    
                case 'Home': // Go to latest
                    e.preventDefault();
                    state.animator.goToLatest();
                    break;
                    
                case 'l': // Load latest
                case 'L':
                    e.preventDefault();
                    const loadBtn = document.getElementById('btn-load-latest');
                    if (loadBtn && !loadBtn.disabled) {
                        this.loadLatestCogs();
                    }
                    break;
                    
                case 's': // Cycle speed
                case 'S':
                    e.preventDefault();
                    if (state.animator.getFrameCount() > 1) {
                        this.cycleSpeed();
                    }
                    break;
            }
        });
    },
    
    /**
     * Handle radar selection changes
     */
    onRadarSelectionChange() {
        const prevRadars = [...state.selectedRadars];
        state.selectedRadars = state.ui.getSelectedRadars();
        
        // Enable/disable load latest button
        const canLoad = state.selectedRadars.length > 0 && state.selectedProduct;
        state.ui.enableLoadLatestButton(canLoad);
        
        // Also update time range button state
        this.onTimeRangeChange();

        // When a time-range animation is already running, apply changes incrementally
        // so existing tile cache is preserved and playback is not interrupted.
        // Skip if the initial batch preload is still in flight to avoid index mismatches.
        if (
            state.animationMode === 'timerange' &&
            state.cogs && state.cogs.length > 0 &&
            !state.mapManager._preloadInProgress
        ) {
            const added   = state.selectedRadars.filter(r => !prevRadars.includes(r));
            const removed = prevRadars.filter(r => !state.selectedRadars.includes(r));

            // Removals are synchronous – process all before any async additions
            removed.forEach(radarCode => this.removeRadarIncremental(radarCode));

            // Additions are async – chain them sequentially to keep state consistent
            if (added.length > 0) {
                added.reduce(
                    (p, radarCode) => p.then(() => this.addRadarIncremental(radarCode)),
                    Promise.resolve()
                );
            }
        }
    },
    
    /**
     * Handle time range input changes
     */
    onTimeRangeChange() {
        const timeRange = state.ui.getTimeRangeValues();
        const hasValidRange = timeRange.start && timeRange.end && timeRange.start < timeRange.end;
        const canLoad = state.selectedRadars.length > 0 && state.selectedProduct && hasValidRange;
        state.ui.enableLoadTimeRangeButton(canLoad);
    },
    
    /**
     * Handle radar/product selection change.
     *
     * When the user changes the product (field) while a time-range animation is
     * already loaded, we automatically reload with the new product so the movie
     * clip continues without requiring a manual button press.
     */
    async onSelectionChange() {
        // Stop any live refresh whenever the user changes their selection
        this.stopLiveRefresh();

        // If in time-range mode and product is valid, reload seamlessly
        if (state.animationMode === 'timerange' && state.selectedProduct) {
            await this.loadColormapOptions();
            await this.loadTimeRangeCogs();
            return;
        }

        // Otherwise clear current display (both latest-mode layers and animation cache)
        state.mapManager.clearCachedFrames();
        state.mapManager.clearRadarLayer();
        state.ui.setTimeDisplay(null);
        state.legend.clear();
        state.cogs = [];
        state.animator.stop();
        state.ui.updatePlayButton(false);
        state.animator.setFrames([]);
        state.hasZoomedToBounds = false;
        state.animationMode = null;
        
        // Update load latest button state
        this.onRadarSelectionChange();
        
        // Load colormap options for new product
        await this.loadColormapOptions();

        // For now, disable animation until user loads data
        state.ui.enableNavButtons(false);
        state.ui.enableAnimationControls(false);
    },

    /**
     * Incrementally add a radar to a running time-range animation.
     *
     * Fetches only the new radar's COGs for the current time window, merges
     * them into the existing grouped frames, creates tile layers for the new
     * radar, and adjusts the current frame index if new frames were inserted
     * before it.  Playback is never stopped.
     *
     * @param {string} radarCode - Radar to add (e.g. 'rma1')
     */
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
                    `⚠️ No data for ${radarCode.toUpperCase()} in current time range`,
                    'error'
                );
                return;
            }

            const tileParams = this.getTileParams();

            // Rebuild the bucket→index map AFTER the await so concurrent updates are safe
            const existingBucketToIdx = new Map();
            state.cogs.forEach((frame, idx) => {
                existingBucketToIdx.set(getCogBucketKey(frame.timestamp), idx);
            });

            // Deduplicate new COGs by bucket key (keep first/newest per bucket).
            // getCogsForTimeRange returns COGs newest-first so Map insertion order is
            // newest-first; reversing the entries converts to oldest-first cheaply.
            const newBucketToCog = new Map();
            newCogs.forEach(cog => {
                const key = getCogBucketKey(cog.observation_time);
                if (!newBucketToCog.has(key)) newBucketToCog.set(key, cog);
            });
            const sortedNewBuckets = Array.from(newBucketToCog.entries()).reverse(); // oldest-first

            // Pass 1 — merge into existing frames (no array index changes)
            const toInsert = []; // [{key, cog}] buckets that need a new frame
            for (const [key, cog] of sortedNewBuckets) {
                if (existingBucketToIdx.has(key)) {
                    const frameIdx = existingBucketToIdx.get(key);
                    state.cogs[frameIdx].cogsByRadar[radarCode] = cog;
                    // Ensure the layer map exists (batch preload may still be filling slots)
                    if (!state.mapManager.cachedFrameLayers[frameIdx]) {
                        state.mapManager.cachedFrameLayers[frameIdx] = {};
                    }
                    state.mapManager.cachedFrameLayers[frameIdx][radarCode] =
                        state.mapManager.createHiddenTileLayer(cog.id, tileParams);
                } else {
                    toInsert.push({ key, cog });
                }
            }

            // Pass 2 — insert brand-new frames using binary search so earlier insertions
            // do not corrupt the position of later ones.  toInsert is already oldest-first.
            const currentIndex = state.animator.getCurrentIndex();
            let indexAdjustment = 0;

            for (const { key, cog } of toInsert) {
                // Binary search for the correct sorted insertion position
                let lo = 0, hi = state.cogs.length;
                while (lo < hi) {
                    const mid = (lo + hi) >>> 1;
                    if (getCogBucketKey(state.cogs[mid].timestamp) < key) lo = mid + 1;
                    else hi = mid;
                }
                const insertIdx = lo;

                const newFrame    = { timestamp: cog.observation_time, cogsByRadar: { [radarCode]: cog } };
                const newLayerMap = { [radarCode]: state.mapManager.createHiddenTileLayer(cog.id, tileParams) };

                state.cogs.splice(insertIdx, 0, newFrame);
                state.mapManager.cachedFrameLayers.splice(insertIdx, 0, newLayerMap);

                // Adjust the map manager's internal visible-frame pointer
                if (
                    state.mapManager.currentCachedFrameIndex >= 0 &&
                    insertIdx <= state.mapManager.currentCachedFrameIndex
                ) {
                    state.mapManager.currentCachedFrameIndex++;
                }

                // Track how many new frames landed before/at the current position
                if (insertIdx <= currentIndex + indexAdjustment) {
                    indexAdjustment++;
                }
            }

            const newCurrentIndex = Math.min(currentIndex + indexAdjustment, state.cogs.length - 1);

            // Update animator frames and index without interrupting playback
            state.animator.updateFrames(state.cogs, newCurrentIndex);

            // Re-show the current frame so the newly added radar appears immediately
            // if it belongs to the currently visible frame
            state.mapManager.showCachedFrame(newCurrentIndex);

            state.ui.updateFrameCounter(newCurrentIndex, state.cogs.length);
            state.ui.updateAnimationSlider(newCurrentIndex, state.cogs.length);
            state.ui.setStatus(`✓ Added ${radarCode.toUpperCase()} — ${state.cogs.length} frames`, 'success');

        } catch (err) {
            console.error('addRadarIncremental error:', err);
            state.ui.setStatus(`Error adding ${radarCode.toUpperCase()}: ${err.message}`, 'error');
        }
    },

    /**
     * Incrementally remove a radar from a running time-range animation.
     *
     * Removes only the tile layers belonging to the radar from every frame in
     * cachedFrameLayers.  Frames that become empty (no radars left) are
     * discarded.  The current frame index is adjusted to compensate for any
     * removed frames.  Playback is never stopped.
     *
     * @param {string} radarCode - Radar to remove (e.g. 'rma1')
     */
    removeRadarIncremental(radarCode) {
        if (state.animationMode !== 'timerange' || !state.cogs || state.cogs.length === 0) return;

        const originalIndex = state.animator.getCurrentIndex();

        // Temporarily hide the currently visible frame to avoid visual glitches
        // while we restructure the layer arrays.
        const currentLayerMap = state.mapManager.cachedFrameLayers[originalIndex];
        if (currentLayerMap) {
            Object.values(currentLayerMap).forEach(layer => layer.setOpacity(0));
        }

        const newFrames      = [];
        const newLayerFrames = [];
        let removedBeforeOriginal = 0;
        let originalFrameRemoved  = false;

        state.cogs.forEach((frame, i) => {
            const layerMap = state.mapManager.cachedFrameLayers[i];

            // Remove this radar's tile layer from the map
            if (layerMap) {
                const layer = layerMap[radarCode];
                if (layer && state.mapManager.map.hasLayer(layer)) {
                    state.mapManager.map.removeLayer(layer);
                }
                delete layerMap[radarCode];
            }

            // Remove from the frame's data object
            delete frame.cogsByRadar[radarCode];

            // Discard the frame entirely if it is now empty
            if (Object.keys(frame.cogsByRadar).length === 0) {
                if (i < originalIndex)  removedBeforeOriginal++;
                if (i === originalIndex) originalFrameRemoved = true;
                return;
            }

            newFrames.push(frame);
            newLayerFrames.push(layerMap || null);
        });

        // Replace the arrays with the compacted versions
        state.mapManager.cachedFrameLayers = newLayerFrames;
        state.cogs = newFrames;

        if (newFrames.length === 0) {
            // All frames were emptied — fall back to an idle state
            state.mapManager.currentCachedFrameIndex = -1;
            state.animator.setFrames([]);
            state.animationMode = null;
            state.ui.enableAnimationControls(false);
            state.ui.enableNavButtons(false);
            state.ui.setStatus(`All frames empty after removing ${radarCode.toUpperCase()}`, 'error');
            return;
        }

        // Compute the new visible-frame index.
        // By construction removedBeforeOriginal <= originalIndex so the subtraction >= 0.
        let newCurrentIndex = originalIndex - removedBeforeOriginal;
        if (originalFrameRemoved) {
            // The active frame was removed — stay at the same numeric position (clamped to array end)
            newCurrentIndex = Math.min(newCurrentIndex, newFrames.length - 1);
        }

        // Update the map manager's pointer to account for the compacted array
        if (originalFrameRemoved) {
            state.mapManager.currentCachedFrameIndex = -1; // will be set by showCachedFrame
        } else {
            state.mapManager.currentCachedFrameIndex = newCurrentIndex;
        }

        // Update animator frames and index without interrupting playback
        state.animator.updateFrames(newFrames, newCurrentIndex);

        // Show the (possibly new) current frame
        state.mapManager.showCachedFrame(newCurrentIndex);

        state.ui.updateFrameCounter(newCurrentIndex, newFrames.length);
        state.ui.updateAnimationSlider(newCurrentIndex, newFrames.length);
        state.ui.setTimeDisplay(newFrames[newCurrentIndex].timestamp);
        state.ui.setStatus(`✓ Removed ${radarCode.toUpperCase()} from animation`, 'success');
    },

    /**
     * Load latest COGs for selected radars and product
     */
    async loadLatestCogs() {
        if (state.selectedRadars.length === 0 || !state.selectedProduct) {
            state.ui.setStatus('Select radar(s) and product', 'error');
            return;
        }
        
        state.ui.setStatus('Loading latest images...', 'loading');
        
        // Stop any running animation before reloading
        state.animator.stop();
        state.ui.updatePlayButton(false);
        
        try {
            // Get latest COGs for all selected radars
            const latestCogs = await api.getLatestCogsForRadars(state.selectedRadars, state.selectedProduct);
            
            // Check which radars have no data
            const radarCodesWithData = latestCogs.map(item => item.radarCode);
            const radarCodesWithoutData = state.selectedRadars.filter(code => !radarCodesWithData.includes(code));
            
            if (latestCogs.length === 0) {
                const radarList = state.selectedRadars.join(', ').toUpperCase();
                const productName = state.products.find(p => p.product_key === state.selectedProduct)?.product_title || state.selectedProduct;
                state.ui.setStatus(
                    `⚠️ No data available for ${radarList} with product "${productName}". Try a different product or radar.`,
                    'error'
                );
                return;
            }
            
            // Show warning if some radars don't have data
            if (radarCodesWithoutData.length > 0) {
                const unavailableRadars = radarCodesWithoutData.map(code => code.toUpperCase()).join(', ');
                console.warn(`No data available for: ${unavailableRadars}`);
            }
            
            // Load colormap using new API — pass current colormap override so colors match tiles
            let colormap = null;
            try {
                colormap = await api.getColormapInfo(state.selectedProduct, state.selectedColormap);
            } catch (error) {
                console.warn('Failed to load colormap:', error);
                // Fallback to old API if new one fails
                try {
                    colormap = await api.getColormap(state.selectedProduct);
                } catch (fallbackError) {
                    console.warn('Failed to load fallback colormap:', fallbackError);
                }
            }
            
            // Clear existing layers (both latest-mode and any previous animation cache)
            state.mapManager.clearCachedFrames();
            state.mapManager.clearRadarLayer();
            state.hasZoomedToBounds = false;
            state.animationMode = 'latest';
            
            // Track first radar for time display
            let firstRadarTime = null;
            
            // Display latest COG for each radar
            latestCogs.forEach(({ radarCode, cog }) => {
                if (!cog) return;
                
                // Get radar bounds for zoom (only for first radar)
                let bounds = null;
                if (!state.hasZoomedToBounds) {
                    const radar = state.radars.find(r => r.code === radarCode);
                    bounds = radar?.extent || null;
                    state.hasZoomedToBounds = true;
                }
                
                // Display on map with colormap/range params
                state.mapManager.setRadarLayer(radarCode, cog.id, bounds, null, this.getTileParams());
                
                // Store first radar's time for display
                if (!firstRadarTime) {
                    firstRadarTime = cog.observation_time;
                }
            });
            
            // Update time display with first radar's time
            if (firstRadarTime) {
                state.ui.setTimeDisplay(firstRadarTime);
            }
            
            // Render legend if available — honour user-set vmin/vmax overrides
            if (colormap) {
                if (state.currentVmin !== null) colormap.vmin = state.currentVmin;
                if (state.currentVmax !== null) colormap.vmax = state.currentVmax;
                state.legend.render(colormap);
                state.legend.show();
            }
            
            // Build success message with radar names
            const loadedRadars = latestCogs.map(item => item.radarCode.toUpperCase()).join(', ');
            const radarText = latestCogs.length === 1 ? 'radar' : 'radars';
            let successMsg = `✓ Showing latest from ${latestCogs.length} ${radarText}: ${loadedRadars}`;
            
            // Add warning about missing radars if applicable
            if (radarCodesWithoutData.length > 0) {
                const unavailableRadars = radarCodesWithoutData.map(code => code.toUpperCase()).join(', ');
                successMsg += ` (${unavailableRadars} has no data)`;
            }
            
            state.ui.setStatus(successMsg, 'success');
            
        } catch (error) {
            console.error('Load error:', error);
            state.ui.setStatus(`Error: ${error.message}`, 'error');
        }
    },
    
    /**
     * Load COGs for selected radars and product within a time range.
     *
     * COGs from all radars are grouped into per-timestamp animation frames so
     * every radar is rendered simultaneously.  All tile layers are created
     * upfront (opacity 0) so the browser pre-fetches and caches them; the
     * animation then just toggles opacity – no network round-trips per frame.
     */
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
            // Fetch flat COG list for all selected radars
            const cogs = await api.getCogsForTimeRange(
                state.selectedRadars,
                state.selectedProduct,
                timeRange.start,
                timeRange.end,
                100
            );
            
            if (cogs.length === 0) {
                const radarList = state.selectedRadars.join(', ').toUpperCase();
                const productName = state.products.find(p => p.product_key === state.selectedProduct)?.product_title || state.selectedProduct;
                state.ui.setStatus(
                    `⚠️ No data available for ${radarList} with product "${productName}" in selected time range.`,
                    'error'
                );
                return;
            }

            // Group COGs from all radars into per-timestamp frames
            const groupedFrames = groupCogsByTimestamp(cogs);

            // Load colormap — pass current colormap override so colors match tiles
            let colormap = null;
            try {
                colormap = await api.getColormapInfo(state.selectedProduct, state.selectedColormap);
            } catch (error) {
                console.warn('Failed to load colormap:', error);
                try {
                    colormap = await api.getColormap(state.selectedProduct);
                } catch (fallbackError) {
                    console.warn('Failed to load fallback colormap:', fallbackError);
                }
            }

            // Clear any previous layers / animation
            state.mapManager.clearCachedFrames();
            state.mapManager.clearRadarLayer();
            state.animator.stop();
            state.ui.updatePlayButton(false);
            state.hasZoomedToBounds = false;
            state.animationMode = 'timerange';

            // Pre-create tile layers in batches so tiles start loading immediately
            // without a burst of requests.  A progress callback updates the status bar.
            const totalLayers = groupedFrames.reduce(
                (sum, f) => sum + Object.keys(f.cogsByRadar).length, 0
            );
            let loadedLayers = 0;
            state.mapManager.preloadFrames(groupedFrames, () => {
                loadedLayers++;
                if (loadedLayers < totalLayers) {
                    state.ui.setStatus(
                        `Caching tiles… (${loadedLayers} / ${totalLayers} layers ready)`,
                        'loading'
                    );
                } else {
                    state.ui.setStatus('All frames cached – ready to play ✓', 'success');
                }
            }, this.getTileParams());

            // Zoom to bounds using any radar from the loaded frames
            const anyFrame = groupedFrames[0];
            const anyRadarCode = Object.keys(anyFrame.cogsByRadar)[0];
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

            // Store grouped frames and hand off to animator.
            // Start at frame 0 (oldest) so animation plays forward in time.
            state.cogs = groupedFrames;
            state.animator.setFrames(groupedFrames);
            state.animator.goToFrame(0); // oldest frame first; fires onFrameChange(0, …)

            // Render legend — honour user-set vmin/vmax overrides
            if (colormap) {
                if (state.currentVmin !== null) colormap.vmin = state.currentVmin;
                if (state.currentVmax !== null) colormap.vmax = state.currentVmax;
                state.legend.render(colormap);
                state.legend.show();
            }

            // Enable animation controls
            if (groupedFrames.length > 1) {
                state.ui.enableAnimationControls(true);
                state.ui.enableNavButtons(true);
                state.ui.updateFrameCounter(0, groupedFrames.length);
                state.ui.updateAnimationSlider(0, groupedFrames.length);
            }

            // Build success message (extract radar codes from grouped frames)
            const radarCodes = [...new Set(
                groupedFrames.flatMap(f => Object.keys(f.cogsByRadar))
            )];
            const loadedRadars = radarCodes.map(code => code.toUpperCase()).join(', ');
            const radarText = radarCodes.length === 1 ? 'radar' : 'radars';

            // In live mode, warn when the actual data span is shorter than requested
            let liveNote = '';
            if (state.liveHours !== null && groupedFrames.length > 0) {
                const oldestFrameTime = new Date(groupedFrames[0].timestamp);
                const newestFrameTime = new Date(groupedFrames[groupedFrames.length - 1].timestamp);
                const requestedStart = state.ui.getTimeRangeValues().start;
                if (requestedStart) {
                    const gapHours = (oldestFrameTime - requestedStart) / MS_PER_HOUR;
                    if (gapHours > 0.5) {
                        const availableHours = ((newestFrameTime - oldestFrameTime) / MS_PER_HOUR).toFixed(1);
                        liveNote = ` ⚠️ Only ${availableHours}h of data available (${state.liveHours}h requested)`;
                    }
                }
            }

            state.ui.setStatus(
                `✓ Loaded ${groupedFrames.length} frames from ${radarCodes.length} ${radarText}: ${loadedRadars} — tiles caching in background${liveNote}`,
                'success'
            );

        } catch (error) {
            console.error('Load time range error:', error);
            state.ui.setStatus(`Error: ${error.message}`, 'error');
        }
    },
    
    /**
     * Load the last N hours of data anchored to the most recent available COG.
     *
     * Unlike the old preset behaviour (which anchored to wall-clock "now"), this
     * finds the newest COG in the database for the current product/radar
     * selection and uses that as the end of the window.  After a successful
     * load it starts a 5-minute polling interval that shifts the window forward
     * whenever newer COGs appear.
     *
     * @param {number} hours - Number of hours to look back from the latest COG.
     */
    async loadLastNHours(hours) {
        if (state.selectedRadars.length === 0 || !state.selectedProduct) {
            state.ui.setStatus('Select radar(s) and product first', 'error');
            return;
        }

        this.stopLiveRefresh();
        state.ui.setStatus('Finding latest data…', 'loading');

        // Open the time-range panel so the user can see the loaded window
        const trContainer = document.getElementById('timerange-container');
        const trToggleBtn = document.getElementById('btn-toggle-timerange');
        if (trContainer) {
            const isHidden = trContainer.style.display === 'none' ||
                window.getComputedStyle(trContainer).display === 'none';
            if (isHidden) {
                trContainer.style.display = 'block';
                if (trToggleBtn) trToggleBtn.textContent = 'Hide Time Range ▲';
            }
        }

        try {
            // Determine the most recent COG time across all selected radars
            const latestItems = await api.getLatestCogsForRadars(
                state.selectedRadars, state.selectedProduct
            );

            if (latestItems.length === 0) {
                const radarList = state.selectedRadars.join(', ').toUpperCase();
                const productName = state.products.find(
                    p => p.product_key === state.selectedProduct
                )?.product_title || state.selectedProduct;
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

            // Populate time-range inputs with the computed window
            state.ui.setTimeRangeValues(startTime, endTime);
            this.onTimeRangeChange();

            // Mark live mode before calling loadTimeRangeCogs so it can detect it
            state.liveHours = hours;

            await this.loadTimeRangeCogs();

            // Start periodic refresh only if the load succeeded (liveHours is still set)
            if (state.liveHours !== null) {
                this.startLiveRefresh(hours);
            }
        } catch (err) {
            console.error('loadLastNHours error:', err);
            state.ui.setStatus(`Error: ${err.message}`, 'error');
            state.liveHours = null;
        }
    },

    /**
     * Start a 5-minute polling interval that refreshes the live N-hours window
     * whenever newer COGs appear in the database.
     *
     * @param {number} hours - N hours to maintain.
     */
    startLiveRefresh(hours) {
        this.stopLiveRefresh();
        state.liveHours = hours;
        state.liveRefreshInterval = setInterval(() => {
            this.refreshLiveWindow();
        }, LIVE_REFRESH_INTERVAL_MS);
        console.log(`Live refresh started: checking every 5 min for new COGs (${hours}h window)`);
    },

    /**
     * Cancel the live polling interval and clear live-mode state.
     */
    stopLiveRefresh() {
        if (state.liveRefreshInterval !== null) {
            clearInterval(state.liveRefreshInterval);
            state.liveRefreshInterval = null;
        }
        state.liveHours = null;
    },

    /**
     * Called every 5 minutes while live mode is active.
     *
     * Checks whether new COGs have been published beyond the current window
     * end.  If so:
     *   – Fetches only the new COGs (current end → new end), not the full window
     *   – Appends new frames to the end of the animation
     *   – Expires frames that have fallen before the new start time
     *   – Adjusts the current frame index to account for removed frames
     *   – Does NOT stop or reset the animation
     */
    async refreshLiveWindow() {
        if (!state.liveHours || !state.selectedRadars.length || !state.selectedProduct) return;
        if (state.animationMode !== 'timerange' || !state.cogs || state.cogs.length === 0) return;

        try {
            const latestItems = await api.getLatestCogsForRadars(
                state.selectedRadars, state.selectedProduct
            );
            if (!latestItems.length) return;

            const newEndTime = latestItems.reduce((max, { cog }) => {
                const t = new Date(cog.observation_time);
                return t > max ? t : max;
            }, new Date(0));

            // Only shift the window when genuinely new data has arrived
            const currentRange = state.ui.getTimeRangeValues();
            if (currentRange.end && newEndTime <= currentRange.end) {
                console.log('Live refresh: no new COGs yet, window unchanged');
                return;
            }

            console.log('New COGs detected, incrementally refreshing live window…');
            const hours        = state.liveHours;
            const newStartTime = new Date(newEndTime.getTime() - hours * MS_PER_HOUR);
            const currentEndTime = currentRange.end;

            // Fetch only the new portion of the time window
            const newCogs = await api.getCogsForTimeRange(
                state.selectedRadars, state.selectedProduct,
                currentEndTime, newEndTime, 100
            );

            // Group new COGs into frames and remove duplicates already in the animation
            const rawNewFrames = groupCogsByTimestamp(newCogs);
            const existingBucketKeys = new Set(state.cogs.map(f => getCogBucketKey(f.timestamp)));
            const newGroupedFrames   = rawNewFrames.filter(
                f => !existingBucketKeys.has(getCogBucketKey(f.timestamp))
            );

            // Determine how many existing frames have expired (before newStartTime).
            // Use a pre-computed numeric timestamp to avoid one Date object per frame.
            const newStartMs   = newStartTime.getTime();
            const expiredCount = state.cogs.filter(
                f => new Date(f.timestamp).getTime() < newStartMs
            ).length;

            const currentIndex = state.animator.getCurrentIndex();
            const tileParams   = this.getTileParams();

            // Build tile layers for new frames before modifying shared state
            const newLayerFrames = newGroupedFrames.map(frame => {
                const layerMap = {};
                Object.entries(frame.cogsByRadar).forEach(([radarCode, cog]) => {
                    layerMap[radarCode] = state.mapManager.createHiddenTileLayer(cog.id, tileParams);
                });
                return layerMap;
            });

            // Remove expired frames from the beginning
            let indexAfterExpiry = currentIndex;
            if (expiredCount > 0) {
                // Clean up tile layers for expired frames
                for (let i = 0; i < expiredCount; i++) {
                    const layerMap = state.mapManager.cachedFrameLayers[i];
                    if (layerMap) {
                        Object.values(layerMap).forEach(layer => {
                            if (state.mapManager.map.hasLayer(layer)) {
                                state.mapManager.map.removeLayer(layer);
                            }
                        });
                    }
                }
                state.cogs.splice(0, expiredCount);
                state.mapManager.cachedFrameLayers.splice(0, expiredCount);

                // Shift the map manager's internal visible-frame pointer
                const prevCachedIdx = state.mapManager.currentCachedFrameIndex;
                if (prevCachedIdx >= 0) {
                    state.mapManager.currentCachedFrameIndex =
                        prevCachedIdx >= expiredCount ? prevCachedIdx - expiredCount : -1;
                }

                indexAfterExpiry = Math.max(0, currentIndex - expiredCount);
            }

            // Append new frames to the end
            if (newGroupedFrames.length > 0) {
                state.cogs.push(...newGroupedFrames);
                state.mapManager.cachedFrameLayers.push(...newLayerFrames);
            }

            // Update time-range UI to reflect the new window
            state.ui.setTimeRangeValues(newStartTime, newEndTime);
            this.onTimeRangeChange();
            state.liveHours = hours;

            const newLength       = state.cogs.length;
            const newCurrentIndex = Math.min(indexAfterExpiry, newLength - 1);

            // Update animator without resetting playback
            state.animator.updateFrames(state.cogs, newCurrentIndex);

            // If the visible cached frame was in the expired range, show the new position
            if (state.mapManager.currentCachedFrameIndex < 0) {
                state.mapManager.showCachedFrame(newCurrentIndex);
            }

            state.ui.updateFrameCounter(newCurrentIndex, newLength);
            state.ui.updateAnimationSlider(newCurrentIndex, newLength);

            console.log(
                `Live refresh: +${newGroupedFrames.length} new frames, ` +
                `-${expiredCount} expired, ${newLength} total`
            );
        } catch (err) {
            console.warn('Live refresh error:', err);
        }
    },

    /**
     * Handle frame change from animator.
     *
     * For animation mode, switches the visible cached frame (all radars for
     * that timestamp are shown simultaneously).  Works for both grouped frames
     * (animation mode) and single-COG frames (legacy).
     */
    onFrameChange(index, frame) {
        if (!frame) return;

        // Animation mode: grouped frame – use pre-cached layers
        if (frame.cogsByRadar) {
            state.mapManager.showCachedFrame(index);
            state.ui.setTimeDisplay(frame.timestamp);
            state.ui.updateFrameCounter(index, state.animator.getFrameCount());
            state.ui.updateAnimationSlider(index, state.animator.getFrameCount());
            return;
        }

        // Legacy / single-COG fallback (latest mode)
        let bounds = null;
        if (!state.hasZoomedToBounds) {
            const radar = state.radars.find(r => r.code === frame.radar_code);
            bounds = radar?.extent || null;
            state.hasZoomedToBounds = true;
        }

        state.mapManager.clearRadarLayer();
        state.mapManager.setRadarLayer(frame.radar_code, frame.id, bounds, null, this.getTileParams());

        state.ui.setTimeDisplay(frame.observation_time);
        state.ui.updateFrameCounter(index, state.animator.getFrameCount());
        state.ui.updateAnimationSlider(index, state.animator.getFrameCount());
    },
    
    /**
     * Load available colormap options for the selected product and show
     * the colormap / range controls.
     */
    async loadColormapOptions() {
        if (!state.selectedProduct) {
            document.getElementById('colormap-group').style.display = 'none';
            document.getElementById('range-group').style.display = 'none';
            return;
        }

        try {
            const info = await api.getColormapInfo(state.selectedProduct);

            // Populate colormap dropdown
            const select = document.getElementById('colormap-select');
            select.innerHTML = '<option value="">Default</option>';
            const options = info.available_colormaps || [];
            options.forEach(cmap => {
                const opt = document.createElement('option');
                opt.value = cmap;
                opt.textContent = cmap;
                if (cmap === info.colormap) opt.selected = true;
                select.appendChild(opt);
            });
            // Restore previous selection if still valid
            if (state.selectedColormap && options.includes(state.selectedColormap)) {
                select.value = state.selectedColormap;
            } else {
                state.selectedColormap = null;
                select.value = '';
            }

            // Set vmin/vmax inputs to product defaults (only when not already overridden)
            if (state.currentVmin === null) {
                document.getElementById('vmin-input').value = info.vmin ?? '';
            }
            if (state.currentVmax === null) {
                document.getElementById('vmax-input').value = info.vmax ?? '';
            }

            document.getElementById('colormap-group').style.display = 'block';
            document.getElementById('range-group').style.display = 'block';
        } catch (err) {
            console.warn('Failed to load colormap options:', err);
        }
    },

    /**
     * Re-apply the current colormap / range when the user changes the controls
     * while data is already loaded.
     *
     * In time-range mode the new tiles are preloaded in the background so the
     * current animation keeps playing until the swap is ready.
     */
    async applyColormapChange() {
        if (!state.animationMode) return;

        // In latest mode (single frame per radar) there is no animation cache
        // to preserve, so just reload normally.
        if (state.animationMode === 'latest') {
            await this.loadLatestCogs();
            return;
        }

        // In time-range mode, reuse the existing groupedFrames (same timestamps
        // and COG IDs) but regenerate tile URLs with the new colormap params.
        // Preload in the background so the current animation remains visible.
        if (!state.cogs || !state.cogs.length) {
            await this.loadTimeRangeCogs();
            return;
        }

        const groupedFrames = state.cogs;
        const tileParams = this.getTileParams();

        state.ui.showMapOverlay('Applying colormap\u2026');

        // Update legend immediately without waiting for tiles
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

        state.mapManager.preloadFramesBackground(
            groupedFrames,
            (loaded, total) => {
                state.ui.updateMapOverlay(`Applying colormap\u2026 ${loaded}\u00a0/\u00a0${total}`);
            },
            (pendingLayers) => {
                const prevIndex = state.animator.getCurrentIndex();
                const wasPlaying = state.animator.getIsPlaying();
                state.animator.stop();
                state.mapManager.commitPendingFrames(pendingLayers);
                // Show the frame that was active when the swap completes;
                // clamp in case any pending layer slots are null (edge case
                // where a batch was cancelled mid-flight before all frames
                // were allocated).
                const safeIndex = Math.min(
                    prevIndex,
                    pendingLayers.filter(Boolean).length - 1
                );
                if (safeIndex >= 0) {
                    state.mapManager.showCachedFrame(safeIndex);
                }
                state.ui.hideMapOverlay();
                state.ui.setStatus('Colormap updated \u2713', 'success');
                if (wasPlaying) state.animator.play();
            },
            tileParams
        );
    },

    /**
     * Return the current tile rendering parameters as a plain object.
     * Null values mean "use server defaults".
     */
    getTileParams() {
        return {
            cmap: state.selectedColormap || null,
            vmin: state.currentVmin,
            vmax: state.currentVmax,
        };
    },

    /**
     * Cycle through animation speeds
     */
    cycleSpeed() {
        const speeds = [0.5, 1.0, 2.0];
        const currentSpeed = state.animator.getSpeed();
        const currentIndex = speeds.indexOf(currentSpeed);
        const nextIndex = (currentIndex + 1) % speeds.length;
        const nextSpeed = speeds[nextIndex];
        
        state.animator.setSpeed(nextSpeed);
        state.ui.updateSpeedButton(nextSpeed);
    },
};

// =============================================================================
// START APPLICATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    app.init();
});