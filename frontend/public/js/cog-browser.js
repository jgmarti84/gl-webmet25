/**
 * COG Browser Application
 * Allows browsing and viewing individual COG files with colormap selection
 */

import { cogBrowserApi } from './cog-browser-api.js';
import { LegendRenderer } from './legend.js';


// =============================================================================
// APPLICATION STATE
// =============================================================================

const state = {
    // Data
    radars: [],
    products: [],
    allColormapOptions: {},
    cogs: [],
    
    // Pagination
    currentPage: 1,
    pageSize: 50,
    totalCogs: 0,

    // Date tree: tracks which date groups are expanded { 'YYYY': bool, 'YYYY/MM': bool, 'YYYY/MM/DD': bool }
    expandedNodes: {},

    // UI State
    selectedRadar: null,
    selectedProduct: null,
    selectedColormap: null,
    activeCoGId: null,
    
    // Map and layers
    map: null,
    cogLayers: {},  // Store layers by cogId
    currentOpacity: 0.7,
    currentBasemap: 'dark',
    
    // UI elements
    statusMessage: null,
    legend: null,
};

// =============================================================================
// MAP BASEMAPS (shared with radar viewer)
// =============================================================================

const BASEMAPS = {
    'dark': {
        name: 'Dark',
        url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
        attribution: '© OpenStreetMap contributors, © CARTO',
        maxZoom: 18
    },
    'light': {
        name: 'Light',
        url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
        attribution: '© OpenStreetMap contributors, © CARTO',
        maxZoom: 18
    },
    'osm': {
        name: 'OpenStreetMap',
        url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    },
    'satellite': {
        name: 'Satellite',
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attribution: 'Tiles © Esri',
        maxZoom: 18
    },
    'terrain': {
        name: 'Terrain',
        url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
        attribution: 'Map data: © OpenStreetMap contributors, SRTM | Map style: © OpenTopoMap',
        maxZoom: 17
    }
};

// =============================================================================
// MAIN APPLICATION
// =============================================================================

