# DATA_FLOW.md — WebMet25 Data Consumption Pipeline

> **Purpose:** Explain how WebMet25 ingests, processes, and displays radar data produced by radarlib.

---

## 1. Overview

WebMet25 is a **data consumer** in the radar/meteorology system. It receives Cloud-Optimized GeoTIFF (COG) files from radarlib, indexes them into a PostgreSQL/PostGIS database, and serves them via REST API to an interactive web frontend.

```
radarlib (producer)
    ↓
    GeoTIFF files @ /product_output/{radar_code}/{product_key}/
    ↓
webmet25 (consumer)
    ├── Indexer: watches, parses, extracts metadata → DB
    ├── API: queries DB, renders tiles
    └── Frontend: displays map with radar overlays
```

---

## 2. Data Ingestion Layer: The Indexer

### 2.1 Entry Point

**File:** [`indexer/indexer/main.py`](../indexer/indexer/main.py)

```python
def run_indexer():
    """Run the indexer service."""
    from radar_db import db_manager
    from indexer.watcher import COGWatcher, TopsAndCoresWatcher
    import threading

    # Wait for database
    if not wait_for_database():
        sys.exit(1)

    # Start TopsAndCores watcher in a background thread
    tops_cores_watcher = TopsAndCoresWatcher()
    t = threading.Thread(target=tops_cores_watcher.run_forever,
                         args=(db_manager.get_session_direct,), daemon=True)
    t.start()

    # COG watcher runs in the main thread
    watcher = COGWatcher()
    watcher.run_forever(db_manager.get_session_direct)
```

**Responsibility:**
- Waits for PostgreSQL database to become available
- Starts `TopsAndCoresWatcher` in a background thread (scans `TOPS_AND_CORES_DIR`)
- Starts `COGWatcher` in the main loop (scans `ROOT_RADAR_PRODUCTS_PATH`)

### 2.2 File System Scanning: COGWatcher

**File:** [`indexer/indexer/watcher.py`](../indexer/indexer/watcher.py)

