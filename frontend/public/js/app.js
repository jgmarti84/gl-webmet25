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
     * Load radars and products from API
     */
    async loadInitialData() {
        // Load radars
        state.radars = await api.getRadars();
        state.ui.populateRadarCheckboxes(state.radars);
        
        // Load products
        state.products = await api.getProducts();
        state.ui.populateSelect('product-select', state.products, 'product_key', 'product_title', 'Select product...');
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
        
        // Load latest button
        document.getElementById('btn-load-latest').addEventListener('click', () => {
            this.loadLatestCogs();
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
            const latestCogs = await api.getLatestCogs(state.selectedRadars, state.selectedProduct);
            
            if (latestCogs.length === 0) {
                state.ui.setStatus('No data available', 'error');
                return;
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
            
            // Display latest COG for each radar
            latestCogs.forEach(({ radarCode, cog }) => {
                if (!cog) return;
                
                // Get radar bounds for zoom
                let bounds = null;
                if (!state.hasZoomedToBounds) {
                    const radar = state.radars.find(r => r.code === radarCode);
                    bounds = radar?.extent || null;
                    state.hasZoomedToBounds = true;
                }
                
                // Display on map
                state.mapManager.setRadarLayer(radarCode, cog.id, bounds);
                
                // Update time display with first radar's time
                if (radarCode === latestCogs[0].radarCode) {
                    state.ui.setTimeDisplay(cog.observation_time);
                }
            });
            
            // Render legend if available
            if (colormap) {
                state.legend.render(colormap);
                state.legend.show();
            }
            
            const radarText = latestCogs.length === 1 ? 'radar' : 'radars';
            state.ui.setStatus(`Showing latest from ${latestCogs.length} ${radarText}`, 'success');
            
        } catch (error) {
            console.error('Load error:', error);
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
            const radar = state.radars.find(r => r.code === state.selectedRadar);
            bounds = radar?.extent || null;
            state.hasZoomedToBounds = true;
        }
        
        // Display frame on map
        state.mapManager.setRadarLayer(frame.id, bounds);
        
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