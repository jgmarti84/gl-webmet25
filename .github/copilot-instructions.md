# webmet25 — Copilot Instructions

## Full Project Discovery
> 📖 A detailed discovery report of this project lives in
> `docs/DISCOVERY_REPORT.md`. This file contains 
> the full technical analysis of the codebase including 
> architecture, modules, database schema, API endpoints, 
> and identified risks.
> Always read the relevant section of this report before 
> writing any code.

---

## About This Repository
webmet25 is the **data consumer** in the radarmet system. It is one 
of two repositories. It ingests Cloud-Optimized GeoTIFF (COG) files 
produced by **radarlib**, indexes them into a PostgreSQL/PostGIS 
database, and serves them via a REST API and interactive Leaflet 
frontend.

---

## System Context
```text
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

### radarlib Output Contract (what we depend on)
> ⚠️ webmet25 depends entirely on radarlib's output format.
> Never assume a different format without checking radarlib's 
> `docs/radarlib_EN.md` Output Contract section first.
> ⚠️ This contract is sourced from radarlib. If radarlib 
> changes its output format, update this section immediately.

### Primary Output Format
- **GeoTIFF (COG):** This is the primary and current output format.
  Cloud-Optimized GeoTIFF is the production standard.
- **PNG:** Deprecated. Kept only for backward compatibility.
  Do not build new features around PNG output.

### File Naming Convention
`<RADAR_NAME>_<TIMESTAMP>_<FIELD>[o]_<ELEVATION>.<ext>`

| Token | Description | Example |
|-------|-------------|---------|
| `RADAR_NAME` | Radar station identifier | `RMA1` |
| `TIMESTAMP` | ISO 8601 format: `YYYYMMDDTHHMMSSZ` | `20260401T205000Z` |
| `FIELD` | Radar field/variable name | `ZDR`, `DBZH` |
| `[o]` | Letter `o` suffix = raw/non-filtered data. Absent = filtered data | `ZDRo` vs `ZDR` |
| `ELEVATION` | Elevation angle in degrees, zero-padded to 2 digits. Currently always `00`. Future versions will support other values | `00` |
| `ext` | File extension | `tif` (primary), `png` (deprecated) |

### Naming Examples
Filtered ZDR field, elevation 00 degrees → GeoTIFF
RMA1_20260401T205000Z_ZDR_00.tif

Non-filtered (raw) ZDR field, elevation 00 degrees → GeoTIFF
RMA1_20260401T205000Z_ZDRo_00.tif

PNG equivalent (deprecated, backward compat only)
RMA1_20260401T205000Z_ZDR_00.png

### Folder Structure
```text
ROOT_RADAR_PRODUCTS_PATH/
└── <RADAR_NAME>/
    └── /YYYY/
        └── /MM/
            └── /DD/
                ├── RMA1_20260401T205000Z_ZDR_00.tif
                ├── RMA1_20260401T205000Z_ZDRo_00.tif
                └── RMA1_20260401T205000Z_ZDR_00.png ← deprecated
