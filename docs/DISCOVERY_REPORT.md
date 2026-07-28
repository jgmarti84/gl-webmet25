# WebMet25 — Technical Discovery Report

> Full technical analysis of the current codebase: architecture, DB schema, API contract, frontend, and known gaps.

---

## 1. Tech Stack

### Backend
- **Python:** 3.11
- **Web Framework:** FastAPI 0.109.0+
- **App Server:** Uvicorn
- **Database ORM:** SQLAlchemy 2.0.0+
- **Database Driver:** psycopg2-binary 2.9.9+ (PostgreSQL)
- **Geospatial ORM:** GeoAlchemy2 0.14.0+ (PostGIS)
- **Migrations:** Alembic 1.13.0+
- **Config:** Pydantic 2.0.0+, pydantic-settings 2.0.0+
- **Cache:** cachetools 5.0.0+ (LRU), redis 5.0.0+

### Geospatial & Raster Processing
- **Rasterio:** 1.3.0+ (COG reading)
- **rio-tiler:** 6.0.0+ (Web Mercator tile generation)
- **Shapely:** 2.0.0+ (geometry operations)
- **GDAL:** system package
- **SciPy:** 1.9.0+ (Gaussian smoothing in frames endpoint)

### Image Processing
- **Pillow:** 10.0.0+ (PNG encoding)
- **NumPy:** 1.24.0+
- **Matplotlib:** 3.7.0+ (colormap utilities)

### Frontend
- **Leaflet:** 1.9.4 (CDN)
- **Basemaps:** IGN Argenmap tile server (proxied + cached by nginx)
- **JavaScript:** ES6 modules (no build tool, no framework)
- **CSS:** Vanilla CSS3 — dark theme (main app), modern-light theme (admin)

### Infrastructure
- **Docker:** multi-service compose stack
- **Nginx:** 1.25+ — reverse proxy, admin Basic Auth, local OSM/IGN tile cache
- **Redis:** 7.2 — LRU eviction, no persistence, L2 frame/tile cache
- **PostgreSQL:** 15 + PostGIS 3.5

---

## 2. Project Architecture

### Directory Structure

