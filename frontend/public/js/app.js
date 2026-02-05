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
    selectedRadar: null,
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
        state.ui.populateSelect('radar-select', state.radars, 'code', 'title', 'Select radar...');
        
        // Load products
        state.products = await api.getProducts();
        state.ui.populateSelect('product-select', state.products, 'product_key', 'product_title', 'Select product...');
    },
    
    /**
     * Setup all event listeners
     */
    setupEventListeners() {
        // Radar/Product selection
        document.getElementById('radar-select').addEventListener('change', (e) => {
            state.selectedRadar = e.target.value;
            this.onSelectionChange();
        });
        
        document.getElementById('product-select').addEventListener('change', (e) => {
            state.selectedProduct = e.target.value;
            this.onSelectionChange();
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
     * Handle radar/product selection change
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
        
        // Need both radar and product selected
        if (!state.selectedRadar || !state.selectedProduct) {
            state.ui.enableNavButtons(false);
            state.ui.enableAnimationControls(false);
            return;
        }
        
        state.ui.setStatus('Loading data...', 'loading');
        
        try {
            // Load COGs and colormap in parallel
            let cogs, colormap;
            try {
                [cogs, colormap] = await Promise.all([
                    api.getCogs(state.selectedRadar, state.selectedProduct, 30),
                    api.getColormap(state.selectedProduct)
                ]);
            } catch (parallelError) {
                // If parallel load fails, try loading separately for better error messages
                try {
                    cogs = await api.getCogs(state.selectedRadar, state.selectedProduct, 30);
                } catch (cogError) {
                    throw new Error(`Failed to load radar images: ${cogError.message}`);
                }
                try {
                    colormap = await api.getColormap(state.selectedProduct);
                } catch (colormapError) {
                    console.warn('Failed to load colormap:', colormapError);
                    colormap = null; // Continue without colormap
                }
            }
            
            state.cogs = cogs;
            
            if (state.cogs.length === 0) {
                state.ui.setStatus('No data available', 'error');
                state.ui.enableNavButtons(false);
                state.ui.enableAnimationControls(false);
                return;
            }
            
            // Setup animation with COGs
            state.animator.setFrames(state.cogs);
            
            // Display the latest frame
            state.animator.goToLatest();
            
            // Render legend if colormap is available
            if (colormap) {
                state.legend.render(colormap);
                state.legend.show();
            }
            
            // Enable controls
            state.ui.enableNavButtons(true);
            state.ui.enableAnimationControls(true);
            state.ui.updatePlayButton(false);
            state.ui.updateSpeedButton(state.animator.getSpeed());
            
            state.ui.setStatus(`Loaded ${state.cogs.length} images`, 'success');
            
        } catch (error) {
            console.error('Load error:', error);
            state.ui.setStatus(`Error: ${error.message}`, 'error');
            state.ui.enableNavButtons(false);
            state.ui.enableAnimationControls(false);
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