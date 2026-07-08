# DATA_FLOW.md — WebMet25 Data Consumption Pipeline

> **Purpose:** Explain how WebMet25 ingests, processes, and displays radar data produced by radarlib.
> **Read this before changing the indexer or API.**

---

## 1. Overview

WebMet25 is a **data consumer** in the radar/meteorology system. It receives Cloud-Optimized GeoTIFF (COG) files and Tops & Cores GeoJSON files from radarlib, indexes them into a PostgreSQL/PostGIS database, and serves them via REST API to an interactive web frontend.

```
radarlib (producer)
    ↓
    GeoTIFF files  @ ROOT_RADAR_PRODUCTS_PATH/{RADAR_NAME}/YYYY/MM/DD/
    GeoJSON files  @ TOPS_AND_CORES_DIR/{radar_code}/YYYY/MM/DD/
    ↓
webmet25 (consumer)
    ├── COGWatcher: watches, parses, extracts metadata → DB (RadarCOG)
    ├── TopsAndCoresWatcher: watches, parses, counts features → DB (TopsAndCores)
    ├── API: queries DB, renders full-image frames (/frames) and tiles (/tiles)
    └── Frontend v2: L.imageOverlay animation + SVG coverage mask
```

---

## 2. Data Ingestion Layer: The Indexer

### 2.1 Entry Point

**File:** [`indexer/indexer/main.py`](../indexer/indexer/main.py)

**Responsibility:**
- Waits for PostgreSQL to become available
- Starts `TopsAndCoresWatcher` in a background thread (scans `TOPS_AND_CORES_DIR`)
- Starts `COGWatcher` in the main thread (scans `ROOT_RADAR_PRODUCTS_PATH`)

### 2.2 File System Scanning: COGWatcher

**File:** [`indexer/indexer/watcher.py`](../indexer/indexer/watcher.py)

**Responsibility:**
- Monitors `ROOT_RADAR_PRODUCTS_PATH` every `SCAN_INTERVAL` seconds (default: 30 s)
- First run: full scan. Subsequent runs: incremental (files modified in last 5 min + overlap)
- For each `.tif` file: parses filename → extracts COG metadata via rasterio → inserts/updates `RadarCOG`
- One bad file does not stop the entire scan
- If `MARK_MISSING_FILES=true` (default): marks previously-indexed files as `MISSING` if no longer on disk
- **`update_radar_activity()`:** Called at end of every scan. Sets `Radar.is_active = True/False` based on whether a recent `AVAILABLE` COG exists within the last `RADAR_ACTIVE_THRESHOLD_HOURS` hours

**Configuration:** [`indexer/indexer/config.py`](../indexer/indexer/config.py)

| Env Var | Default | Description |
|---------|---------|-------------|
| `WATCH_PATH` | `/product_output` | Root path to scan for COG files |
| `SCAN_INTERVAL` | `30` | Seconds between scans |
| `FILE_PATTERN` | `*.tif` | Glob pattern for COG files |
| `COMPUTE_STATS` | `true` | Compute per-band min/max/mean statistics |
| `COMPUTE_CHECKSUM` | `false` | Compute SHA-256 checksum on index |
| `RADAR_ACTIVE_THRESHOLD_HOURS` | `2` | Hours of recency to consider a radar active |
| `MARK_MISSING_FILES` | `true` | Mark indexed files as MISSING if not found |
| `RADAR_CODES` | *(all)* | CSV or JSON array to restrict which radars to index |
| `TOPS_AND_CORES_DIR` | `/tops_and_cores` | Root path to scan for GeoJSON tops & cores files |
| `LOGS_PATH` | `/logs` | Log output directory |

### 2.2b TopsAndCores Scanning: TopsAndCoresWatcher

**File:** [`indexer/indexer/watcher.py`](../indexer/indexer/watcher.py)

- Monitors `TOPS_AND_CORES_DIR` recursively for `*_TOPS_CORES.geojson` files
- For each new file: parses filename → opens GeoJSON and counts cores, tops, total features → inserts/updates `TopsAndCores` record
- Marks files as `MISSING` if previously indexed but no longer present

### 2.3 Filename Parsing: COGFilenameParser

**File:** [`indexer/indexer/parser.py`](../indexer/indexer/parser.py)

**Pattern 0 — Current production format:**
```
{RADAR}_{strategy}_{vol_nr}_{YYYYMMDDTHHMMSSZ}_{FIELD}[o].tif
```
Examples:
```
RMA1_0315_01_20260401T205000Z_DBZH.tif    # Filtered reflectivity, vol 01
RMA1_0315_01_20260401T205000Z_DBZHo.tif   # Unfiltered (raw), vol 01
RMA1_0315_04_20260401T205000Z_COLMAX.tif  # Column max, vol 04 (vigilant)
```

**Pattern 1 — Legacy format (backward compatibility only):**
```
{RADAR}_{YYYYMMDDTHHMMSSZ}_{FIELD}[o]_{elev}.tif
```
Example: `RMA1_20260401T205000Z_DBZHo_00.tif`
(Indexed with `strategy=None`, `vol_nr=None`. A WARNING is logged.)

**TopsAndCoresFilenameParser** parses `{radar_code}_{strategy}_{vol_nr}_{YYYYMMDDHHMMSS}_TOPS_CORES.geojson` (no `T` or `Z` in timestamp).

### 2.4 Metadata Extraction: COGRegistrar

