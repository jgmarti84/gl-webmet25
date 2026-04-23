# COMPONENTS.md — WebMet25 Frontend Modules

> **Purpose:** Document the functional components of the WebMet25 frontend, their responsibilities, and file locations.

---

## Overview

The WebMet25 frontend is a modular JavaScript application built with vanilla ES6, Leaflet, and CartoDB basemaps. It has **no build tool, no framework dependencies, and no state management library**—all state is managed in a global `state` object in `app.js`.

**File Organization:**
```
frontend/public/
├── index.html                 # Main HTML page skeleton
├── cog-browser.html          # Alternative detailed COG browser view
├── css/
│   └── styles.css            # All UI styling (444 lines, dark theme)
└── js/
    ├── app.js                # Main orchestrator & state management
    ├── api.js                # REST API client
    ├── map.js                # Leaflet map wrapper
    ├── animation.js          # Frame animation controller
    ├── controls.js           # UI control handlers
    ├── legend.js             # Legend renderer
    ├── cog-browser-api.js    # [Alternative] API client for COG browser
    └── cog-browser.js        # [Alternative] COG browser app
```

---

## Core Components

### 1. **app.js** — Main Application Orchestrator

**File:** [`frontend/public/js/app.js`](../../frontend/public/js/app.js)

**Responsibility:** Central orchestrator that initializes all modules, manages global application state, and coordinates interactions between components. Handles startup sequence, user event delegation, and module lifecycle.

**Key Exports:**
- `state` object — Global state containing radars, products, selectedRadars, selectedProduct, COGs, animation mode, timers
- `init()` — Bootstrap function called on page load
- Event listeners for radar/product selection, time window buttons, animation controls, settings

**Dependencies:** Imports `api.js`, `map.js`, `animation.js`, `controls.js`, `legend.js`

**State Shape:**
```javascript
const state = {
    radars: [],                    // From GET /radars
    products: [],                  // From GET /products
    cogs: [],                      // From GET /cogs (filtered)
    selectedRadars: [],            // User's multi-select choices
    selectedProduct: null,         // User's dropdown choice
    mapManager: null,              // MapManager instance
    animator: null,                // AnimationController instance
    ui: null,                      // UIControls instance
    legend: null,                  // LegendRenderer instance
    animationMode: null,           // "live" or "replay" or null
    liveRefreshInterval: null,     // Interval ID for polling
    // ... 10+ more state fields
};
```

---

### 2. **api.js** — REST API Client

**File:** [`frontend/public/js/api.js`](../../frontend/public/js/api.js)

**Responsibility:** Encapsulates all HTTP communication with the backend API. Provides functions to fetch radars, products, COG metadata, colormap data, and handles error responses. Single source of truth for API base URL.

**Key Functions:**
- `getRadars()` → `GET /api/v1/radars` — List all radar stations
- `getProducts()` → `GET /api/v1/products` — List available products
- `getCogs(radarCode, productKey, hoursBack)` → `GET /api/v1/cogs?...` — Query COG metadata with time filtering
- `getColormapInfo(productKey)` → `GET /api/v1/products/{key}/colormap` — Fetch color scale entries
- `getTileUrl(cogId, z, x, y)` → Constructs URL for tile endpoint (no fetch, returns URL string for Leaflet)

**Dependencies:** None (standalone HTTP client)

**Error Handling:** All functions catch errors and throw descriptive exceptions; caller must handle with try/catch

---

### 3. **map.js** — Leaflet Map Manager

**File:** [`frontend/public/js/map.js`](../../frontend/public/js/map.js)

**Responsibility:** Wraps Leaflet map initialization, basemap switching, radar layer management (add/remove/setOpacity), and map bounds/zoom control. Provides a simple interface for adding/removing radar overlay tiles.

**Key Methods:**
- `init(containerId, centerLat, centerLon, zoom)` — Create map with initial view
- `setBasemap(basemapKey)` — Switch between Dark, Streets, Satellite, Terrain
- `addRadarLayer(cogId, radarCode, tileUrl)` → Creates `L.TileLayer` and adds to map
- `removeRadarLayer(cogId)` → Remove layer from map
- `setOpacity(cogId, opacity)` — Adjust layer transparency (0–1)
- `setBounds(bounds)` — Fit map to bounding box
- `getMap()` — Return underlying Leaflet map instance

**Dependencies:** Leaflet (loaded from CDN), CartoDB basemap providers

**State Maintained:** Internal `layers` object mapping `cogId` → `L.TileLayer` instance

---

### 4. **animation.js** — Frame Animation Controller

**File:** [`frontend/public/js/animation.js`](../../frontend/public/js/animation.js)

**Responsibility:** Manages playback of radar data frame sequences. Handles play/pause, speed control (0.5x–2x), manual frame navigation, and automatic frame updates at regular intervals. Coordinates with map manager to display current frame.