```

### GeoTIFF Metadata Fields

| Field | Value | Purpose |
|---|---|---|
| **CRS** | EPSG:4326 | Geographic coordinate system (WGS84 lat/lon) |
| **radarlib_cmap** | Colormap name string | Name of matplotlib colormap used (e.g., `"grc_th"`) |
| **vmin** | Float | Minimum data value for color scaling |
| **vmax** | Float | Maximum data value for color scaling |
| **field_name** | String | Radar field name (e.g., `"DBZH"`) |
| **timestamp** | ISO 8601 | Data acquisition timestamp |

### Critical Rules
- **Never change this contract without updating webmet25 indexer.**
- **Do not add new output formats without updating both repos.**
- When implementing multi-elevation support in the future, the
  `ELEVATION` token must remain zero-padded to 2 digits (e.g.,
  `05`, `10`) to preserve consistent file naming.
- PNG generation should not be extended or improved. If a task
  involves PNG output, flag it and ask for confirmation.

> ⚠️ webmet25 depends entirely on radarlib's output format.
> Never assume a different format without checking radarlib's 
> `docs/radarlib_EN.md` Output Contract section first.

- **Primary format:** Cloud-Optimized GeoTIFF (.tif)
- **PNG:** Deprecated, backward compatibility only
- **File naming:**

---

## Tech Stack
- **Language:** Python 3.11
- **Backend:** FastAPI, SQLAlchemy, Alembic, GeoAlchemy2, Uvicorn
- **Geospatial:** Rasterio, rio-tiler, Shapely, GDAL
- **Database:** PostgreSQL with PostGIS, Alembic for migrations
- **Frontend:** Leaflet, CartoDB basemaps, plain JavaScript ES6
- **DevOps:** Docker, Docker Compose, VSCode Dev Containers

---

## Project Architecture
api/ # FastAPI backend
database/ # Shared SQLAlchemy models
indexer/ # COG file watcher and database updater
frontend/ # Static files served via Nginx
radar_db/ # Shared Python package: DB models and utilities
docs/ # Project documentation
tests/ # Automated tests


---

## Database Schema
| Table | Primary Key | Key Fields |
|-------|-------------|------------|
| `Radar` | `code` | `title`, `center_lat`, `center_long`, `is_active` |
| `RadarProduct` | `id` | `product_key` (UNIQUE), `product_title`, `min_value`, `max_value` |
| `RadarCOG` | `id` | `radar_code` (FK), `product_id` (FK), `file_path` (UNIQUE), `observation_time`, `status` |
| `Reference` | `id` | `product_id` (FK), `value`, `color` |
| `Estrategia` | `code` | `description` |

---

## API Contract
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/radars` | List all radars |
| GET | `/radars/{radar_code}` | Get radar details |
| GET | `/products` | List radar products |
| GET | `/cogs` | Query COG metadata |
| GET | `/tiles/{cog_id}/{z}/{x}/{y}.png` | Render tile image |
| GET | `/tiles/{cog_id}/metadata` | Get tile metadata |
| GET | `/products/{product_key}/colormap` | Get product colormap |

---

## Indexer
- **COGWatcher:** Scans `ROOT_RADAR_PRODUCTS_PATH` for new/modified files
- **COGFilenameParser:** Parses filenames using radarlib naming convention
- **COGRegistrar:** Extracts metadata, inserts/updates `RadarCOG` records
- Marks missing files as `MISSING` status in database

---

## Frontend
- Leaflet map with radar/product selectors
- Multiple radar selection with opacity control
- Frame animation with speed control (0.5x–2x)
- Periodic polling for new COGs (5 minute interval)
- **Modules:** `app.js`, `api.js`, `map.js`, `animation.js`

---

## Coding Conventions & Rules
> Always follow these when generating code.

- **Language version:** Python 3.11
- **Formatter:** black (run before every commit)
- **Linter:** flake8
- **Type hints:** Required on all functions (enforced by mypy)
- **Naming:**
  - Variables and functions: `snake_case`
  - Classes: `PascalCase`
  - Constants: `UPPER_SNAKE_CASE`
- **Error handling:** Always raise specific descriptive exceptions.
  Never use bare `except:` clauses.
- **Database:** Always use transactions for any write operations.
  Never write to the database outside of a transaction block.
- **API:** Never return a 500 error to the client. Always handle 
  missing files and missing records gracefully with proper 4xx 
  responses.

---

## Known Gaps & Technical Debt
> Do not replicate these patterns. Always suggest fixes when 
> touching these areas.

### Critical
- ❌ No authentication or authorization. API is completely open.
- ❌ No transactions in indexer. Partial failures corrupt DB state.
- ❌ Missing files cause 500 errors. Must be handled gracefully.

### High Priority
- ❌ No tile caching. Every tile is recomputed on each request.
- ❌ Incomplete error handling in tile rendering and indexer.
- ❌ No rate limiting. API is vulnerable to DOS attacks.
- ❌ Database credentials in plaintext in `docker-compose.yml`.

### Medium Priority
- ❌ Hardcoded API base URL in frontend.
- ❌ No pagination on products and references endpoints.
- ❌ No automated tests.
- ❌ No monitoring or log aggregation.

---

## SDD Workflow — Follow This Every Time
When I give you a task, strictly follow this cycle:

### 1. PROPOSAL
- Read this file fully
- Read the relevant section of `docs/webmet25_EN.md`
- Read the relevant source files
- Propose the code changes
- Flag any conflict with the radarlib Output Contract immediately
- Do not violate the coding conventions above
- Always flag any task that touches security, transactions, 
  or file path handling as HIGH RISK before proposing code

### 2. APPLY
- Wait for my approval or feedback
- Adjust based on my response
- Provide final code only after I confirm

### 3. ARCHIVE
- After code is applied, explicitly tell me:
  - Does `docs/webmet25_EN.md` need to be updated?
  - Does this `copilot-instructions.md` need to be updated?
  - Does the radarlib Output Contract need to be updated?
  - Does the radarlib `copilot-instructions.md` need to be updated?