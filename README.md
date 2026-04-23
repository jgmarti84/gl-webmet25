# WebMet25 — Radar Visualization & Data Indexing System

WebMet25 is a **data consumer** application in the radar/meteorology system. It ingests Cloud-Optimized GeoTIFF (COG) files produced by [radarlib](https://gitlab.example.com/radarlib), indexes them into a PostgreSQL/PostGIS database, and serves them via a REST API with an interactive Leaflet-based web frontend for real-time radar visualization.

## System Context

```
radarlib (producer)
    │
    ├── outputs GeoTIFF COGs to ROOT_RADAR_PRODUCTS_PATH
    │
    ▼
webmet25 (consumer)
    │
    ├── Indexer watches ROOT_RADAR_PRODUCTS_PATH
    │   ├── parses filenames
    │   ├── extracts metadata
    │   └── stores in PostgreSQL/PostGIS
    │
    ├── FastAPI serves metadata + tiles
    │
    └── Leaflet frontend renders radar map
```

---

## Features

- **Real-Time Indexing:** Automatic file-system watcher that scans for new COG files every 30 seconds
- **Spatial Database:** PostGIS integration for geographic queries and bounding-box calculations
- **REST API:** Comprehensive endpoints for querying radars, products, COGs, and rendering tiles
- **Interactive Map:** Leaflet-based visualization with multiple radar overlay support
- **Animation Controls:** Play/pause, speed control (0.5x–2x), and manual frame navigation
- **Time-Window Selection:** Load data for specific time ranges with automatic grouping by timestamp
- **Live Mode:** 5-minute polling to continuously refresh animation with newest available data
- **Colormap Management:** Dynamic colormap selection with value-range filtering
- **Geolocation Support:** Auto-detect user location and pre-select nearest radars
- **Opacity Control:** Per-radar layer transparency adjustment
- **Legend Rendering:** Dynamic color scale visualization from database Reference entries

---

## Tech Stack

### Backend
- **Language:** Python 3.11
- **Web Framework:** [FastAPI](https://fastapi.tiangolo.com/) 0.109.0+
- **App Server:** [Uvicorn](https://www.uvicorn.org/)
- **Database ORM:** [SQLAlchemy](https://www.sqlalchemy.org/) 2.0.0+
- **Database Driver:** [psycopg2-binary](https://www.psycopg.org/) 2.9.9+ (PostgreSQL)
- **Geospatial ORM:** [GeoAlchemy2](https://geoalchemy-2.readthedocs.io/) 0.14.0+ (PostGIS support)
- **Migrations:** [Alembic](https://alembic.sqlalchemy.org/) 1.13.0+
- **Configuration:** [Pydantic](https://docs.pydantic.dev/) 2.0.0+, [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) 2.0.0+

### Geospatial & Raster Processing
- **Rasterio:** 1.3.0+ (Cloud-Optimized GeoTIFF reading and metadata extraction)
- **rio-tiler:** 6.0.0+ (Web Mercator tile generation from COGs)
- **Shapely:** 2.0.0+ (Geometry operations and bounding-box calculations)
- **GDAL:** System package with `gdal-bin` and `libgdal-dev`

### Image Processing
- **Pillow:** 10.0.0+ (PNG encoding)
- **NumPy:** 1.24.0+ (Array operations on tile data)
- **Matplotlib:** 3.7.0+ (Colormap utilities)

### Frontend
- **Leaflet:** 1.9.4 (via CDN)
- **CartoDB Basemaps:** Via Leaflet providers plugin
- **JavaScript:** ES6 modules (no build tool)
- **CSS:** Vanilla CSS3 (dark theme, responsive layout)
- **HTML5:** Semantic markup

### DevOps & Containerization
- **Docker:** Multi-stage builds per service
- **Docker Compose:** 3.8+ for orchestration
- **Nginx:** Reverse proxy and static file serving
- **VSCode Dev Containers:** For local development

### Database
- **PostgreSQL:** 15+ with PostGIS 3.5
- **PostGIS:** Spatial database extension
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
│       ├── main.py               # FastAPI app initialization & routers
│       ├── config.py             # APISettings configuration
│       ├── schemas/
│       │   └── responses.py      # Pydantic response models
│       ├── routers/              # API endpoint handlers
│       │   ├── radars.py         # GET /radars, /radars/{code}
│       │   ├── products.py       # GET /products
│       │   ├── cogs.py           # GET /cogs with filtering
│       │   ├── tiles.py          # GET /tiles/{cog_id}/{z}/{x}/{y}.png
│       │   └── colormap.py       # GET /products/{key}/colormap
│       ├── services/             # Business logic
│       │   └── tile_service.py   # TileService for COG rendering
│       └── utils/                # Utility functions
│           └── colormaps.py      # Colormap configuration
│
├── database/                      # Shared database package
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── README.md                 # Database management guide
│   ├── alembic.ini               # Alembic migration config
│   ├── migrations/               # Alembic migration files
│   │   ├── env.py
│   │   └── versions/
│   ├── radar_db/                 # Python package (shared by API & Indexer)
│   │   ├── __init__.py
│   │   ├── config.py             # DatabaseSettings
│   │   ├── database.py           # DatabaseManager, connection pooling
│   │   ├── models.py             # SQLAlchemy models
│   │   ├── seeds.py              # DataSeeder for initial data
│   │   └── manage.py             # CLI for init, seed, migrate, reset
│   └── seed_data/
│       ├── initial_data.json     # Seed data (radars, products, references)
│       └── initial_data_00.json  # Alternative seed format
│
├── frontend/                      # Static web frontend (Nginx)
│   ├── Dockerfile
│   ├── nginx.conf                # Reverse proxy configuration
│   ├── README.md                 # Frontend-specific documentation
│   └── public/
│       ├── index.html            # Main radar visualization page
│       ├── cog-browser.html      # Alternative COG browser view
│       ├── css/
│       │   └── styles.css        # Dark theme, responsive styles (444 lines)
│       └── js/
│           ├── app.js            # Main app orchestrator (logic, state)
│           ├── api.js            # REST API client
│           ├── map.js            # Leaflet map manager
│           ├── animation.js      # Frame animation controller
│           ├── controls.js       # UI control handlers
│           ├── legend.js         # Legend renderer
│           ├── cog-browser-api.js # Alternative API client
│           └── cog-browser.js    # Alternative app variant
│
├── indexer/                       # COG file indexing service
│   ├── Dockerfile
│   ├── requirements.txt
│   └── indexer/
│       ├── __init__.py
│       ├── main.py               # Entry point: run_indexer(), run_single_scan()
│       ├── config.py             # IndexerSettings (env vars)
│       ├── watcher.py            # COGWatcher — file system scanning
│       ├── registrar.py          # COGRegistrar — file parsing & DB registration
│       ├── parser.py             # COGFilenameParser — filename parsing
│       └── manage.py             # CLI: check, populate-cog-metadata
│
├── docker-compose.yml            # Production orchestration
├── docker-compose.devcontainer.yml # Dev container overrides
├── .env.example                  # Environment variable template
├── .gitignore
├── LICENSE
├── README.md                     # This file
└── docs/
    └── DISCOVERY_REPORT.md      # Comprehensive technical analysis
```

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ RADARLIB (External Producer)                                    │
│ Outputs COG files with embedded GeoTIFF metadata tags           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    /product_output/
              (shared volume or NAS mount)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ INDEXER SERVICE (Container: radar_indexer)                      │
│                                                                   │
│ • Watches /product_output for *.tif files                       │
│ • Every 30 seconds: scan, parse filenames, extract metadata     │
│ • Register in database or mark MISSING                          │
│ • Uses COGWatcher → COGFilenameParser → COGRegistrar            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ DATABASE (Container: radar_db, PostgreSQL + PostGIS)            │
│                                                                   │
│ • RadarCOG table: stores file metadata, bbox, rendering params  │
│ • Radar, RadarProduct, Reference tables: lookups                │
│ • Indexed by: radar_code, product_id, observation_time, status  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ API (Container: radar_api, FastAPI + Uvicorn)                   │
│                                                                   │
│ Endpoints:                                                        │
│  • GET /radars — List all radar stations                         │
│  • GET /products — List available radar products                │
│  • GET /cogs — Query COG metadata with filtering                │
│  • GET /tiles/{id}/{z}/{x}/{y}.png — Render map tile            │
│  • GET /products/{key}/colormap — Get color scale               │
│                                                                   │
│ Services:                                                         │
│  • TileService: opens COG, renders tile, applies colormap       │
│  • ColormapService: builds legend from Reference entries        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ FRONTEND (Container: radar_frontend, Nginx + Leaflet)           │
│                                                                   │
│ • Interactive Leaflet map with radar overlays                    │
│ • Radar & product selection with multi-select support           │
│ • Time-window picker (preset or custom range)                   │
│ • Animation controls: play/pause, speed, frame navigation       │
│ • Live mode: 5-min polling for newest data                      │
│ • Geolocation auto-init                                         │
│ • Opacity slider, legend display, map snapshot                  │
│                                                                   │
│ Architecture:                                                     │
│  • app.js — State management & orchestration                    │
│  • api.js — REST client                                         │
│  • map.js — Leaflet wrapper                                     │
│  • animation.js — Frame playback controller                     │
│  • controls.js — UI event handlers                              │
│  • legend.js — Colormap legend renderer                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    (Browser)
                    User visualization
```

### Folder Responsibilities

| Folder | Purpose | Key Responsibility |
|--------|---------|-------------------|
| `api/` | FastAPI backend | REST endpoints for data queries and tile rendering |
| `database/` | Shared DB layer | SQLAlchemy models, migrations, connection pooling |
| `frontend/` | Web UI | Interactive map visualization, state management |
| `indexer/` | File watcher | Scan filesystem, parse filenames, index COGs |
| `docs/` | Documentation | Technical analysis and architecture details |

---

## Installation & Quick Start

### Prerequisites

- **Docker** and **Docker Compose** 3.8+
- **Git**
- **COG files** available at `/path/to/product_output` (shared volume)

### Clone & Setup

```bash
# Clone the repository
git clone <repository-url> webmet25
cd webmet25

# Copy environment template
cp .env.example .env

# Edit .env as needed (DB credentials, paths, etc.)
nano .env
```

### Run with Docker Compose

```bash
# Start all services (database, indexer, API, frontend)
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f api
docker-compose logs -f indexer
```

### Access the Application

- **Frontend:** `http://localhost` (Nginx reverse proxy)
- **API Docs:** `http://localhost:8000/docs` (FastAPI Swagger UI)
- **API Health:** `http://localhost:8000/health`

### Database Management

```bash
# Initialize database (runs automatically on first docker-compose up)
docker exec radar_db_init python -m radar_db.manage init

# Seed initial data (radar stations, products, color references)
docker exec radar_db_init python -m radar_db.manage seed

# Run database migrations
docker exec radar_db_init python -m radar_db.manage migrate

# Check database connection
docker exec radar_indexer python -m indexer.manage check
```

---

## API Overview

### Base URL

```
http://localhost:8000/api/v1
```

### Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check (DB status) |
| `/radars` | GET | List all radar stations |
| `/radars/{code}` | GET | Get specific radar details |
| `/products` | GET | List available radar products |
| `/cogs` | GET | Query COG metadata with filters |
| `/tiles/{cog_id}/{z}/{x}/{y}.png` | GET | Render map tile |
| `/products/{product_key}/colormap` | GET | Get color scale entries |

For detailed API documentation, visit `http://localhost:8000/docs` after starting the API container.

---

## Frontend Features

### Radar Selection
- Multi-select checkboxes for simultaneous visualization
- Toggle to show/hide inactive radar stations
- **Load Latest** button to fetch newest available data

### Product/Field Selection
- Dropdown to choose radar product (e.g., COLMAX, DBZH)
- Toggle for **Filtered** vs. **Unfiltered** fields (processed vs. raw data)
- Colormap selector with custom value-range filtering

### Time-Window Control
- Preset buttons: Last 1.5h, 3h, 4.5h, 6h
- Custom date/time range picker
- **Live mode** with 5-minute auto-refresh

### Animation Controls
- **Play/Pause** button
- **Previous/Next** frame navigation
- **Speed** control (0.5x, 1x, 1.5x, 2x)
- Frame counter and timeline slider
- **Latest** button to jump to most recent frame

### Map Interaction
- Basemap selector (Dark, Light, OpenStreetMap, Satellite, Terrain)
- Opacity slider for radar layers
- **Snapshot** button to download current map view
- Pan, zoom, and layer toggle controls (Leaflet native)

### Geolocation
- Auto-detect user location (browser + IP fallback)
- Automatically select 3 nearest active radars
- Load last 3 hours of data on initialization

### Legend
- Dynamic color scale visualization
- Value-to-color mapping from database Reference entries
- Show/hide toggle

---

## Database Schema Overview

### Core Tables

**Radar** — Radar station metadata
- `code` (PK): station identifier (e.g., "RMA1")
- `title`, `description`: display name
- `center_lat`, `center_long`: station location
- `img_radio`: coverage radius (km)
- `is_active`: visibility flag
- `point1_lat/long`, `point2_lat/long`: bounding box corners

**RadarProduct** — Product type definitions
- `product_key` (UNIQUE): identifier (e.g., "COLMAX", "DBZH")
- `product_title`, `product_description`: display info
- `min_value`, `max_value`: data range
- `unit`: measurement unit (e.g., "dBZ")

**RadarCOG** — Indexed COG file references
- `id` (PK): database ID
- `radar_code` (FK): which radar
- `product_id` (FK): which product
- `observation_time`: data acquisition timestamp
- `file_path` (UNIQUE): relative path on disk
- `file_size_bytes`, `file_checksum`: file metadata
- `cog_cmap`, `cog_vmin`, `cog_vmax`: rendering parameters from GeoTIFF tags
- `bbox` (PostGIS POLYGON): geographic extent
- `status`: AVAILABLE, MISSING, or ERROR
- Spatial & raster metadata: CRS, resolution, width, height, dtype

**Reference** — Color scale entries for legends
- `id` (PK), `product_id` (FK)
- `value`: numeric value (e.g., 10.0 dBZ)
- `color`: hex color code (e.g., "#a40000")
- `color_font`: label text color

**Estrategia, Volumen** — Scanning strategy configuration (optional)

For full schema details, see [`database/README.md`](database/README.md).

---

## Development

### Local Setup with Dev Containers

```bash
# Open in VSCode with dev container support
code .

# In VSCode Command Palette: "Dev Containers: Reopen in Container"
# Select "webmet" configuration
```

### Running Tests

```bash
# Execute into the tests container (if exists)
docker exec -it radar_tests pytest tests/

# Run specific test file
docker exec -it radar_tests pytest tests/api/test_radars.py -v
```

### Code Style & Quality

- **Formatter:** [black](https://github.com/psf/black) (Python)
- **Linter:** [flake8](https://flake8.pycqa.org/) (Python)
- **Type Checking:** [mypy](https://www.mypy-lang.org/) (Python)
- **Frontend:** No formatter/linter (vanilla JS/CSS)

Run before committing:

```bash
black api/ database/ indexer/
flake8 api/ database/ indexer/
mypy api/ database/ indexer/
```

---

## Linking to radarlib

WebMet25 depends on the **radarlib** output contract. The expected file format and metadata are defined in radarlib's documentation:

- **Primary Format:** Cloud-Optimized GeoTIFF (.tif)
- **PNG:** Deprecated (backward compatibility only)
- **File Naming:** `<RADAR_NAME>_<TIMESTAMP>_<FIELD>[o]_<ELEVATION>.<ext>`
- **GeoTIFF Tags:** `radarlib_cmap`, `radarlib_vmin`, `radarlib_vmax`, `field_name`, `timestamp`
- **Output Path:** `ROOT_RADAR_PRODUCTS_PATH/{radar_code}/{product_key}/{filename}.tif`

See [`docs/DISCOVERY_REPORT.md`](docs/DISCOVERY_REPORT.md) for full architectural details.

---

## Troubleshooting

### Database Connection Issues

```bash
# Check database health
docker-compose ps radar_db

# View database logs
docker-compose logs radar_db

# Restart database
docker-compose restart radar_db
```

### Indexer Not Finding Files

```bash
# Check indexer logs
docker-compose logs indexer

# Verify watch path exists and is accessible
docker exec radar_indexer ls -la /product_output

# Run single scan manually
docker exec radar_indexer python -m indexer.main --single --debug
```

### Tiles Not Rendering

```bash
# Check API logs
docker-compose logs api

# Verify COG file exists and is readable
docker exec radar_api ls -la /product_output/{radar_code}/{product_key}/

# Test tile endpoint directly
curl http://localhost:8000/api/v1/tiles/1/10/500/400.png -o test.png
```

### Frontend Not Loading

```bash
# Check Nginx logs
docker-compose logs frontend

# Verify API is accessible from frontend container
docker exec radar_frontend curl http://api:8000/health

# Check browser console for JavaScript errors (F12)
```

---

## Performance Tips

- **Tile Caching:** Tiles are rendered on-demand. For high-traffic deployments, consider adding HTTP cache headers or a Redis layer.
- **Database Indexing:** RadarCOG table is indexed on `radar_code`, `product_id`, `observation_time`, and `status`.
- **Animation Preloading:** Leaflet tiles are pre-fetched in background before animation starts.
- **Geolocation:** Browser Geolocation API is tried first; falls back to IP-based geolocation if denied.

---

## Known Gaps & Limitations

See [`docs/DISCOVERY_REPORT.md`](docs/DISCOVERY_REPORT.md) **Section 8: Gaps & Risks** for detailed information on:

- No authentication/authorization
- Incomplete error handling in tile rendering
- Missing tile caching (HTTP + Redis)
- No automated tests
- Secrets exposed in plaintext
- Limited multi-elevation support
- No rate limiting

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Support & Contributions

For questions, bug reports, or feature requests, please open an issue in the GitLab repository.

Before contributing:
1. Read [`docs/DISCOVERY_REPORT.md`](docs/DISCOVERY_REPORT.md) for architecture details
2. Follow code style guidelines (black, flake8, mypy)
3. Add tests for new functionality
4. Update documentation

---

## Acknowledgments

**WebMet25** is developed and maintained by **Grupo Radar Córdoba (GRC)** — Universidad Nacional de Córdoba, Argentina.

Consumes output from **radarlib**, the data producer library for meteorological radar processing and visualization.

---

**Last Updated:** April 20, 2026  
**Version:** 1.0.0
