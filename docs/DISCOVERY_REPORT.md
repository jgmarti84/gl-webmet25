# WebMet25 Discovery Report

## 1. Tech Stack

### Backend
- **Python:** 3.11 (specified in Dockerfiles)
- **Web Framework:** FastAPI 0.109.0+
- **App Server:** Uvicorn with standard extras
- **Database ORM:** SQLAlchemy 2.0.0+
- **Database Driver:** psycopg2-binary 2.9.9+ (PostgreSQL)
- **Geospatial:** GeoAlchemy2 0.14.0+ (PostGIS support)
- **Database Migrations:** Alembic 1.13.0+
- **Config Management:** Pydantic 2.0.0+, pydantic-settings 2.0.0+
- **Environment:** python-dotenv 1.0.0+

### Geospatial & Raster Processing
- **Rasterio:** 1.3.0+ (COG reading)
- **rio-tiler:** 6.0.0+ (tile generation)
- **Shapely:** 2.0.0+ (geometry operations)
- **GDAL:** system package with gdal-bin and libgdal-dev

### Image Processing & Visualization
- **Pillow:** 10.0.0+
- **NumPy:** 1.24.0+
- **Matplotlib:** 3.7.0+ (colormap utilities)

### Frontend
- **Leaflet:** 1.9.4 (CDN-loaded)
- **CartoDB Basemaps:** Via Leaflet providers
- **JavaScript:** ES6 modules (no build tool)
- **HTML5/CSS3:** Plain vanilla JS, no framework

### DevOps & Containerization
- **Docker:** Multi-stage builds per service
- **Docker Compose:** 3.8+
- **Dev Containers:** VSCode Dev Containers for genpro and webmet services

### Database
- **PostgreSQL:** With PostGIS extension
- **Alembic:** For schema versioning and migrations

---

## 2. Project Architecture

### Directory Structure

```
.
├── .devcontainer/                 # VSCode dev container configs
│   ├── genpro/devcontainer.json  # Genpro dev environment
│   └── webmet/devcontainer.json  # Webmet dev environment
├── api/                           # FastAPI backend service
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .vscode/launch.json       # Debug config
│   └── app/
│       ├── config.py             # APISettings (FastAPI config)
│       ├── main.py               # FastAPI app setup, middleware, routers
│       ├── schemas/              # Pydantic response models
│       │   ├── __init__.py
│       │   └── responses.py      # HealthResponse, RadarResponse, COGResponse, etc.
│       ├── routers/              # API endpoint handlers
│       │   ├── radars.py         # GET /radars, /radars/{code}
│       │   ├── products.py       # GET /products
│       │   ├── cogs.py           # GET /cogs with filtering
│       │   ├── tiles.py          # GET /tiles/{cog_id}/{z}/{x}/{y}.png
│       │   └── colormap.py       # GET /products/{key}/colormap
│       ├── services/             # Business logic
│       │   ├── __init__.py
│       │   └── tile_service.py   # TileService for COG tile rendering
│       └── utils/                # Utilities
│           └── colormaps.py      # FIELD_COLORMAP_OPTIONS, colormap_for_field()
├── database/                      # Shared database package
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── README.md                 # Comprehensive database management guide
│   ├── alembic.ini               # Alembic config
│   ├── migrations/
│   │   ├── env.py                # Alembic environment setup
│   │   └── versions/             # Migration files
│   ├── radar_db/                 # Python package
│   │   ├── __init__.py           # Exports: db_manager, get_db, models
│   │   ├── config.py             # DatabaseSettings
│   │   ├── database.py           # DatabaseManager, get_db(), init_db()
│   │   ├── models.py             # SQLAlchemy models: Radar, RadarProduct, RadarCOG, Reference, Volumen, Estrategia
│   │   ├── seeds.py              # DataSeeder class, run_seeds()
│   │   └── manage.py             # CLI: init, seed, check, reset, info, migrate, shell
│   └── seed_data/
│       ├── initial_data.json     # Main seed file
│       └── initial_data_00.json  # Alternative seed format
├── frontend/                      # Static frontend served by Nginx
│   ├── Dockerfile
│   ├── nginx.conf                # Nginx reverse proxy config
│   ├── README.md
│   ├── public/
│   │   ├── index.html            # Main radar viewer
│   │   ├── cog-browser.html      # COG browser alternative view
│   │   ├── css/
│   │   │   └── styles.css        # All UI styles (444 lines, dark theme)
│   │   └── js/
│   │       ├── app.js            # Main app orchestrator (275 lines)
│   │       ├── api.js            # API client module (70 lines)
│   │       ├── map.js            # Leaflet map manager (97 lines)
│   │       ├── animation.js      # Frame animation controller (170 lines)
│   │       ├── controls.js       # UI controls & status (148 lines)
│   │       ├── legend.js         # Colormap legend renderer (98 lines)
│   │       ├── cog-browser-api.js # Alternative API client for browser
│   │       └── cog-browser.js    # COG browser app variant (63 lines shown)
├── indexer/                       # COG file indexing service
│   ├── Dockerfile
│   ├── requirements.txt
│   └── indexer/
│       ├── __init__.py
│       ├── config.py             # IndexerSettings
│       ├── main.py               # Entry point: run_indexer(), run_single_scan()
│       ├── watcher.py            # COGWatcher class (not fully shown)
│       ├── registrar.py          # COGRegistrar: file parsing, metadata extraction
│       ├── parser.py             # COGFilenameParser, ParsedCOGInfo (not fully shown)
│       └── manage.py             # CLI: check, populate-cog-metadata
├── docker-compose.yml            # Production compose
├── docker-compose.devcontainer.yml # Dev overrides
├── genpro25.yml                  # Genpro25 configuration (not part of webmet25)
├── .env.example
├── .gitignore
└── README.md
```

### Clear Separation Between Backend & Frontend

**Yes**, very clear:

- **Backend:** `/api` (FastAPI) + `/database` (shared SQLAlchemy models)
- **Frontend:** `/frontend` (plain vanilla JS via Nginx)
- **Shared:** `/database/radar_db` is a Python package imported by both `api` and `indexer`
- **Indexer:** `/indexer` is a separate service (consumes filesystem, writes to database)

---

## 3. Database Schema

All models are in `database/radar_db/models.py`.

### Core Models & Relationships