```
webmet25/
├── .github/
│   └── copilot-instructions.md   # Full AI context reference
├── .claude/
│   └── skills/                   # Claude Code skill definitions
├── .devcontainer/                # VSCode dev container configs
├── api/                          # FastAPI backend service
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py               # App setup, CORS, middleware, routers
│       ├── config.py             # APISettings (DB, COG path, GDAL, Redis)
│       ├── schemas/
│       │   ├── responses.py      # Public Pydantic response models
│       │   └── admin.py          # Admin CRUD Pydantic models
│       ├── routers/
│       │   ├── radars.py
│       │   ├── products.py
│       │   ├── cogs.py
│       │   ├── tiles.py
│       │   ├── frames.py         # v2 primary — full-image COG rendering
│       │   ├── colormap.py       # DB-backed colormap service
│       │   ├── tops_cores.py
│       │   └── admin.py          # All admin CRUD
│       ├── services/
│       │   ├── tile_service.py   # TileService with thread pool executor
│       │   ├── colormap_service.py # Thread-safe singleton, 5-min TTL cache
│       │   ├── redis_client.py   # Redis connection management
│       │   └── smoothing.py      # Gaussian float-data blur (scipy)
│       └── utils/
│           └── colormaps.py      # Hardcoded fallback colormap builders
├── database/
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── migrations/
│   │   └── versions/             # 5 migration files as of July 2026
│   └── radar_db/
│       ├── models.py             # All SQLAlchemy models
│       ├── database.py           # DatabaseManager singleton
│       ├── seeds.py              # DataSeeder (seed_all / sync_all)
│       └── manage.py             # CLI: init, seed, sync, check, info, reset, migrate, shell
├── frontend/
│   ├── Dockerfile
│   ├── docker-entrypoint.sh      # Generates admin.htpasswd at startup
│   ├── nginx.conf
│   └── public/
│       ├── index.html            # Multi-radar map SPA shell
│       ├── radar.html            # One-radar detail page
│       ├── admin.html            # Admin SPA shell
│       ├── cog-browser.html      # Alternative COG browser
│       ├── css/
│       │   ├── styles.css        # Main app dark theme
│       │   └── admin.css         # Admin modern-light theme
│       └── js/
│           ├── admin.js          # Admin SPA orchestrator (1994 lines)
│           ├── admin-api.js      # Admin REST client (151 lines)
│           ├── shared/
│           │   ├── api.js        # REST client (213 lines)
│           │   ├── controls.js   # UIControls (602 lines)
│           │   ├── legend.js     # LegendRenderer (217 lines)
│           │   ├── tops-cores.js # TopsCoresLayer (255 lines)
│           │   ├── time-wheel.js # iOS HH:MM picker (93 lines)
│           │   ├── cog-browser-api.js
│           │   └── cog-browser.js
│           └── v2/
│               ├── app.js        # Multi-radar orchestrator (2526 lines)
│               ├── radar-app.js  # One-radar orchestrator (1662 lines)
│               ├── map.js        # MapManager (1076 lines)
│               ├── animation.js  # AnimationController (429 lines)
│               ├── radar-utils.js # Shared helpers (225 lines)
│               └── constants.js  # Constants (43 lines)
├── indexer/
│   └── indexer/
│       ├── main.py
│       ├── config.py             # IndexerSettings
│       ├── watcher.py            # COGWatcher + TopsAndCoresWatcher
│       ├── registrar.py          # COGRegistrar + TopsAndCoresRegistrar
│       ├── parser.py             # COGFilenameParser + TopsAndCoresFilenameParser
│       ├── deleter.py            # ProductDeleter (disk + DB cleanup utility)
│       └── manage.py
├── tests/
│   ├── Dockerfile
│   ├── api/                      # httpx API contract tests (6 files)
│   ├── indexer/                  # Unit tests (2 files)
│   └── e2e/                      # Playwright browser tests (3 files)
├── scripts/
│   ├── MANAGE_COMMANDS.md
│   └── delete_products.sh
└── docs/
    ├── DATA_FLOW.md
    ├── COMPONENTS.md
    ├── DISCOVERY_REPORT.md
    ├── E2E_TESTING.md
    └── OPERATIONS.md
```

### Service Map (`docker-compose.yml`)

| Container | Image | Role |
|-----------|-------|------|
| `radar_db` | postgis/postgis:15-3.5 | PostgreSQL + PostGIS (port 5433) |
| `redis` | redis:7.2-alpine | L2 frame/tile cache (512 MB LRU) |
| `db-init` | database Dockerfile | One-shot `init` + `seed`, then exits |
| `indexer` | indexer Dockerfile | COGWatcher + TopsAndCoresWatcher daemon |
| `api` | api Dockerfile | FastAPI + Uvicorn (port 8000) |
| `frontend` | frontend Dockerfile | Nginx (port 80) serving static files |

---

## 3. Database Schema

### 3.1 Models

All defined in `database/radar_db/models.py`.

#### `radars`
| Column | Type | Notes |
|--------|------|-------|
| `code` | String(16) PK | "RMA1", "AR5" |
| `title` | String(64) | Display name |
| `description` | String(64) | Optional |
| `center_lat` | Numeric(12,8) | |
| `center_long` | Numeric(12,8) | |
| `img_radio` | Integer | Coverage radius in km |
| `is_active` | Boolean | Updated by `update_radar_activity()` |
| `detail_view_enabled` | Boolean | Enables `radar.html` detail page link |
| `point1_lat/long` | Numeric(14,10) | Bounding box corner 1 |
| `point2_lat/long` | Numeric(14,10) | Bounding box corner 2 |
| `created_at`, `updated_at` | DateTime(tz) | |