**Responsibility:**
- Monitors `ROOT_RADAR_PRODUCTS_PATH` every `SCAN_INTERVAL` seconds (default: 30s)
- First run: full scan. Subsequent runs: incremental (files modified in last 5 min + overlap)
- For each `.tif` file:
  - Parses filename to extract metadata (supports both production and legacy formats)
  - Extracts COG metadata using rasterio
  - Registers in database or marks as MISSING
  - Handles errors gracefully (one bad file doesn't stop the scan)
- **`update_radar_activity()`:** Called at the end of every scan cycle. Sets `Radar.is_active = True/False` based on whether a recent AVAILABLE COG exists within the last `RADAR_ACTIVE_THRESHOLD_HOURS` hours.

**Configuration:** [`indexer/indexer/config.py`](../indexer/indexer/config.py)

```python
WATCH_PATH = "/product_output"
SCAN_INTERVAL = 30               # seconds
FILE_PATTERN = "*.tif"
COMPUTE_STATS = True
COMPUTE_CHECKSUM = False
RADAR_ACTIVE_THRESHOLD_HOURS = 2  # hours; used by update_radar_activity()
TOPS_AND_CORES_DIR = "/tops_and_cores"
```

### 2.2b TopsAndCores Scanning: TopsAndCoresWatcher

**File:** [`indexer/indexer/watcher.py`](../indexer/indexer/watcher.py)

**Responsibility:**
- Monitors `TOPS_AND_CORES_DIR` recursively for `*_TOPS_CORES.geojson` files (same poll interval as COGWatcher)
- For each new file:
  - Parses filename to extract `radar_code`, `strategy`, `vol_nr`, `observation_time`
  - Opens GeoJSON and counts cores, tops, and total features
  - Inserts/updates `TopsAndCores` record
  - Marks files as `MISSING` if previously indexed but no longer present

### 2.3 Filename Parsing: COGFilenameParser

**File:** `indexer/indexer/parser.py` (referenced in DISCOVERY_REPORT.md)

**Supported Filename Patterns:**

**Pattern 0 — Current production format:**
```
<RADAR>_<STRATEGY>_<VOL_NR>_<TIMESTAMP>_<FIELD>[o].tif
```
Examples:
```
RMA1_0315_01_20260401T205000Z_DBZH.tif    # Filtered reflectivity, vol 01
RMA1_0315_01_20260401T205000Z_DBZHo.tif   # Unfiltered (raw), vol 01
RMA1_0315_04_20260401T205000Z_COLMAX.tif  # Column max, vol 04 (vigilant)
```

**Pattern 1 — Legacy format (backward compatibility):**
```
<RADAR>_<TIMESTAMP>_<FIELD>[o]_<ELEVATION>.tif
```
Example: `RMA1_20260401T205000Z_DBZHo_00.tif`
(Indexed with `strategy=None`, `vol_nr=None`. A WARNING is logged.)

**Extraction (Pattern 0):**
- `radar_code` = `"RMA1"` (from filename)
- `product_key` = `"DBZH"` or `"DBZHo"` (field name including optional `o` suffix)
- `observation_time` = `"20260401T205000Z"` (ISO 8601 UTC)
- `strategy` = `"0315"` (4-digit strategy code)
- `vol_nr` = `"01"` (2-digit volume number)

**Validation:**
- Radar code must exist in `Radar` table
- Product key must exist in `RadarProduct` table
- Timestamp must be parseable as ISO 8601

### 2.4 Metadata Extraction: COGRegistrar

**File:** `indexer/indexer/registrar.py` (referenced in DISCOVERY_REPORT.md)

**Data Extracted from GeoTIFF:**

#### From File System:
```python
file_size_bytes = file_path.stat().st_size
file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
file_checksum = compute_sha256(file_path)  # if COMPUTE_CHECKSUM=true
```

#### From GeoTIFF Profile (via rasterio):
```python
width = src.width
height = src.height
num_bands = src.count
dtype = str(src.dtypes[0])  # e.g., "float32"
crs = str(src.crs)  # e.g., "EPSG:4326"
nodata_value = src.nodata
compression = src.profile.get('compress')
resolution_x = src.res[0]
resolution_y = src.res[1]
```

#### From GeoTIFF Tags (radarlib metadata):
```python
tags = src.tags()
cog_cmap = tags.get("radarlib_cmap")        # e.g., "grc_th"
cog_vmin = float(tags.get("radarlib_vmin")) # e.g., 5.0
cog_vmax = float(tags.get("radarlib_vmax")) # e.g., 75.0
field_name = tags.get("field_name")        # e.g., "DBZH"
timestamp = tags.get("timestamp")          # ISO 8601 string
```

#### Optional Statistics (via rasterio, if COMPUTE_STATS=true):
```python
data = src.read(1, masked=True)
data_min = float(data.min())
data_max = float(data.max())
data_mean = float(data.mean())
valid_pixel_count = int(data.count())
```

#### Spatial Extent (PostGIS):
```python
# Transform GeoTIFF bounds from native CRS to WGS84
bounds = transform_bounds(src.crs, 'EPSG:4326', *src.bounds)
bbox_geom = box(*bounds)  # Create WGS84 polygon
metadata['bbox'] = from_shape(bbox_geom, srid=4326)
```

---

## 3. Database Schema: Data Model

### 3.1 Core Tables

**All models defined in:** [`database/radar_db/models.py`](../database/radar_db/models.py)

#### **Radar** (Reference Data)
```python
class Radar(Base):
    __tablename__ = 'radars'
    
    code: str (PK)           # "RMA1", "AR5"
    title: str               # "Córdoba" 
    center_lat: Decimal
    center_long: Decimal
    img_radio: int           # Coverage radius (km)
    is_active: bool          # Display flag
    point1_lat, point1_long  # Bounding box corner 1
    point2_lat, point2_long  # Bounding box corner 2
    created_at, updated_at: DateTime(tz)
    
    # Relationships
    cog_files: List[RadarCOG]  # 1:M back_populates
```

#### **RadarProduct** (Reference Data)
```python
class RadarProduct(Base):
    __tablename__ = 'radar_products'
    
    id: int (PK)                      # Auto-increment
    product_key: str (UNIQUE, INDEX)  # "DBZH", "COLMAX", "ZDRo"
    product_title: str                # "Reflectivity", "Column Max"
    enabled: bool
    see_in_open: bool
    min_value, max_value: float       # Display range
    unit: str                         # "dBZ", "percent"
    created_at, updated_at: DateTime(tz)
    
    # Relationships
    references: List[Reference]    # 1:M back_populates (color scale)
    cog_files: List[RadarCOG]      # 1:M back_populates
```

#### **RadarCOG** (Main Data Table — Indexed Files)
```python
class RadarCOG(Base):
    __tablename__ = 'radar_cogs'
    
    # Identity
    id: int (PK)                          # Auto-increment
    
    # Foreign Keys (indexed)
    radar_code: str (FK → Radar.code)
    product_id: int (FK → RadarProduct.id)
    estrategia_code: str (FK → Estrategia.code, nullable)
    
    # File Metadata
    file_path: str (UNIQUE, INDEX)        # Relative path: "RMA1/DBZH/RMA1_..._DBZH_00.tif"
    file_name: str                        # Just the filename
    file_size_bytes: int
    file_mtime: DateTime(tz)              # Last modified
    file_checksum: str(64)                # SHA256
    
    # Observation Metadata
    observation_time: DateTime(tz) (INDEX)  # When radar acquired data
    
    # GeoTIFF File Properties
    crs: str                          # "EPSG:4326"
    width: int
    height: int
    num_bands: int
    dtype: str                        # "float32", "uint8"
    resolution_x, resolution_y: float
    nodata_value: float
    compression: str                  # "deflate", None
    
    # COG Rendering Metadata (from radarlib tags)
    cog_data_type: str                # "raw_float", "rgba", "unknown"
    cog_cmap: str                     # Colormap name
    cog_vmin, cog_vmax: float         # Data range for display
    
    # radarlib production metadata (NULL for legacy files)
    vol_nr: str(16)                   # Volume number: "01", "02", "04"
    radar_coverage_m: float           # Coverage radius in metres
    
    # Optional Statistics
    data_min, data_max, data_mean: float
    valid_pixel_count: int
    
    # Spatial
    bbox: Geometry('POLYGON', srid=4326)  # WGS84 bounding box
    
    # Status
    status: Enum (PENDING, AVAILABLE, PROCESSING, ERROR, ARCHIVED, MISSING)
    error_message: Text
    show_me: bool
    
    # Timestamps
    created_at: DateTime(tz)
    updated_at: DateTime(tz)
    
    # Relationships
    radar: Radar (M:1 back_populates)
    product: RadarProduct (M:1 back_populates)
    estrategia: Estrategia (M:1 back_populates, nullable)
    
    # Unique: (radar_code, product_id, observation_time, elevation_angle, vol_nr)
    # vol_nr=NULL rows (legacy) are independent due to NULL != NULL in PostgreSQL
```

#### **TopsAndCores** (Indexed GeoJSON Files)
```python
class TopsAndCores(Base):
    __tablename__ = 'tops_and_cores'
    
    id: int (PK)
    radar_code: str (FK → Radar.code)
    observation_time: DateTime(tz) (INDEX)
    file_path: str (UNIQUE)
    file_name: str
    feature_count: int            # Total features (cores + tops)
    core_count: int
    top_count: int
    status: COGStatus             # AVAILABLE or MISSING
    strategy: str (nullable)      # e.g. "0315"
    vol_nr: str (nullable)        # e.g. "00"
    created_at: DateTime(tz)
    updated_at: DateTime(tz)
    
    radar: Radar (M:1 back_populates)
```

#### **Reference** (Color Scale Entries)
```python
class Reference(Base):
    __tablename__ = 'references'
    
    id: int (PK)
    product_id: int (FK → RadarProduct.id, INDEX)
    title: str
    description: str
    unit: str
    value: float              # e.g., 10.0 dBZ
    color: str(7)             # "#ff0000"
    color_font: str(7)        # "#ffffff"
    
    # Relationships
    product: RadarProduct (M:1 back_populates)
```

### 3.2 Indexes (Performance)

```sql
CREATE INDEX idx_radar_cog_radar_code ON radar_cogs(radar_code);
CREATE INDEX idx_radar_cog_product_id ON radar_cogs(product_id);
CREATE INDEX idx_radar_cog_observation_time ON radar_cogs(observation_time);
CREATE INDEX idx_radar_cog_status ON radar_cogs(status);
CREATE INDEX idx_radar_cog_file_path ON radar_cogs(file_path);  -- UNIQUE
CREATE INDEX idx_radar_cog_vol_nr ON radar_cogs(vol_nr);
CREATE INDEX idx_reference_product_id ON references(product_id);
CREATE INDEX idx_tops_cores_observation_time ON tops_and_cores(observation_time);
CREATE INDEX idx_tops_cores_radar_code ON tops_and_cores(radar_code);
-- Composite (radar_code, product_id, observation_time, vol_nr)
CREATE INDEX idx_cog_radar_product_time ON radar_cogs(radar_code, product_id, observation_time, vol_nr);
-- Spatial
CREATE INDEX idx_cog_bbox ON radar_cogs USING GIST (bbox);
```

### 3.3 Initial Data: Seeds

**File:** [`database/seed_data/initial_data.json`](../database/seed_data/initial_data.json)

Loaded on first database initialization by [`database/radar_db/seeds.py`](../database/radar_db/seeds.py):

```python
class DataSeeder:
    def load_json(self) -> bool:
        """Load data from JSON file."""
        # Read initial_data.json
        # Parse records by model type (Radar, RadarProduct, Reference)
        # Insert into database
    
    def _seed_radar(self, record: dict) -> Radar:
        """Create Radar record."""
        
    def _seed_product(self, record: dict) -> RadarProduct:
        """Create RadarProduct record."""
        
    def _seed_reference(self, record: dict) -> Reference:
        """Create Reference (colormap entry) record."""
```

**Example seed data:**
```json
{
  "model": "radar_db.radar",
  "data": {
    "code": "RMA1",
    "title": "Córdoba Radar",
    "center_lat": -31.41,
    "center_long": -64.43,
    "is_active": true
  }
}
```

---

## 4. API Layer: Data Query & Serving

### 4.1 API Router Architecture

**Base URL:** `http://localhost:8000/api/v1`

**Entry point:** [`api/app/main.py`](../api/app/main.py)

```python
from .routers import (
    radars_router, products_router, cogs_router,
    tiles_router, colormap_router, frames_router, tops_cores_router
)

app.include_router(radars_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(cogs_router, prefix="/api/v1")
app.include_router(tiles_router, prefix="/api/v1")
app.include_router(colormap_router, prefix="/api/v1")
app.include_router(frames_router, prefix="/api/v1")   # v2: full-image frames
app.include_router(tops_cores_router, prefix="/api/v1")  # convective tops & cores
```

### 4.2 Radars Endpoint

**File:** [`api/app/routers/radars.py`](../api/app/routers/radars.py)

```python
@router.get("/radars", response_model=RadarListResponse)
def list_radars(
    active_only: bool = True,  # Query param
    db: Session = Depends(get_db)
) -> RadarListResponse:
    """List all radar stations."""
    query = db.query(Radar)
    if active_only:
        query = query.filter(Radar.is_active == True)
    radars = query.all()
    return RadarListResponse(
        radars=[RadarResponse.from_orm(r) for r in radars],
        count=len(radars)
    )

@router.get("/radars/{radar_code}", response_model=RadarResponse)
def get_radar(
    radar_code: str,
    db: Session = Depends(get_db)
) -> RadarResponse:
    """Get specific radar details."""
    radar = db.query(Radar).filter_by(code=radar_code).first()
    if not radar:
        raise HTTPException(status_code=404, detail="Radar not found")
    return RadarResponse.from_orm(radar)
```

**Response Schema:**
```python
class RadarResponse(BaseModel):
    code: str
    title: str
    center_lat: float
    center_long: float
    is_active: bool
    extent: ExtentResponse  # computed from point1/point2
```

### 4.3 Products Endpoint

**File:** [`api/app/routers/products.py`](../api/app/routers/products.py)

```python
@router.get("/products", response_model=ProductListResponse)
def list_products(db: Session = Depends(get_db)) -> ProductListResponse:
    """List available radar products."""
    products = db.query(RadarProduct).filter_by(enabled=True).all()
    return ProductListResponse(
        products=[ProductResponse.from_orm(p) for p in products],
        count=len(products)
    )
```

**Response Schema:**
```python
class ProductResponse(BaseModel):
    id: int
    product_key: str
    product_title: str
    min_value: Optional[float]
    max_value: Optional[float]
    unit: Optional[str]
```

### 4.4 COGs Endpoint (Most Important for Data)

**File:** [`api/app/routers/cogs.py`](../api/app/routers/cogs.py)

```python
@router.get("/cogs", response_model=COGListResponse)
def list_cogs(
    radar_code: Optional[str] = None,
    product_key: Optional[str] = None,     # Exact-match on polarimetric_var
    strategy: Optional[str] = None,         # e.g. "0315"
    vol_nr: Optional[List[str]] = Query(default=None),  # Repeatable: ?vol_nr=01&vol_nr=02
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 50,                   # max 200
    db: Session = Depends(get_db)
) -> COGListResponse:
    """Query COG metadata with filtering."""
    query = db.query(RadarCOG).filter(RadarCOG.status == COGStatus.AVAILABLE)
    
    if radar_code:
        query = query.filter(RadarCOG.radar_code == radar_code)
    if product_key:
        # Exact match on polarimetric_var (respects 'o' suffix)
        query = query.filter(
            (RadarCOG.polarimetric_var == product_key) |
            (RadarCOG.product.has(RadarProduct.product_key == product_key))
        )
    if strategy:
        query = query.filter(RadarCOG.estrategia_code == strategy)
    if vol_nr:  # List[str] — repeatable: ?vol_nr=01&vol_nr=02
        query = query.filter(RadarCOG.vol_nr.in_(vol_nr))
    if start_time:
        query = query.filter(RadarCOG.observation_time >= start_time)
    if end_time:
        query = query.filter(RadarCOG.observation_time <= end_time)
    ...
```

**Response includes:** `id`, `radar_code`, `product_key`, `observation_time`, `cog_cmap`, `cog_vmin`, `cog_vmax`, `bbox`, `strategy`, `vol_nr`, `radar_coverage_m`
        page_size=page_size
    )