**File:** [`indexer/indexer/registrar.py`](../indexer/indexer/registrar.py)

Data extracted from each GeoTIFF:
- **File system:** `file_size_bytes`, `file_mtime`
- **GeoTIFF profile (rasterio):** `width`, `height`, `num_bands`, `dtype`, `crs`, `nodata_value`, `compression`, `resolution_x/y`
- **GeoTIFF tags (radarlib):** `cog_cmap` (`radarlib_cmap`), `cog_vmin` (`radarlib_vmin`), `cog_vmax` (`radarlib_vmax`), `field_name`, `timestamp`
- **Optional statistics (if `COMPUTE_STATS=true`):** `data_min`, `data_max`, `data_mean`, `valid_pixel_count`
- **Spatial (PostGIS):** bounds reprojected to WGS84 → stored as `bbox` POLYGON

**TopsAndCoresRegistrar** opens the GeoJSON, counts features by `type` property (`core` vs `top`), and upserts the `TopsAndCores` record.

---

## 3. Database Schema: Data Model

**All models defined in:** [`database/radar_db/models.py`](../database/radar_db/models.py)

### 3.1 Core Tables

#### **Radar** (Reference Data)
```python
code: str (PK)                # "RMA1", "AR5"
title: str
description: str (nullable)
center_lat, center_long: Decimal
img_radio: int                # Coverage radius in km
is_active: bool               # Updated by update_radar_activity()
detail_view_enabled: bool     # Enables the one-radar detail page (radar.html)
point1_lat, point1_long       # Bounding box corner 1
point2_lat, point2_long       # Bounding box corner 2
created_at, updated_at: DateTime(tz)
```

#### **RadarProduct** (Reference Data)
```python
id: int (PK)
product_key: str (UNIQUE)     # "DBZH", "DBZHo", "COLMAX"
product_title: str
enabled: bool
see_in_open: bool             # Show in unfiltered view
min_value, max_value: float   # Authoritative display range
unit: str                     # "dBZ", "percent", etc.
default_cmap: str (nullable)  # DB-canonical default colormap name
```

#### **RadarCOG** (Main Data Table — Indexed COG Files)
```python
id: int (PK)

# Foreign Keys
radar_code: str (FK → Radar.code)
product_id: int (FK → RadarProduct.id)
estrategia_code: str (FK → Estrategia.code, nullable)  # NULL for legacy files

# Observation
observation_time: DateTime(tz) (INDEX)
polarimetric_var: str(16)     # Exact field name including 'o' suffix, e.g. "DBZHo"
elevation_angle: float        # Legacy files only; NULL for production files
vol_nr: str(16)               # "01", "02", "04"; NULL for legacy files
radar_coverage_m: float       # Coverage radius in metres (from COG tag); NULL for legacy

# File
file_path: str (UNIQUE)
file_name: str
file_size_bytes: int
file_mtime: DateTime(tz)
file_checksum: str(64)        # SHA-256 (populated if COMPUTE_CHECKSUM=true)

# GeoTIFF properties
crs: str                      # "EPSG:3857" (Web Mercator — production standard)
width, height: int
num_bands: int
dtype: str                    # "float32"
resolution_x, resolution_y: float
nodata_value: float
compression: str

# Rendering metadata (from radarlib GeoTIFF tags)
cog_data_type: str            # "raw_float", "rgba", "unknown"
cog_cmap: str                 # Colormap name, e.g. "grc_th"
cog_vmin, cog_vmax: float     # Data range for colormap

# Optional statistics
data_min, data_max, data_mean: float
valid_pixel_count: int

# Spatial
bbox: Geometry('POLYGON', srid=4326)  # WGS84 bounding box

# Status
status: COGStatus enum        # AVAILABLE, MISSING, ERROR, PENDING, PROCESSING, ARCHIVED
error_message: Text
show_me: bool

# Unique constraint: (radar_code, product_id, observation_time, elevation_angle, vol_nr)
# NULL vol_nr rows (legacy) are independent because NULL != NULL in PostgreSQL
```

#### **TopsAndCores** (Indexed GeoJSON Files)
```python
id: int (PK)
radar_code: str (FK → Radar.code)
observation_time: DateTime(tz) (INDEX)
file_path: str (UNIQUE)
file_name: str
feature_count: int            # Total features (cores + tops)
core_count: int
top_count: int
status: COGStatus             # AVAILABLE or MISSING
strategy: str (nullable)      # "0315"
vol_nr: str (nullable)        # e.g. "00"
created_at, updated_at: DateTime(tz)
```

#### **Reference** (Color Scale Entries for Legends)
```python
id: int (PK)
product_id: int (FK → RadarProduct.id, INDEX)
title, description, unit: str
value: float                  # e.g. 10.0 dBZ
color: str(7)                 # "#ff0000"
color_font: str(7)            # "#ffffff"
```

#### **Estrategia / Volumen** (Scanning Strategy Definitions)
```python
# Estrategia
code: str (PK)                # "0315"
description: str
volumenes: M:M via estrategia_volumen association table

# Volumen
id: int (PK)
value: int                    # Volume number integer
```

#### **ColormapStop** (DB-Backed Colormaps)
```python
id: int (PK)
cmap_name: str               # e.g. "grc_th"
channel: str                  # "r", "g", or "b"
position: float               # 0.0 – 1.0 within the color range
val_left, val_right: float    # Physical data values for this segment
sort_order: int
is_system: bool               # System colormaps cannot be deleted (→ 403)
# Index: (cmap_name, channel, sort_order)
```