#### `radar_products`
| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `product_key` | String(16) UNIQUE | "DBZH", "DBZHo", "COLMAX" |
| `product_title` | String(64) | Display name |
| `product_description` | Text | |
| `enabled` | Boolean | |
| `see_in_open` | Boolean | Show in unfiltered toggle |
| `min_value`, `max_value` | Float | Authoritative display range |
| `unit` | String(32) | "dBZ", "percent" |
| `default_cmap` | String(64) | DB-canonical default colormap name |

#### `radar_cogs`
| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `radar_code` | String FK → radars.code | |
| `product_id` | Integer FK → radar_products.id | |
| `estrategia_code` | String FK → estrategias.code | NULL for legacy files |
| `observation_time` | DateTime(tz) INDEX | |
| `polarimetric_var` | String(16) | Exact field name incl. `o` suffix, e.g. "DBZHo" |
| `elevation_angle` | Float | Legacy files only; NULL for production |
| `vol_nr` | String(16) | "01", "02", "04"; NULL for legacy |
| `radar_coverage_m` | Float | Coverage radius in metres (from COG tag) |
| `file_path` | String UNIQUE | Relative path on disk |
| `file_name` | String | Filename only |
| `file_size_bytes` | Integer | |
| `file_mtime` | DateTime(tz) | |
| `file_checksum` | String(64) | SHA-256 (if `COMPUTE_CHECKSUM=true`) |
| `crs` | String | "EPSG:3857" (Web Mercator) |
| `width`, `height` | Integer | Pixels |
| `num_bands` | Integer | |
| `dtype` | String | "float32" |
| `resolution_x`, `resolution_y` | Float | Degrees/metre per pixel |
| `nodata_value` | Float | |
| `compression` | String | "deflate", None |
| `cog_data_type` | String | "raw_float", "rgba", "unknown" |
| `cog_cmap` | String | Colormap name from radarlib tag |
| `cog_vmin`, `cog_vmax` | Float | Data range from radarlib tag |
| `data_min`, `data_max`, `data_mean` | Float | Band statistics (if computed) |
| `valid_pixel_count` | Integer | |
| `bbox` | Geometry('POLYGON', srid=4326) | WGS84 bounding box |
| `status` | COGStatus enum | AVAILABLE, MISSING, ERROR, PENDING, PROCESSING, ARCHIVED |
| `error_message` | Text | |
| `show_me` | Boolean | |
| `created_at`, `updated_at` | DateTime(tz) | |

**Unique constraint:** `(radar_code, product_id, observation_time, elevation_angle, vol_nr)` — NULL vol_nr rows are each independent (NULL ≠ NULL in PostgreSQL).

#### `tops_and_cores`
| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `radar_code` | String FK → radars.code | |
| `observation_time` | DateTime(tz) INDEX | |
| `file_path` | String UNIQUE | |
| `file_name` | String | |
| `feature_count` | Integer | Total GeoJSON features |
| `core_count` | Integer | Features with `type=core` |
| `top_count` | Integer | Features with `type=top` |
| `status` | COGStatus | AVAILABLE or MISSING |
| `strategy` | String(16) | e.g. "0315" |
| `vol_nr` | String(16) | e.g. "00" |
| `created_at`, `updated_at` | DateTime(tz) | |

#### `references`
| Column | Type |
|--------|------|
| `id` | Integer PK |
| `product_id` | Integer FK → radar_products.id INDEX |
| `title`, `description`, `unit` | String |
| `value` | Float |
| `color`, `color_font` | String(7) |

#### `estrategias` / `volumenes`
`estrategias(code PK, description)` ↔ M:M via `estrategia_volumen` ↔ `volumenes(id PK, value int)`.