```

**Response Schema:**
```python
class COGResponse(BaseModel):
    id: int
    radar_code: str
    product_key: str
    observation_time: datetime
    file_path: str
    cog_cmap: Optional[str]
    cog_vmin: Optional[float]
    cog_vmax: Optional[float]
    bbox: dict  # GeoJSON-like bbox
```

### 4.5 Tiles Endpoint (Rendering)

**File:** [`api/app/routers/tiles.py`](../api/app/routers/tiles.py)

```python
@router.get("/tiles/{cog_id}/{z}/{x}/{y}.png", response_class=PNGResponse)
def get_tile(
    cog_id: int,
    z: int,
    x: int,
    y: int,
    colormap: Optional[str] = None,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    db: Session = Depends(get_db)
) -> bytes:
    """Render a Web Mercator tile from COG."""
    # Get COG from database
    cog = db.query(RadarCOG).filter_by(id=cog_id, status=COGStatus.AVAILABLE).first()
    if not cog:
        raise HTTPException(status_code=404, detail="COG not found")
    
    # Use TileService to render
    tile_service = TileService(cog_base_path=settings.cog_base_path)
    tile_bytes = tile_service.get_tile(
        file_path=cog.file_path,
        z=z, x=x, y=y,
        colormap=colormap or cog.cog_cmap,
        vmin=vmin or cog.cog_vmin,
        vmax=vmax or cog.cog_vmax
    )
    return tile_bytes
