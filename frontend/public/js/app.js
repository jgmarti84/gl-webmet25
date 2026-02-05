/**
 * Radar Visualization App - Step 1 (Minimal Version)
 * 
 * Features:
 * - Display map with base layer
 * - Load radars from API
 * - Load products from API
 * - Display radar tiles on map
 * - Basic time navigation
 */

// =============================================================================
// CONFIGURATION
// =============================================================================

const CONFIG = {
    // API base URL - adjust if needed
    API_BASE: window.location.hostname === 'localhost' 
        ? 'http://localhost:8000/api/v1'
        : '/api/v1',
    
    // Default map center (Argentina)
    DEFAULT_CENTER: [-34.0, -64.0],
    DEFAULT_ZOOM: 5,
    
    // Radar layer opacity
    RADAR_OPACITY: 0.7,
};

// =============================================================================
// STATE
// =============================================================================

const state = {
    map: null,
    radarLayer: null,
    
    radars: [],
    products: [],
    cogs: [],
    
    selectedRadar: null,
    selectedProduct: null,
    currentCogIndex: 0,
};

// =============================================================================
// API FUNCTIONS
// =============================================================================

const api = {
    async get(endpoint) {
        const response = await fetch(`${CONFIG.API_BASE}${endpoint}`);
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        return response.json();
    },
    
    async getRadars() {
        const data = await this.get('/radars');
        return data.radars || [];
    },
    
    async getProducts() {
        const data = await this.get('/products');
        return data.products || [];
    },
    
    async getCogs(radarCode, productKey, limit = 20) {
        const params = new URLSearchParams({
            radar_code: radarCode,
            product_key: productKey,
            page_size: limit,
        });
        const data = await this.get(`/cogs?${params}`);
        return data.cogs || [];
    },
    
    async getLatestCog(radarCode, productKey) {
        return this.get(`/cogs/latest?radar_code=${radarCode}&product_key=${productKey}`);
    },
    
    getTileUrl(cogId) {
        return `${CONFIG.API_BASE}/tiles/${cogId}/{z}/{x}/{y}.png`;
    },
};

// =============================================================================
// UI FUNCTIONS
// =============================================================================

const ui = {
    setStatus(message, type = '') {
        const status = document.getElementById('status');
        status.textContent = message;
        status.className = `status ${type}`;
    },
    
    setTimeDisplay(dateString) {
        const display = document.getElementById('time-display');
        if (!dateString) {
            display.textContent = '--:--';
            return;
        }
        
        const date = new Date(dateString);
        display.textContent = date.toLocaleString('es-AR', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            timeZone: 'America/Argentina/Buenos_Aires',
        });
    },
    
    populateSelect(selectId, items, valueKey, labelKey, placeholder = 'Select...') {
        const select = document.getElementById(selectId);
        select.innerHTML = `<option value="">${placeholder}</option>`;
        
        items.forEach(item => {
            const option = document.createElement('option');
            option.value = item[valueKey];
            option.textContent = item[labelKey];
            select.appendChild(option);
        });
    },
    
    enableNavButtons(enabled) {
        document.getElementById('btn-prev').disabled = !enabled;
        document.getElementById('btn-next').disabled = !enabled;
        document.getElementById('btn-latest').disabled = !enabled;
    },
};

// =============================================================================
// MAP FUNCTIONS
// =============================================================================

const map = {
    init() {
        // Create map
        state.map = L.map('map').setView(CONFIG.DEFAULT_CENTER, CONFIG.DEFAULT_ZOOM);
        
        // Add base layer (OpenStreetMap)
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 18,
        }).addTo(state.map);
        
        // Alternative: Dark base layer (comment above and uncomment this)
        // L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        //     attribution: '© OpenStreetMap contributors, © CARTO',
        //     maxZoom: 18,
        // }).addTo(state.map);
    },
    
    setRadarLayer(cogId, bounds = null) {
        // Remove existing radar layer
        if (state.radarLayer) {
            state.map.removeLayer(state.radarLayer);
            state.radarLayer = null;
        }
        
        if (!cogId) return;
        
        // Add new radar layer
        const tileUrl = api.getTileUrl(cogId);
        
        state.radarLayer = L.tileLayer(tileUrl, {
            opacity: CONFIG.RADAR_OPACITY,
            maxZoom: 18,
            tms: false,
        }).addTo(state.map);
        
        // Fit to bounds if provided
        if (bounds) {
            state.map.fitBounds([
                [bounds.lat_min, bounds.lon_min],
                [bounds.lat_max, bounds.lon_max],
            ]);
        }
    },
    
    clearRadarLayer() {
        if (state.radarLayer) {
            state.map.removeLayer(state.radarLayer);
            state.radarLayer = null;
        }
    },
};