8 system colormaps seeded: `grc_th`, `grc_th2`, `grc_rain`, `grc_g`, `grc_rho`, `grc_zdr`, `grc_vrad`, `Theodore16`.

#### **ProductColormapOption** (Product ↔ Colormap Pairings)
```python
id: int (PK)
product_key: str (FK → RadarProduct.product_key)
cmap_name: str
# UniqueConstraint: (product_key, cmap_name)
```

### 3.2 Indexes (Performance)

```sql
-- radar_cogs
idx_radar_cog_radar_code         ON radar_cogs(radar_code)
idx_radar_cog_product_id         ON radar_cogs(product_id)
idx_radar_cog_observation_time   ON radar_cogs(observation_time)
idx_radar_cog_status             ON radar_cogs(status)
idx_radar_cog_file_path          ON radar_cogs(file_path)  -- UNIQUE
idx_radar_cog_vol_nr             ON radar_cogs(vol_nr)
idx_cog_radar_product_time       ON radar_cogs(radar_code, product_id, observation_time, vol_nr)
idx_cog_bbox                     ON radar_cogs USING GIST (bbox)

-- tops_and_cores
idx_tops_cores_observation_time  ON tops_and_cores(observation_time)
idx_tops_cores_radar_code        ON tops_and_cores(radar_code)

-- references
idx_reference_product_id         ON references(product_id)

-- colormap_stops
idx_cmap_stop_name_channel_order ON colormap_stops(cmap_name, channel, sort_order)
```

### 3.3 Initial Data: Seeds

**File:** [`database/seed_data/initial_data.json`](../database/seed_data/initial_data.json)

Seeds 21 radars (AR5, AR7, AR8, RMA1–RMA18, RMA00), 20 products (COLMAX, COLMAXo, DBZH, DBZHo, RHOHV, RHOHVo, ZDR, ZDRo, VRAD, VRADo, WRAD, WRADo, KDP, KDPo, PHIDP, PHIDPo, DBZV, DBZVo, MOSAICO, MOSAICOo), ~80 references, 5 volumenes, 11 estrategias, 46 product-colormap option pairings, and 8 system colormaps.

---

## 4. API Layer: Data Query & Serving

### 4.1 API Router Architecture

**Entry point:** [`api/app/main.py`](../api/app/main.py)

```python
app.include_router(radars_router,     prefix="/api/v1")
app.include_router(products_router,   prefix="/api/v1")
app.include_router(cogs_router,       prefix="/api/v1")
app.include_router(tiles_router,      prefix="/api/v1")
app.include_router(colormap_router,   prefix="/api/v1")
app.include_router(frames_router,     prefix="/api/v1")
app.include_router(tops_cores_router, prefix="/api/v1")
app.include_router(admin_router,      prefix="/api/v1")
```

Middleware: `X-Process-Time` response header. Global exception handler returns structured JSON (never a raw 500 traceback).

### 4.2 Radars Endpoint

**File:** [`api/app/routers/radars.py`](../api/app/routers/radars.py)

- `GET /radars` — query param `active_only: bool = True`
- `GET /radars/{radar_code}` — 404 if not found

**`RadarResponse`** fields: `code`, `title`, `description`, `center_lat`, `center_long`, `img_radio`, `is_active`, `detail_view_enabled`, `extent` (computed bbox dict).

### 4.3 Products Endpoint

**File:** [`api/app/routers/products.py`](../api/app/routers/products.py)

- `GET /products` — params: `enabled_only: bool = True`, `vol_nr: List[str]` (repeatable), `strategy: str`
- `GET /products/{product_key}` — 404 if not found
- `GET /products/{product_key}/colormap` — **deprecated**; returns legacy `ColormapResponse` from Reference table. Use `/colormap/info/{product_key}` instead.

### 4.4 COGs Endpoint

**File:** [`api/app/routers/cogs.py`](../api/app/routers/cogs.py)

- `GET /cogs` — paginated list; params: `radar_code`, `product_key`, `strategy`, `vol_nr` (repeatable), `start_time`, `end_time`, `page`, `page_size (1–200, default 50)`
- `GET /cogs/latest` — most recent available COG; params: `radar_code`, `product_key`, `vol_nr`, `strategy`
- `GET /cogs/timeline` — available timestamps; params: `radar_code`, `product_key`, `hours (1–48, default 6)`; returns `TimelineResponse`
- `GET /cogs/{cog_id}` — get one COG by database ID

**`COGResponse`** fields: `id`, `radar_code`, `product_key`, `product_id`, `observation_time`, `elevation_angle`, `file_path`, `file_name`, `data_min`, `data_max`, `bbox`, `tile_url`, `cog_data_type`, `cog_cmap`, `cog_vmin`, `cog_vmax`, `strategy`, `vol_nr`, `radar_coverage_m`.

`product_key` filtering uses exact match on `polarimetric_var` (respects `o` suffix) OR on `RadarProduct.product_key` for base-name matches.

### 4.5 Tiles Endpoint (v1 — Web Mercator Tiles)

**File:** [`api/app/routers/tiles.py`](../api/app/routers/tiles.py)