#### `colormap_stops`
| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `cmap_name` | String | e.g. "grc_th" |
| `channel` | String | "r", "g", or "b" |
| `position` | Float | 0.0 – 1.0 within color range |
| `val_left`, `val_right` | Float | Physical data values for this segment |
| `sort_order` | Integer | |
| `is_system` | Boolean | System colormaps → 403 on DELETE |

8 system colormaps: `grc_th`, `grc_th2`, `grc_rain`, `grc_g`, `grc_rho`, `grc_zdr`, `grc_vrad`, `Theodore16`.

#### `product_colormap_options`
`(id PK, product_key FK, cmap_name)` — UniqueConstraint `(product_key, cmap_name)`.

### 3.2 `COGStatus` Enum Values

| Value | Meaning |
|-------|---------|
| `AVAILABLE` | File indexed and accessible |
| `MISSING` | Previously indexed; file no longer on disk |
| `ERROR` | Metadata extraction failed during indexing |
| `PENDING` | Reserved; not currently used |
| `PROCESSING` | Reserved; not currently used |
| `ARCHIVED` | Reserved; not currently used |

---

## 4. Indexer

### 4.1 Execution Flow

```
indexer/indexer/main.py: run_indexer()
├── wait_for_database()            # Retry until PostgreSQL responds
├── TopsAndCoresWatcher.run_forever()   → background daemon thread
└── COGWatcher.run_forever()       → main thread (blocks forever)

COGWatcher loop (every SCAN_INTERVAL=30 s):
├── First run: glob all *.tif under WATCH_PATH
├── Subsequent runs: glob files modified in last 5 min + 30 s overlap
├── For each file:
│   ├── COGFilenameParser.parse(filename)  → ParseResult
│   ├── COGRegistrar.register_file(path, session)  → cog_id or None
│   └── catch Exception → log error, continue (bad file ≠ stop scan)
└── update_radar_activity(session)   → set Radar.is_active based on recent AVAILABLE COGs

TopsAndCoresWatcher loop (same SCAN_INTERVAL):
├── rglob *_TOPS_CORES.geojson under TOPS_AND_CORES_DIR
└── For each file:
    └── TopsAndCoresRegistrar.register(path, session)
```

### 4.2 Filename Parsing

`COGFilenameParser` tries Pattern 0 first; falls back to Pattern 1 (legacy):

| Pattern | Format | Notes |
|---------|--------|-------|
| 0 (production) | `{RADAR}_{strategy}_{vol_nr}_{YYYYMMDDTHHMMSSZ}_{FIELD}[o].tif` | Full metadata |
| 1 (legacy) | `{RADAR}_{YYYYMMDDTHHMMSSZ}_{FIELD}[o]_{elev}.tif` | strategy=None, vol_nr=None; WARNING logged |

`TopsAndCoresFilenameParser` parses: `{RADAR}_{strategy}_{vol_nr}_{YYYYMMDDHHMMSS}_TOPS_CORES.geojson` (no `T` or `Z`).

### 4.3 Database Registration

`COGRegistrar.register_file()`:
1. Parse filename → validate radar code in DB, validate product key in DB
2. Open with `rasterio` → extract CRS, bounds, dimensions, dtype, tags
3. Transform bounds to WGS84 (GeoAlchemy2 `from_shape`)
4. INSERT `RadarCOG` with `status=AVAILABLE` (ON CONFLICT via file_path UNIQUE: update metadata)
5. If `MARK_MISSING_FILES=true`: compare indexed paths against disk; mark absent ones `MISSING`

### 4.4 Product Deleter (`indexer/indexer/deleter.py`)

`ProductDeleter.delete_products(date, radar_codes, product_keys)`:
- Scans filesystem for `.tif` files matching criteria
- Deletes files from disk; removes empty parent directories
- Deletes matching `RadarCOG` DB records in a single transaction
- Optionally deletes `genpro25.log.YYYY-MM-DD` log files

