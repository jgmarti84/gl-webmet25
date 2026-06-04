# COMPONENTS.md — WebMet25 Frontend Modules

> **Purpose:** Document the functional components of the WebMet25 frontend, their responsibilities, and file locations.

---

## Overview

The WebMet25 frontend is a modular JavaScript application built with vanilla ES6, Leaflet, and CartoDB basemaps. It has **no build tool, no framework dependencies, and no state management library**—all state is managed in a global `state` object in `app.js`.

**File Organization:**
```
frontend/public/
├── index.html                 # Main HTML page skeleton
├── admin.html                 # Admin panel SPA (served at /admin, Basic Auth)
├── cog-browser.html          # Alternative detailed COG browser view
├── css/
│   ├── styles.css            # Main app UI styling (dark theme)
│   └── admin.css             # Admin panel styling (modern-light theme)
└── js/
    ├── admin.js              # Admin panel orchestrator (CRUD, filters, colormap creator)
    ├── admin-api.js          # Admin REST client (/api/v1/admin/*)
    ├── shared/               # Shared by v1 and v2
    │   ├── api.js            # REST API client
    │   ├── controls.js       # UI control handlers (+ radar ordering, time-wheel wiring)
    │   ├── legend.js         # Legend renderer
    │   ├── tops-cores.js     # TopsCoresLayer (L.circleMarker)
    │   ├── time-wheel.js     # iOS-style HH:MM scroll picker (custom time range)
    │   ├── cog-browser-api.js
    │   └── cog-browser.js
    └── v2/                   # Current production frontend
        ├── app.js            # Main orchestrator & state management
        ├── map.js            # MapManager with L.imageOverlay
        └── animation.js      # AnimationController with requestAnimationFrame
```

> **v2 is the current production standard.** The v1 directory is preserved for reference.
> The **admin panel** (`admin.html` + `admin.js` + `admin-api.js` + `admin.css`) is an independent SPA — see the *Admin Panel* component below.

---

## Core Components

### 1. **app.js** (v2) — Main Application Orchestrator

**File:** [`frontend/public/js/v2/app.js`](../../frontend/public/js/v2/app.js)

**Responsibility:** Central orchestrator for the v2 frontend. Manages global application state, initializes all modules, handles radar/product selection, coverage mode switching, animation continuity, tops & cores visibility, and live refresh polling.

**Key Exports:**
- `state` object — Global state (radars, products, selectedRadars, selectedProduct, COGs, animator, mapManager, topsCoresLayer, ...)
- `init()` — Bootstrap function called on page load

**State Shape (v2):**
```javascript
const state = {
    radars: [],
    products: [],
    cogs: [],
    selectedRadars: [],
    selectedProduct: null,
    showUnfilteredProducts: false,
    showInactiveRadars: false,
    activeTimeWindowHours: 1.5,   // default 90 min
    selectedColormap: null,
    currentVmin: null,
    currentVmax: null,
    fieldOpacity: {},             // per-radar opacity
    mapManager: null,
    animator: null,
    ui: null,
    legend: null,
    topsCoresLayer: null,
    topsCoresVisible: false,
    topsCoresPointSize: 8,
    animationMode: null,          // "live" | "replay" | null
    liveRefreshInterval: null,
    radarStatusRefreshInterval: null,
    // ... more
};
```

**Coverage Modes (`COVERAGE_MODES` constant):**
```javascript
const COVERAGE_MODES = [
    { id: 'cd',  label: 'C+D', volNrs: ['01', '02'], strategy: '0315', filteredFieldsAvailable: true },
    { id: 'vig', label: 'VIG', volNrs: ['04'],        strategy: '0315', filteredFieldsAvailable: false },
];
```
Mode is persisted to `localStorage` key `webmet25_coverage_mode`. COG queries pass the active mode’s `volNrs` as `?vol_nr=` params.