#### **Radar** (`radars` table)
```python
code: String(16) [PK]
title: String(64)
description: String(64)
center_lat: Numeric(12, 8)
center_long: Numeric(12, 8)
img_radio: Integer
is_active: Boolean
point1_lat: Numeric(14, 10)  # Bounding box corner 1
point1_long: Numeric(14, 10)
point2_lat: Numeric(14, 10)  # Bounding box corner 2
point2_long: Numeric(14, 10)
created_at: DateTime(tz)
updated_at: DateTime(tz)

Relationships:
  - 1:M with RadarCOG (cog_files)
```

**Source:** `database/radar_db/models.py` lines 37-56

#### **RadarProduct** (`radar_products` table)
```python
id: Integer [PK, auto]
product_key: String(16) [UNIQUE, INDEX] (e.g., "COLMAX", "DBZH", "VRAD")
product_title: String(64)
product_description: Text
enabled: Boolean
see_in_open: Boolean
min_value: Float
max_value: Float
unit: String(32)
created_at: DateTime(tz)
updated_at: DateTime(tz)

Relationships:
  - 1:M with Reference (references)
  - 1:M with RadarCOG (cog_files)
```

**Source:** `database/radar_db/models.py` lines 70-92

#### **Reference** (`references` table)
```python
id: Integer [PK, auto]
product_id: Integer [FK → RadarProduct.id, CASCADE]
title: String(64)
description: Text
unit: String(32)
value: Float
color: String(16)  # Hex color code
color_font: String(16)
created_at: DateTime(tz)
updated_at: DateTime(tz)

Relationships:
  - M:1 with RadarProduct (product)
```