See [`docs/OPERATIONS.md`](OPERATIONS.md) for usage.

---

## 5. API Contract

### 5.1 Public Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Health check: DB status + timestamp |
| GET | `/api/v1/radars` | List radars (`?active_only=true`) |
| GET | `/api/v1/radars/{code}` | Get one radar |
| GET | `/api/v1/products` | List products (`?enabled_only=true&vol_nr=01&strategy=0315`) |
| GET | `/api/v1/products/{key}` | Get one product |
| GET | `/api/v1/products/{key}/colormap` | **Deprecated** — use `/colormap/info/{key}` |
| GET | `/api/v1/cogs` | Paginated COG list (filters: radar_code, product_key, strategy, vol_nr[], start_time, end_time, page, page_size) |
| GET | `/api/v1/cogs/latest` | Most recent COG for radar+product |
| GET | `/api/v1/cogs/timeline` | Available timestamps (`?radar_code&product_key&hours`) |
| GET | `/api/v1/cogs/{id}` | Get one COG |
| GET | `/api/v1/frames/{id}/image.png` | Full-image COG PNG (`?colormap&vmin&vmax&filter_vmin&filter_vmax&smooth&smooth_sigma`) |
| GET | `/api/v1/tiles/{id}/{z}/{x}/{y}.png` | Web Mercator tile (`?colormap&vmin&vmax`) |
| GET | `/api/v1/tiles/by-params/{radar}/{product}/{timestamp}/{z}/{x}/{y}.png` | Tile by params |
| GET | `/api/v1/tiles/{id}/metadata` | Tile rendering metadata |
| GET | `/api/v1/tiles/cache/stats` | Cache statistics |
| GET | `/api/v1/colormap/names` | All colormap names |
| GET | `/api/v1/colormap/options` | Per-product colormap options |
| GET | `/api/v1/colormap/defaults` | Per-product default colormap |
| GET | `/api/v1/colormap/colors/{name}` | Hex color list (`?steps=256`) |
| GET | `/api/v1/colormap/info/{key}` | Full colormap info for a product |
| POST | `/api/v1/colormap/cache/invalidate` | Flush in-process colormap cache |
| GET | `/api/v1/tops-cores` | Query metadata (required: `radar_codes[]`, `time_from`, `time_to`) |
| GET | `/api/v1/tops-cores/{id}/features` | Raw GeoJSON FeatureCollection |

### 5.2 Admin Endpoints (`/api/v1/admin/*`, nginx Basic Auth)

| Resource | Operations |
|----------|-----------|
| `/admin/radars` | GET, GET/{code}, POST, PUT/{code}, PATCH/{code}, DELETE/{code} |
| `/admin/products` | GET, GET/{id}, POST, PUT/{id}, PATCH/{id}, DELETE/{id} |
| `/admin/references` | GET (`?product_id`), GET/{id}, POST, PUT/{id}, DELETE/{id}, DELETE bulk by `product_id` |
| `/admin/cogs` | GET (paginated+filtered), GET/{id}, PATCH/{id} (status), DELETE/{id}, DELETE bulk |
| `/admin/estrategias` | GET, GET/{code}, POST, PUT/{code}, DELETE/{code} |
| `/admin/volumenes` | GET, GET/{id}, POST, PUT/{id}, DELETE/{id} |
| `/admin/tops-cores` | GET (paginated), GET/{id}, PATCH/{id} (status), DELETE/{id}, DELETE bulk |
| `/admin/colormap-stops` | GET summaries, GET/{name}, POST (one row), DELETE/{name} (→ 403 if system) |
| `/admin/colormap-from-hex` | POST (create from stops array + product_keys) → 409 if name exists |
| `/admin/colormap-options` | GET (`?product_key`), POST, DELETE/{id} |

### 5.3 Response Models (Key Schemas)

**`RadarResponse`:** `code`, `title`, `description`, `center_lat`, `center_long`, `img_radio`, `is_active`, `detail_view_enabled`, `extent` (bbox dict)