**Dependencies:** `shared/api.js`, `v2/map.js`, `v2/animation.js`, `shared/controls.js`, `shared/legend.js`, `shared/tops-cores.js`

---

### 2. **api.js** — REST API Client

**File:** [`frontend/public/js/shared/api.js`](../../frontend/public/js/shared/api.js)

**Responsibility:** Encapsulates all HTTP communication with the backend API. Provides functions to fetch radars, products, COG metadata, colormap data, and handles error responses. Single source of truth for API base URL.

**Key Functions:**
- `getRadars()` → `GET /api/v1/radars`
- `getProducts()` → `GET /api/v1/products`
- `getCogs(radarCode, productKey, startTime, endTime, strategy?, volNrs?)` → `GET /api/v1/cogs?...` — supports `strategy` and `vol_nr` (repeatable) for coverage-mode filtering
- `getColormapInfo(productKey)` → `GET /api/v1/products/{key}/colormap`
- `getFrameUrl(cogId, params)` → constructs `/frames/{id}/image.png` URL with query params
- `getTopsAndCores(radarCodes, timeFrom, timeTo)` → `GET /api/v1/tops-cores`
- `getTopsAndCoresFeatures(id)` → `GET /api/v1/tops-cores/{id}/features`

**Dependencies:** None (standalone HTTP client)

**Error Handling:** All functions catch errors and throw descriptive exceptions; caller must handle with try/catch

---

### 3. **map.js** (v2) — Leaflet Map Manager

**File:** [`frontend/public/js/v2/map.js`](../../frontend/public/js/v2/map.js)

**Responsibility:** Wraps Leaflet map with `L.imageOverlay`-based radar rendering. Manages loading frames from `/frames/{id}/image.png`, displaying them as geo-referenced overlays, basemap switching, coverage mask (SVG), and opacity control.

**Key Methods:**
- `init(containerId)` — Create map with initial view
- `setBasemap(key)` — Switch between OSM, IGN, and other basemaps
- `loadFrames(cogsByFrame)` — Pre-fetch all frame images and store as `L.imageOverlay`
- `showFrame(index)` — Display frame at index (hide others)
- `setOpacity(radarCode, opacity)` — Adjust radar overlay opacity
- `addRadarCoverage(code, lat, lng, radius_m)` — Add SVG circle to coverage mask
- `removeRadarCoverage(code)` — Remove coverage circle
- `updateParams(newParams)` — Update colormap/range params and reload frames (atomic background swap)

**State Maintained:** Internal `_frameImages` map, `_overlays` per radar, `_coverageMask` SVG

---

### 3b. **Gaussian Smoothing** — Server-side Image Filter

**Implemented in:** [`api/app/services/smoothing.py`](../../api/app/services/smoothing.py)  
**Exposed via:** `/frames/{cog_id}/image.png?smooth=true&smooth_sigma=0.8`

**Responsibility:** Applies a Gaussian blur (`scipy.ndimage.gaussian_filter`) to the raw float data array *before* colormap application, producing visually smoother radar images. Executed server-side on the render thread.

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `smooth` | bool | false | Enable/disable Gaussian smoothing |
| `smooth_sigma` | float | 0.8 | Standard deviation of Gaussian kernel (pixels). Higher = more blur |

**Behavior:**
- Applied after data masking and before colormap lookup — smoothing operates on float values, not RGBA pixels
- When `smooth=false` the `smooth_sigma` param is ignored and has no effect on cache keys
- Cache key includes `(smooth, smooth_sigma)` only when `smooth=true`, so unsmoothed requests always share the same key regardless of the sigma value sent

**Frontend integration:** The `smooth` and `smooth_sigma` values are appended to the `/frames/{id}/image.png` URL built by `shared/api.js`. The settings panel in v2 exposes a smoothing toggle and a sigma slider.

---

### 4. **animation.js** (v2) — Frame Animation Controller

**File:** [`frontend/public/js/v2/animation.js`](../../frontend/public/js/v2/animation.js)