**Key Methods:**
- `setFrames(frames)` — Load COG sequence (Array of `{timestamp, cogsByRadar: {...}}`)
- `play()` / `pause()` — Start/stop playback
- `nextFrame()` / `previousFrame()` — Manual navigation
- `setSpeed(speed)` — Set playback multiplier (0.5–2.0)
- `setToFrame(index)` — Jump to specific frame index
- `getCurrentFrameIndex()` — Get current position

**Dependencies:** `map.js` (calls `addRadarLayer`, `removeRadarLayer`)

**State Maintained:** `currentFrameIndex`, `isPlaying`, `speed`, `frames[]`, `intervalId`

**Frame Update Logic:** On play, every `200ms / speed` milliseconds, increment frame index and render (show frame layers, hide others)

---

### 5. **controls.js** — UI Control Handlers

**File:** [`frontend/public/js/controls.js`](../../frontend/public/js/controls.js)

**Responsibility:** Manages all UI control panels, buttons, and status displays. Populates/updates selectors (radar checkboxes, product dropdown, time window buttons), updates status notifications, and enables/disables buttons based on app state.

**Key Methods:**
- `populateRadarCheckboxes(radars)` — Build radar multi-select panel
- `populateProductSelect(products)` — Build product dropdown
- `updateStatus(message, duration)` — Show status toast (auto-hide after duration)
- `updateFrameCounter(current, total)` — Display "5 / 30"
- `updateTimeBadge(hoursBack)` — Update time window badge
- `enableButton(id)` / `disableButton(id)` — Set button enabled state
- `showError(message)` → `updateStatus()` with error styling
- `togglePanel(panelId)` — Open/close floating panels (radar, product, time, settings)

**Dependencies:** DOM manipulation only; no external libraries

**DOM Elements Modified:** Input checkboxes, dropdowns, span badges, notification divs, button states

---

### 6. **legend.js** — Legend Renderer

**File:** [`frontend/public/js/legend.js`](../../frontend/public/js/legend.js)

**Responsibility:** Fetches colormap data from API and renders an interactive legend showing color-to-value mappings. Displays color boxes with value labels and descriptions; supports show/hide toggle.

**Key Methods:**
- `render(productKey)` → Async function that fetches colormap via `api.js`, then builds HTML legend in DOM
- `show()` / `hide()` — Toggle legend visibility
- `clear()` — Remove all legend entries

**Dependencies:** `api.js` (calls `getColormapInfo`)

**DOM Elements Modified:** `#legend-container` div with nested color-box + label items

**Rendering Format:** For each Reference entry: colored square (hex color), value, and optional title

---

### 7. **cog-browser-api.js** — [Alternative] Specialized API Client

**File:** [`frontend/public/js/cog-browser-api.js`](../../frontend/public/js/cog-browser-api.js)

**Responsibility:** Variant of `api.js` used by the alternative COG browser view (`cog-browser.html`). Provides the same core API functions but may include additional query/filtering capabilities for detailed COG inspection.

**Differences from `api.js`:** May support additional query parameters, pagination details, or metadata filters specific to the COG browser use case.

**Note:** This is a secondary module; primary application uses `api.js`

---

### 8. **cog-browser.js** — [Alternative] COG Browser Application

**File:** [`frontend/public/js/cog-browser.js`](../../frontend/public/js/cog-browser.js)

**Responsibility:** Alternative frontend implementation for detailed COG file browsing and inspection (`cog-browser.html`). Provides a table-based view of COG metadata with sorting/filtering, separate from the main animated map view.

**Purpose:** For developers/ops to inspect individual COG files, timestamps, file sizes, rendering parameters, and status

**Note:** This is a secondary view; primary radar visualization uses `app.js`

---

## HTML Pages

### **index.html** — Main Radar Visualization Page

**File:** [`frontend/public/index.html`](../../frontend/public/index.html)

**Responsibility:** Defines the DOM skeleton for the main radar visualization application. Contains containers for the Leaflet map, icon bar (module buttons), floating panels (radar/product/time selectors), animation controls, legend, and status displays.

**Key DOM Elements:**
- `<div id="map">` — Leaflet map container
- `<div id="icon-bar">` — Vertical button bar (radar, product, time, snapshot, settings)
- `<div id="panel-module-a/b/c">` — Floating control panels
- `<div id="animation-controls">` — Play/pause, speed, frame counter
- `<div id="legend-container">` — Legend display
- `<div id="status">` — Status notification area
- `<script type="module" src="js/app.js">` — Entry point

**Loaded Scripts:**
- Leaflet 1.9.4 (CDN)
- CartoDB basemap providers (CDN)
- Local modules via ES6 imports in `app.js`

---

### **cog-browser.html** — Alternative COG Browser Page

**File:** [`frontend/public/cog-browser.html`](../../frontend/public/cog-browser.html)

**Responsibility:** Provides a detailed table view for inspecting COG files directly (metadata, timestamps, file sizes, status). Separate from the main animated map visualization.

