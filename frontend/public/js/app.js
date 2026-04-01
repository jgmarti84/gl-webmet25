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
};

// =============================================================================
// HELPERS
// =============================================================================

/**
 * Group a flat list of COGs (from multiple radars) into animation frames.
 *
 * COGs that fall within the same `toleranceMinutes` window are merged into one
 * frame so all selected radars are rendered simultaneously at each step.
 *
 * @param {Array}  cogs             - Raw COG objects (sorted newest-first)
 * @param {number} toleranceMinutes - Bucket size in minutes (default 5)
 * @returns {Array} groupedFrames   - [{timestamp, cogsByRadar: {code: cog}}, …]
 *                                    sorted newest-first
 */
function groupCogsByTimestamp(cogs, toleranceMinutes = 5) {
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
        
        // Time range preset buttons
        document.querySelectorAll('.preset-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const hours = parseInt(e.target.dataset.hours);
                const endDate = new Date();
                const startDate = new Date(endDate.getTime() - hours * 60 * 60 * 1000);
                state.ui.setTimeRangeValues(startDate, endDate);
                this.onTimeRangeChange();
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
            this.loadLatestCogs();
        });
        
        // Load time range button
        document.getElementById('btn-load-timerange').addEventListener('click', () => {
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
        state.selectedRadars = state.ui.getSelectedRadars();
        
        // Enable/disable load latest button
        const canLoad = state.selectedRadars.length > 0 && state.selectedProduct;
        state.ui.enableLoadLatestButton(canLoad);
        
        // Also update time range button state
        this.onTimeRangeChange();
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
            state.ui.setStatus(
                `✓ Loaded ${groupedFrames.length} frames from ${radarCodes.length} ${radarText}: ${loadedRadars} — tiles caching in background`,
                'success'
            );

        } catch (error) {
            console.error('Load time range error:', error);
            state.ui.setStatus(`Error: ${error.message}`, 'error');
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
     */
    async applyColormapChange() {
        if (state.animationMode === 'latest') {
            await this.loadLatestCogs();
        } else if (state.animationMode === 'timerange') {
            await this.loadTimeRangeCogs();
        }
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