**`COGResponse`:** `id`, `radar_code`, `product_key`, `product_id`, `observation_time`, `elevation_angle`, `file_path`, `file_name`, `data_min`, `data_max`, `bbox`, `tile_url`, `cog_data_type`, `cog_cmap`, `cog_vmin`, `cog_vmax`, `strategy`, `vol_nr`, `radar_coverage_m`

**`TopsAndCoresRecord`:** `id`, `radar_code`, `observation_time`, `file_name`, `feature_count`, `core_count`, `top_count`, `status`, `strategy`, `vol_nr`

---

## 6. Frontend Architecture

### 6.1 v2 vs v1

| Aspect | v1 (legacy, `js/v1/`) | v2 (production, `js/v2/`) |
|--------|-----------------------|--------------------------|
| Radar layer | `L.tileLayer` | `L.imageOverlay` |
| Endpoint | `/tiles/{id}/{z}/{x}/{y}.png` | `/frames/{id}/image.png` |
| Animation | `setInterval` opacity toggle | `requestAnimationFrame` |
| DOM objects | ~180 TileLayers per session | 1 overlay per radar+product |
| HTTP requests | ~1800 per session | ~180 per session |
| Coverage mask | None | SVG pane (z-index 300) |
| Tops & Cores | None | Blob polygon fills (z-index 440) + SVG core markers (z-index 450); pre-loaded for all frames at startup |
| One-radar page | None | `radar.html` + `radar-app.js` |
| Admin panel | None | Separate SPA at `/admin` |

### 6.2 Key Design Invariants

1. **Animation continuity:** All data loads go through `_loadFramesWithContinuity()` — animation never stops mid-load. Never call `animator.stop()`, `animator.reset()`, or clear layers before new frames are staged.

2. **Spanish UI:** All user-facing text is in Spanish (es-AR). `console.*` debug logs stay in English.

3. **Coverage mode:** `COVERAGE_MODES` in `constants.js` defines which `vol_nr` values map to each mode. Mode persisted to `webmet25_coverage_mode`.

4. **Colormap normalization vs filter:** The `/frames` endpoint's `filter_vmin`/`filter_vmax` alpha-mask pixels outside the range — they do NOT change colormap normalization. Colormap normalization always uses product defaults.

5. **Basemap:** Default is `argenmap` (IGN). Always use `MapManager.setBasemap(key)`.

6. **Radar ordering:** `sortRadarsForDisplay` in `controls.js` — active before inactive; RMA before AR; numeric ascending with RMA00 (number 0) sorted last.

### 6.3 localStorage Keys (v2)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `webmet25_show_inactive_radars` | boolean | false | Show inactive radars |
| `webmet25_show_filtered_fields` | boolean | false | Show filtered (non-`o`) fields |
| `webmet25_live_refresh_interval_ms` | number | 300000 | Live refresh interval (ms) |
| `webmet25_radar_refresh_interval_min` | number | 10 | Radar status refresh (min) |
| `webmet25_coverage_visible` | boolean | false | Coverage mask toggle |
| `webmet25_coverage_opacity` | number | 0.4 | Coverage mask opacity |
| `webmet25_coverage_mode` | string | 'cd' | Active coverage mode id |
| `webmet25_tops_cores_visible` | boolean | false | Tops & Cores layer toggle |
| `webmet25_tops_cores_size` | number | 8 | Circle marker radius (px) |
| `webmet25_smooth_enabled` | boolean | false | Gaussian smoothing toggle |
| `webmet25_smooth_sigma` | number | 0.8 | Gaussian sigma value |
| `webmet25_selected_basemap` | string | 'argenmap' | Active basemap key |

### 6.4 Module Sizes