// =============================================================================
// MAIN APP LOGIC
// =============================================================================

const app = {
    async init() {
        ui.setStatus('Initializing...', 'loading');
        
        try {
            // Initialize map
            map.init();
            
            // Load radars
            state.radars = await api.getRadars();
            ui.populateSelect('radar-select', state.radars, 'code', 'title', 'Select radar...');
            
            // Load products
            state.products = await api.getProducts();
            ui.populateSelect('product-select', state.products, 'product_key', 'product_title', 'Select product...');
            
            // Setup event listeners
            this.setupEventListeners();
            
            // Disable nav buttons initially
            ui.enableNavButtons(false);
            
            ui.setStatus('Ready', 'success');
            
        } catch (error) {
            console.error('Init error:', error);
            ui.setStatus(`Error: ${error.message}`, 'error');
        }
    },
    
    setupEventListeners() {
        // Radar selection
        document.getElementById('radar-select').addEventListener('change', (e) => {
            state.selectedRadar = e.target.value;
            this.onSelectionChange();
        });
        
        // Product selection
        document.getElementById('product-select').addEventListener('change', (e) => {
            state.selectedProduct = e.target.value;
            this.onSelectionChange();
        });
        
        // Navigation buttons
        document.getElementById('btn-prev').addEventListener('click', () => this.navigate(-1));
        document.getElementById('btn-next').addEventListener('click', () => this.navigate(1));
        document.getElementById('btn-latest').addEventListener('click', () => this.goToLatest());
    },
    
    async onSelectionChange() {
        // Clear current display
        map.clearRadarLayer();
        ui.setTimeDisplay(null);
        state.cogs = [];
        state.currentCogIndex = 0;
        
        // Need both radar and product selected
        if (!state.selectedRadar || !state.selectedProduct) {
            ui.enableNavButtons(false);
            return;
        }
        
        ui.setStatus('Loading data...', 'loading');
        
        try {
            // Load COGs for this radar/product combination
            state.cogs = await api.getCogs(state.selectedRadar, state.selectedProduct);
            
            if (state.cogs.length === 0) {
                ui.setStatus('No data available', 'error');
                ui.enableNavButtons(false);
                return;
            }
            
            // Display the latest (first in list, since sorted desc)
            state.currentCogIndex = 0;
            this.displayCurrentCog();
            
            ui.enableNavButtons(true);
            ui.setStatus(`Loaded ${state.cogs.length} images`, 'success');
            
        } catch (error) {
            console.error('Load error:', error);
            ui.setStatus(`Error: ${error.message}`, 'error');
            ui.enableNavButtons(false);
        }
    },
    
    displayCurrentCog() {
        if (state.cogs.length === 0) return;
        
        const cog = state.cogs[state.currentCogIndex];
        
        // Get radar bounds for initial zoom
        const radar = state.radars.find(r => r.code === state.selectedRadar);
        const bounds = radar?.extent || null;
        
        // Display on map
        map.setRadarLayer(cog.id, bounds);
        
        // Update time display
        ui.setTimeDisplay(cog.observation_time);
        
        // Update status
        ui.setStatus(`${state.currentCogIndex + 1} / ${state.cogs.length}`, '');
    },
    
    navigate(direction) {
        if (state.cogs.length === 0) return;
        
        const newIndex = state.currentCogIndex + direction;
        
        // Check bounds
        if (newIndex < 0 || newIndex >= state.cogs.length) {
            return;
        }
        
        state.currentCogIndex = newIndex;
        this.displayCurrentCog();
    },
    
    goToLatest() {
        if (state.cogs.length === 0) return;
        
        state.currentCogIndex = 0; // First item is latest (sorted desc)
        this.displayCurrentCog();
    },
};

// =============================================================================
// START APP
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    app.init();
});