```

**Rendering Logic (TileService):**

**File:** [`api/app/services/tile_service.py`](../api/app/services/tile_service.py)

```python
class TileService:
    def get_tile(
        self, file_path: str, z: int, x: int, y: int,
        colormap: str, vmin: float, vmax: float
    ) -> bytes:
        """Render map tile from COG."""
        # 1. Open COG with rasterio
        with rasterio.open(self.cog_base_path / file_path) as src:
            
            # 2. Use rio_tiler to get Web Mercator tile
            tile_data = tile_read(
                src,
                x=x, y=y, z=z,
                dst_crs="EPSG:3857"  # Web Mercator
            )
            
            # 3. Apply colormap
            colored = apply_colormap(
                tile_data.data,
                colormap_name=colormap,
                vmin=vmin,
                vmax=vmax
            )
            
            # 4. Encode to PNG
            png_bytes = encode_png(colored)
            return png_bytes
```

### 4.6 Frames Endpoint (v2 — Full COG Image)

**File:** [`api/app/routers/frames.py`](../api/app/routers/frames.py)

```
GET /frames/{cog_id}/image.png
```

Returns the entire COG as a single georeferenced RGBA PNG. Used by the v2 frontend (`L.imageOverlay`) to replace ~10 individual tile requests per frame with a single request.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `colormap` | str | from COG tag | Matplotlib colormap name |
| `vmin` / `vmax` | float | from COG tag | Color scale range |
| `filter_vmin` / `filter_vmax` | float | null | Mask pixels outside range (transparent) |
| `smooth` | bool | false | Apply Gaussian smoothing before colormap |
| `smooth_sigma` | float | 0.8 | Gaussian sigma (ignored when `smooth=false`) |

**Gaussian Smoothing Detail:**
- Implemented in `api/app/services/smoothing.py` via `scipy.ndimage.gaussian_filter`
- Applied to float data array **before** colormap lookup (not post-render pixel blur)
- Cache key includes `(smooth, smooth_sigma)` only when `smooth=true`; unsmoothed requests always share the same L1/L2 cache key regardless of sigma sent by client

**Response Headers:**
- `X-Bbox-West`, `X-Bbox-South`, `X-Bbox-East`, `X-Bbox-North` — WGS84 bounds (reprojected from native CRS)
- `X-Width`, `X-Height` — image dimensions in pixels
- `ETag`, `Cache-Control` — caching headers

**Caching:** L1 LRU in-process cache (750 entries) + L2 Redis cache (key prefix `frame:`). Independent from the tile cache (`tile:` prefix).

---

### 4.7 Tops & Cores Endpoints

**File:** [`api/app/routers/tops_cores.py`](../api/app/routers/tops_cores.py)

```
GET /tops-cores
```
Query metadata records. Returns an empty list when no records match (never 404).

**Query Parameters:** `radar_codes[]` (repeatable), `time_from`, `time_to`, `status` (default `available`)

**Response:** List of `TopsAndCoresRecord` with `id`, `radar_code`, `observation_time`, `core_count`, `top_count`, `feature_count`, `strategy`, `vol_nr`, `status`.

```
GET /tops-cores/{id}/features
```
Fetch raw GeoJSON FeatureCollection from disk. Returns 404 if record not found; updates record status to `MISSING` in DB if file not found at serve time. Cache-Control: immutable 86400s.

---

### 4.8 Colormap Endpoint

**File:** [`api/app/routers/colormap.py`](../api/app/routers/colormap.py)

```python
@router.get("/products/{product_key}/colormap", response_model=ColormapResponse)
def get_colormap(
    product_key: str,
    db: Session = Depends(get_db)
) -> ColormapResponse:
    """Get color scale (legend) for product."""
    product = db.query(RadarProduct).filter_by(product_key=product_key).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Get color scale entries, sorted by value
    references = db.query(Reference)\
        .filter_by(product_id=product.id)\
        .order_by(Reference.value)\
        .all()
    
    return ColormapResponse(
        product_key=product_key,
        entries=[
            {
                "value": ref.value,
                "color": ref.color,
                "label": ref.title or str(ref.value)
            }
            for ref in references
        ]
    )