**Purpose:** Color scale entries for visualization legends (e.g., dBZ value 10.0 → color #a40000)

#### **RadarCOG** (`radar_cogs` table) - **Main data table**
```python
id: Integer [PK, auto]

# Foreign Keys
radar_code: String(16) [FK → Radar.code, CASCADE, INDEX]
product_id: Integer [FK → RadarProduct.id, SET NULL, INDEX]
estrategia_code: String(16) [FK → Estrategia.code, SET NULL, INDEX]

# Temporal
observation_time: DateTime(tz) [NOT NULL, INDEX]
processing_time: DateTime(tz) [DEFAULT now()]
indexed_at: DateTime(tz) [DEFAULT now()]

# Scan Parameters
polarimetric_var: String(16) [DEFAULT '', INDEX]  (e.g., "VV", "HH")
elevation_angle: Float [DEFAULT 0.0]

# File Info
file_path: String(512) [NOT NULL, UNIQUE]
file_name: String(256) [NOT NULL, INDEX]
file_size_bytes: Integer
file_mtime: DateTime(tz)
file_checksum: String(64)  (SHA256)

# COG Metadata (rasterio-extracted)
crs: String(64)
resolution_x: Float
resolution_y: Float
width: Integer
height: Integer
num_bands: Integer [DEFAULT 1]
dtype: String(32)
nodata_value: Float
compression: String(32)

# Data Statistics (optional, from rasterio)
data_min: Float
data_max: Float
data_mean: Float
valid_pixel_count: Integer

# Spatial (PostGIS)
bbox: Geometry('POLYGON', srid=4326)

# COG Rendering Metadata (from GeoTIFF tags)
cog_data_type: String(16)  (raw_float, rgba, unknown)
cog_cmap: String(64)  (default colormap name)
cog_vmin: Float
cog_vmax: Float

# Status & Display
status: Enum(COGStatus)  [DEFAULT AVAILABLE, INDEX]
error_message: Text
show_me: Boolean [DEFAULT True]

# Timestamps
created_at: DateTime(tz) [DEFAULT now()]
updated_at: DateTime(tz) [onupdate now()]

Relationships:
  - M:1 with Radar (radar)
  - M:1 with RadarProduct (product)
  - M:1 with Estrategia (estrategia)
```

**Source:** `database/radar_db/models.py` lines 136-210

#### **Volumen** (`volumenes` table)
```python
id: Integer [PK]
value: Integer
```

#### **Estrategia** (`estrategias` table)
```python
code: String(16) [PK]
description: Text
volumenes: [List via association table]

Association Table:
  estrategia_volumen (estrategia_code FK, volumen_id FK)
```

**Purpose:** Strategy/volume management (scanning volumes for different radars)

### COGStatus Enum
```python
AVAILABLE = "available"
MISSING = "missing"
ERROR = "error"
```

### Key Indices
- `Radar.code` (PK)
- `RadarProduct.product_key` (UNIQUE)
- `RadarCOG.file_path` (UNIQUE)
- `RadarCOG.radar_code`, `RadarCOG.observation_time`, `RadarCOG.product_id`, `RadarCOG.status`

---

## 4. Data Flow: From Radarlib GeoTIFFs to Frontend

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. RADARLIB (External) → GeoTIFF Production                     │
│    └─ Produces COG files (Cloud-Optimized GeoTIFFs) at:        │
│       /product_output/{radar_code}/{product}/{filename}.tif     │
│    └─ Each COG has embedded GeoTIFF tags:                       │
│       - radarlib_cmap (colormap name)                           │
│       - radarlib_data_type (raw_float or rgba)                  │
│       - radarlib_vmin, radarlib_vmax (data range)               │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. INDEXER SERVICE (indexer/indexer/main.py)                    │
│    └─ Watches /product_output directory (via COGWatcher)        │
│    └─ Every SCAN_INTERVAL seconds (default 30s):               │
│       a) Scans for new/modified .tif files                      │
│       b) For each file:                                         │
│          - Parse filename → RadarCode, ProductKey, ObsTime      │
│            [via COGFilenameParser @ indexer/parser.py]          │
│          - Extract metadata with rasterio:                      │
│            [COGRegistrar.extract_cog_metadata() ↓]              │
│            * Read GeoTIFF tags (cmap, vmin, vmax)               │
│            * Compute bbox, resolution, dtype                    │
│            * Optional: statistics (min/max/mean)                │
│          - Compute SHA256 checksum                              │
│       c) INSERT/UPDATE RadarCOG record in database              │
│          [COGRegistrar.register_file() → RadarCOG model]        │
│       d) Set status = COGStatus.AVAILABLE                       │
│    └─ Periodically check for MISSING files (mark as MISSING)    │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. DATABASE (PostgreSQL + PostGIS)                              │
│    └─ Stores RadarCOG records with:                             │
│       - file_path (relative to COG_BASE_PATH)                   │
│       - Spatial bbox (PostGIS POLYGON)                          │
│       - Rendering metadata (cog_cmap, cog_vmin, cog_vmax)       │
│       - Status (AVAILABLE/MISSING/ERROR)                        │
│    └─ Indexed for fast queries by:                              │
│       - radar_code, product_id, observation_time                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. FASTAPI BACKEND (api/app/main.py + routers)                  │
│    └─ Provides REST API to query indexed COG metadata           │
│                                                                   │
│    GET /api/v1/cogs                                             │
│    └─ Query: radar_code, product_key, start_time, end_time      │
│    └─ Returns: Array of COGResponse with id, file_path,         │
│       observation_time, product info, link to tile endpoint     │
│                                                                   │
│    GET /api/v1/tiles/{cog_id}/{z}/{x}/{y}.png                   │
│    └─ Parameters: colormap, vmin, vmax overrides                │
│    └─ Logic:                                                     │
│       a) Load RadarCOG record from DB                           │
│       b) Build full path: COG_BASE_PATH + file_path             │
│       c) Open COG with rasterio                                 │
│       d) Use rio_tiler to render {z}/{x}/{y} tile               │
│       e) Apply colormap (from cog_cmap or param or default)     │
│       f) Convert to PNG and return                              │
│    └─ Returns: PNG image (256×256)                              │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. FRONTEND (frontend/public/)                                  │
│    └─ Fetches COG metadata:                                     │
│       GET /api/v1/radars → List available radars                │
│       GET /api/v1/products → List available products            │
│       GET /api/v1/cogs?radar_code=AR5&product_key=COLMAX        │
│                    → List COG files (30 most recent)            │
│       GET /api/v1/products/{product_key}/colormap               │
│                    → Color scale entries for legend              │
│                                                                   │
│    └─ Renders on Leaflet map:                                   │
│       For each COG in selection:                                │
│         - Create L.TileLayer URL template:                      │
│           /api/v1/tiles/{cog_id}/{z}/{x}/{y}.png               │
│         - Add layer to map                                      │
│         - Apply opacity control                                 │
│                                                                   │
│    └─ Animation:                                                │
│       - Play/pause through COG frames (ordered by obs_time)     │
│       - Periodically swap visible layer to next COG             │
│       - Speed control (0.5x–2x)                                 │
│                                                                   │
│    └─ Legend:                                                    │
│       - Render Reference entries as color boxes + labels        │
│       - Display on map panel                                    │
└─────────────────────────────────────────────────────────────────┘
```

### Key Flow Files

| Step | Module | Key Functions |
|------|--------|----------------|
| 1 | radarlib (external) | Produces COGs with embedded tags |
| 2a | `indexer/main.py` | `wait_for_database()`, `run_indexer()` |
| 2b | `indexer/watcher.py` | `COGWatcher.run_scan()` (not fully shown but referenced) |
| 2c | `indexer/parser.py` | `COGFilenameParser.parse(filename)` → `ParsedCOGInfo` |
| 2d | `indexer/registrar.py` | `COGRegistrar.register_file()`, `extract_cog_metadata()` |
| 3 | `database/radar_db/database.py` | `DatabaseManager`, `get_db()` |
| 4a | `api/app/routers/cogs.py` | `list_cogs()` endpoint |
| 4b | `api/app/routers/tiles.py` | `get_tile()` endpoint using `TileService` |
| 4c | `api/app/services/tile_service.py` | `TileService.get_tile()`, `read_cog_metadata()` |
| 5 | `frontend/public/js/api.js` | `api.getCogs()`, `api.getColormap()` |
| 5 | `frontend/public/js/map.js` | `MapManager.addRadarLayer()` |

**Critical Path:** GeoTIFF → Indexed in DB → Query via REST → Render tiles → Display on map

---

## 5. API Contract

All endpoints prefixed with `/api/v1` (configurable via `settings.api_prefix`).

### Health & Root

#### `GET /health`
- **Response:** `HealthResponse`
  ```json
  {
    "status": "ok" | "degraded",
    "database": true | false,
    "timestamp": "2025-01-30T12:34:56Z"
  }
  ```
- **Implementation:** `api/app/main.py` line 97

#### `GET /`
- **Response:** JSON object
  ```json
  {
    "name": "Radar Visualization API",
    "version": "1.0.0",
    "docs": "/docs",
    "health": "/health"
  }
  ```

---

### Radars

#### `GET /radars`
- **Query Parameters:**
  - `active_only: bool` (default: `true`) – Return only active radars
- **Response:** `RadarListResponse`
  ```json
  {
    "radars": [
      {
        "code": "AR5",
        "title": "Pergamino",
        "description": "Radar Doppler...",
        "center_lat": -33.94612,
        "center_long": -60.56260,
        "img_radio": 240,
        "is_active": true,
        "extent": {
          "lat_max": -31.755835,
          "lat_min": -36.109429,
          "lon_max": -57.898350,
          "lon_min": -63.226849
        }
      },
      ...
    ],
    "count": 15
  }
  ```
- **Implementation:** `api/app/routers/radars.py` line 16
- **Notes:** `extent` computed from `point1_lat/long`, `point2_lat/long` via `Radar.get_extent()`

#### `GET /radars/{radar_code}`
- **Path Parameters:**
  - `radar_code: str` (e.g., "AR5", "RMA1")
- **Response:** `RadarResponse` (same structure as above)
- **HTTP Status:**
  - `200` on success
  - `404` if radar not found
- **Implementation:** `api/app/routers/radars.py` line 55

---

### Products

#### `GET /products`
- **Query Parameters:** None
- **Response:** `ProductListResponse`
  ```json
  {
    "products": [
      {
        "id": 1,
        "product_key": "COLMAX",
        "product_title": "Composite Reflectivity (Max)",
        "product_description": "Maximum reflectivity...",
        "enabled": true,
        "see_in_open": true,
        "min_value": -20.0,
        "max_value": 80.0,
        "unit": "dBZ"
      },
      ...
    ],
    "count": 24
  }
  ```
- **Implementation:** `api/app/routers/products.py` (referenced but full content not shown)

---

### COGs (Cloud Optimized GeoTIFFs)

#### `GET /cogs`
- **Query Parameters:**
  - `radar_code: str` (optional) – Filter by radar
  - `product_key: str` (optional) – Filter by product
  - `start_time: datetime` (optional) – Observation time >= start_time
  - `end_time: datetime` (optional) – Observation time <= end_time
  - `page: int` (default: 1, min: 1) – Pagination page
  - `page_size: int` (default: 50, min: 1, max: 200) – Items per page
- **Response:** `COGListResponse`
  ```json
  {
    "cogs": [
      {
        "id": 12345,
        "radar_code": "AR5",
        "product_key": "COLMAX",
        "file_path": "AR5/COLMAX/20250130_120000.tif",
        "observation_time": "2025-01-30T12:00:00Z",
        "processing_time": "2025-01-30T12:05:30Z",
        "status": "available",
        "cog_vmin": -20.0,
        "cog_vmax": 80.0,
        "cog_cmap": "grc_th"
      },
      ...
    ],
    "count": 150,
    "total": 2847,
    "page": 1,
    "page_size": 50
  }
  ```
- **Implementation:** `api/app/routers/cogs.py` line 22
- **Notes:** Returns most recent COGs first (order by `observation_time DESC`)

---

### Tiles (Rendered Images)

#### `GET /tiles/{cog_id}/{z}/{x}/{y}.png`
- **Path Parameters:**
  - `cog_id: int` – Database ID of RadarCOG record
  - `z: int` – Tile zoom level
  - `x: int` – Tile column (Web Mercator)
  - `y: int` – Tile row (Web Mercator)
- **Query Parameters:**
  - `colormap: str` (optional) – Override colormap (e.g., "grc_th", "viridis", "pyart_NWSRef")
  - `vmin: float` (optional) – Override minimum data value for scaling
  - `vmax: float` (optional) – Override maximum data value for scaling
- **Response:** PNG image (256×256 bytes)
- **HTTP Status:**
  - `200` with PNG blob on success
  - `404` if COG not found
  - `500` if tile rendering fails
- **Implementation:** `api/app/routers/tiles.py` line 18
- **Logic:**
  1. Query `RadarCOG` by ID, load `product` relationship
  2. Determine colormap: param → COG stored → default
  3. Open file at `COG_BASE_PATH + file_path` with rasterio
  4. Use `rio_tiler` to read tile at `{z}/{x}/{y}`
  5. Apply colormap with `vmin/vmax` scaling
  6. Render to PNG and return

#### `GET /tiles/{cog_id}/metadata`
- **Path Parameters:**
  - `cog_id: int`
- **Response:** JSON with rendering metadata
  ```json
  {
    "cog_data_type": "raw_float",
    "cog_cmap": "grc_th",
    "cog_vmin": -20.0,
    "cog_vmax": 80.0,
    "available_colormaps": ["grc_th", "viridis", "pyart_NWSRef", ...],
    "product_key": "COLMAX",
    "unit": "dBZ"
  }
  ```
- **Implementation:** `api/app/routers/tiles.py` line 198
- **Purpose:** Frontend uses this to populate colormap selector

---

### Colormaps

#### `GET /products/{product_key}/colormap`
- **Path Parameters:**
  - `product_key: str` (e.g., "COLMAX")
- **Query Parameters:**
  - `colormap_name: str` (optional) – Specific colormap variant
- **Response:** `ColormapResponse`
  ```json
  {
    "product_key": "COLMAX",
    "colormap_name": "grc_th",
    "min_value": -20.0,
    "max_value": 80.0,
    "unit": "dBZ",
    "entries": [
      {
        "value": -20.0,
        "color": "#009f00",
        "color_font": "#000000"
      },
      {
        "value": 0.0,
        "color": "#200b0b",
        "color_font": "#FFFFFF"
      },
      {
        "value": 10.0,
        "color": "#a40000",
        "color_font": "#FFFFFF"
      },
      ...
    ]
  }
  ```
- **Implementation:** `api/app/routers/colormap.py` (referenced but not fully shown)
- **Data Source:** `Reference` model entries linked to `RadarProduct`

---

### Summary Table

| Endpoint | Method | Purpose | Key File |
|----------|--------|---------|----------|
| `/health` | GET | Health check | `api/app/main.py` |
| `/` | GET | API info | `api/app/main.py` |
| `/radars` | GET | List radars | `api/app/routers/radars.py` |
| `/radars/{code}` | GET | Get specific radar | `api/app/routers/radars.py` |
| `/products` | GET | List products | `api/app/routers/products.py` |
| `/cogs` | GET | Query COG metadata | `api/app/routers/cogs.py` |
| `/tiles/{id}/{z}/{x}/{y}.png` | GET | Render tile | `api/app/routers/tiles.py` |
| `/tiles/{id}/metadata` | GET | Tile rendering info | `api/app/routers/tiles.py` |
| `/products/{key}/colormap` | GET | Color scale | `api/app/routers/colormap.py` |

---

## 6. Indexer

### How It Works

The indexer is a file system watcher that monitors `/product_output` for new/modified COG files and registers them in the database.

#### Architecture
```
indexer/
├── main.py              # Entry point: run_indexer(), run_single_scan()
├── config.py            # IndexerSettings (env vars)
├── watcher.py           # COGWatcher class
├── registrar.py         # COGRegistrar: file metadata extraction
└── parser.py            # COGFilenameParser: filename → metadata
```

#### Execution Flow

**1. Startup (`indexer/main.py:run_indexer()`)**
```python
def run_indexer():
    """Run the indexer service."""
    if not wait_for_database():  # Poll DB until ready
        sys.exit(1)
    watcher = COGWatcher()
    watcher.run_forever(db_manager.get_session_direct)  # Loop forever