const app = {
    /**
     * Initialize the application
     */
    async init() {
        state.statusMessage = document.getElementById('status-message');
        
        this.setStatus('Initializing...', 'loading');
        
        try {
            // Wait for Leaflet to be loaded
            await this.waitForLeaflet();
            
            // Initialize map
            this.initMap();
            
            // Initialize legend
            state.legend = new LegendRenderer('legend-container');
            
            // Load initial data
            await this.loadInitialData();
            
            // Setup event listeners
            this.setupEventListeners();
            
            // Load colormap preferences
            this.loadColormapPreference();
            
            this.setStatus('Ready', 'success');
            
        } catch (error) {
            console.error('Init error:', error);
            this.setStatus(`Error: ${error.message}`, 'error');
        }
    },
    
    /**
     * Wait for Leaflet library to be loaded
     */
    async waitForLeaflet(maxWait = 5000) {
        const startTime = Date.now();
        
        while (typeof L === 'undefined') {
            if (Date.now() - startTime > maxWait) {
                throw new Error('Leaflet library failed to load.');
            }
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        
        console.log('Leaflet loaded successfully');
    },
    
    /**
     * Initialize the Leaflet map
     */
    initMap() {
        const DEFAULT_CENTER = [-34.0, -64.0];
        const DEFAULT_ZOOM = 5;
        
        state.map = L.map('map').setView(DEFAULT_CENTER, DEFAULT_ZOOM);
        
        // Add initial basemap
        this.setBasemap('dark');
    },
    
    /**
     * Change basemap
     */
    setBasemap(basemapKey) {
        if (!BASEMAPS[basemapKey]) {
            console.warn(`Unknown basemap: ${basemapKey}`);
            return;
        }
        
        // Remove existing base layer
        if (state.baseLayer) {
            state.map.removeLayer(state.baseLayer);
        }
        
        // Add new base layer
        const basemap = BASEMAPS[basemapKey];
        state.baseLayer = L.tileLayer(basemap.url, {
            attribution: basemap.attribution,
            maxZoom: basemap.maxZoom,
        }).addTo(state.map);
        
        state.currentBasemap = basemapKey;
    },
    
    /**
     * Load radars and products from API
     */
    async loadInitialData() {
        state.radars = await cogBrowserApi.getRadars();
        state.products = await cogBrowserApi.getProducts();
        state.allColormapOptions = await cogBrowserApi.getColormapOptions();
        
        this.populateRadarSelect();
        this.populateProductSelect();
    },
    
    /**
     * Populate radar select dropdown
     */
    populateRadarSelect() {
        const select = document.getElementById('radar-select');
        
        // Clear existing options
        select.innerHTML = '<option value="">Select radar...</option>';
        
        // Add radars sorted by code
        state.radars
            .sort((a, b) => a.code.localeCompare(b.code))
            .forEach(radar => {
                const option = document.createElement('option');
                option.value = radar.code;
                option.textContent = `${radar.code} - ${radar.title}`;
                select.appendChild(option);
            });
    },
    
    /**
     * Populate product select dropdown
     */
    populateProductSelect() {
        const select = document.getElementById('product-select');
        
        // Clear existing options
        select.innerHTML = '<option value="">Select product...</option>';
        
        // Add products sorted by key
        state.products
            .sort((a, b) => a.product_key.localeCompare(b.product_key))
            .forEach(product => {
                const option = document.createElement('option');
                option.value = product.product_key;
                option.textContent = `${product.product_key} - ${product.product_title}`;
                select.appendChild(option);
            });
    },
    
    /**
     * Populate colormap select dropdown based on selected product
     */
    populateColormapSelect() {
        const select = document.getElementById('colormap-select');
        
        if (!state.selectedProduct) {
            select.innerHTML = '<option value="">Select product first</option>';
            select.disabled = true;
            return;
        }
        
        // Get available colormaps for this product
        const productKey = state.selectedProduct.toUpperCase();
        const colormaps = state.allColormapOptions[productKey] || [];
        
        // Clear and populate
        select.innerHTML = '<option value="">Default</option>';
        select.disabled = false;
        
        colormaps.forEach(cmapName => {
            const option = document.createElement('option');
            option.value = cmapName;
            option.textContent = cmapName;
            select.appendChild(option);
        });
        
        // Restore saved preference if available
        const savedCmap = this.getColormapPreference(state.selectedProduct);
        if (savedCmap && colormaps.includes(savedCmap)) {
            select.value = savedCmap;
            state.selectedColormap = savedCmap;
        } else {
            select.value = '';
            state.selectedColormap = null;
        }
        
        // Load and display colormap info (vmin/vmax)
        this.loadAndDisplayColormapInfo();
    },
    
    /**
     * Load and display colormap vmin/vmax
     */
    async loadAndDisplayColormapInfo() {
        const rangeDisplay = document.getElementById('colormap-range');
        const rangeText = document.getElementById('range-text');
        
        if (!state.selectedProduct) {
            rangeDisplay.style.display = 'none';
            state.legend.hide();
            return;
        }
        
        try {
            const colormapInfo = await cogBrowserApi.getColormapInfo(
                state.selectedProduct,
                state.selectedColormap
            );
            
            console.log('Colormap Info received:', colormapInfo);
            
            if (colormapInfo && colormapInfo.vmin !== undefined && colormapInfo.vmax !== undefined) {
                rangeText.textContent = `Range: ${colormapInfo.vmin.toFixed(2)} to ${colormapInfo.vmax.toFixed(2)}`;
                rangeDisplay.style.display = 'block';
                
                // Add unit info if available
                const productInfo = state.products.find(p => p.product_key === state.selectedProduct);
                if (!colormapInfo.unit && productInfo) {
                    colormapInfo.unit = productInfo.unit;
                }
                
                // Render the legend with colors
                state.legend.render(colormapInfo);
                state.legend.show();
                
                console.log('Legend rendered with:', { vmin: colormapInfo.vmin, vmax: colormapInfo.vmax });
            } else {
                rangeDisplay.style.display = 'none';
                state.legend.hide();
                console.warn('Colormap info missing vmin/vmax:', colormapInfo);
            }
        } catch (error) {
            console.warn('Failed to load colormap info:', error);
            rangeDisplay.style.display = 'none';
            state.legend.hide();
        }
    },

    
    /**
     * Load COGs for selected radar and product (first page).
     */
    async loadCogs() {
        if (!state.selectedRadar || !state.selectedProduct) {
            this.setStatus('Select radar and product', 'info');
            return;
        }
        
        // Reset pagination and previously loaded COGs on a fresh load
        state.currentPage = 1;
        state.cogs = [];
        state.expandedNodes = {};
        
        this.setStatus('Loading COGs...', 'loading');
        
        try {
            const result = await cogBrowserApi.getCogs(
                state.selectedRadar,
                state.selectedProduct,
                state.currentPage,
                state.pageSize
            );

            state.cogs = result.cogs;
            state.totalCogs = result.total;

            if (state.cogs.length === 0) {
                this.setStatus('No COGs available for this selection', 'info');
                this.renderCogList();
                return;
            }
            
            this.renderCogList();
            this.setStatus(`Loaded ${state.cogs.length} of ${state.totalCogs} COGs`, 'success');
            
        } catch (error) {
            console.error('Load COGs error:', error);
            this.setStatus(`Error loading COGs: ${error.message}`, 'error');
            this.renderCogList();
        }
    },

    /**
     * Load the next page of COGs and append them to the existing list.
     */
    async loadMoreCogs() {
        if (!state.selectedRadar || !state.selectedProduct) return;

        state.currentPage += 1;
        this.setStatus('Loading more COGs...', 'loading');

        try {
            const result = await cogBrowserApi.getCogs(
                state.selectedRadar,
                state.selectedProduct,
                state.currentPage,
                state.pageSize
            );

            state.cogs = state.cogs.concat(result.cogs);
            state.totalCogs = result.total;

            this.renderCogList();
            this.setStatus(`Loaded ${state.cogs.length} of ${state.totalCogs} COGs`, 'success');

        } catch (error) {
            console.error('Load more COGs error:', error);
            state.currentPage -= 1; // roll back on failure
            this.setStatus(`Error loading COGs: ${error.message}`, 'error');
        }
    },
    
    /**
     * Render COG list grouped by date (YYYY → MM → DD hierarchy).
     * Expanding/collapsing a node preserves state in state.expandedNodes.
     */
    renderCogList() {
        const cogList = document.getElementById('cog-list');
        
        if (state.cogs.length === 0) {
            cogList.innerHTML = '<div class="cog-list-empty">No COGs available.</div>';
            return;
        }

        // Build date tree: { year: { month: { day: [cog, …] } } }
        const tree = {};
        state.cogs.forEach(cog => {
            const d = new Date(cog.observation_time);
            const y = String(d.getUTCFullYear());
            const m = String(d.getUTCMonth() + 1).padStart(2, '0');
            const day = String(d.getUTCDate()).padStart(2, '0');

            if (!tree[y]) tree[y] = {};
            if (!tree[y][m]) tree[y][m] = {};
            if (!tree[y][m][day]) tree[y][m][day] = [];
            tree[y][m][day].push(cog);
        });

        cogList.innerHTML = '';

        Object.keys(tree).sort((a, b) => b - a).forEach(year => {
            const yearKey = year;
            const yearExpanded = state.expandedNodes[yearKey] !== false; // default open

            const yearEl = this._makeFolderNode(`📅 ${year}`, yearExpanded, () => {
                state.expandedNodes[yearKey] = !yearExpanded;
                this.renderCogList();
            });
            cogList.appendChild(yearEl);

            if (!yearExpanded) return;

            const yearChildren = document.createElement('div');
            yearChildren.className = 'cog-tree-children';
            cogList.appendChild(yearChildren);

            Object.keys(tree[year]).sort((a, b) => b - a).forEach(month => {
                const monthKey = `${yearKey}/${month}`;
                const monthExpanded = state.expandedNodes[monthKey] !== false; // default open

                const monthEl = this._makeFolderNode(`📂 ${year}/${month}`, monthExpanded, () => {
                    state.expandedNodes[monthKey] = !monthExpanded;
                    this.renderCogList();
                }, 1);
                yearChildren.appendChild(monthEl);

                if (!monthExpanded) return;

                const monthChildren = document.createElement('div');
                monthChildren.className = 'cog-tree-children';
                yearChildren.appendChild(monthChildren);

                Object.keys(tree[year][month]).sort((a, b) => b - a).forEach(dayStr => {
                    const dayKey = `${monthKey}/${dayStr}`;
                    const dayExpanded = state.expandedNodes[dayKey] !== false; // default open
                    const dayCogs = tree[year][month][dayStr];

                    const dayEl = this._makeFolderNode(
                        `📁 ${year}/${month}/${dayStr} (${dayCogs.length})`,
                        dayExpanded,
                        () => {
                            state.expandedNodes[dayKey] = !dayExpanded;
                            this.renderCogList();
                        },
                        2
                    );
                    monthChildren.appendChild(dayEl);

                    if (!dayExpanded) return;

                    const dayChildren = document.createElement('div');
                    dayChildren.className = 'cog-tree-children';
                    monthChildren.appendChild(dayChildren);

                    // Sort COGs newest-first within each day
                    dayCogs
                        .slice()
                        .sort((a, b) => new Date(b.observation_time) - new Date(a.observation_time))
                        .forEach(cog => {
                            const item = document.createElement('div');
                            item.className = 'cog-item';
                            if (state.activeCoGId === cog.id) item.classList.add('active');
                            item.style.marginLeft = '48px';

                            const d = new Date(cog.observation_time);
                            const timeStr = d.toLocaleTimeString('en-US', {
                                hour: '2-digit',
                                minute: '2-digit',
                                second: '2-digit',
                                hour12: false,
                                timeZone: 'UTC',
                            }) + ' UTC';

                            item.innerHTML = `
                                <div class="cog-item-time">${timeStr}</div>
                                <div class="cog-item-info">Elev: ${cog.elevation_angle.toFixed(1)}°</div>
                            `;

                            item.addEventListener('click', () => this.onCogItemClick(cog, item));
                            dayChildren.appendChild(item);
                        });
                });
            });
        });

        // Append "Load More" button if there are more COGs on the server
        if (state.cogs.length < state.totalCogs) {
            const remaining = state.totalCogs - state.cogs.length;
            const loadMoreBtn = document.createElement('button');
            loadMoreBtn.className = 'action-btn';
            loadMoreBtn.style.marginTop = '8px';
            loadMoreBtn.textContent = `Load ${Math.min(state.pageSize, remaining)} more…`;
            loadMoreBtn.addEventListener('click', () => this.loadMoreCogs());
            cogList.appendChild(loadMoreBtn);
        }
    },

    /**
     * Create a collapsible folder node for the date tree.
     * @param {string} label - Display text
     * @param {boolean} expanded - Whether the node starts expanded
     * @param {Function} onToggle - Called when the user clicks the node
     * @param {number} indent - Indentation level (0, 1, 2)
     */
    _makeFolderNode(label, expanded, onToggle, indent = 0) {
        const el = document.createElement('div');
        el.className = 'cog-date-node';
        el.style.paddingLeft = `${indent * 16}px`;
        el.innerHTML = `<span class="cog-date-arrow">${expanded ? '▾' : '▸'}</span> ${label}`;
        el.addEventListener('click', onToggle);
        return el;
    },
    
    /**
     * Handle COG item click
     */
    async onCogItemClick(cog, itemEl) {
        state.activeCoGId = cog.id;
        
        // Update UI
        document.querySelectorAll('.cog-item').forEach(item => {
            item.classList.remove('active');
        });
        itemEl.classList.add('active');
        
        // Display on map
        this.displayCogOnMap(cog);
        
        // Update time display
        const date = new Date(cog.observation_time);
        document.getElementById('time-display').textContent = date.toLocaleString();
    },
    
    /**
     * Display COG on map (only one COG per radar at a time)
     */
    displayCogOnMap(cog) {
        // Remove previous layer for this radar
        if (state.cogLayers[cog.radar_code]) {
            state.map.removeLayer(state.cogLayers[cog.radar_code]);
        }
        
        // Get tile URL with colormap if selected
        const tileUrl = cogBrowserApi.getTileUrl(cog.id, state.selectedColormap);
        
        // Add new layer
        const layer = L.tileLayer(tileUrl, {
            opacity: state.currentOpacity,
            maxZoom: 18,
            tms: false,
        }).addTo(state.map);
        
        state.cogLayers[cog.radar_code] = layer;
        
        // Fit to bounds if available
        if (cog.bbox) {
            const bounds = L.latLngBounds(
                [cog.bbox.min_lat, cog.bbox.min_lon],
                [cog.bbox.max_lat, cog.bbox.max_lon]
            );
            state.map.fitBounds(bounds);
        }
        
        this.setStatus(`Displaying COG from ${cog.observation_time}`, 'success');
    },
    
    /**
     * Update colormap for all active COGs
     */
    updateColormap() {
        if (!state.activeCoGId) return;
        
        const activeCog = state.cogs.find(c => c.id === state.activeCoGId);
        if (activeCog) {
            this.displayCogOnMap(activeCog);
            
            // Save preference
            if (state.selectedProduct) {
                this.saveColormapPreference(state.selectedProduct, state.selectedColormap);
            }
        }
        
        // Update colormap range display
        this.loadAndDisplayColormapInfo();
    },
    
    /**
     * Setup all event listeners
     */
    setupEventListeners() {
        // Radar selection
        document.getElementById('radar-select').addEventListener('change', (e) => {
            state.selectedRadar = e.target.value;
            this.loadCogs();
        });
        
        // Product selection
        document.getElementById('product-select').addEventListener('change', (e) => {
            state.selectedProduct = e.target.value;
            this.populateColormapSelect();
            this.loadCogs();
        });
        
        // Colormap selection
        document.getElementById('colormap-select').addEventListener('change', (e) => {
            state.selectedColormap = e.target.value || null;
            this.updateColormap();
        });
        
        // Basemap selection
        document.getElementById('basemap-select').addEventListener('change', (e) => {
            this.setBasemap(e.target.value);
        });
        
        // Opacity slider
        document.getElementById('opacity-slider').addEventListener('input', (e) => {
            const opacity = parseFloat(e.target.value) / 100;
            state.currentOpacity = opacity;
            
            // Update all layers
            Object.values(state.cogLayers).forEach(layer => {
                layer.setOpacity(opacity);
            });
            
            // Update display
            document.getElementById('opacity-display').textContent = 
                Math.round(opacity * 100) + '%';
        });
    },
    
    /**
     * Save colormap preference to localStorage
     */
    saveColormapPreference(productKey, colormapName) {
        try {
            const prefs = JSON.parse(localStorage.getItem('cogBrowserPrefs') || '{}');
            prefs.colormaps = prefs.colormaps || {};
            prefs.colormaps[productKey] = colormapName;
            localStorage.setItem('cogBrowserPrefs', JSON.stringify(prefs));
        } catch (e) {
            console.warn('Failed to save colormap preference:', e);
        }
    },
    
    /**
     * Load colormap preference from localStorage
     */
    getColormapPreference(productKey) {
        try {
            const prefs = JSON.parse(localStorage.getItem('cogBrowserPrefs') || '{}');
            return prefs.colormaps?.[productKey] || null;
        } catch (e) {
            console.warn('Failed to load colormap preference:', e);
            return null;
        }
    },
    
    /**
     * Load all colormap preferences
     */
    loadColormapPreference() {
        try {
            const prefs = JSON.parse(localStorage.getItem('cogBrowserPrefs') || '{}');
            console.log('Loaded colormap preferences:', prefs);
        } catch (e) {
            console.warn('Failed to load preferences:', e);
        }
    },
    
    /**
     * Set status message
     */
    setStatus(message, type = 'info') {
        if (!state.statusMessage) return;
        
        state.statusMessage.textContent = message;
        state.statusMessage.classList.remove('info', 'success', 'error', 'loading');
        state.statusMessage.classList.add('show', type);
    },
};

// =============================================================================
// START APPLICATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    app.init();
});