```

---

## 5. Frontend Layer: Data Display & State

> **v2 is the current production standard.** v1 (L.tileLayer + /tiles endpoint) is preserved for reference only. All new development targets v2.

### 5.0 Frontend File Structure

```
frontend/public/js/
├── shared/                # Shared by v1 and v2
│   ├── api.js             # REST API client (all endpoints)
│   ├── controls.js        # UI controls (panels, buttons, toggles)
│   ├── legend.js          # Color scale legend renderer
│   ├── tops-cores.js      # TopsCoresLayer (L.circleMarker)
│   ├── cog-browser-api.js # COG browser alternative API client
│   └── cog-browser.js     # COG browser alternative view
└── v2/                    # Current production frontend
    ├── app.js             # Main orchestrator (2300+ lines, state machine)
    ├── map.js             # MapManager with L.imageOverlay
    └── animation.js       # AnimationController with requestAnimationFrame
```

**v2 key properties:**
- Uses `L.imageOverlay` (not `L.tileLayer`) — 1 overlay per radar, not ~180 tile layers
- Uses `/frames/{id}/image.png` endpoint instead of `/tiles/{id}/{z}/{x}/{y}.png`
- Uses `requestAnimationFrame` for animation loop
- All field, colormap, and range-filter changes go through `_loadFramesWithContinuity()` — animation never stops
- Coverage mask rendered as SVG inside `coverageMaskPane` (zIndex 300)
- `TopsCoresLayer` renders cores (blue) and tops (red) as `L.circleMarker`

### 5.1 Global State Management

**File:** [`frontend/public/js/v2/app.js`](../frontend/public/js/v2/app.js)

```javascript
// Global state object
const state = {
    radars: [],                    // From GET /radars
    products: [],                  // From GET /products
    cogs: [],                      // From GET /cogs (filtered by selection)
    selectedRadars: [],            // User's multi-select choices
    selectedProduct: null,         // User's dropdown choice
    showUnfilteredProducts: false, // Toggle for [o]-suffix fields
    showInactiveRadars: false,     // Toggle for inactive radars
    activeTimeWindowHours: 1.5,    // Default time window
    selectedColormap: null,
    currentVmin: null,
    currentVmax: null,
    fieldOpacity: {},              // Per-radar opacity
    mapManager: null,              // MapManager (v2) instance
    animator: null,                // AnimationController (v2) instance
    ui: null,
    legend: null,
    hasZoomedToBounds: false,
    animationMode: null,           // "live" or "replay" or null
    liveHours: null,
    liveRefreshInterval: null,
    radarStatusRefreshInterval: null,
    topsCoresLayer: null,          // TopsCoresLayer instance
    topsCoresVisible: false,
    topsCoresPointSize: 8,
};
```

### 5.2 Data Flow: Initialization

**File:** [`frontend/public/js/app.js`](../frontend/public/js/app.js)

```javascript
async function init() {
    // 1. Fetch radars and products from API
    const radars = await api.getRadars();
    const products = await api.getProducts();
    state.radars = radars;
    state.products = products;
    
    // 2. Initialize map
    state.mapManager = new MapManager();
    state.mapManager.init('map');
    
    // 3. Populate UI controls
    state.ui = new UIControls();
    state.ui.populateRadarCheckboxes(radars);
    state.ui.populateProductSelect(products);
    
    // 4. Try geolocation
    const userLocation = await getBrowserGeolocation();
    if (userLocation) {
        const nearestRadars = findNearestRadars(userLocation, radars, 3);
        state.selectedRadars = nearestRadars.map(r => r.code);
        // Auto-load COGs for nearest radars
        await loadCogs(nearestRadars[0].code, 'DBZHo', 3);
    }
}
```

### 5.3 COG Loading

**File:** [`frontend/public/js/api.js`](../frontend/public/js/api.js)

```javascript
/**
 * Fetch COG metadata from API for given radar and product.
 */