```

**2. Scanning Loop (`COGWatcher.run_scan()`)**
Every `SCAN_INTERVAL` seconds (default 30):
- List all `.tif` files in `WATCH_PATH` (default `/product_output`)
- For each file not yet in database:
  - Parse filename → extract radar_code, product_key, observation_time
  - Extract COG metadata (rasterio)
  - Create/update `RadarCOG` record
- Periodically check for files that disappeared → mark as `MISSING`

**3. Filename Parsing (`COGFilenameParser`)**

From `indexer/registrar.py` context:
```python
parsed = self.parser.parse(str(file_path))
if not parsed.is_valid:
    logger.warning(f"Could not parse file: {file_path} - {parsed.error}")
    return None
```

The parser extracts from filename/path:
- `radar_code` (e.g., "AR5")
- `product_key` (e.g., "COLMAX")
- `observation_time` (e.g., "20250130_120000" → datetime)
- Validates radar exists in database

**4. Metadata Extraction (`COGRegistrar.extract_cog_metadata()`)**

Opens file with rasterio and extracts:
```python
# From GeoTIFF itself
metadata['width'] = src.width
metadata['height'] = src.height
metadata['num_bands'] = src.count
metadata['dtype'] = str(src.dtypes[0])
metadata['crs'] = str(src.crs)
metadata['nodata_value'] = src.nodata
metadata['resolution_x'] = src.res[0]
metadata['resolution_y'] = src.res[1]
metadata['compression'] = src.profile.get('compress')

# From GeoTIFF tags (set by radarlib)
tags = src.tags()
if tags.get("radarlib_cmap"):
    metadata['cog_cmap'] = tags["radarlib_cmap"]