**Responsibility:** Manages playback of radar frame sequences using `requestAnimationFrame`. Handles play/pause, speed control (0.5x–2x), manual navigation, and atomic frame buffer swaps for continuity.

**Key Methods:**
- `setFrames(frames)` — Atomically swap frame buffer (animation keeps running)
- `play()` / `pause()` — Start/stop playback
- `nextFrame()` / `previousFrame()` — Manual navigation
- `setSpeed(speed)` — Set playback multiplier (0.5–2.0)
- `getCurrentFrameIndex()` — Get current position

**State Maintained:** `currentFrameIndex`, `isPlaying`, `speed`, `frames[]`, `_rafHandle`

**Key Difference from v1:** Uses `requestAnimationFrame` (not `setInterval`); frame buffer swap via `setFrames()` is atomic and never stops the animation.

---

### 5. **controls.js** — UI Control Handlers

**File:** [`frontend/public/js/shared/controls.js`](../../frontend/public/js/shared/controls.js)

**Responsibility:** Manages all UI control panels, buttons, and status displays. Populates/updates selectors (radar checkboxes, product dropdown, time window buttons), updates status notifications, and enables/disables buttons based on app state.

**Key Methods:**
- `populateRadarCheckboxes(radars)` — Build radar multi-select panel (order via `sortRadarsForDisplay`)
- `sortRadarsForDisplay(radars)` — Order: active before inactive; RMA group before AR group; numeric ascending within a group with `RMA00` (number 0) sorted **last** (`RMA1…RMA17, RMA00, AR5…`)
- `populateProductSelect(products)` — Build product dropdown
- `setTimeRangeValues(start, end)` / `getTimeRangeValues()` — Read/write the canonical `#start-date`/`#end-date` `datetime-local` inputs (also syncs the date input + TimeWheel)
- `initTimeWheels()` / `refreshTimeWheels()` — Build the custom-range TimeWheels; re-center them after the panel becomes visible
- `updateStatus(message, duration)` — Show status toast (auto-hide after duration)
- `updateFrameCounter(current, total)` — Display "5 / 30"
- `togglePanel(panelId)` — Open/close floating panels (radar, product, time, settings)

**Dependencies:** `shared/time-wheel.js`; otherwise DOM manipulation only

**DOM Elements Modified:** Input checkboxes, dropdowns, span badges, notification divs, button states

---

### 5b. **time-wheel.js** — iOS-style HH:MM Picker

**File:** [`frontend/public/js/shared/time-wheel.js`](../../frontend/public/js/shared/time-wheel.js)

**Responsibility:** A compact, scroll-snapping time picker (two columns: hours 00–23, minutes 00–59) with a centered selection band, used by the custom time-range control. Replaces the native `datetime-local` time spinner.