async function getCogs(radarCode, productKey, hoursBack = 3) {
    const now = new Date();
    const startTime = new Date(now - hoursBack * MS_PER_HOUR);
    
    const response = await fetch(
        `${API_BASE_URL}/api/v1/cogs` +
        `?radar_code=${radarCode}` +
        `&product_key=${productKey}` +
        `&start_time=${startTime.toISOString()}` +
        `&end_time=${now.toISOString()}` +
        `&page_size=30`
    );
    
    if (!response.ok) {
        throw new Error(`API error: ${response.statusText}`);
    }
    
    const data = await response.json();
    return data.cogs;  // Array of COGResponse
}

/**
 * Group COGs by timestamp (±5 min tolerance) for animation.
 */
function groupCogsByTimestamp(cogs, toleranceMinutes = 5) {
    const MS_TOLERANCE = toleranceMinutes * 60 * 1000;
    const groups = {};
    
    // Sort cogs newest first
    const sorted = cogs.sort((a, b) => 
        new Date(b.observation_time) - new Date(a.observation_time)
    );
    
    for (const cog of sorted) {
        const bucket = Math.floor(
            new Date(cog.observation_time) / MS_TOLERANCE
        ) * MS_TOLERANCE;
        
        if (!groups[bucket]) {
            groups[bucket] = { timestamp: new Date(bucket), cogsByRadar: {} };
        }
        
        groups[bucket].cogsByRadar[cog.radar_code] = cog;
    }
    
    return Object.values(groups).sort((a, b) => b.timestamp - a.timestamp);
}
```

### 5.4 Map Layer Management

**File:** [`frontend/public/js/map.js`](../frontend/public/js/map.js)

```javascript
class MapManager {
    constructor() {
        this.map = null;
        this.layers = {};  // { cogId: L.TileLayer }
    }
    
    addRadarLayer(cog, displayName) {
        /**
         * Add a radar overlay (COG tile layer) to the map.
         */
        const tileUrl = `${API_BASE_URL}/api/v1/tiles/${cog.id}/{z}/{x}/{y}.png`;
        
        const layer = L.tileLayer(tileUrl, {
            attribution: `${displayName} (${cog.observation_time})`,
            opacity: 0.7
        });
        
        this.layers[cog.id] = layer;
        layer.addTo(this.map);
        return layer;
    }
    
    removeRadarLayer(cogId) {
        if (this.layers[cogId]) {
            this.map.removeLayer(this.layers[cogId]);
            delete this.layers[cogId];
        }
    }
    
    setOpacity(cogId, opacity) {
        if (this.layers[cogId]) {
            this.layers[cogId].setOpacity(opacity);
        }
    }
}
```

### 5.5 Animation Controller

**File:** [`frontend/public/js/animation.js`](../frontend/public/js/animation.js)

```javascript
class AnimationController {
    constructor(mapManager) {
        this.frames = [];          // Array of {timestamp, cogsByRadar: {}}
        this.currentFrameIndex = 0;
        this.isPlaying = false;
        this.speed = 1.0;          // 0.5x to 2x
        this.mapManager = mapManager;
        this.intervalId = null;
    }
    
    setFrames(frames) {
        /**
         * Load COG sequence for animation.
         * frames = [{timestamp, cogsByRadar: {...}}, ...]
         */
        this.frames = frames;
        this.currentFrameIndex = frames.length - 1;  // Start at newest
        this.render();
    }
    
    play() {
        this.isPlaying = true;
        const frameIntervalMs = 200 / this.speed;
        
        this.intervalId = setInterval(() => {
            if (this.currentFrameIndex > 0) {
                this.currentFrameIndex--;
            } else {
                this.currentFrameIndex = this.frames.length - 1;  // Loop
            }
            this.render();
        }, frameIntervalMs);
    }
    
    pause() {
        this.isPlaying = false;
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }
    