if tags.get("radarlib_vmin"):
    metadata['cog_vmin'] = float(tags["radarlib_vmin"])
if tags.get("radarlib_vmax"):
    metadata['cog_vmax'] = float(tags["radarlib_vmax"])

# Spatial: compute WGS84 bounding box
bounds = transform_bounds(src.crs, 'EPSG:4326', *src.bounds)
bbox_geom = box(*bounds)
metadata['bbox'] = from_shape(bbox_geom, srid=4326)  # PostGIS geometry

# Optional: statistics (if COMPUTE_STATS=true)
if settings.compute_stats:
    data = src.read(1, masked=True)
    metadata['data_min'] = float(data.min())
    metadata['data_max'] = float(data.max())
    metadata['data_mean'] = float(data.mean())
    metadata['valid_pixel_count'] = int(data.count())
```

**5. Database Registration (`COGRegistrar.register_file()`)**

```python
def register_file(self, file_path: Path) -> Optional[int]:
    # Get relative path
    rel_path = str(file_path.relative_to(self.base_path))
    
    # Skip if already indexed
    if self.is_already_indexed(rel_path):
        return None
    
    # Parse filename
    parsed = self.parser.parse(str(file_path))
    
    # Validate radar exists
    radar = session.query(Radar).filter_by(code=parsed.radar_code).first()
    if not radar:
        raise ValueError(f"Radar {parsed.radar_code} not found")
    
    # Get product ID
    product_id = self.get_product_id(parsed.product_key)
    
    # Extract metadata
    metadata = self.extract_cog_metadata(file_path)
    
    # Create RadarCOG record
    cog = RadarCOG(
        radar_code=parsed.radar_code,
        product_id=product_id,
        observation_time=parsed.observation_time,
        file_path=rel_path,
        file_name=file_path.name,
        file_size_bytes=file_path.stat().st_size,
        file_mtime=datetime.fromtimestamp(file_path.stat().st_mtime),
        file_checksum=self.compute_checksum(file_path) if settings.compute_checksum else None,
        status=COGStatus.AVAILABLE,
        **metadata  # Unpack all extracted fields
    )
    
    session.add(cog)
    session.commit()
    return cog.id
```

#### Relationship: Folders → Database

**File System Structure** (inferred):
```
/product_output/
├── AR5/              # radar_code
│   ├── COLMAX/       # product_key
│   │   ├── 20250130_120000.tif
│   │   ├── 20250130_130000.tif
│   │   └── ...
│   ├── DBZH/
│   │   └── ...
│   └── ...
├── RMA1/
│   └── ...
└── ...
```

**Mapping to Database:**
- Folder structure → parsed into `radar_code`, `product_key`
- Filename → parsed to `observation_time`
- File path (relative to `COG_BASE_PATH`) → stored as `file_path` in `RadarCOG`
- File scanning → checks `file_path` uniqueness to avoid re-indexing

#### Configuration (`indexer/config.py`)

```python
class IndexerSettings(BaseSettings):
    db_host: str = "localhost"          # alias: DB_HOST
    db_port: int = 5432                 # alias: DB_PORT
    db_name: str = "radar_db"           # alias: DB_NAME
    db_user: str = "postgres"           # alias: DB_USER
    db_password: str = "postgres"       # alias: DB_PASSWORD
    
    watch_path: str = "/product_output" # alias: WATCH_PATH
    scan_interval_seconds: int = 30     # alias: SCAN_INTERVAL
    file_pattern: str = "*.tif"         # alias: FILE_PATTERN
    radar_codes_raw: str = ''           # alias: RADAR_CODES (optional filter)
    compute_stats: bool = True          # alias: COMPUTE_STATS
    compute_checksum: bool = False      # alias: COMPUTE_CHECKSUM
    mark_missing_files: bool = True     # alias: MARK_MISSING_FILES
```

#### CLI Commands (`indexer/manage.py`)

```bash
# Check database connection
python -m indexer.manage check

# Extract and update COG metadata for all indexed files
python -m indexer.manage populate-cog-metadata
python -m indexer.manage populate-cog-metadata -p /custom/cog/path
```

#### Docker Integration

In `docker-compose.yml` line 36:
```yaml
indexer:
  build:
    context: ./
    dockerfile: ./indexer/Dockerfile
  container_name: radar_indexer
  environment:
    DB_HOST: radar_db
    WATCH_PATH: /product_output
    SCAN_INTERVAL: 30
    FILE_PATTERN: "*.tif"
    COMPUTE_STATS: "true"
    COMPUTE_CHECKSUM: "false"
    RADAR_CODES: "RMA1"  # Optional: only watch specific radars
  volumes:
    - ../product_output:/product_output:ro  # Read-only mount
  depends_on:
    radar_db:
      condition: service_healthy
```

---

## 7. Frontend

### Purpose
Interactive web application for visualizing radar data on a map with animation controls.

### Views / Pages

#### **Main View** (`frontend/public/index.html`)
- **Path:** `/` (served by Nginx)
- **Map:** Leaflet map with dark CartoDB basemap
- **Controls Panel** (top-right):
  - Basemap selector (Dark, Streets, Satellite, Terrain)
  - Radar selector (checkboxes for multiple selection)
  - Product selector (dropdown)
  - Opacity slider
- **Animation Controls** (bottom):
  - Play/Pause button
  - Speed control (0.5x, 1x, 1.5x, 2x)
  - Previous/Next frame buttons
  - Frame counter (e.g., "5/30")
  - Timeline slider
- **Legend** (left panel):
  - Color scale for selected product
  - Value labels and units
  - Show/hide toggle
- **Status Display:**
  - Loading indicator
  - Error messages
  - Last update time

#### **COG Browser View** (`frontend/public/cog-browser.html`)
- Alternative detailed view
- Browse individual COG files
- Inspect metadata
- (Similar architecture, different presentation)

### Architecture & Modules

**File Organization:**
```
frontend/public/
├── index.html                  # Main page skeleton
├── cog-browser.html           # Alternative page
├── css/styles.css             # UI styling (444 lines, dark theme #1a1a2e)
└── js/
    ├── app.js                 # Main orchestrator (275 lines)
    ├── api.js                 # REST API client (70 lines)
    ├── map.js                 # Leaflet map manager (97 lines)
    ├── animation.js           # Frame animation (170 lines)
    ├── controls.js            # UI controls (148 lines)
    ├── legend.js              # Legend renderer (98 lines)
    ├── cog-browser-api.js     # Alternative API client
    └── cog-browser.js         # Alternative app (63 lines shown)
