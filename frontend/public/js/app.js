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
    
    // Module instances
    mapManager: null,
    animator: null,
    ui: null,
    legend: null,
    
    // Flags
    hasZoomedToBounds: false,
};

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
            if (container.style.display === 'none') {
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
            if (container.style.display === 'none') {
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
     * Handle radar/product selection change (for animation mode)
     */
    async onSelectionChange() {
        // Clear current display
        state.mapManager.clearRadarLayer();
        state.ui.setTimeDisplay(null);
        state.legend.clear();
        state.cogs = [];
        state.animator.stop();
        state.animator.setFrames([]);
        state.hasZoomedToBounds = false;
        
        // Update load latest button state
        this.onRadarSelectionChange();
        
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
            
            // Load colormap
            let colormap = null;
            try {
                colormap = await api.getColormap(state.selectedProduct);
            } catch (error) {
                console.warn('Failed to load colormap:', error);
            }
            
            // Clear existing layers
            state.mapManager.clearRadarLayer();
            state.hasZoomedToBounds = false;
            
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
                
                // Display on map
                state.mapManager.setRadarLayer(radarCode, cog.id, bounds);
                
                // Store first radar's time for display
                if (!firstRadarTime) {
                    firstRadarTime = cog.observation_time;
                }
            });
            
            // Update time display with first radar's time
            if (firstRadarTime) {
                state.ui.setTimeDisplay(firstRadarTime);
            }
            
            // Render legend if available
            if (colormap) {
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
     * Load COGs for selected radars and product within a time range
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
            // Get COGs for time range
            const cogs = await api.getCogsForTimeRange(
                state.selectedRadars, 
                state.selectedProduct,
                timeRange.start,
                timeRange.end,
                100 // limit
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
            
            // Load colormap
            let colormap = null;
            try {
                colormap = await api.getColormap(state.selectedProduct);
            } catch (error) {
                console.warn('Failed to load colormap:', error);
            }
            
            // Store COGs
            state.cogs = cogs;
            state.hasZoomedToBounds = false;
            
            // Setup animation with frames
            state.animator.setFrames(cogs);
            state.animator.goToLatest(); // Start at most recent
            
            // Display first frame (most recent)
            if (cogs.length > 0) {
                const firstCog = cogs[0];
                
                // Get radar bounds for zoom
                let bounds = null;
                const radar = state.radars.find(r => r.code === firstCog.radar_code);
                bounds = radar?.extent || null;
                
                // Display on map
                state.mapManager.clearRadarLayer();
                state.mapManager.setRadarLayer(firstCog.radar_code, firstCog.id, bounds);
                state.hasZoomedToBounds = true;
                
                // Update time display
                state.ui.setTimeDisplay(firstCog.observation_time);
            }
            
            // Render legend if available
            if (colormap) {
                state.legend.render(colormap);
                state.legend.show();
            }
            
            // Enable animation controls
            if (cogs.length > 1) {
                state.ui.enableAnimationControls(true);
                state.ui.enableNavButtons(true);
                state.ui.updateFrameCounter(0, cogs.length);
                state.ui.updateAnimationSlider(0, cogs.length);
            }
            
            // Build success message
            const radarCodes = [...new Set(cogs.map(c => c.radar_code))];
            const loadedRadars = radarCodes.map(code => code.toUpperCase()).join(', ');
            const radarText = radarCodes.length === 1 ? 'radar' : 'radars';
            state.ui.setStatus(
                `✓ Loaded ${cogs.length} frames from ${radarCodes.length} ${radarText}: ${loadedRadars}`,
                'success'
            );
            
        } catch (error) {
            console.error('Load time range error:', error);
            state.ui.setStatus(`Error: ${error.message}`, 'error');
        }
    },
    
    /**
     * Handle frame change from animator
     */
    onFrameChange(index, frame) {
        if (!frame) return;
        
        // Get radar bounds for initial zoom (only first time)
        let bounds = null;
        if (!state.hasZoomedToBounds) {
            const radar = state.radars.find(r => r.code === frame.radar_code);
            bounds = radar?.extent || null;
            state.hasZoomedToBounds = true;
        }
        
        // Clear and display new frame on map
        state.mapManager.clearRadarLayer();
        state.mapManager.setRadarLayer(frame.radar_code, frame.id, bounds);
        
        // Update UI
        state.ui.setTimeDisplay(frame.observation_time);
        state.ui.updateFrameCounter(index, state.animator.getFrameCount());
        state.ui.updateAnimationSlider(index, state.animator.getFrameCount());
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