    render() {
        /**
         * Update map layers to show current frame.
         */
        const frame = this.frames[this.currentFrameIndex];
        
        // Remove all layers
        Object.keys(this.mapManager.layers).forEach(cogId => {
            this.mapManager.removeRadarLayer(cogId);
        });
        
        // Add layers for this frame
        for (const [radarCode, cog] of Object.entries(frame.cogsByRadar)) {
            this.mapManager.addRadarLayer(cog, radarCode);
        }
    }
}
```

### 5.6 Legend Rendering

**File:** [`frontend/public/js/legend.js`](../frontend/public/js/legend.js)

```javascript
class LegendRenderer {
    async render(productKey) {
        /**
         * Fetch colormap from API and render legend.
         */
        const colormap = await api.getColormapInfo(productKey);
        
        const container = document.getElementById('legend-container');
        container.innerHTML = '';
        
        for (const entry of colormap.entries) {
            const item = document.createElement('div');
            item.className = 'legend-item';
            
            const color = document.createElement('span');
            color.className = 'legend-color';
            color.style.backgroundColor = entry.color;
            
            const label = document.createElement('span');
            label.textContent = `${entry.value} ${entry.label || ''}`;
            
            item.appendChild(color);
            item.appendChild(label);
            container.appendChild(item);
        }
    }
}
```

### 5.7 Live Refresh

**File:** [`frontend/public/js/app.js`](../frontend/public/js/app.js) (within `init()`)

```javascript
// Start live polling (every 5 minutes)
const LIVE_REFRESH_INTERVAL_MS = 5 * 60 * 1000;

state.liveRefreshInterval = setInterval(async () => {
    // Fetch newest COGs
    const latestCogs = await api.getLatestCogsMultiRadar(
        state.selectedRadars,
        state.selectedProduct
    );
    
    // Group by timestamp
    const frames = groupCogsByTimestamp(latestCogs);
    
    // Update animation frames
    state.animator.setFrames(frames);
    
    // If playing, animation will show new frames
}, LIVE_REFRESH_INTERVAL_MS);
```

---

## 6. Data State Lifecycle

### 6.1 Startup Sequence

```
┌─ Docker compose up
│
├─ PostgreSQL starts
│  └─ Waits for health
│
├─ DB init container
│  ├─ Runs alembic migrations
│  ├─ Loads seed_data/initial_data.json
│  │  └─ Inserts Radar, RadarProduct, Reference records
│  └─ Exits
│
├─ Indexer starts
│  ├─ Waits for DB
│  └─ Enters infinite loop:
│     └─ Every 30s: scan /product_output
│        ├─ List *.tif files
│        ├─ Parse filename
│        ├─ Extract metadata with rasterio
│        ├─ INSERT/UPDATE RadarCOG in DB (or mark MISSING)
│        └─ Continue
│
├─ API starts
│  ├─ Loads from database on first request
│  └─ Serves endpoints
│
└─ Frontend loads @ http://localhost
   ├─ GET /radars → populate dropdown
   ├─ GET /products → populate selector
   ├─ GET /cogs → fetch latest
   ├─ Render map
   └─ Set up polling (every 5 min)
```

### 6.2 COG Lifecycle in DB

```
File Created @ /product_output/RMA1/DBZH/...

    ↓

Indexer Scan (30s interval)
├─ File detected
├─ Check if file_path already in DB
│  └─ If yes: skip (UNIQUE constraint)
│  └─ If no: continue
├─ Parse filename → radar_code, product_key, observation_time
├─ Validate radar_code exists in Radar table
├─ Validate product_key exists in RadarProduct table
└─ Extract metadata → INSERT RadarCOG
   └─ status = AVAILABLE

    ↓

API Query (GET /cogs)
├─ Filter by radar_code, product_key, time range
├─ ORDER BY observation_time DESC
├─ LIMIT page_size
└─ Return COGResponse (includes id, file_path, cog_cmap, cog_vmin, cog_vmax)

    ↓

Frontend
├─ Fetch COGs via GET /cogs
├─ Group by timestamp (±5 min)
├─ Create animation frames
└─ For each frame, render COG tiles:
   └─ GET /tiles/{cog_id}/{z}/{x}/{y}.png

    ↓

Tile Rendering
├─ Load COG from /product_output/{file_path}
├─ Use rio_tiler to extract Web Mercator tile
├─ Apply colormap (from cog_cmap or param)
├─ Encode to PNG
└─ Return to browser

    ↓

Map Display
└─ Leaflet renders tile layers on map
```

### 6.3 Status Transitions

```
RadarCOG.status enum:
- PENDING       (not in use currently)
- AVAILABLE ◄─── Default on INSERT
- PROCESSING    (reserved for future use)
- ERROR         (if metadata extraction fails)
- ARCHIVED      (retained from previous run)
- MISSING       (file was indexed but no longer exists)
```

---

## 7. Error Handling & Edge Cases

### 7.1 Indexer Error Handling

**Goal:** One bad file doesn't stop the entire scan.

```python
def run_scan(self, session):
    """Scan directory, handle errors gracefully."""
    for file_path in self.watch_path.glob('*.tif'):
        try:
            parsed = self.parser.parse(str(file_path))
            if not parsed.is_valid:
                logger.warning(f"Could not parse: {file_path} - {parsed.error}")
                continue
            
            cog_id = self.registrar.register_file(file_path, session)
            if cog_id:
                logger.info(f"Indexed COG {cog_id}: {file_path}")
        
        except Exception as e:
            logger.error(f"Failed to index {file_path}: {e}")
            # Mark as ERROR in DB if possible
            # Continue with next file
            continue