```

**Module Responsibilities:**

1. **`app.js`** – Main Application State & Orchestration
   - Global `state` object: radars, products, selectedRadars, selectedProduct, cogs, animation state
   - `init()`: Bootstrap app, wait for Leaflet, load data, setup listeners
   - Coordinates module interactions (map ↔ animation ↔ legend ↔ API)
   - Handles events: radar selection change, product change, time range input

2. **`api.js`** – REST API Client
   - Functions:
     - `getRadars()` → calls `GET /api/v1/radars`, returns `data.radars[]`
     - `getProducts()` → `GET /api/v1/products`, returns `data.products[]`
     - `getCogs(radarCode, productKey, limit=20)` → `GET /api/v1/cogs?radar_code=X&product_key=Y&page_size=Z`
     - `getLatestCog(radarCode, productKey)` → Single most recent COG
     - `getLatestCogsMultiRadar(radarCodes, productKey)` → Latest from each radar
     - `getColormapInfo(productKey, colormapName)` → `GET /api/v1/products/{key}/colormap`
     - `getColormapOptions()` → All available colormaps

3. **`map.js`** – Leaflet Map Manager
   - `MapManager` class
   - Methods:
     - `init(containerId)` → Create map with center, zoom
     - `setBasemap(key)` → Switch basemap layer
     - `addRadarLayer(cogId, displayName)` → Add L.TileLayer for COG tiles
     - `removeRadarLayer(cogId)` → Remove layer
     - `setOpacity(value)` → Adjust layer transparency

4. **`animation.js`** – Frame Animation Controller
   - `AnimationController` class
   - State: currentFrameIndex, isPlaying, speed (0.5x–2x)
   - Methods:
     - `setFrames(cogArray)` → Load COG sequence
     - `play()` / `pause()` → Toggle animation
     - `setSpeed(speed)` → Update playback speed
     - `nextFrame()` / `previousFrame()` → Manual navigation
     - `setToFrame(index)` → Jump to frame
   - Internal: Timer updates map layer every `200ms * (1/speed)`

5. **`controls.js`** – UI Control Handlers
   - `UIControls` class
   - Methods:
     - `populateRadarCheckboxes(radars)` → Build radar selector
     - `populateProductSelect(products)` → Build product dropdown
     - `updateStatus(message)` → Display status text
     - `updateFrameCounter(current, total)` → Show "5/30"
     - `enableButton(id)` / `disableButton(id)` → UI state management
     - `showError(message)` → Error toast

6. **`legend.js`** – Legend Renderer
   - `LegendRenderer` class
   - Methods:
     - `render(colormapData)` → Creates HTML legend from Reference entries
     - `show()` / `hide()` → Toggle visibility
   - Output: DOM with color boxes + labels

### Data Flow (Frontend)

```
┌─────────────────────────────────────┐
│ 1. INITIALIZATION (app.js:init())   │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 2. LOAD INITIAL DATA (api.js)       │
│    - GET /api/v1/radars             │
│    - GET /api/v1/products           │
│    Populate state.radars[]          │
│    Populate state.products[]        │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 3. RENDER CONTROLS (controls.js)    │
│    - Populate radar checkboxes      │
│    - Populate product select        │
│    - Initialize map (map.js)        │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 4. USER SELECTS RADAR & PRODUCT     │
│    (event listener fires)           │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 5. FETCH COG DATA (api.js)          │
│    GET /api/v1/cogs                 │
│      ?radar_code=AR5                │
│      &product_key=COLMAX            │
│      &page_size=30                  │
│    → state.cogs[] (sorted by time)  │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 6. FETCH COLORMAP (api.js)          │
│    GET /api/v1/products/COLMAX/...  │
│    /colormap                        │
│    → Render legend (legend.js)      │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 7. ADD MAP LAYERS (map.js)          │
│    For each COG:                    │
│      - Create L.TileLayer           │
│      - URL: /api/v1/tiles/{id}/...  │
│      - Add to map                   │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 8. INITIALIZE ANIMATION (animation) │
│    Set initial frame visible        │
│    Start/pause based on state       │
│    Show frame counter               │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 9. PLAYBACK (animation.js loop)     │
│    Timer: every 200ms               │
│    - currentFrameIndex++            │
│    - Swap visible layer             │
│    - Update UI                      │
│    - Loop if enabled                │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 10. USER INTERACTION                │
│    - Opacity slider → map.setOp()   │
│    - Prev/Next → animation.prev/nxt │
│    - Play/Pause → animation.toggle()│
│    - Speed → animation.setSpeed()   │
└─────────────────────────────────────┘
```

### Key Features

- **Multiple Selections:** User can select multiple radars, see layers for all
- **Time Grouping:** Frontend groups COGs by observation time (±5 min tolerance) → can animate all radars simultaneously
- **Responsive:** Works on desktop, tablet, mobile (Leaflet is responsive)
- **Dark Theme:** #1a1a2e background, light text
- **Error Handling:** Graceful fallbacks if API unavailable
- **Live Refresh:** Periodic polling to fetch new COGs (5-minute interval)

### Example URL Flow

1. User opens `http://localhost`
2. Browser loads `/index.html` (from Nginx)
3. JavaScript imports modules (api.js, map.js, app.js, etc.)
4. `app.init()` calls `api.getRadars()` → `http://localhost:8000/api/v1/radars`
5. User selects radar "AR5" and product "COLMAX"
6. `api.getCogs("AR5", "COLMAX")` → `http://localhost:8000/api/v1/cogs?radar_code=AR5&product_key=COLMAX&page_size=30`
7. Backend returns 30 most recent COG metadata (ids, timestamps)
8. For each COG, map adds tile layer URL: `http://localhost:8000/api/v1/tiles/12345/10/500/400.png`
9. Leaflet fetches tiles on demand as map pans/zooms
10. User clicks Play → animation loop cycles through COG layers

---

## 8. Gaps & Risks

### 🔴 Critical Issues

1. **No Authentication / Authorization**
   - **Location:** `api/app/main.py` – No FastAPI dependency or middleware
   - **Risk:** Anyone can query any radar data, modify via unprotected endpoints (if PUT/DELETE added), DOS attack vector
   - **Impact:** High (security)
   - **Recommendation:** Add OAuth2/JWT, role-based access control, rate limiting

2. **Incomplete Routers**
   - **Location:** `api/app/routers/products.py` – Referenced but full implementation not shown
   - **Location:** `api/app/routers/colormap.py` – Referenced but not visible
   - **Risk:** Unknown if these endpoints fully implemented or have bugs
   - **Impact:** Medium (functionality)
   - **Recommendation:** Complete and test all router implementations