**Class `TimeWheel`:**
- `new TimeWheel(container, { onChange })` — Builds the two columns; `onChange(hour, minute)` fires after the user settles on a value (scroll-end debounce ~120 ms, or tap-to-select)
- `set(hour, minute)` — Set the wheel without firing `onChange`
- `refresh()` — Re-apply scroll positions + highlight (must be called when the wheel becomes visible, since scrollTop can't be set while hidden)

**Integration:** `controls.js` owns two wheels (`startWheel`, `endWheel`). They combine with native `type="date"` inputs to drive the **hidden canonical** `#start-date`/`#end-date` `datetime-local` inputs (the single source of truth read by the rest of the app). Styling lives in `styles.css` (`.time-wheel`, `.tw-col`, `.tw-item`, `.tw-selection`).

---

### 6. **legend.js** — Legend Renderer

**File:** [`frontend/public/js/shared/legend.js`](../../frontend/public/js/shared/legend.js)

**Responsibility:** Fetches colormap data from API and renders an interactive legend showing color-to-value mappings. Displays color boxes with value labels and descriptions; supports show/hide toggle.

**Key Methods:**
- `render(productKey)` → Async function that fetches colormap via `api.js`, then builds HTML legend in DOM
- `show()` / `hide()` — Toggle legend visibility
- `clear()` — Remove all legend entries
- `render(colormap, { filterVmin, filterVmax })` — Pass filter range separately; never mutate `colormap.vmin`/`vmax` before calling

**Dependencies:** `api.js` (calls `getColormapInfo`)

**DOM Elements Modified:** `#legend-container` div with nested color-box + label items

**Rendering Format:** For each Reference entry: colored square (hex color), value, and optional title

---

### 7. **tops-cores.js** — Tops & Cores Layer

**File:** [`frontend/public/js/shared/tops-cores.js`](../../frontend/public/js/shared/tops-cores.js)

**Responsibility:** Manages a `L.layerGroup()` of `L.circleMarker` instances overlaid on the map showing convective cores and storm tops detected by radarlib.

**Key Methods:**
- `addTo(map)` — Add layer group to Leaflet map
- `updateFrame(frame)` — Fetch tops & cores for the current frame's ±2.5 min time window and render markers
- `show()` / `hide()` — Toggle layer visibility
- `setPointSize(radius)` — Update all marker radii (4–20px)

**Marker Style:**
- Cores: `fillColor: '#3b82f6'` (blue), black border
- Tops: `fillColor: '#ef4444'` (red), black border

**State persistence:** `webmet25_tops_cores_visible`, `webmet25_tops_cores_size` in `localStorage`.

**Integration:** Gated to COLMAX and COLMAXo products; toggle appears in the field settings panel.

---

### 8. **cog-browser-api.js** — [Alternative] Specialized API Client

**File:** [`frontend/public/js/shared/cog-browser-api.js`](../../frontend/public/js/shared/cog-browser-api.js)

**Responsibility:** Variant of `api.js` used by the alternative COG browser view (`cog-browser.html`). Provides the same core API functions but may include additional query/filtering capabilities for detailed COG inspection.

**Differences from `api.js`:** May support additional query parameters, pagination details, or metadata filters specific to the COG browser use case.

**Note:** This is a secondary module; primary application uses `api.js`

---

### 9. **cog-browser.js** — [Alternative] COG Browser Application

**File:** [`frontend/public/js/shared/cog-browser.js`](../../frontend/public/js/shared/cog-browser.js)

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

### **admin.html** — Admin Panel SPA

**File:** [`frontend/public/admin.html`](../../frontend/public/admin.html)

**Responsibility:** DOM skeleton for the admin panel — sidebar (OHMC logo + grouped section nav + "← Volver al mapa"), header with back button, a generic form modal, and the colormap creator modal. Served at `/admin` behind nginx HTTP Basic Auth.

**Loaded Scripts:** `js/admin.js` (which imports `js/admin-api.js`). Styled by `css/admin.css` (modern-light theme).

---

## Admin Panel

> A standalone single-page admin app for CRUD over every database table, plus a visual colormap creator/editor. Independent from the v1/v2 visualization frontend. **Auth:** temporary nginx HTTP Basic Auth on `/admin` and `/api/v1/admin/*` (see [`frontend/nginx.conf`](../../frontend/nginx.conf)); **TODO: replace with JWT.**

### A. **admin.js** — Admin Orchestrator

**File:** [`frontend/public/js/admin.js`](../../frontend/public/js/admin.js)

**Responsibility:** Renders and wires every admin section, the filter/sort system, and the colormap creator/editor.

**Sections (hash-routed):** `dashboard`, `radars`, `products`, `references`, `cogs`, `tops-cores`, `estrategias`, `volumenes`, `colormaps`, `colormap-options`.

**Navigation & return-to-map:**
- Section switches use `history.replaceState` so admin browsing **never pushes** browser history.
- The main map links here from its **Settings panel** (`#admin-link`), setting a per-tab `sessionStorage` flag `webmet25_admin_from_main`.
- **← Volver al mapa** calls `history.back()` when that flag is set (browser bfcache restores the map exactly as left), otherwise navigates to `/`.

**Filtering & sorting (Django-admin style):**
- `FILTER_CONFIG` declares per-section facets. `renderFilterBar` builds a global search + per-column facet controls; `applyRowFilters` shows/hides rows purely in the DOM (no refetch, no focus loss); `wireFilterBar` binds them. Facet types: `text` (substring), `select` (distinct values), `boolean` (Sí/No). Live result count.
- Every meaningful column header is sortable (`wireSortHeaders` + `switchSort`), with ▲/▼ indicators via `decorateSortHeaders`.
- COGs/Tops use server-side filters (paginated) plus a client quick-search over the loaded page.

**Row actions:** inline SVG icons — pencil (`ICON_EDIT`) and trash (`ICON_TRASH`), `currentColor`-tinted.

**Colormap creator/editor (`openColormapCreator`):**
- Live horizontal gradient preview (`<canvas>` + `createLinearGradient`) with **draggable stop ticks** (pointer events) overlaid; stop rows have slider + number + color swatch; product assignment as toggle chips.
- **Create:** `POST /colormap-from-hex`. **Edit:** prefills from reconstructed hex stops (`stopsToHexStops`) + currently-assigned products, then delete-recreates (`DELETE /colormap-stops/{name}` → `POST /colormap-from-hex`) and reconciles options (no update endpoint exists). Name is read-only in edit mode.
- After any change: `POST /api/v1/colormap/cache/invalidate`.

**View Stops:** shows the real rendered gradient (from `/api/v1/colormap/colors/{name}`) plus the channel stop table.

**Colormap Options:** add and edit per-product↔colormap pairings (edit = create new + delete old).

### B. **admin-api.js** — Admin REST Client

**File:** [`frontend/public/js/admin-api.js`](../../frontend/public/js/admin-api.js)

**Responsibility:** Thin client for `/api/v1/admin/*` (base `ADMIN_API_BASE`). Exposes CRUD per resource (radars, products, references, cogs, estrategias, volumenes, tops-cores), colormap stops/summaries, `createColormapFromHex`, colormap options, and `getDashboardCounts()`. Surfaces 401s as a session-expired message; unwraps `{detail}` errors.

### C. **admin.css** — Admin Styling

**File:** [`frontend/public/css/admin.css`](../../frontend/public/css/admin.css)

**Responsibility:** Modern-light theme (distinct from the dark main app): grouped gradient sidebar, sticky/zebra/hover tables, soft-shadow cards, filter bar, compact icon action buttons (`.ico`, `:has(.ico)`), and the colormap creator (gradient preview, draggable `.creator-stop-tick`, product chips).

---

## Styling

### **styles.css** — Main App Styling

**File:** [`frontend/public/css/styles.css`](../../frontend/public/css/styles.css)

**Responsibility:** Main visualization app stylesheet — dark theme (`#1a1a2e` background, light text, `#4fc3f7` accent), responsive layout, all floating panels/controls, and the custom-range **TimeWheel** styles (`.time-wheel`, `.tw-col`, `.tw-item`, `.tw-selection`).

> The **admin panel** uses a separate stylesheet, [`css/admin.css`](../../frontend/public/css/admin.css) (modern-light theme) — see the *Admin Panel* component.

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
v2/app.js (main orchestrator)
├── shared/api.js (REST client)
├── v2/map.js (Leaflet wrapper — L.imageOverlay + SVG coverage mask)
│   └── Leaflet (CDN)
├── v2/animation.js (frame player — requestAnimationFrame)
│   └── v2/map.js
├── shared/controls.js (UI handlers)
│   └── shared/time-wheel.js (custom-range HH:MM picker)
├── shared/legend.js (color scale renderer)
│   └── shared/api.js
├── shared/tops-cores.js (L.circleMarker layer)
│   └── shared/api.js
└── index.html (DOM skeleton)
    └── styles.css

cog-browser.html (alternative view)
├── shared/cog-browser-api.js
└── shared/cog-browser.js

admin.html (admin SPA, /admin, Basic Auth)
├── js/admin.js (CRUD, filters/sort, colormap creator/editor)
│   └── js/admin-api.js (/api/v1/admin/* client)
└── css/admin.css (modern-light theme)
```

---

## Data Flow Through Components (v2)

```
1. User opens http://localhost
   ↓
2. index.html loads → v2/app.js:init() called
   ├── api.getRadars() → state.radars
   ├── api.getProducts() → state.products
   ├── MapManager.init() → initialize Leaflet map + SVG coverage pane
   ├── controls.populateRadarCheckboxes(state.radars)
   ├── controls.populateProductSelect(state.products)
   ├── legend.render(defaultProduct)
   └── geolocation → auto-select nearest radars (up to 3), load COLMAX 1.5h
   ↓
3. User selects radar(s) and product
   ├── _loadFramesWithContinuity() called (never stops animation)
   │   ├── api.getCogs(radars, product, strategy, volNrs, timeRange)
   │   ├── group COGs by timestamp bucket (±5 min)
   │   ├── pre-fetch frame images: GET /frames/{id}/image.png
   │   └── animator.setFrames(stagingFrames)  ← atomic swap
   └── legend.render(selectedProduct)
   ↓
4. Animation loop (requestAnimationFrame)
   ├── For each tick:
   │   ├── animator advances frameIndex
   │   ├── MapManager.showFrame(index)  ← sets L.imageOverlay URL
   │   ├── controls.updateFrameCounter()
   │   └── topsCoresLayer.updateFrame(frame)  ← fire-and-forget
   └── Continues uninterrupted during field/colormap changes
   ↓
5. User changes field, colormap, or range filter
   └── _loadFramesWithContinuity() → background reload → atomic swap
   ↓
6. Coverage mode toggle (C+D ↔ VIG)
   ├── Updates active mode → different volNrs
   └── _loadFramesWithContinuity() with new volNrs
   ↓
7. Live refresh (every 5 min)
   └── refreshLiveWindow() → incremental diff → animator.setFrames()
```

---

## State Lifecycle

On page load `init()` bootstraps the state, fetches data, and starts the animation if radars are auto-selected via geolocation. All subsequent changes (field, colormap, time window, coverage mode) go through `_loadFramesWithContinuity()` which guarantees animation never stops.

---

## Browser Compatibility

- **Chrome/Edge:** 88+
- **Firefox:** 78+
- **Safari:** 14+
- **Mobile:** Any with ES6 module support (iOS Safari 15+, Android Chrome 80+)

**Requirements:** ES6 modules, Fetch API, Leaflet 1.9.4 (CDN), Canvas API.

---

## Key Design Principles

1. **No Build Tool:** Pure ES6 modules served directly; no webpack/vite
2. **No Framework:** Vanilla JavaScript; direct DOM manipulation
3. **Single-Responsibility Modules:** Each `.js` file has one clear purpose
4. **Global State:** `state` object in `v2/app.js` is the source of truth
5. **Animation Continuity:** All data changes go through `_loadFramesWithContinuity()` — animation never stops mid-load
6. **Async/Await:** Modern async patterns throughout
7. **Responsive Design:** Mobile-first CSS, dark theme

---

## Known Limitations & Future Work

- ❌ No offline support or service worker caching
- ❌ No WebSocket real-time updates (polls every 5 minutes instead)
- ❌ Module coupling via global `state` object (could refactor to event emitter pattern)
- ✅ RESOLVED: Frame pre-loading (v2 pre-fetches all frames before animating)

---

**Document Version:** 2.1.0  
**Last Updated:** June 4, 2026