| File | Lines | Role |
|------|-------|------|
| `v2/app.js` | 2526 | Multi-radar map orchestrator |
| `v2/radar-app.js` | 1662 | One-radar detail page |
| `v2/map.js` | 1076 | MapManager + coverage mask |
| `js/admin.js` | 1994 | Admin SPA |
| `v2/animation.js` | 429 | AnimationController |
| `shared/controls.js` | 602 | UIControls |
| `shared/tops-cores.js` | 255 | TopsCoresLayer |
| `shared/api.js` | 213 | REST client |
| `shared/legend.js` | 217 | LegendRenderer |
| `v2/radar-utils.js` | 225 | Shared helpers |

---

## 7. Nginx Configuration

`frontend/nginx.conf` (key behaviors):

- `GET /` → serves `index.html` (SPA fallback via `try_files`)
- `GET /admin` and `GET /admin/*` → HTTP Basic Auth (`admin.htpasswd`), serves `admin.html`
- `POST,GET /api/v1/admin/*` → Basic Auth + `proxy_pass http://api:8000`
- `GET /api/*` → `proxy_pass http://api:8000`, `proxy_buffering off` (SSE/streaming support)
- `GET /osm-tiles/*` → proxy to `tile.openstreetmap.org`, 30-day local cache (1 GB max zone)
- `GET /ign-tiles/*` → proxy to `wms.ign.gob.ar`, 7-day local cache (same zone)
- `GET /health` → inline 200 OK (no API hit needed)
- gzip enabled for text/css/json/js/xml

The local tile proxy means basemap tiles are cached on the server after first request, reducing external dependency and latency.

---

## 8. Gaps & Technical Debt

### 8.1 Critical

| # | Issue | Status |
|---|-------|--------|
| C1 | Admin auth uses temporary **nginx HTTP Basic Auth** — must be replaced with JWT before production | ❌ Open |
| C2 | No transactions in the indexer — partial failures can leave DB in inconsistent state | ❌ Open |
| C3 | Database credentials in plaintext in `docker-compose.yml` | ❌ Open |

### 8.2 High Priority

| # | Issue | Status |
|---|-------|--------|
| H1 | No rate limiting on the public API — vulnerable to denial-of-service | ❌ Open |
| H2 | Incomplete error handling in tile renderer (some edge cases may still 500) | ❌ Open |
| H3 | L1 LRU + L2 Redis cache for frames and tiles | ✅ Resolved |
| H4 | Gaussian smoothing in frames endpoint | ✅ Resolved |

### 8.3 Medium Priority

| # | Issue | Status |
|---|-------|--------|
| M1 | No pagination on products and references endpoints | ❌ Open |
| M2 | No monitoring or log aggregation | ❌ Open |
| M3 | No automatic archival/cleanup of old COG records | ❌ Open |
| M4 | API contract tests + indexer unit tests + Playwright e2e tests | ✅ Resolved |
| M5 | Coverage Mode Toggle (C+D / VIG) via `COVERAGE_MODES` | ✅ Resolved |
| M6 | Tops & Cores convective layer (indexer + API + frontend) | ✅ Resolved |
| M7 | Radar activity auto-updated by indexer (`update_radar_activity()`) | ✅ Resolved |

### 8.4 Low Priority / Technical Debt

| # | Issue | Status |
|---|-------|--------|
| L1 | Pydantic V2 class-based `class Config:` deprecated in `indexer/config.py` and `radar_db/config.py` — must migrate to `ConfigDict` before Pydantic V3 | ❌ Open |
| L2 | `GET /products/{key}/colormap` endpoint is deprecated — use `GET /colormap/info/{key}` instead | ❌ Documented, not removed |
| L3 | v1 frontend (`js/v1/`) retained as legacy reference — can be removed once fully confident in v2 | ❌ Open |
| L4 | No WebSocket real-time updates — polling every 5 min instead | ❌ Open (by design for now) |

---

**Document Version:** 2.0.0  
**Last Updated:** July 8, 2026
