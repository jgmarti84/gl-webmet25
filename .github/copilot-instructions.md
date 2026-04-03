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

## Testing Strategy & Structure
> All tests live in the `tests/` folder.
> Tests run inside the `tests` Docker service defined in 
> `docker-compose.devcontainer.yml`.
> Never add test dependencies to api or indexer requirements.

### Folder Structure
```
tests/
├── api/        # API contract tests using httpx
├── indexer/    # Indexer unit tests
└── e2e/        # Browser tests using Playwright
```

### Running Tests
```bash
# Exec into the tests container
docker exec -it radar_tests bash

# Run all tests
pytest

# Run only API tests
pytest tests/api/ -v

# Run only a specific test file
pytest tests/api/test_health.py -v

# Run E2E tests
pytest tests/e2e/ -v
```

### Test Layers
| Layer | Location | Tool | What it tests |
|-------|----------|------|---------------|
| API Contract | `tests/api/` | pytest + httpx | Every endpoint in the API Contract |
| Indexer | `tests/indexer/` | pytest | File parsing, DB transactions |
| E2E | `tests/e2e/` | pytest + Playwright | Frontend behavior in real browser |

### File Naming
- One test file per router file
- Test file name must match the router it tests
- Examples:
  - `api/app/routers/radars.py` → `tests/api/test_radars.py`
  - `api/app/routers/cogs.py` → `tests/api/test_cogs.py`

### Required Test Pattern
Every test file must follow this exact pattern:
```python
import pytest
import httpx
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
```

### Required Tests Per Endpoint
Every endpoint must have ALL of the following tests:

1. **HTTP status code test**
   - Happy path must return the correct 2xx status code
   - Example: `test_radars_returns_200`

2. **Response fields test**
   - Response must contain all fields defined in the API Contract
   - Example: `test_radars_response_has_required_fields`

3. **Content type test**
   - Response must return `application/json`
   - Example: `test_radars_returns_json`

4. **Error path test**
   - Invalid inputs must return correct 4xx status codes
   - Never assert a 500 error. A 500 is always a bug, not a 
     valid error response.
   - Example: `test_radar_invalid_code_returns_404`

5. **Data type test**
   - Assert that field types match the contract
     (e.g., strings are strings, numbers are numbers, 
     lists are lists)
   - Example: `test_radars_returns_list`

### Rules
- Always use `API_BASE_URL` from environment variables
- Never hardcode URLs or ports in test files
- Never use pytest fixtures yet, keep tests simple and explicit
- Always test both the happy path AND the error path
- A failing test means the API Contract is violated, 
  not that the test is wrong
- If a test reveals a bug, document it in the Known Gaps section
  of this file before fixing it
- Never skip a test with `@pytest.mark.skip` without adding a 
  comment explaining why

---

## Rules for Writing E2E Tests
> Follow these rules when writing Playwright tests in tests/e2e/

### Required Setup
```python
import pytest
from playwright.sync_api import Page

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend:80")
```

### Required Tests Per Frontend Feature
1. **Page loads test:** Assert the page loads without errors
2. **Key element visible test:** Assert critical UI elements are visible
3. **User interaction test:** Simulate real user interactions
4. **API integration test:** Assert the frontend correctly displays 
   data from the API

### Rules
- Always use `FRONTEND_URL` from environment variables
- Test real user flows, not implementation details
- Always take a screenshot on failure for debugging:
```python
page.screenshot(path="tests/e2e/screenshots/failure.png")
```
---

## Rules for Writing Indexer Tests
> Follow these rules when writing tests in tests/indexer/

### Test File Structure
\```
tests/indexer/
├── test_filename_parser.py  # Pure unit tests for COGFilenameParser
├── test_registrar.py        # DB integration tests for COGRegistrar  
└── test_watcher.py          # Scan logic and error resilience tests
\```

### Rules
- test_filename_parser.py must NEVER connect to the database
- test_filename_parser.py must test every filename variation 
  defined in the Output Contract
- Always test both valid AND invalid filenames
- Always test the [o] suffix (raw/non-filtered) separately
- test_registrar.py must verify transaction rollback on failure
- test_watcher.py must verify that one bad file does not stop 
  the entire scan
- Never mock the filename parser in registrar tests, use real 
  filenames from the Output Contract

### Additional Indexer Testing Rules
- Use `@pytest.mark.parametrize` for filename parser tests
---

## SDD Workflow — Follow This Every Time
When I give you a task, strictly follow this cycle:

### 1. PROPOSAL ⚠️
- Read this file fully
- Read the relevant source files
- **DO NOT create, modify, or delete any files yet**
- Show me the code you would write in the chat only
- Explain your decisions and flag any risks
- Wait for my explicit message saying "approved" or "apply" 
  before touching any files

### 2. APPLY
- Wait for my approval or feedback
- Adjust based on my response
- Provide final code only after I confirm

### 3. ARCHIVE
- After code is applied, explicitly tell me:
  - Does the documentation need to be updated?
  - Does this `copilot-instructions.md` need to be updated?
  - Does the API Contract need to be updated?