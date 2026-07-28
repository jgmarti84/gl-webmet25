# WebMet25 — Radar Visualization & Data Indexing System

WebMet25 is the **data consumer** in the radarmet system. It ingests Cloud-Optimized GeoTIFF (COG) files produced by [radarlib](https://gitlab.example.com/radarlib), indexes them into a PostgreSQL/PostGIS database, and serves them via a REST API with an interactive Leaflet-based web frontend for real-time radar visualization.

## System Context

```
radarlib (producer)
    │
    ├── outputs GeoTIFF COGs     → ROOT_RADAR_PRODUCTS_PATH
    ├── outputs Tops & Cores GeoJSON → TOPS_AND_CORES_DIR
    │
    ▼
webmet25 (consumer)
    │
    ├── Indexer watches ROOT_RADAR_PRODUCTS_PATH (every 30 s)
    ├── TopsAndCoresWatcher watches TOPS_AND_CORES_DIR (same interval)
    │   ├── parses filenames
    │   ├── extracts metadata
    │   └── stores in PostgreSQL/PostGIS
    │
    ├── FastAPI serves metadata + full-image frames
    │
    └── Leaflet v2 frontend renders animated radar map
```

---

## Features

- **Real-Time Indexing:** File-system watcher scans for new COG files every 30 seconds; marks deleted files as MISSING
- **Tops & Cores:** Convective cores and storm tops from radarlib GeoJSON are indexed and displayed as semi-transparent orange blob polygon fills with SVG core markers (COLMAX products only)
- **Coverage Mode Toggle:** Switch between C+D mode (volumes 01/02) and Vigilancia mode (volume 04)
- **Spatial Database:** PostGIS integration for geographic queries and bounding-box calculations
- **REST API:** Full endpoint suite for radars, products, COGs, frames, colormaps, tops & cores, and admin CRUD
- **Interactive Map (v2):** Leaflet with `L.imageOverlay` — one image per radar per frame instead of ~180 tiles
- **One-Radar Detail Page:** `radar.html?code=XXX` — multi-layer field compositor with per-layer colormap and range filter
- **Frame Animation:** `requestAnimationFrame`-based playback; animation never interrupts during data loads
- **Coverage Mode:** SVG mask pane that dims areas outside radar coverage; per-radar coverage rings
- **Time-Window Selection:** Preset (1.5 h / 3 h / 4.5 h / 6 h) or custom date + iOS-style time wheel
- **Live Mode:** Configurable auto-refresh (default 5 minutes) anchored to the latest available data
- **Colormap Management:** DB-backed colormap system; visual creator/editor in the admin panel
- **Gaussian Smoothing:** Server-side float-data blur before colormap (configurable sigma)
- **Geolocation:** Browser geolocation → auto-select 3 nearest active radars
- **Admin Panel:** Full-featured CRUD SPA at `/admin` (nginx Basic Auth) for every database table
- **Snapshot:** Canvas compositing of basemap + radar overlays + legend + metadata → PNG download
- **Tile & Frame Cache:** L1 LRU in-process + L2 Redis cache for rendered frames

---

## Tech Stack

### Backend
- **Language:** Python 3.11
- **Web Framework:** FastAPI 0.109.0+
- **App Server:** Uvicorn
- **Database ORM:** SQLAlchemy 2.0.0+
- **Database Driver:** psycopg2-binary 2.9.9+
- **Geospatial ORM:** GeoAlchemy2 0.14.0+
- **Migrations:** Alembic 1.13.0+
- **Configuration:** Pydantic 2.0.0+, pydantic-settings 2.0.0+
- **Cache:** cachetools 5.0.0+ (LRU), redis 5.0.0+

### Geospatial & Raster Processing
- **Rasterio:** 1.3.0+ (Cloud-Optimized GeoTIFF reading)
- **rio-tiler:** 6.0.0+ (Web Mercator tile generation)
- **Shapely:** 2.0.0+ (Geometry operations)
- **GDAL:** System package
- **SciPy:** 1.9.0+ (Gaussian smoothing)

### Image Processing
- **Pillow:** 10.0.0+
- **NumPy:** 1.24.0+
- **Matplotlib:** 3.7.0+ (colormap utilities)

### Frontend
- **Leaflet:** 1.9.4 (via CDN)
- **Basemaps:** IGN Argenmap (argenmap, argenmap_gris, argenmap_topo, argenmap_oscuro, argenmap_hibrido)
- **JavaScript:** ES6 modules (no build tool)
- **CSS:** Vanilla CSS3 (dark theme main app, modern-light admin)

### DevOps & Containerization
- **Docker:** Multi-stage builds per service
- **Docker Compose:** 3.8+ for orchestration
- **Nginx:** Reverse proxy, static serving, admin Basic Auth, OSM/IGN tile caching
- **Redis:** 7.2 (LRU cache, no persistence)
- **VSCode Dev Containers:** For local development

### Database
- **PostgreSQL:** 15+ with PostGIS 3.5
- **Alembic:** Schema versioning and migrations

---

## Project Architecture

### Directory Structure

```
webmet25/
├── api/                           # FastAPI backend service
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py               # FastAPI app setup, middleware, routers
│       ├── config.py             # APISettings (env vars, GDAL tuning, Redis config)
│       ├── schemas/
│       │   ├── responses.py      # Pydantic response models (public API)
│       │   └── admin.py          # Pydantic models for admin CRUD
│       ├── routers/
│       │   ├── radars.py         # GET /radars, /radars/{code}
│       │   ├── products.py       # GET /products, /products/{key}
│       │   ├── cogs.py           # GET /cogs, /cogs/latest, /cogs/timeline, /cogs/{id}
│       │   ├── tiles.py          # GET /tiles/{id}/{z}/{x}/{y}.png + metadata + cache stats
│       │   ├── frames.py         # GET /frames/{id}/image.png (v2 primary)
│       │   ├── colormap.py       # GET /colormap/names|options|defaults|colors|info + invalidate
│       │   ├── tops_cores.py     # GET /tops-cores, /tops-cores/{id}/features
│       │   └── admin.py          # /api/v1/admin/* CRUD for all tables
│       ├── services/
│       │   ├── tile_service.py   # TileService — COG tile rendering with thread pool
│       │   ├── colormap_service.py # ColormapService — DB-first colormap with 5-min TTL cache
│       │   ├── redis_client.py   # Redis connection management
│       │   └── smoothing.py      # Gaussian float-data blur (scipy)
│       └── utils/
│           └── colormaps.py      # Hardcoded fallback colormap builders
│
├── database/                      # Shared database package
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── README.md                 # DB management guide
│   ├── alembic.ini
│   ├── migrations/               # Alembic migration files
│   │   └── versions/
│   ├── radar_db/
│   │   ├── __init__.py
│   │   ├── config.py             # DatabaseSettings
│   │   ├── database.py           # DatabaseManager, get_db(), init_db()
│   │   ├── models.py             # All SQLAlchemy models
│   │   ├── seeds.py              # DataSeeder (seed_all / sync_all)
│   │   └── manage.py             # CLI: init, seed, sync, check, info, reset, migrate, shell
│   └── seed_data/
│       └── initial_data.json     # 21 radars, 20 products, references, colormaps
│
├── frontend/                      # Static web frontend (Nginx)
│   ├── Dockerfile
│   ├── docker-entrypoint.sh      # Generates admin.htpasswd at startup
│   ├── nginx.conf                # Reverse proxy, Basic Auth, OSM/IGN tile cache
│   ├── README.md
│   └── public/
│       ├── index.html            # Multi-radar map SPA shell
│       ├── radar.html            # One-radar detail page (radar.html?code=AR5)
│       ├── admin.html            # Admin panel SPA shell
│       ├── cog-browser.html      # Alternative COG file browser
│       ├── css/
│       │   ├── styles.css        # Main app dark theme
│       │   └── admin.css         # Admin modern-light theme
│       └── js/
│           ├── admin.js          # Admin SPA orchestrator
│           ├── admin-api.js      # Admin REST client (/api/v1/admin/*)
│           ├── shared/           # Shared by v1 and v2
│           │   ├── api.js        # REST API client
│           │   ├── controls.js   # UI handlers (radar list, time wheel, badges)
│           │   ├── legend.js     # Colormap legend renderer
│           │   ├── tops-cores.js # TopsCoresLayer (blob polygons + SVG markers)
│           │   └── time-wheel.js # iOS-style HH:MM scroll picker
│           └── v2/               # Current production frontend
│               ├── app.js        # Multi-radar map orchestrator (2500+ lines)
│               ├── radar-app.js  # One-radar page orchestrator (1660+ lines)
│               ├── map.js        # MapManager (L.imageOverlay + SVG coverage mask)
│               ├── animation.js  # AnimationController (requestAnimationFrame)
│               ├── radar-utils.js # Shared helpers for radar-app.js
│               └── constants.js  # COVERAGE_MODES, defaults, timing constants
│
├── indexer/                       # COG file indexing service
│   ├── Dockerfile
│   ├── requirements.txt
│   └── indexer/
│       ├── main.py               # Entry: starts COGWatcher + TopsAndCoresWatcher
│       ├── config.py             # IndexerSettings (env vars)
│       ├── watcher.py            # COGWatcher + TopsAndCoresWatcher
│       ├── registrar.py          # COGRegistrar + TopsAndCoresRegistrar
│       ├── parser.py             # COGFilenameParser + TopsAndCoresFilenameParser
│       ├── deleter.py            # ProductDeleter (disk + DB cleanup)
│       └── manage.py             # CLI: check, populate-cog-metadata
│
├── tests/                         # Automated test suite
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── conftest.py
│   ├── api/                      # API contract tests (httpx)
│   │   ├── test_health.py
│   │   ├── test_radars.py
│   │   ├── test_products.py
│   │   ├── test_cogs.py
│   │   ├── test_tiles.py
│   │   └── test_colormap.py
│   ├── indexer/                  # Indexer unit tests
│   │   ├── test_filename_parser.py
│   │   └── test_registrar.py
│   └── e2e/                      # Browser tests (Playwright/Chromium)
│       ├── conftest.py
│       ├── test_admin_panel.py
│       ├── test_radar_ordering.py
│       └── test_time_wheel.py
│
├── scripts/
│   ├── MANAGE_COMMANDS.md        # Docker disk cleanup reference
│   └── delete_products.sh        # Wrapper for ProductDeleter
├── docs/                          # Technical documentation
│   ├── DATA_FLOW.md
│   ├── COMPONENTS.md
│   ├── DISCOVERY_REPORT.md
│   ├── E2E_TESTING.md
│   └── OPERATIONS.md
├── docker-compose.yml            # Production stack (6 services)
├── docker-compose.devcontainer.yml # Dev container overrides (test services)
└── .env.example                  # Environment variable template
```

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ RADARLIB (External Producer)                                    │
│ Outputs COG .tif files + TOPS_CORES .geojson files             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
              /product_output/    /tops_and_cores/
              (shared volumes — read-only for webmet25)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ INDEXER SERVICE (radar_indexer)                                 │
│                                                                   │
│ • COGWatcher: scans /product_output for *.tif (every 30 s)     │
│ • TopsAndCoresWatcher: scans /tops_and_cores for *.geojson     │
│ • Parses filenames, extracts rasterio metadata                  │
│ • INSERT/UPDATE RadarCOG and TopsAndCores records in DB        │
│ • update_radar_activity() after every scan                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ DATABASE (radar_db — PostgreSQL 15 + PostGIS 3.5)              │
│                                                                   │
│ Tables: Radar, RadarProduct, RadarCOG, TopsAndCores            │
│         Reference, Estrategia, Volumen                          │
│         colormap_stops, product_colormap_options               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ API (radar_api — FastAPI + Uvicorn, port 8000)                 │
│                                                                   │
│  GET /radars[/{code}]      GET /products[/{key}]               │
│  GET /cogs[/latest|/timeline|/{id}]                            │
│  GET /frames/{id}/image.png  ← v2 primary (full-image COG)    │
│  GET /tiles/{id}/{z}/{x}/{y}.png  ← v1 / compatibility        │
│  GET /colormap/names|options|defaults|colors|info             │
│  GET /tops-cores  GET /tops-cores/{id}/features               │
│  /api/v1/admin/*  ← full CRUD (nginx Basic Auth)              │
│                                                                   │
│  Cache: L1 LRU (750 entries) + L2 Redis (frame: prefix)       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ REDIS (redis:7.2-alpine — L2 cache, LRU eviction)             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ FRONTEND (frontend-v2 — Nginx port 80)                         │
│                                                                   │
│ • Multi-radar map (index.html + v2/app.js)                     │
│ • One-radar detail page (radar.html + v2/radar-app.js)         │
│ • Admin SPA (admin.html + admin.js — Basic Auth)               │
│ • L.imageOverlay — 1 PNG per radar per frame                   │
│ • requestAnimationFrame animation loop                         │
│ • SVG coverage mask + per-radar rings                          │
│ • Coverage modes: C+D (vol 01/02) ↔ Vigilancia (vol 04)       │
│ • TopsCoresLayer: blob polygon fills + SVG core markers        │
│ • Nginx proxies+caches OSM and IGN Argenmap tile servers       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Installation & Quick Start

### Prerequisites

- **Docker** and **Docker Compose** 3.8+
- **COG files** at the path configured in `WATCH_PATH` (default `/product_output`)

### Clone & Setup

```bash
git clone <repository-url> webmet25
cd webmet25
cp .env.example .env
# Edit .env: DB credentials, paths, ADMIN_USERNAME/ADMIN_PASSWORD
```

### Run with Docker Compose

```bash
# Start all services
docker compose up -d

# Check service status
docker compose ps

# View logs
docker compose logs -f api
docker compose logs -f indexer
```

### Access the Application

- **Frontend map:** `http://localhost`
- **Admin panel:** `http://localhost/admin` (HTTP Basic Auth — credentials from `.env`)
- **API docs (Swagger):** `http://localhost:8000/docs`
- **API health:** `http://localhost/api/v1/health`

### Database Management

```bash
# Initialize tables + seed initial data (runs automatically via db-init service)
docker compose exec db-init python -m radar_db.manage init
docker compose exec db-init python -m radar_db.manage seed

# Sync seed data (full upsert — updates existing records, adds missing ones)
docker compose exec db-init python -m radar_db.manage sync

# Run pending migrations
docker compose exec db-init python -m radar_db.manage migrate upgrade

# Check database connection
docker compose exec db-init python -m radar_db.manage check

# Full reset + reseed (destructive — development only)
docker compose exec db-init python -m radar_db.manage reset --force --seed
```

See [`database/README.md`](database/README.md) for the full reference.

---

## API Overview

### Base URL

```
http://localhost/api/v1
```
(Proxied through nginx on port 80. Direct API port: 8000.)

### Public Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (DB + timestamp) |
| GET | `/radars` | List radar stations (`?active_only=true`) |
| GET | `/radars/{code}` | Get one radar |
| GET | `/products` | List products (`?vol_nr=01&strategy=0315`) |
| GET | `/products/{key}` | Get one product |
| GET | `/cogs` | Query COG metadata (`?radar_code&product_key&strategy&vol_nr&start_time&end_time&page&page_size`) |
| GET | `/cogs/latest` | Most recent COG for radar + product |
| GET | `/cogs/timeline` | Available timestamps for animation |
| GET | `/cogs/{id}` | Get one COG by ID |
| GET | `/frames/{cog_id}/image.png` | Full COG as georeferenced RGBA PNG — **v2 primary** (`?colormap&vmin&vmax&filter_vmin&filter_vmax&smooth&smooth_sigma`) |
| GET | `/tiles/{cog_id}/{z}/{x}/{y}.png` | Web Mercator tile — v1 / compatibility |
| GET | `/tiles/{cog_id}/metadata` | Tile rendering metadata |
| GET | `/colormap/names` | All colormap names |
| GET | `/colormap/options` | Per-product colormap options |
| GET | `/colormap/defaults` | Per-product default colormap |
| GET | `/colormap/colors/{name}` | Hex color list for a colormap |
| GET | `/colormap/info/{product_key}` | Full colormap info for a product |
| POST | `/colormap/cache/invalidate` | Flush colormap in-process cache |
| GET | `/tops-cores` | Query TopsAndCores metadata (`?radar_codes[]&time_from&time_to`) |
| GET | `/tops-cores/{id}/features` | Raw GeoJSON FeatureCollection from disk |

### Admin Endpoints (`/api/v1/admin/*`, nginx Basic Auth)

CRUD for: `radars`, `products`, `references`, `cogs`, `tops-cores`, `estrategias`, `volumenes`, `colormap-stops`, `colormap-from-hex`, `colormap-options`.

See [`docs/DATA_FLOW.md`](docs/DATA_FLOW.md) §4.9 for the full admin endpoint table.

---

## Frontend Features

### Multi-Radar Map (`/`)
- Multi-select radar list (sorted: active first, RMA before AR, numeric ascending with RMA00 last)
- `›` button on each radar to open the one-radar detail page
- **Coverage mode toggle:** C+D (volumes 01/02, full product suite) ↔ Vigilancia (volume 04, unfiltered only)
- Product selector with filtered/unfiltered toggle (inverted: checked = filtered = no `o` suffix)
- Time window: presets (1.5 h / 3 h / 4.5 h / 6 h) + custom date + iOS-style time wheel
- Live mode with configurable auto-refresh interval
- **Animation:** `requestAnimationFrame` playback, speed 0.5×–2×, manual frame navigation
- **Coverage mask:** SVG pane that dims outside radar coverage; opacity slider
- **Tops & Cores layer:** convective blob polygon fills (semi-transparent orange) with SVG core markers; top altitude shown in marker tooltip (COLMAX products only)
- **Gaussian smoothing:** server-side blur with configurable sigma
- **Basemap selector:** IGN Argenmap variants (default: Argenmap standard)
- Per-radar opacity slider
- **Snapshot:** canvas compositing of map + legend + timestamp → PNG download
- Settings panel with admin panel link

### One-Radar Detail Page (`/radar.html?code=XXX`)
- Multi-layer field system: add multiple fields, each with independent colormap, range filter, opacity, and smoothing
- Drag-to-reorder layers; eye toggle per layer; colormap strip with ticks
- Per-layer collapsible settings panel (Ajustes)
- Always operates in C+D mode (no VIG toggle)
- Coverage rings for each active layer's coverage radius

### Admin Panel (`/admin`, Basic Auth)
- Django-admin-style filtering and sorting for every table
- Visual colormap creator/editor with draggable gradient stops and live preview
- Hash-routed SPA; "← Volver al mapa" restores the main map via browser bfcache

---

## Database Schema Overview

| Table | Key Fields |
|-------|-----------|
| `radars` | `code` (PK), `title`, `center_lat/long`, `img_radio`, `is_active`, `detail_view_enabled` |
| `radar_products` | `product_key` (UNIQUE), `product_title`, `min_value`, `max_value`, `unit`, `default_cmap` |
| `radar_cogs` | `radar_code` (FK), `product_id` (FK), `estrategia_code` (FK), `observation_time`, `polarimetric_var`, `vol_nr`, `radar_coverage_m`, `file_path` (UNIQUE), `bbox` (PostGIS), `status` |
| `tops_and_cores` | `radar_code` (FK), `observation_time`, `file_path` (UNIQUE), `core_count`, `top_count`, `feature_count`, `strategy`, `vol_nr`, `status` |
| `references` | `product_id` (FK), `value`, `color`, `color_font` (color scale entries) |
| `estrategias` | `code`, `description`; M:M → `volumenes` |
| `volumenes` | `id`, `value` (integer volume number) |
| `colormap_stops` | `cmap_name`, `channel` (r/g/b), `position`, `val_left`, `val_right`, `sort_order`, `is_system` |
| `product_colormap_options` | `product_key` (FK), `cmap_name` (M:M pairing) |

`RadarCOG.status` enum: `AVAILABLE`, `MISSING`, `ERROR`, `PENDING`, `PROCESSING`, `ARCHIVED`

For full schema details, see [`docs/DATA_FLOW.md`](docs/DATA_FLOW.md) §3.

---

## Development

### Running Tests

```bash
# All tests (API + indexer + e2e)
docker exec radar_tests pytest

# API contract tests only
docker exec radar_tests pytest tests/api/ -v

# E2E browser tests (Playwright)
docker exec radar_tests pytest tests/e2e/ -v

# Single test file
docker exec radar_tests pytest tests/api/test_radars.py -v
```

See [`docs/E2E_TESTING.md`](docs/E2E_TESTING.md) for the full e2e setup guide.

### Code Style & Quality

```bash
black api/ database/ indexer/
flake8 api/ database/ indexer/
mypy api/ database/ indexer/
```

### radarlib Output Contract

WebMet25 depends entirely on radarlib's output format.

**Current production filename:** `{RADAR}_{strategy}_{vol_nr}_{YYYYMMDDTHHMMSSZ}_{FIELD}[o].tif`
Example: `RMA1_0315_01_20260401T205000Z_DBZHo.tif`

**Legacy filename (backward compat):** `{RADAR}_{YYYYMMDDTHHMMSSZ}_{FIELD}[o]_{elev}.tif`

**Folder structure:** `ROOT_RADAR_PRODUCTS_PATH/{RADAR_NAME}/YYYY/MM/DD/`

**GeoTIFF tags required:** `radarlib_cmap`, `radarlib_vmin`, `radarlib_vmax`, `field_name`

See [`.github/copilot-instructions.md`](.github/copilot-instructions.md) for the full contract.

---

## Known Gaps & Technical Debt

- ⚠️ Admin panel uses temporary **nginx HTTP Basic Auth** — must be replaced with JWT before production
- ❌ No transactions in the indexer — partial failures can leave DB in inconsistent state
- ❌ Database credentials in plaintext in `docker-compose.yml`
- ❌ No rate limiting on the public API
- ❌ No automatic archival/cleanup of old COG records
- ❌ Pydantic V2 class-based config deprecated in `indexer/config.py` and `radar_db/config.py` — must migrate to `ConfigDict` before Pydantic V3

---

## Acknowledgments

**WebMet25** is developed and maintained by **Grupo Radar Córdoba (GRC)** — Universidad Nacional de Córdoba, Argentina.

Consumes output from **radarlib**, the data producer library for meteorological radar processing.

---

**Version:** 2.0.0  
**Last Updated:** July 8, 2026