**Key DOM Elements:** Table columns for COG ID, radar code, product, timestamp, file size, status, etc.

**Loaded Scripts:** `cog-browser-api.js`, `cog-browser.js`

---

## Styling

### **styles.css** — All UI Styling

**File:** [`frontend/public/css/styles.css`](../../frontend/public/css/styles.css)

**Responsibility:** Comprehensive stylesheet (444 lines) providing dark theme colors, responsive layout, and styling for all UI components. Defines the professional dark aesthetic (`#1a1a2e` background, light text) matching reference implementations.

**Key Sections:**
- **Color scheme:** Dark background, accents, hover states
- **Layout:** Flexbox/grid for responsive design
- **Components:** Icon buttons, floating panels, animation controls, legend, status notifications
- **Responsive breakpoints:** Mobile, tablet, desktop sizes
- **Accessibility:** Focus states, contrast ratios, semantic HTML

**No external CSS frameworks used** — Pure vanilla CSS3

---

## Module Dependency Graph

```
app.js (main orchestrator)
├── api.js (REST client)
├── map.js (Leaflet wrapper)
│   └── Leaflet (CDN)
├── animation.js (frame player)
│   └── map.js (layer management)
├── controls.js (UI handlers)
├── legend.js (color scale renderer)
│   └── api.js (fetch colormap)
└── index.html (DOM skeleton)
    └── styles.css (styling)

cog-browser.html (alternative view)
├── cog-browser-api.js
└── cog-browser.js
```

---

## Data Flow Through Components

```
1. User opens http://localhost
   ↓
2. index.html loads, Leaflet initializes
   ↓
3. app.js:init() called
   ├── api.getRadars() → state.radars
   ├── api.getProducts() → state.products
   ├── map.init() → initialize Leaflet map
   ├── controls.populateRadarCheckboxes(state.radars)
   ├── controls.populateProductSelect(state.products)
   └── legend.render(defaultProduct)
   ↓
4. User selects radar(s) and product
   ├── Event listener fires
   ├── api.getCogs(selectedRadar, selectedProduct) → state.cogs
   ├── group COGs by timestamp → frames
   ├── animator.setFrames(frames)
   └── legend.render(selectedProduct)
   ↓
5. User clicks Play
   ├── animator.play() starts interval
   ├── Every 200ms / speed:
   │   ├── animator.nextFrame()
   │   ├── map.removeRadarLayer(previousCogId)
   │   └── map.addRadarLayer(currentCogId)
   └── controls.updateFrameCounter()
   ↓
6. User adjusts opacity slider
   └── map.setOpacity(currentCogId, newOpacity)
```

---

## State Lifecycle

### Initialization
```javascript
// Global state created in app.js
const state = {
    radars: [],
    products: [],
    // ... all fields initialized to empty/null
};

// On page load
app.init()
    .then(() => api.getRadars())
    .then(radars => { state.radars = radars; controls.populate...(radars); })
    // ... similar for products
```

### User Interaction → State Update → UI Rerender
```javascript
// User clicks radar checkbox
checkbox.addEventListener('change', (e) => {
    const radarCode = e.target.value;
    state.selectedRadars.push(radarCode);  // Update state
    api.getCogs(radarCode, state.selectedProduct).then(cogs => {
        state.cogs = cogs;  // Update state
        animator.setFrames(groupCogsByTimestamp(cogs));  // Rerender
        legend.render(state.selectedProduct);
    });
});
```

---

## Browser Compatibility

- **Chrome/Edge:** 88+
- **Firefox:** 78+
- **Safari:** 14+
- **Mobile Browsers:** Any with ES6 module support (iOS Safari 15+, Android Chrome 80+)

**Requirements:**
- ES6 module support (all modern browsers)
- Fetch API (for HTTP requests)
- Leaflet 1.9.4 (loaded from CDN)
- Canvas API (for map rendering and snapshot download)

---

## Key Design Principles

1. **No Build Tool:** Pure ES6 modules served directly; no webpack/vite
2. **No Framework:** Vanilla JavaScript; all DOM manipulation is direct
3. **Single-Responsibility Modules:** Each `.js` file has one clear purpose
4. **Global State:** `state` object in `app.js` is the source of truth
5. **Async/Await:** Modern async patterns for API calls and delayed actions
6. **CMS Principles:** Event-driven architecture; modules communicate via state mutations
7. **Responsive Design:** Mobile-first CSS with dark theme
8. **Error Resilience:** Try/catch blocks throughout; degradeful fallbacks if API unavailable

---

## Known Limitations & Future Work

- ❌ No animation frame preloading (tiles fetched on first render)
- ❌ Animation speed hard-coded to 200ms base interval (should be configurable per device)
- ❌ No offline support or service worker caching
- ❌ No WebSocket real-time updates (polls every 5 minutes instead)
- ❌ Module coupling via global `state` object (could refactor to event emitter pattern)

---

**Document Version:** 1.0.0  
**Last Updated:** April 20, 2026