- `GET /tiles/{cog_id}/{z}/{x}/{y}.png` — render 256×256 tile; params: `colormap`, `vmin`, `vmax`; ETag/conditional GET → 304; CPU rendering offloaded to thread pool executor
- `GET /tiles/by-params/{radar_code}/{product_key}/{timestamp}/{z}/{x}/{y}.png` — tile by radar+product+timestamp; `timestamp` = ISO string or `"latest"`
- `GET /tiles/{cog_id}/metadata` — returns `cog_data_type`, `cmap`, `vmin`, `vmax`, `product_key`, `available_colormaps`
- `GET /tiles/cache/stats` — L1 LRU + L2 Redis cache statistics (monitoring)

Cache: `TTLCache(maxsize=500, ttl=300 s)` for COG metadata. Cache-Control: recent COGs → `max-age=60`; COGs older than 10 min → `max-age=86400, immutable`.

### 4.6 Frames Endpoint (v2 — Full COG Image)

**File:** [`api/app/routers/frames.py`](../api/app/routers/frames.py)

Returns the entire COG raster as a single georeferenced RGBA PNG. Used by the v2 frontend (`L.imageOverlay`) to replace ~10 tile requests per frame with a single request.

**Endpoint:** `GET /frames/{cog_id}/image.png`

**Query parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `colormap` | str | from COG tag | Colormap name |
| `vmin` / `vmax` | float | from COG tag | Data-to-color scaling range |
| `filter_vmin` / `filter_vmax` | float | null | Alpha-mask pixels outside range (transparent) |
| `smooth` | bool | false | Apply Gaussian blur before colormap |
| `smooth_sigma` | float | 0.8 | Gaussian kernel sigma (0.1–3.0); ignored when `smooth=false` |

**Response headers:** `X-Bbox-West`, `X-Bbox-South`, `X-Bbox-East`, `X-Bbox-North` (WGS84), `X-Width`, `X-Height`, `ETag`, `Cache-Control`.

**Caching:** L1 LRU `(maxsize=750)` in-process + L2 Redis (key prefix `frame:`). Cache key includes `(file_path, colormap, vmin, vmax, filter_vmin, filter_vmax, smooth, smooth_sigma)`. When `smooth=false` the sigma slot is `None`, so all unsmoothed requests share the same cache entry.

**Gaussian smoothing:** Implemented in [`api/app/services/smoothing.py`](../api/app/services/smoothing.py) via `scipy.ndimage.gaussian_filter`. Applied to the raw float data array **before** colormap lookup — smoothing operates on physical values, not RGBA pixels.

**Error:** Returns 503 on transient `RasterioIOError` (retryable); 404 if COG not found in DB.

### 4.7 Tops & Cores Endpoints

**File:** [`api/app/routers/tops_cores.py`](../api/app/routers/tops_cores.py)

- `GET /tops-cores` — params: `radar_codes[]` (required, repeatable), `time_from` (required), `time_to` (required), `status (default: "available")`; returns empty list (never 404) when no records match; `Cache-Control: no-cache`
- `GET /tops-cores/{record_id}/features` — returns raw GeoJSON `FeatureCollection` as `application/geo+json`; ETag/conditional GET → 304; `Cache-Control: public, max-age=86400, immutable`; marks record `MISSING` in DB if file not found on disk

**`TopsAndCoresRecord`** response: `id`, `radar_code`, `observation_time`, `file_name`, `feature_count`, `core_count`, `top_count`, `status`, `strategy`, `vol_nr`.

### 4.8 Colormap Endpoints

**File:** [`api/app/routers/colormap.py`](../api/app/routers/colormap.py)