3. **COGWatcher Not Fully Shown**
   - **Location:** `indexer/indexer/watcher.py` – Referenced but implementation hidden
   - **Location:** `indexer/indexer/parser.py` – `COGFilenameParser`, `ParsedCOGInfo` logic not visible
   - **Risk:** Unknown if filename parsing is robust, if edge cases handled (missing files, corrupt TIFFs, etc.)
   - **Impact:** Medium (reliability)
   - **Recommendation:** Audit watcher and parser for error handling, file locking, concurrency

4. **No Transactions / Atomic Operations**
   - **Location:** `indexer/registrar.py` line 160+ – Direct session.add/commit
   - **Risk:** If COG metadata extraction fails mid-way, partial record inserted; if indexer crashes, database left in inconsistent state
   - **Impact:** Medium (data integrity)
   - **Recommendation:** Use try/except with rollback; implement idempotent registration

5. **File Path Assumptions**
   - **Issue:** Backend assumes `COG_BASE_PATH + file_path` always exists when serving tiles
   - **Location:** `api/app/routers/tiles.py` line 38 – Opens file without existence check
   - **Risk:** If file deleted after indexing, 500 error to frontend; no graceful handling
   - **Impact:** Medium (reliability)
   - **Recommendation:** Check file existence; return 404 with message; mark COG as MISSING

---

### 🟡 Design Issues

6. **Hardcoded API Base URL in Frontend**
   - **Location:** `frontend/public/js/api.js` line 9
   ```javascript
   const API_BASE = window.location.hostname === 'localhost' 
       ? 'http://localhost:8000/api/v1'
       : '/api/v1';
   ```
   - **Risk:** Requires Nginx reverse proxy for prod; breaks if API on different host/port
   - **Impact:** Low (works with current setup, but fragile)
   - **Recommendation:** Use environment variable or config file; add fallback

7. **COG File Path Is Exposed in API**
   - **Location:** `api/app/schemas/responses.py` – `COGResponse.file_path` returned
   - **Location:** `api/app/routers/cogs.py` line 22 – `list_cogs()` returns file path
   - **Risk:** Leaks internal file structure; frontend doesn't use it (only `cog_id` needed)
   - **Impact:** Low (information disclosure)
   - **Recommendation:** Remove `file_path` from API response; use only internal to backend

8. **No Pagination for Products/References**
   - **Location:** `api/app/routers/products.py` (not shown but likely unimplemented)
   - **Risk:** If 1000s of products, all returned in one response → memory/bandwidth spike
   - **Impact:** Low (current dataset small)
   - **Recommendation:** Add pagination for products, references, colormaps

9. **Animation Speed Hard-Coded**
   - **Location:** `frontend/public/js/animation.js` line ~
   - **Risk:** `200ms * (1/speed)` assumes certain COG size; too fast for slow networks
   - **Impact:** Low (UX)
   - **Recommendation:** Make frame interval configurable; add loading state for tiles

10. **No Caching of Tile Responses**
    - **Location:** `api/app/routers/tiles.py` line 18 – `/tiles` is blocking
    - **Risk:** Each tile render (even identical calls) re-reads file, re-renders, re-encodes PNG
    - **Impact:** Medium (performance) – hundreds of duplicate requests per animation cycle
    - **Recommendation:** Add HTTP `Cache-Control` headers; consider Redis cache for common tiles

---

### 🟠 Missing Functionality

11. **No Support for Multi-Elevation Scans**
    - **Database:** `elevation_angle` stored in `RadarCOG` but never used in filtering
    - **Location:** `database/radar_db/models.py` line 163
    - **Risk:** Different elevation angles produce different reflectivity; mixing them on same layer leads to confusing visualization
    - **Impact:** Low-Medium (depends on use case)
    - **Recommendation:** Add optional elevation filter to `GET /cogs`; document behavior

12. **No Projection Information**
    - **Database:** `crs` stored (e.g., "EPSG:4326") but never returned to frontend
    - **Risk:** Frontend assumes Web Mercator tiles; if COG in different projection, tiles misaligned
    - **Impact:** Low (assuming all COGs in same projection; verify with radarlib)
    - **Recommendation:** Return CRS in metadata; document project requirements

13. **Legend Entries Not Sorted**
    - **Location:** `api/app/routers/colormap.py` – Unclear how entries ordered
    - **Risk:** If unsorted, legend display looks random
    - **Impact:** Low (UX)
    - **Recommendation:** Ensure `Reference` entries sorted by value in query

14. **No Data Refresh Endpoint**
    - **Risk:** Frontend polls every 5 minutes for new COGs; no way to force immediate refresh
    - **Impact:** Low (periodicity acceptable for radar data)
    - **Recommendation:** Add optional `GET /cogs?refresh=true` or WebSocket push

---

### 🔵 Incomplete Error Handling

15. **Missing Error Messages**
    - **Location:** `api/app/routers/tiles.py` line 38 – No try/except around tile rendering
    - **Risk:** Malformed COG or missing file → generic 500 to frontend, no debug info
    - **Impact:** Low-Medium (ops difficulty)
    - **Recommendation:** Wrap tile logic in try/except; log error; return 422 with reason

16. **Indexer Doesn't Handle Corrupted COGs**
    - **Location:** `indexer/registrar.py` line 108+
    - **Risk:** If rasterio.open() fails, exception bubbles up; entire scan aborted
    - **Impact:** Medium (reliability)
    - **Recommendation:** Catch rasterio errors; mark COG as ERROR; continue scanning

17. **No Connection Pool Exhaustion Handling**
    - **Location:** `database/radar_db/database.py` – Pool settings hardcoded
    - **Risk:** Under load, connections may exhaust; timeouts not configurable
    - **Impact:** Low (unless high traffic)
    - **Recommendation:** Make `db_pool_size`, `max_overflow` configurable; add monitoring

---

### 🟣 Testing & Documentation Gaps

18. **No Unit Tests**
    - **Risk:** Regressions undetected; critical logic untested
    - **Impact:** Medium (quality)
    - **Recommendation:** Add pytest suite for routers, services, models

19. **No Integration Tests**
    - **Risk:** Full API flow not validated; COG ingestion → tile rendering pipeline untested
    - **Impact:** Medium (quality)
    - **Recommendation:** Add Docker test environment; mock radarlib output; test end-to-end

20. **API Documentation Incomplete**
    - **Risk:** Frontend developers must reverse-engineer from code
    - **Impact:** Low (FastAPI auto-generates docs at `/docs`)
    - **Recommendation:** Ensure all routers have docstrings; test `/docs` page