```

### 7.2 API Error Handling

**Goal:** Never return 500. Always handle missing/corrupted files gracefully.

```python
@router.get("/tiles/{cog_id}/{z}/{x}/{y}.png")
def get_tile(cog_id, z, x, y, db: Session = Depends(get_db)):
    cog = db.query(RadarCOG).filter_by(id=cog_id).first()
    
    if not cog:
        return HTTPException(status_code=404, detail="COG not found")
    
    if cog.status != COGStatus.AVAILABLE:
        return HTTPException(status_code=404, detail="COG not available")
    
    try:
        tile_bytes = tile_service.get_tile(...)
    except FileNotFoundError:
        # File was in DB but no longer exists
        # Mark as MISSING and return 404
        cog.status = COGStatus.MISSING
        session.commit()
        return HTTPException(status_code=404, detail="File not found")
    
    except Exception as e:
        logger.error(f"Tile rendering failed: {e}")
        return HTTPException(status_code=500, detail="Rendering error")
    
    return tile_bytes
```

### 7.3 Frontend Error Handling

```javascript
async function loadCogs(radarCode, productKey, hoursBack) {
    try {
        const cogs = await api.getCogs(radarCode, productKey, hoursBack);
        
        if (cogs.length === 0) {
            ui.showError(`No COGs found for ${productKey}`);
            return;
        }
        
        const frames = groupCogsByTimestamp(cogs);
        animator.setFrames(frames);
        
    } catch (error) {
        logger.error(`Failed to load COGs: ${error}`);
        ui.showError("Failed to load radar data. Check API connection.");
    }
}
```

---

## 8. Configuration & Environment Variables

### 8.1 Indexer Configuration

**File:** `indexer/indexer/config.py`

```python
# From environment variables:
WATCH_PATH = os.getenv("WATCH_PATH", "/product_output")
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "30"))
FILE_PATTERN = os.getenv("FILE_PATTERN", "*.tif")
COMPUTE_STATS = os.getenv("COMPUTE_STATS", "true").lower() == "true"
COMPUTE_CHECKSUM = os.getenv("COMPUTE_CHECKSUM", "false").lower() == "true"
RADAR_CODES = os.getenv("RADAR_CODES", "").split(",")  # Optional filter
```

**Set in docker-compose.yml:**
```yaml
indexer:
  environment:
    DB_HOST: radar_db
    WATCH_PATH: /product_output
    SCAN_INTERVAL: 30
    FILE_PATTERN: "*.tif"
    COMPUTE_STATS: "true"
    COMPUTE_CHECKSUM: "false"
```

### 8.2 API Configuration

**File:** `api/app/config.py`

```python
class APISettings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "radar_prod_db"
    db_user: str = "radar"
    db_password: str = "radarpass"
    cog_base_path: str = "/product_output"
    cors_origins: str = "*"
```

### 8.3 Database Configuration

**File:** `database/radar_db/config.py`

```python
class DatabaseSettings(BaseSettings):
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_password: str
    pool_size: int = 5
    max_overflow: int = 10
```

---

## 9. Data Retention & Cleanup

### 9.1 COG File Lifecycle

- **Produced by radarlib:** File placed in `/product_output/{radar_code}/{product_key}/`
- **Indexed by webmet25:** RadarCOG record created with `status=AVAILABLE`
- **Queried by API:** Returned in `/cogs` endpoint (only if `status=AVAILABLE`)
- **Rendered on frontend:** Tile layers added to map
- **Deleted from filesystem:** Indexer detects on next scan → marks `status=MISSING`
- **Archived:** No automatic deletion from DB (retention policy TBD)

### 9.2 Database Cleanup (Future)

Currently **not implemented**. Gaps noted:

- ❌ No automatic archival of old COG records
- ❌ No retention policy (e.g., keep last 30 days)
- ❌ Manual cleanup required: `DELETE FROM radar_cogs WHERE status='MISSING'`

---

## 10. Summary: Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│ RADARLIB (External)                                                  │
│ Produces: /product_output/RMA1/DBZH/RMA1_20260401T205000Z_DBZH_00.tif│
│ Tags: radarlib_cmap, radarlib_vmin, radarlib_vmax, field_name        │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│ INDEXER (File Watcher Every 30s)                                     │
│ ├─ Scan /product_output                                              │
│ ├─ Parse filename → radar_code, product_key, observation_time        │
│ ├─ Extract COG metadata (rasterio): bbox, dtype, crs, statistics    │
│ └─ INSERT/UPDATE RadarCOG in PostgreSQL                              │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│ DATABASE (PostgreSQL + PostGIS)                                      │
│ ├─ Radar (reference: code, title, location)                         │
│ ├─ RadarProduct (reference: product_key, min/max, unit)             │
│ ├─ RadarCOG (main: id, file_path, bbox, status, timestamps)         │
│ └─ Reference (colormap: product_id, value, color)                   │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│ API (FastAPI)                                                        │
│ ├─ GET /radars → RadarList                                           │
│ ├─ GET /products → ProductList                                       │
│ ├─ GET /cogs?radar_code=...&product_key=... → COGList               │
│ ├─ GET /tiles/{cog_id}/{z}/{x}/{y}.png → PNG (via rio_tiler)        │
│ └─ GET /products/{key}/colormap → RefList                            │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│ FRONTEND (Leaflet + ES6 Modules)                                     │
│ ├─ app.js: State mgmt & orchestration                               │
│ ├─ api.js: REST client → fetch COGs, group by timestamp             │
│ ├─ map.js: Leaflet wrapper → TileLayer for each COG                 │
│ ├─ animation.js: Play/pause frames, speed control                   │
│ ├─ legend.js: Render colormap from Reference entries                │
│ └─ User: sees animated radar map with multiple overlays             │
└──────────────────────────────────────────────────────────────────────┘
```

---

**Document Version:** 2.0.0  
**Last Updated:** May 29, 2026