Backed by `ColormapService` — a thread-safe singleton with a 5-minute TTL cache. Resolution order: DB (`colormap_stops`) → hardcoded builders in `utils/colormaps.py` → PyART → matplotlib.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/colormap/names` | List all colormap names defined in DB |
| GET | `/colormap/options` | Map of `product_key → [cmap_names]` |
| GET | `/colormap/defaults` | Map of `product_key → default_cmap_name` |
| GET | `/colormap/colors/{cmap_name}` | Hex color list (param: `steps=256`, range 2–1024) |
| GET | `/colormap/info/{product_key}` | Full info: `colormap`, `vmin`, `vmax`, `colors[]`, `ticks[]`, `available_colormaps[]`; optional `?colormap=` override |
| POST | `/colormap/cache/invalidate` | Flush in-process cache after DB edits |

### 4.9 Admin API & Panel

**Router:** [`api/app/routers/admin.py`](../api/app/routers/admin.py) — base path `/api/v1/admin`  
**Frontend:** [`frontend/public/admin.html`](../frontend/public/admin.html) + [`js/admin.js`](../frontend/public/js/admin.js), served at `/admin`

**Authentication (temporary):** Both `/admin` and `/api/v1/admin/` are behind **nginx HTTP Basic Auth** (`admin.htpasswd`). The public `/api/v1/*` API stays open. ⚠️ TODO: replace with JWT before production.

**Endpoint groups:**

| Resource | Operations |
|----------|-----------|
| Radars | `GET list`, `GET /{code}`, `POST → 201`, `PUT /{code}`, `PATCH /{code}`, `DELETE /{code} → 204` |
| Products | `GET list`, `GET /{id}`, `POST → 201`, `PUT /{id}`, `PATCH /{id}`, `DELETE /{id} → 204` |
| References | `GET list` (`?product_id`), `GET /{id}`, `POST → 201`, `PUT /{id}`, `DELETE /{id} → 204`, `DELETE bulk by product_id` |
| COGs | `GET paginated+filtered`, `GET /{id}`, `PATCH /{id}` (status only), `DELETE /{id} → 204`, `DELETE bulk` (at least one filter required) |
| Estrategias | `GET list`, `GET /{code}`, `POST → 201`, `PUT /{code}`, `DELETE /{code} → 204` |
| Volumenes | `GET list`, `GET /{id}`, `POST → 201`, `PUT /{id}`, `DELETE /{id} → 204` |
| Tops & Cores | `GET paginated`, `GET /{id}`, `PATCH /{id}` (status only), `DELETE /{id} → 204`, `DELETE bulk` |
| Colormap Stops | `GET summaries`, `GET /{name}` (all rows), `POST → 201` (one row), `DELETE /{name}` (system → 403) |
| Colormap from Hex | `POST → 201`: create from `{cmap_name, stops:[{position, color}], product_keys[]}`; **409 if name already exists** (no upsert) |
| Colormap Options | `GET` (`?product_key`), `POST → 201`, `DELETE /{id} → 204` |

**Edit pattern (no update endpoint for colormaps):** delete-then-recreate — `DELETE /colormap-stops/{name}` → `POST /colormap-from-hex` with same name → reconcile options → `POST /colormap/cache/invalidate`.

**Panel features:** Django-admin-style filtering (global search + per-column `text`/`select`/`boolean` facets, live count, sortable columns), inline pencil/trash icon row actions, visual colormap creator/editor with draggable gradient stops.

---

## 5. Frontend Layer: Data Display & State

> **v2 is the current production standard.** v1 (L.tileLayer + /tiles endpoint) is preserved in `js/v1/` for reference only. All new development targets v2.

### 5.0 Frontend File Structure

```
frontend/public/
├── index.html              # Multi-radar map SPA shell
├── radar.html              # One-radar detail page (radar.html?code=AR5)
├── admin.html              # Admin SPA shell
├── cog-browser.html        # Alternative COG file browser
├── css/
│   ├── styles.css          # Main app dark theme
│   └── admin.css           # Admin modern-light theme
└── js/
    ├── admin.js            # Admin SPA orchestrator
    ├── admin-api.js        # Admin REST client (/api/v1/admin/*)
    ├── shared/             # Shared by v1 and v2
    │   ├── api.js          # REST API client (all public endpoints)
    │   ├── controls.js     # UIControls class (radar list, time wheels, badges)
    │   ├── legend.js       # LegendRenderer class
    │   ├── tops-cores.js   # TopsCoresLayer (L.circleMarker)
    │   └── time-wheel.js   # iOS-style HH:MM scroll picker
    └── v2/                 # Current production frontend
        ├── app.js          # Multi-radar map orchestrator (2500+ lines)
        ├── radar-app.js    # One-radar page orchestrator (1660+ lines)
        ├── map.js          # MapManager with L.imageOverlay + SVG coverage mask
        ├── animation.js    # AnimationController with requestAnimationFrame
        ├── radar-utils.js  # Shared helpers (groupCogsByTimestamp, geolocation, etc.)
        └── constants.js    # COVERAGE_MODES, MS_PER_HOUR, defaults
```

### 5.1 Global State: Multi-Radar Map (`v2/app.js`)

The `state` object in `v2/app.js` is the single source of truth for the multi-radar map:

```javascript
const state = {
    radars: [],                    // From GET /radars
    products: [],                  // From GET /products
    cogs: [],                      // COG objects for current selection
    selectedRadars: [],            // User-selected radar codes
    selectedProduct: null,         // Current product key (includes 'o' suffix)
    showUnfilteredProducts: false, // Show unfiltered ('o') products toggle
    showInactiveRadars: false,
    activeTimeWindowHours: 1.5,    // Default 90 min
    selectedColormap: null,
    currentVmin: null,
    currentVmax: null,
    fieldOpacity: {},              // { radarCode: 0–1 }
    mapManager: null,              // MapManager instance
    animator: null,                // AnimationController instance
    ui: null,                      // UIControls instance
    legend: null,                  // LegendRenderer instance
    animationMode: null,           // "live" | "replay" | null
    liveHours: null,
    liveRefreshInterval: null,
    radarStatusRefreshInterval: null,
    topsCoresLayer: null,          // TopsCoresLayer instance
    topsCoresVisible: false,
    topsCoresPointSize: 8,
    smoothingEnabled: false,       // Gaussian smooth toggle
    smoothingSigma: 0.8,
    coverageModeId: 'cd',          // 'cd' (C+D) or 'vig' (Vigilancia)
    resumePending: false,          // Deferred resume after incremental load
};
```

### 5.2 Coverage Modes

Defined in `v2/constants.js`:

```javascript
const COVERAGE_MODES = [
    {
        id: 'cd',
        label: 'C+D',
        volNrs: ['01', '02'],
        strategy: '0315',
        filteredFieldsAvailable: true,
        defaultProduct: 'COLMAXo',
    },
    {
        id: 'vig',
        label: 'VIG',
        volNrs: ['04'],
        strategy: '0315',
        filteredFieldsAvailable: false,  // No filtered products in VIG mode
        defaultProduct: 'DBZHo',
    },
];
```

Mode is persisted to `localStorage` key `webmet25_coverage_mode`. COG queries pass the active mode's `volNrs` as `?vol_nr=` params. Switching modes triggers a full `_loadFramesWithContinuity()` reload.

### 5.3 Data Flow: Initialization (Multi-Radar Map)

1. `app.init()` — waits for Leaflet, creates `MapManager`, `AnimationController`, `UIControls`, `LegendRenderer`, `TopsCoresLayer`
2. `loadInitialData()` — `GET /radars` + `GET /products`; restores `coverageModeId` from localStorage
3. `controls.populateRadarCheckboxes(radars, showInactive)` — builds radar list with `›` drill-down buttons
4. Geolocation — browser geolocation → nearest 3 radars auto-selected → `loadLastNHours(1.5)` with `COLMAX`
5. Live refresh timer starts (default 5 min)

### 5.4 COG Loading & Animation Continuity

All data loads go through `_loadFramesWithContinuity(loadFn, opts)`:

1. `_fetchTimeRangeFrames()` — pure data fetch: `api.getCogsForTimeRange()` per selected radar, `groupCogsByTimestamp()` into buckets
2. Animation continues running from the current buffer (never stops)
3. `mapManager.updateParams(cogsByFrame, productKey, params, onProgress)` — pre-fetches all frame images in the background by calling `GET /frames/{id}/image.png` for each COG
4. `animator.updateFrames(frames, productKey)` — atomic swap; rAF loop picks up new frames on next tick

> ⚠️ **Invariant:** Never call `animator.stop()`, `animator.reset()`, or clear layers before new frames are staged. All data loading must go through `_loadFramesWithContinuity`.

### 5.5 Map Layer Management (`v2/map.js`)

**`MapManager`** manages Leaflet map + frame image cache + SVG coverage mask:

- `_frameImages`: `Array<Map<overlayKey, ImageEntry>>` — outer array indexed by frame, inner Map keyed by `${radarCode}__${productKey}`
- `_overlays`: `Map<overlayKey, L.imageOverlay>` — Leaflet overlays (one per radar+product, shared across frames)
- Each frame image is fetched via `fetch()` (to read `X-Bbox-*` response headers), stored as blob → object URL
- `loadFrames(cogsByFrame, productKey, params, onProgress)` — parallel fetch of all frames
- `showFrame(frameIndex, radarCodes, productKey)` — hides all overlays, shows the relevant ones at current opacity; this is the animation hot path
- `updateParams(cogsByFrame, productKey, params, onProgress)` — shadow-loads into new structures, then atomically swaps `_frameImages` (no animation interruption)
- `addRadarToFrame()` / `removeFrame()` — incremental splicing for add/remove radar without full reload

**Coverage mask SVG:**
- Rendered inside `coverageMaskPane` (Leaflet pane, z-index 300)
- Dark `<rect>` with `<mask>` that punches transparent ellipses per radar coverage area
- Redraws on `moveend` and `zoomend` only (not every frame — zero animation lag)
- `addRadarCoverage(code, lat, lng, radius_m)` / `removeRadarCoverage(code)` / `setRadarCoverageRings(code, rings)` / `setCoverageOpacity(opacity)`

**Basemaps:** `argenmap`, `argenmap_gris`, `argenmap_topo`, `argenmap_oscuro`, `argenmap_hibrido` (IGN Argentina). Default: `argenmap`. Persisted to `webmet25_selected_basemap`. Always use `MapManager.setBasemap(key)` — never manipulate `_baseLayer` directly.

### 5.6 Animation Controller (`v2/animation.js`)

**`AnimationController`** uses `requestAnimationFrame` (not `setInterval`):

- `_frames`: current frame array; `_currentFrame`: pointer; `_playing`: boolean; `_speedMultiplier`: 0.5–2.0
- `play()` / `pause()` / `toggle()` — start/stop rAF loop (`_scheduleLoop`)
- `updateFrames(frames, productKey, currentIndex)` — atomically replaces the frame list; clamps pointer; restarts loop if was playing
- `_tick()` — advances `_currentFrame`, calls `_showCurrentFrame()` → `mapManager.showFrame()` + fires `_onFrameChange` callback
- `_onFrameChange` callback in `app.js`: updates time display, frame counter, tops & cores layer

### 5.7 One-Radar Detail Page (`radar.html` + `v2/radar-app.js`)

`radar.html?code=AR5[&field=DBZHo]` — single-radar multi-layer compositor. Always operates in C+D mode.

**Layer object shape:**
```javascript
{
    id, productKey, productTitle,
    opacity,           // 0–1 (default 1.0 for first layer, 0.7 for subsequent)
    visible,
    colormap,          // From api.getColormapInfo()
    selectedColormap,  // Override (null = product default)
    vmin, vmax,        // Alpha-mask filter bounds (null = no filter)
    smoothingEnabled, smoothingSigma,
    coverageRadius,    // Metres from COG tag (null = radar.img_radio * 1000)
    zIndex,
    settingsExpanded,
}
```

**`showAllLayersAtFrame(frameIndex)`** — called on every animation tick instead of the single-product `showFrame`. Composites all visible layers in z-order with per-layer opacity.

**Range filter invariant:** `vmin`/`vmax` sent to `/frames` are alpha-masking bounds only (pixels outside range → transparent). Colormap normalization always uses product defaults from `colormap_for_field()` — never changed by the filter. UI inputs are pre-populated with `colormap.vmin/vmax` so clicking "Aplicar" without narrowing has no visual effect.

### 5.8 Tops & Cores Layer (`shared/tops-cores.js`)

**`TopsCoresLayer`** manages `L.layerGroup()` in `topsCoresPane` (z-index 450):

- `updateFrame(frame)` — fire-and-forget: aborts previous in-flight, fetches `/tops-cores?time_from=...&time_to=...&radar_codes=...` (±2.5 min window), then parallel `GET /tops-cores/{id}/features`, renders `L.circleMarker`
- Stale responses older than the latest rendered timestamp are dropped
- Cores: `fillColor: '#3b82f6'` (blue); Tops: `fillColor: '#ef4444'` (red); both: black border
- Gated to COLMAX and COLMAXo products

### 5.9 Legend Renderer (`shared/legend.js`)

`LegendRenderer.render(colormapData, filterOptions)`:
- Builds gradient bar (32 CSS stops) from `colormapData.colors[]` array
- Tick source priority: `colormapData.ticks` (Reference rows) → 5 auto-spaced values
- Filter range displayed as bracket markers (does not mutate `colormap.vmin/vmax`)
- `buildGradient(colors, startFraction, endFraction)` maps the filter window into the full colormap bar

### 5.10 Time Display

Frame timestamps are formatted in `America/Argentina/Buenos_Aires` timezone. The `setTimeDisplay` method in `UIControls` uses this locale explicitly.

---

## 6. Data State Lifecycle

### 6.1 Startup Sequence

```
Docker compose up
│
├── PostgreSQL starts
├── Redis starts
│
├── db-init container
│   ├── python -m radar_db.manage init  (create tables, stamp Alembic head)
│   ├── python -m radar_db.manage seed  (insert initial data)
│   └── exits (restart: "no")
│
├── Indexer starts
│   ├── Waits for DB
│   ├── Starts TopsAndCoresWatcher (background thread)
│   └── Enters main loop: every 30 s scan ROOT_RADAR_PRODUCTS_PATH
│       ├── Parse filename → radar_code, product_key, vol_nr, strategy
│       ├── Extract metadata via rasterio
│       ├── INSERT/UPDATE RadarCOG (status = AVAILABLE)
│       └── update_radar_activity()
│
├── API starts (FastAPI + Uvicorn)
│   ├── Initializes Redis connection
│   ├── Configures GDAL env
│   └── Serves endpoints
│
└── Frontend loads @ http://localhost
    ├── GET /api/v1/radars → populate radar list
    ├── GET /api/v1/products → populate product selector
    ├── Geolocation → auto-select 3 nearest radars
    ├── GET /api/v1/cogs → fetch latest frames
    ├── Parallel GET /frames/{id}/image.png for each COG
    └── Start animation + live refresh timer
```

### 6.2 COG Lifecycle in DB

```
File created @ ROOT_RADAR_PRODUCTS_PATH/RMA1/2026/04/01/RMA1_0315_01_20260401T205000Z_DBZHo.tif
    ↓
Indexer scan (30 s interval)
├── Filename parsed: radar=RMA1, strategy=0315, vol_nr=01, field=DBZHo
├── Validate radar in DB; validate product in DB
└── INSERT RadarCOG → status = AVAILABLE
    ↓
API: GET /cogs?radar_code=RMA1&product_key=DBZHo&vol_nr=01
├── Filter: status=AVAILABLE, vol_nr=01
└── Return COGResponse (id, file_path, cog_cmap, cog_vmin, cog_vmax, bbox, strategy, vol_nr, radar_coverage_m)
    ↓
Frontend: GET /frames/{cog_id}/image.png?colormap=grc_th&vmin=5&vmax=75
├── L1 LRU cache miss → L2 Redis miss → render
│   ├── Open file with rasterio
│   ├── Read float32 data array
│   ├── Optional: scipy.ndimage.gaussian_filter (if smooth=true)
│   ├── Apply colormap via matplotlib → RGBA array
│   └── Encode to PNG via Pillow
├── Return PNG + X-Bbox-* headers
└── Store in L1 LRU + L2 Redis
    ↓
MapManager: L.imageOverlay.setUrl(objectUrl) — shows PNG over WGS84 bounds
    ↓
Animation: rAF loop → showFrame(index) → display current frame
```

### 6.3 Status Transitions

```
COGStatus enum:
  AVAILABLE  ◄── Default on INSERT
  MISSING    ◄── File was indexed but no longer exists on disk
  ERROR      ◄── Metadata extraction failed during indexing
  PENDING    (reserved, not currently used)
  PROCESSING (reserved, not currently used)
  ARCHIVED   (reserved, not currently used)
```

The `/frames` and `/tiles` endpoints mark a COG `MISSING` if the file is not found on disk at serve time.

---

## 7. Error Handling & Edge Cases

- **Never HTTP 500:** The API wraps all handlers; missing files/records return proper 4xx
- **503 on transient errors:** `/frames` returns 503 (not 500) on `RasterioIOError` (retryable)
- **Empty results:** `/tops-cores` returns `[]`, not 404, when no records match
- **Incremental radar add/remove:** `addRadarIncremental()` / `removeRadarIncremental()` splice the `_frameImages` structure without reloading all frames or stopping animation
- **One bad file:** COGWatcher catches per-file exceptions; scan continues
- **NULL vol_nr uniqueness:** PostgreSQL treats NULL != NULL, so legacy (vol_nr=NULL) rows for the same radar+product+timestamp are each unique

---

## 8. Configuration & Environment Variables

### 8.1 Indexer Configuration

See §2.2 for the full table of `IndexerSettings` env vars.

### 8.2 API Configuration

**File:** [`api/app/config.py`](../api/app/config.py) — `APISettings(BaseSettings)`

| Field | Env Var | Default | Description |
|-------|---------|---------|-------------|
| `db_host` | `DB_HOST` | `postgres` | DB hostname |
| `db_port` | `DB_PORT` | `5432` | DB port |
| `db_name` | `DB_NAME` | `radar_db` | DB name |
| `db_user` | `DB_USER` | `radar` | DB user |
| `db_password` | `DB_PASSWORD` | `radarpass` | DB password |
| `cog_base_path` | `COG_BASE_PATH` | `/product_output` | Root path to COG files |
| `cors_origins` | `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `tile_render_threads` | `TILE_RENDER_THREADS` | `8` | Thread pool size for tile rendering |
| `redis_host` | `REDIS_HOST` | `redis` | Redis hostname |
| `redis_port` | `REDIS_PORT` | `6379` | Redis port |
| `redis_enabled` | `REDIS_ENABLED` | `true` | Enable L2 Redis cache |
| `redis_tile_ttl_seconds` | `REDIS_TILE_TTL_SECONDS` | `86400` | TTL for older COG cache entries |
| `redis_tile_ttl_recent_seconds` | `REDIS_TILE_TTL_RECENT_SECONDS` | `3600` | TTL for recent COG cache entries |

GDAL tuning: `GDAL_CACHEMAX`, `VSI_CACHE`, `VSI_CACHE_SIZE`, `GDAL_DISABLE_READDIR_ON_OPEN`.

### 8.3 Database Configuration

**File:** `database/radar_db/config.py` — `DatabaseSettings(BaseSettings)`

Env vars: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`

### 8.4 Frontend / Nginx Configuration

`ADMIN_USERNAME` and `ADMIN_PASSWORD` are read by `docker-entrypoint.sh` at container startup to generate `/etc/nginx/admin.htpasswd`. Changing them requires rebuilding or restarting the frontend container.

Nginx also caches OSM and IGN Argenmap tiles locally (30-day and 7-day TTL respectively) to reduce external requests.

---

## 9. Data Retention & Cleanup

- **No automatic archival.** COG records are kept in DB indefinitely; files deleted from disk are marked `MISSING`.
- **Manual cleanup:** Use `ProductDeleter` (see [`docs/OPERATIONS.md`](OPERATIONS.md)) or direct SQL: `DELETE FROM radar_cogs WHERE status='missing'`
- **Indexer `MARK_MISSING_FILES`:** Set to `false` to disable missing-file detection (not recommended for production)

---

## 10. Summary: Data Flow Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│ RADARLIB (External)                                               │
│ Produces: ROOT_RADAR_PRODUCTS_PATH/RMA1/2026/04/01/              │
│           RMA1_0315_01_20260401T205000Z_DBZHo.tif               │
│           (tags: radarlib_cmap, radarlib_vmin, radarlib_vmax)   │
│ Produces: TOPS_AND_CORES_DIR/RMA1/2026/04/01/                   │
│           RMA1_0315_01_20260401205000_TOPS_CORES.geojson        │
└────────────────────────────────────────────────────────────────────┘
                                  ↓
┌────────────────────────────────────────────────────────────────────┐
│ INDEXER (COGWatcher + TopsAndCoresWatcher, every 30 s)           │
│ ├── Parse filename → radar, strategy, vol_nr, field, timestamp   │
│ ├── Extract metadata: rasterio → bbox, dtype, crs, stats        │
│ └── INSERT/UPDATE RadarCOG + TopsAndCores in PostgreSQL         │
└────────────────────────────────────────────────────────────────────┘
                                  ↓
┌────────────────────────────────────────────────────────────────────┐
│ DATABASE (PostgreSQL + PostGIS)                                   │
│ ├── Radar, RadarProduct, Reference (reference data)             │
│ ├── RadarCOG (main: id, polarimetric_var, vol_nr, bbox, status) │
│ ├── TopsAndCores (id, radar_code, obs_time, core/top counts)    │
│ ├── Estrategia, Volumen (scanning strategy definitions)         │
│ └── colormap_stops, product_colormap_options (colormap system)  │
└────────────────────────────────────────────────────────────────────┘
                                  ↓
┌────────────────────────────────────────────────────────────────────┐
│ API (FastAPI) + Redis (L2 cache)                                  │
│ ├── GET /radars, /products, /cogs → metadata                    │
│ ├── GET /frames/{id}/image.png → full COG PNG (v2 primary)     │
│ │   L1 LRU (750) + L2 Redis (frame: prefix) cache              │
│ ├── GET /tiles/{id}/{z}/{x}/{y}.png → tile (v1/compat)          │
│ ├── GET /colormap/* → DB-backed colormap data                   │
│ └── GET /tops-cores, /tops-cores/{id}/features                  │
└────────────────────────────────────────────────────────────────────┘
                                  ↓
┌────────────────────────────────────────────────────────────────────┐
│ FRONTEND (Leaflet v2)                                             │
│ ├── app.js: multi-radar state + _loadFramesWithContinuity       │
│ ├── radar-app.js: one-radar multi-layer compositor              │
│ ├── map.js: L.imageOverlay + atomic frame swap + SVG mask       │
│ ├── animation.js: requestAnimationFrame loop                    │
│ ├── tops-cores.js: L.circleMarker fire-and-forget layer         │
│ └── User: animated radar map with coverage mask + legend        │
└────────────────────────────────────────────────────────────────────┘
```

---

**Document Version:** 3.0.0  
**Last Updated:** July 8, 2026