21. **Frontend Module Coupling**
    - **Location:** `frontend/public/js/app.js` line 0+
    - **Risk:** Modules reference global state; hard to test in isolation
    - **Impact:** Low (works, but not maintainable)
    - **Recommendation:** Refactor to dependency injection; use event emitter pattern

---

### 📋 Deployment & Operations

22. **No Secrets Management**
    - **Risk:** Database password in `docker-compose.yml` (plaintext)
    - **Location:** `docker-compose.yml` line 79
    - **Impact:** High (security)
    - **Recommendation:** Use Docker secrets or environment file; .env not committed

23. **No Monitoring / Logging Aggregation**
    - **Location:** Logs only to stdout; Docker collects them but no centralized logging
    - **Risk:** Hard to debug production issues
    - **Impact:** Medium (ops)
    - **Recommendation:** Add structured logging (JSON); ELK stack or CloudWatch

24. **Health Checks Incomplete**
    - **Location:** `api/app/main.py` line 97 – Only checks DB connectivity
    - **Risk:** Missing checks: tile rendering, indexer health, API response time
    - **Impact:** Low-Medium (observability)
    - **Recommendation:** Expand health check to include tile test

---

### 🏗️ Architectural Concerns

25. **Tight Coupling Between API & Indexer**
    - **Issue:** Both import `radar_db` directly; share same DB models
    - **Risk:** Schema change breaks both; difficult to scale services independently
    - **Impact:** Low (current single-instance deployment; would matter at scale)
    - **Recommendation:** Consider API versioning; separate read/write models

26. **No Rate Limiting**
    - **Location:** `api/app/main.py`
    - **Risk:** Malicious client can DOS by hammering `/tiles/` endpoint
    - **Impact:** Medium (availability)
    - **Recommendation:** Add slowapi or similar rate limiter

27. **Tile Rendering Synchronous**
    - **Location:** `api/app/routers/tiles.py` line 18 – `/tiles` is blocking
    - **Risk:** Under high concurrency, tile requests slow down API
    - **Impact:** Low (assumes reasonable animation speed; tile size manageable)
    - **Recommendation:** Consider async tile rendering; Celery queue for slow tiles

---

## Summary Table

| # | Category | Issue | Severity | File | Recommendation |
|---|----------|-------|----------|------|-----------------|
| 1 | Security | No authentication | 🔴 High | `api/app/main.py` | Add OAuth2/JWT |
| 2 | Dev | Incomplete routers | 🟡 Medium | `api/app/routers/products.py` | Complete & test |
| 3 | Dev | COGWatcher/Parser hidden | 🟡 Medium | `indexer/indexer/watcher.py` | Audit error handling |
| 4 | Data | No atomic transactions | 🔴 Medium | `indexer/indexer/registrar.py` | Add try/except + rollback |
| 5 | Reliability | File existence not checked | 🟡 Medium | `api/app/routers/tiles.py` | Add 404 handling |
| 6 | Design | Hardcoded API URL | 🟡 Low | `frontend/public/js/api.js` | Use config file |
| 7 | Design | File path exposed in API | 🟡 Low | `api/app/schemas/responses.py` | Remove from response |
| 8 | Design | No pagination on products | 🟡 Low | `api/app/routers/products.py` | Add pagination |
| 9 | UX | Animation speed hardcoded | 🟡 Low | `frontend/public/js/animation.js` | Make configurable |
| 10 | Performance | No tile caching | 🟡 Medium | `api/app/routers/tiles.py` | Add HTTP cache headers |
| 11 | Feature | Multi-elevation not supported | 🟠 Low-Med | `database/radar_db/models.py` | Add elevation filter |
| 12 | Feature | Projection info not returned | 🟠 Low | `api/app/routers/tiles.py` | Return CRS in metadata |
| 13 | UX | Legend entries not sorted | 🟡 Low | `api/app/routers/colormap.py` | Sort by value |
| 14 | Feature | No data refresh endpoint | 🟠 Low | `api/app/routers/cogs.py` | Add refresh trigger |
| 15 | Error Handling | Missing error messages | 🟡 Low-Med | `api/app/routers/tiles.py` | Add try/except logging |
| 16 | Error Handling | Indexer doesn't handle corrupted COGs | 🟡 Medium | `indexer/indexer/registrar.py` | Mark as ERROR, continue |
| 17 | Error Handling | No conn pool exhaustion handling | 🟠 Low | `database/radar_db/database.py` | Make pool configurable |
| 18 | Testing | No unit tests | 🟡 Medium | — | Add pytest |
| 19 | Testing | No integration tests | 🟡 Medium | — | Add E2E tests |
| 20 | Docs | API docs incomplete | 🟡 Low | — | Add docstrings |
| 21 | Architecture | Frontend module coupling | 🟡 Low | `frontend/public/js/app.js` | Refactor modules |
| 22 | Security | Secrets in docker-compose | 🔴 High | `docker-compose.yml` | Use env secrets |
| 23 | Ops | No monitoring | 🟡 Medium | — | Add ELK/CloudWatch |
| 24 | Ops | Incomplete health checks | 🟡 Low-Med | `api/app/main.py` | Expand health endpoint |
| 25 | Architecture | Tight API/Indexer coupling | 🟠 Low | | Consider versioning |
| 26 | Security | No rate limiting | 🟡 Medium | `api/app/main.py` | Add slowapi |
| 27 | Performance | Tile rendering sync | 🟠 Low | `api/app/routers/tiles.py` | Consider async |

---

## Conclusion

WebMet25 is a **well-structured, functional radar visualization system** with clear separation of concerns. The architecture successfully achieves its goal: ingest COG files from radarlib, index them, serve them via REST API, and render on interactive map.

**Strengths:**
- ✅ Modular architecture (API, Indexer, Frontend clearly separated)
- ✅ Proper use of PostGIS for spatial queries
- ✅ Responsive frontend with Leaflet
- ✅ Comprehensive database management CLI
- ✅ Docker Compose orchestration solid

**Weaknesses:**
- ❌ No authentication/authorization
- ❌ Incomplete error handling in indexer & API
- ❌ Missing tile caching (performance issue)
- ❌ No automated tests
- ❌ Secrets exposed in config

**For Production:**
1. Implement authentication (OAuth2)
2. Add comprehensive error handling & logging
3. Implement tile caching (HTTP + Redis)
4. Add rate limiting
5. Set up monitoring (health checks, logs, metrics)
6. Add integration tests
7. Use secrets manager (not plaintext env vars)
8. Document API thoroughly
9. Audit COGFilenameParser & COGWatcher for robustness
10. Consider async tile rendering under load
