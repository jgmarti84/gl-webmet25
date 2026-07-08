# DATA_FLOW.md — Pipeline de Consumo de Datos de WebMet25

> Versión en español de [DATA_FLOW.md](DATA_FLOW.md).

> **Propósito:** Explicar cómo WebMet25 ingesta, procesa y muestra los datos de radar producidos por radarlib.
> **Leer antes de modificar el indexer o la API.**

---

## 1. Resumen general

WebMet25 es un **consumidor de datos** en el sistema de radar/meteorología. Recibe archivos Cloud-Optimized GeoTIFF (COG) y archivos GeoJSON de Tops y Cores desde radarlib, los indexa en una base de datos PostgreSQL/PostGIS y los sirve a través de una API REST a un frontend web interactivo.

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

## 2. Capa de ingesta de datos: el Indexer

### 2.1 Punto de entrada

**Archivo:** [`indexer/indexer/main.py`](../indexer/indexer/main.py)

**Responsabilidad:**
- Espera a que PostgreSQL esté disponible
- Inicia `TopsAndCoresWatcher` en un hilo en segundo plano (escanea `TOPS_AND_CORES_DIR`)
- Inicia `COGWatcher` en el hilo principal (escanea `ROOT_RADAR_PRODUCTS_PATH`)

### 2.2 Escaneo del sistema de archivos: COGWatcher

**Archivo:** [`indexer/indexer/watcher.py`](../indexer/indexer/watcher.py)

**Responsabilidad:**
- Monitorea `ROOT_RADAR_PRODUCTS_PATH` cada `SCAN_INTERVAL` segundos (valor por defecto: 30 s)
- Primera ejecución: escaneo completo. Ejecuciones posteriores: incremental (archivos modificados en los últimos 5 min + solapamiento)
- Para cada archivo `.tif`: analiza el nombre de archivo → extrae metadatos COG mediante rasterio → inserta/actualiza `RadarCOG`
- Un archivo con error no detiene el escaneo completo
- Si `MARK_MISSING_FILES=true` (valor por defecto): marca como `MISSING` los archivos previamente indexados que ya no existan en disco
- **`update_radar_activity()`:** Se invoca al final de cada escaneo. Establece `Radar.is_active = True/False` según si existe un COG `AVAILABLE` reciente dentro de las últimas `RADAR_ACTIVE_THRESHOLD_HOURS` horas

**Configuración:** [`indexer/indexer/config.py`](../indexer/indexer/config.py)

| Variable de entorno | Valor por defecto | Descripción |
|---------------------|-------------------|-------------|
| `WATCH_PATH` | `/product_output` | Ruta raíz para escanear archivos COG |
| `SCAN_INTERVAL` | `30` | Segundos entre escaneos |
| `FILE_PATTERN` | `*.tif` | Patrón glob para archivos COG |
| `COMPUTE_STATS` | `true` | Calcular estadísticas de mín/máx/media por banda |
| `COMPUTE_CHECKSUM` | `false` | Calcular checksum SHA-256 al indexar |
| `RADAR_ACTIVE_THRESHOLD_HOURS` | `2` | Horas de antigüedad para considerar un radar activo |
| `MARK_MISSING_FILES` | `true` | Marcar archivos indexados como MISSING si no se encuentran |
| `RADAR_CODES` | *(todos)* | CSV o array JSON para restringir qué radares indexar |
| `TOPS_AND_CORES_DIR` | `/tops_and_cores` | Ruta raíz para escanear archivos GeoJSON de tops y cores |
| `LOGS_PATH` | `/logs` | Directorio de salida de logs |

### 2.2b Escaneo de TopsAndCores: TopsAndCoresWatcher

**Archivo:** [`indexer/indexer/watcher.py`](../indexer/indexer/watcher.py)

- Monitorea `TOPS_AND_CORES_DIR` de forma recursiva buscando archivos `*_TOPS_CORES.geojson`
- Para cada archivo nuevo: analiza el nombre de archivo → abre el GeoJSON y contabiliza cores, tops y features totales → inserta/actualiza el registro `TopsAndCores`
- Marca los archivos como `MISSING` si estaban indexados pero ya no están presentes

### 2.3 Análisis del nombre de archivo: COGFilenameParser

**Archivo:** [`indexer/indexer/parser.py`](../indexer/indexer/parser.py)

**Patrón 0 — Formato de producción actual:**
```
{RADAR}_{strategy}_{vol_nr}_{YYYYMMDDTHHMMSSZ}_{FIELD}[o].tif
```
Ejemplos:
```
RMA1_0315_01_20260401T205000Z_DBZH.tif    # Filtered reflectivity, vol 01
RMA1_0315_01_20260401T205000Z_DBZHo.tif   # Unfiltered (raw), vol 01
RMA1_0315_04_20260401T205000Z_COLMAX.tif  # Column max, vol 04 (vigilant)
```

**Patrón 1 — Formato legacy (solo compatibilidad hacia atrás):**
```
{RADAR}_{YYYYMMDDTHHMMSSZ}_{FIELD}[o]_{elev}.tif
```
Ejemplo: `RMA1_20260401T205000Z_DBZHo_00.tif`
(Indexado con `strategy=None`, `vol_nr=None`. Se registra un WARNING.)

**TopsAndCoresFilenameParser** analiza `{radar_code}_{strategy}_{vol_nr}_{YYYYMMDDHHMMSS}_TOPS_CORES.geojson` (sin `T` ni `Z` en el timestamp).

### 2.4 Extracción de metadatos: COGRegistrar

**Archivo:** [`indexer/indexer/registrar.py`](../indexer/indexer/registrar.py)

Datos extraídos de cada GeoTIFF:
- **Sistema de archivos:** `file_size_bytes`, `file_mtime`
- **Perfil GeoTIFF (rasterio):** `width`, `height`, `num_bands`, `dtype`, `crs`, `nodata_value`, `compression`, `resolution_x/y`
- **Tags GeoTIFF (radarlib):** `cog_cmap` (`radarlib_cmap`), `cog_vmin` (`radarlib_vmin`), `cog_vmax` (`radarlib_vmax`), `field_name`, `timestamp`
- **Estadísticas opcionales (si `COMPUTE_STATS=true`):** `data_min`, `data_max`, `data_mean`, `valid_pixel_count`
- **Espacial (PostGIS):** límites reproyectados a WGS84 → almacenados como POLYGON en `bbox`

**TopsAndCoresRegistrar** abre el GeoJSON, contabiliza features por propiedad `type` (`core` vs `top`) y hace upsert del registro `TopsAndCores`.

---

## 3. Esquema de base de datos: Modelo de datos

**Todos los modelos definidos en:** [`database/radar_db/models.py`](../database/radar_db/models.py)

### 3.1 Tablas principales

#### **Radar** (Datos de referencia)
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

#### **RadarProduct** (Datos de referencia)
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

#### **RadarCOG** (Tabla principal de datos — Archivos COG indexados)
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

#### **TopsAndCores** (Archivos GeoJSON indexados)
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

#### **Reference** (Entradas de escala de color para leyendas)
```python
id: int (PK)
product_id: int (FK → RadarProduct.id, INDEX)
title, description, unit: str
value: float                  # e.g. 10.0 dBZ
color: str(7)                 # "#ff0000"
color_font: str(7)            # "#ffffff"
```

#### **Estrategia / Volumen** (Definiciones de estrategia de escaneo)
```python
# Estrategia
code: str (PK)                # "0315"
description: str
volumenes: M:M via estrategia_volumen association table

# Volumen
id: int (PK)
value: int                    # Volume number integer
```

#### **ColormapStop** (Colormaps respaldados por BD)
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

8 colormaps del sistema sembrados: `grc_th`, `grc_th2`, `grc_rain`, `grc_g`, `grc_rho`, `grc_zdr`, `grc_vrad`, `Theodore16`.

#### **ProductColormapOption** (Emparejamientos Producto ↔ Colormap)
```python
id: int (PK)
product_key: str (FK → RadarProduct.product_key)
cmap_name: str
# UniqueConstraint: (product_key, cmap_name)
```

### 3.2 Índices (Rendimiento)

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

### 3.3 Datos iniciales: Semillas

**Archivo:** [`database/seed_data/initial_data.json`](../database/seed_data/initial_data.json)

Siembra 21 radares (AR5, AR7, AR8, RMA1–RMA18, RMA00), 20 productos (COLMAX, COLMAXo, DBZH, DBZHo, RHOHV, RHOHVo, ZDR, ZDRo, VRAD, VRADo, WRAD, WRADo, KDP, KDPo, PHIDP, PHIDPo, DBZV, DBZVo, MOSAICO, MOSAICOo), ~80 referencias, 5 volúmenes, 11 estrategias, 46 emparejamientos de opciones producto-colormap y 8 colormaps del sistema.

---

## 4. Capa de la API: Consulta y servicio de datos

### 4.1 Arquitectura de routers de la API

**Punto de entrada:** [`api/app/main.py`](../api/app/main.py)

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

Middleware: encabezado de respuesta `X-Process-Time`. El manejador global de excepciones retorna JSON estructurado (nunca un traceback crudo de 500).

### 4.2 Endpoint de radares

**Archivo:** [`api/app/routers/radars.py`](../api/app/routers/radars.py)

- `GET /radars` — parámetro de consulta `active_only: bool = True`
- `GET /radars/{radar_code}` — 404 si no se encuentra

Campos de **`RadarResponse`**: `code`, `title`, `description`, `center_lat`, `center_long`, `img_radio`, `is_active`, `detail_view_enabled`, `extent` (dict bbox calculado).

### 4.3 Endpoint de productos

**Archivo:** [`api/app/routers/products.py`](../api/app/routers/products.py)

- `GET /products` — parámetros: `enabled_only: bool = True`, `vol_nr: List[str]` (repetible), `strategy: str`
- `GET /products/{product_key}` — 404 si no se encuentra
- `GET /products/{product_key}/colormap` — **deprecado**; retorna `ColormapResponse` legacy desde la tabla Reference. Usar `/colormap/info/{product_key}` en su lugar.

### 4.4 Endpoint de COGs

**Archivo:** [`api/app/routers/cogs.py`](../api/app/routers/cogs.py)

- `GET /cogs` — lista paginada; parámetros: `radar_code`, `product_key`, `strategy`, `vol_nr` (repetible), `start_time`, `end_time`, `page`, `page_size (1–200, por defecto 50)`
- `GET /cogs/latest` — COG disponible más reciente; parámetros: `radar_code`, `product_key`, `vol_nr`, `strategy`
- `GET /cogs/timeline` — timestamps disponibles; parámetros: `radar_code`, `product_key`, `hours (1–48, por defecto 6)`; retorna `TimelineResponse`
- `GET /cogs/{cog_id}` — obtiene un COG por ID de base de datos

Campos de **`COGResponse`**: `id`, `radar_code`, `product_key`, `product_id`, `observation_time`, `elevation_angle`, `file_path`, `file_name`, `data_min`, `data_max`, `bbox`, `tile_url`, `cog_data_type`, `cog_cmap`, `cog_vmin`, `cog_vmax`, `strategy`, `vol_nr`, `radar_coverage_m`.

El filtrado por `product_key` utiliza coincidencia exacta sobre `polarimetric_var` (respeta el sufijo `o`) O sobre `RadarProduct.product_key` para coincidencias por nombre base.

### 4.5 Endpoint de Tiles (v1 — Tiles Web Mercator)

**Archivo:** [`api/app/routers/tiles.py`](../api/app/routers/tiles.py)

- `GET /tiles/{cog_id}/{z}/{x}/{y}.png` — renderizar tile de 256×256; parámetros: `colormap`, `vmin`, `vmax`; ETag/GET condicional → 304; renderizado CPU delegado a thread pool executor
- `GET /tiles/by-params/{radar_code}/{product_key}/{timestamp}/{z}/{x}/{y}.png` — tile por radar+producto+timestamp; `timestamp` = cadena ISO o `"latest"`
- `GET /tiles/{cog_id}/metadata` — retorna `cog_data_type`, `cmap`, `vmin`, `vmax`, `product_key`, `available_colormaps`
- `GET /tiles/cache/stats` — estadísticas de caché L1 LRU + L2 Redis (monitoreo)

Caché: `TTLCache(maxsize=500, ttl=300 s)` para metadatos de COG. Cache-Control: COGs recientes → `max-age=60`; COGs de más de 10 min → `max-age=86400, immutable`.

### 4.6 Endpoint de Frames (v2 — Imagen COG completa)

**Archivo:** [`api/app/routers/frames.py`](../api/app/routers/frames.py)

Retorna el raster COG completo como un único PNG RGBA georeferenciado. Lo utiliza el frontend v2 (`L.imageOverlay`) para reemplazar ~10 solicitudes de tiles por fotograma con una sola solicitud.

**Endpoint:** `GET /frames/{cog_id}/image.png`

**Parámetros de consulta:**

| Parámetro | Tipo | Valor por defecto | Descripción |
|-----------|------|-------------------|-------------|
| `colormap` | str | desde tag del COG | Nombre del colormap |
| `vmin` / `vmax` | float | desde tag del COG | Rango de escala datos-a-color |
| `filter_vmin` / `filter_vmax` | float | null | Máscara alfa para píxeles fuera del rango (transparente) |
| `smooth` | bool | false | Aplicar desenfoque gaussiano antes del colormap |
| `smooth_sigma` | float | 0.8 | Sigma del kernel gaussiano (0.1–3.0); se ignora cuando `smooth=false` |

**Encabezados de respuesta:** `X-Bbox-West`, `X-Bbox-South`, `X-Bbox-East`, `X-Bbox-North` (WGS84), `X-Width`, `X-Height`, `ETag`, `Cache-Control`.

**Caché:** L1 LRU `(maxsize=750)` en proceso + L2 Redis (prefijo de clave `frame:`). La clave de caché incluye `(file_path, colormap, vmin, vmax, filter_vmin, filter_vmax, smooth, smooth_sigma)`. Cuando `smooth=false` el slot sigma es `None`, por lo que todas las solicitudes sin suavizado comparten la misma entrada de caché.

**Suavizado gaussiano:** Implementado en [`api/app/services/smoothing.py`](../api/app/services/smoothing.py) mediante `scipy.ndimage.gaussian_filter`. Se aplica al arreglo de datos float crudo **antes** de la búsqueda en el colormap — el suavizado opera sobre valores físicos, no sobre píxeles RGBA.

**Error:** Retorna 503 ante errores transitorios `RasterioIOError` (reintentable); 404 si el COG no se encuentra en la BD.

### 4.7 Endpoints de Tops y Cores

**Archivo:** [`api/app/routers/tops_cores.py`](../api/app/routers/tops_cores.py)

- `GET /tops-cores` — parámetros: `radar_codes[]` (obligatorio, repetible), `time_from` (obligatorio), `time_to` (obligatorio), `status (por defecto: "available")`; retorna lista vacía (nunca 404) cuando no hay registros que coincidan; `Cache-Control: no-cache`
- `GET /tops-cores/{record_id}/features` — retorna `FeatureCollection` GeoJSON cruda como `application/geo+json`; ETag/GET condicional → 304; `Cache-Control: public, max-age=86400, immutable`; marca el registro como `MISSING` en la BD si el archivo no se encuentra en disco

Respuesta **`TopsAndCoresRecord`**: `id`, `radar_code`, `observation_time`, `file_name`, `feature_count`, `core_count`, `top_count`, `status`, `strategy`, `vol_nr`.

### 4.8 Endpoints de Colormap

**Archivo:** [`api/app/routers/colormap.py`](../api/app/routers/colormap.py)

Respaldado por `ColormapService` — un singleton thread-safe con caché de TTL de 5 minutos. Orden de resolución: BD (`colormap_stops`) → constructores hardcodeados en `utils/colormaps.py` → PyART → matplotlib.

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /colormap/names | Lista todos los nombres de colormap definidos en la BD |
| GET | /colormap/options | Mapa de product_key → [cmap_names] |
| GET | /colormap/defaults | Mapa de product_key → default_cmap_name |
| GET | /colormap/colors/{cmap_name} | Lista de colores hex (parámetro: steps=256, rango 2–1024) |
| GET | /colormap/info/{product_key} | Información completa: colormap, vmin, vmax, colors[], ticks[], available_colormaps[]; override opcional con ?colormap= |
| POST | /colormap/cache/invalidate | Invalida la caché en proceso después de ediciones en la BD |

### 4.9 API de Admin y Panel

**Router:** [`api/app/routers/admin.py`](../api/app/routers/admin.py) — ruta base `/api/v1/admin`  
**Frontend:** [`frontend/public/admin.html`](../frontend/public/admin.html) + [`js/admin.js`](../frontend/public/js/admin.js), servido en `/admin`

**Autenticación (temporal):** Tanto `/admin` como `/api/v1/admin/` están protegidos por **nginx HTTP Basic Auth** (`admin.htpasswd`). La API pública `/api/v1/*` permanece abierta. ⚠️ TODO: reemplazar con JWT antes de producción.

**Grupos de endpoints:**

| Recurso | Operaciones |
|---------|-------------|
| Radares | `GET list`, `GET /{code}`, `POST → 201`, `PUT /{code}`, `PATCH /{code}`, `DELETE /{code} → 204` |
| Productos | `GET list`, `GET /{id}`, `POST → 201`, `PUT /{id}`, `PATCH /{id}`, `DELETE /{id} → 204` |
| Referencias | `GET list` (`?product_id`), `GET /{id}`, `POST → 201`, `PUT /{id}`, `DELETE /{id} → 204`, `DELETE bulk by product_id` |
| COGs | `GET paginated+filtered`, `GET /{id}`, `PATCH /{id}` (status only), `DELETE /{id} → 204`, `DELETE bulk` (at least one filter required) |
| Estrategias | `GET list`, `GET /{code}`, `POST → 201`, `PUT /{code}`, `DELETE /{code} → 204` |
| Volúmenes | `GET list`, `GET /{id}`, `POST → 201`, `PUT /{id}`, `DELETE /{id} → 204` |
| Tops y Cores | `GET paginated`, `GET /{id}`, `PATCH /{id}` (status only), `DELETE /{id} → 204`, `DELETE bulk` |
| Stops de Colormap | `GET summaries`, `GET /{name}` (all rows), `POST → 201` (one row), `DELETE /{name}` (system → 403) |
| Colormap desde Hex | `POST → 201`: create from `{cmap_name, stops:[{position, color}], product_keys[]}`; **409 si el nombre ya existe** (sin upsert) |
| Opciones de Colormap | `GET` (`?product_key`), `POST → 201`, `DELETE /{id} → 204` |

**Patrón de edición (sin endpoint de actualización para colormaps):** eliminar y recrear — `DELETE /colormap-stops/{name}` → `POST /colormap-from-hex` con el mismo nombre → reconciliar opciones → `POST /colormap/cache/invalidate`.

**Funcionalidades del panel:** Filtrado estilo Django-admin (búsqueda global + facetas por columna de tipo `text`/`select`/`boolean`, conteo en vivo, columnas ordenables), acciones de fila con íconos de lápiz/papelera en línea, creador/editor visual de colormaps con stops de gradiente arrastrables.

---

## 5. Capa del frontend: Visualización y estado de datos

> **v2 es el estándar de producción actual.** v1 (`L.tileLayer` + endpoint `/tiles`) se conserva en `js/v1/` solo como referencia. Todo el desarrollo nuevo apunta a v2.

### 5.0 Estructura de archivos del frontend

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

### 5.1 Estado global: Mapa multi-radar (`v2/app.js`)

El objeto `state` en `v2/app.js` es la única fuente de verdad para el mapa multi-radar:

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

### 5.2 Modos de cobertura

Definidos en `v2/constants.js`:

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

El modo se persiste en la clave `webmet25_coverage_mode` de `localStorage`. Las consultas de COG pasan los `volNrs` del modo activo como parámetros `?vol_nr=`. Cambiar de modo dispara una recarga completa mediante `_loadFramesWithContinuity()`.

### 5.3 Flujo de datos: Inicialización (Mapa multi-radar)

1. `app.init()` — espera a Leaflet, crea `MapManager`, `AnimationController`, `UIControls`, `LegendRenderer`, `TopsCoresLayer`
2. `loadInitialData()` — `GET /radars` + `GET /products`; restaura `coverageModeId` desde localStorage
3. `controls.populateRadarCheckboxes(radars, showInactive)` — construye la lista de radares con botones de detalle `›`
4. Geolocalización — geolocalización del navegador → los 3 radares más cercanos se seleccionan automáticamente → `loadLastNHours(1.5)` con `COLMAX`
5. Se inicia el temporizador de actualización en vivo (por defecto 5 min)

### 5.4 Carga de COGs y continuidad de animación

Todas las cargas de datos pasan por `_loadFramesWithContinuity(loadFn, opts)`:

1. `_fetchTimeRangeFrames()` — obtención pura de datos: `api.getCogsForTimeRange()` por cada radar seleccionado, `groupCogsByTimestamp()` en grupos
2. La animación continúa ejecutándose desde el buffer actual (nunca se detiene)
3. `mapManager.updateParams(cogsByFrame, productKey, params, onProgress)` — precarga todas las imágenes de fotogramas en segundo plano llamando a `GET /frames/{id}/image.png` por cada COG
4. `animator.updateFrames(frames, productKey)` — intercambio atómico; el loop rAF toma los nuevos fotogramas en el siguiente tick

> ⚠️ **Invariante:** Nunca llamar a `animator.stop()`, `animator.reset()`, ni limpiar capas antes de que los nuevos fotogramas estén preparados. Toda carga de datos debe pasar por `_loadFramesWithContinuity`.

### 5.5 Gestión de capas del mapa (`v2/map.js`)

**`MapManager`** administra el mapa Leaflet + la caché de imágenes de fotogramas + la máscara de cobertura SVG:

- `_frameImages`: `Array<Map<overlayKey, ImageEntry>>` — array externo indexado por fotograma, Map interno con clave `${radarCode}__${productKey}`
- `_overlays`: `Map<overlayKey, L.imageOverlay>` — overlays de Leaflet (uno por radar+producto, compartidos entre fotogramas)
- Cada imagen de fotograma se obtiene mediante `fetch()` (para leer los encabezados de respuesta `X-Bbox-*`), almacenada como blob → object URL
- `loadFrames(cogsByFrame, productKey, params, onProgress)` — obtención paralela de todos los fotogramas
- `showFrame(frameIndex, radarCodes, productKey)` — oculta todos los overlays, muestra los relevantes con la opacidad actual; este es el camino crítico de animación
- `updateParams(cogsByFrame, productKey, params, onProgress)` — carga en paralelo en nuevas estructuras, luego intercambia `_frameImages` de forma atómica (sin interrumpir la animación)
- `addRadarToFrame()` / `removeFrame()` — splicing incremental para agregar/quitar radar sin recarga completa

**Máscara de cobertura SVG:**
- Renderizada dentro de `coverageMaskPane` (pane de Leaflet, z-index 300)
- `<rect>` oscuro con `<mask>` que perfora elipses transparentes por área de cobertura de cada radar
- Se redibuja únicamente en `moveend` y `zoomend` (no en cada fotograma — cero lag de animación)
- `addRadarCoverage(code, lat, lng, radius_m)` / `removeRadarCoverage(code)` / `setRadarCoverageRings(code, rings)` / `setCoverageOpacity(opacity)`

**Mapas base:** `argenmap`, `argenmap_gris`, `argenmap_topo`, `argenmap_oscuro`, `argenmap_hibrido` (IGN Argentina). Por defecto: `argenmap`. Se persiste en `webmet25_selected_basemap`. Siempre usar `MapManager.setBasemap(key)` — nunca manipular `_baseLayer` directamente.

### 5.6 Controlador de animación (`v2/animation.js`)

**`AnimationController`** utiliza `requestAnimationFrame` (no `setInterval`):

- `_frames`: array de fotogramas actual; `_currentFrame`: puntero; `_playing`: booleano; `_speedMultiplier`: 0.5–2.0
- `play()` / `pause()` / `toggle()` — inicia/detiene el loop rAF (`_scheduleLoop`)
- `updateFrames(frames, productKey, currentIndex)` — reemplaza atómicamente la lista de fotogramas; ajusta el puntero; reinicia el loop si estaba reproduciendo
- `_tick()` — avanza `_currentFrame`, llama a `_showCurrentFrame()` → `mapManager.showFrame()` + dispara el callback `_onFrameChange`
- Callback `_onFrameChange` en `app.js`: actualiza la visualización de tiempo, el contador de fotogramas y la capa de tops y cores

### 5.7 Página de detalle de un radar (`radar.html` + `v2/radar-app.js`)

`radar.html?code=AR5[&field=DBZHo]` — compositor multi-capa de un solo radar. Siempre opera en modo C+D.

**Estructura del objeto de capa:**
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

**`showAllLayersAtFrame(frameIndex)`** — se invoca en cada tick de animación en lugar del `showFrame` de un solo producto. Compone todas las capas visibles en orden z con opacidad por capa.

**Invariante del filtro de rango:** los valores `vmin`/`vmax` enviados a `/frames` son solo límites de máscara alfa (los píxeles fuera del rango → transparentes). La normalización del colormap siempre usa los valores por defecto del producto desde `colormap_for_field()` — nunca se modifican por el filtro. Los inputs de la UI se preinicializan con `colormap.vmin/vmax`, por lo que hacer clic en "Aplicar" sin acotar el rango no tiene efecto visual.

### 5.8 Capa de Tops y Cores (`shared/tops-cores.js`)

**`TopsCoresLayer`** administra `L.layerGroup()` en `topsCoresPane` (z-index 450):

- `updateFrame(frame)` — fire-and-forget: cancela la solicitud anterior en vuelo, obtiene `/tops-cores?time_from=...&time_to=...&radar_codes=...` (ventana de ±2.5 min), luego `GET /tops-cores/{id}/features` en paralelo, renderiza `L.circleMarker`
- Las respuestas desactualizadas más antiguas que el último timestamp renderizado se descartan
- Cores: `fillColor: '#3b82f6'` (azul); Tops: `fillColor: '#ef4444'` (rojo); ambos: borde negro
- Restringida a los productos COLMAX y COLMAXo

### 5.9 Renderizador de leyenda (`shared/legend.js`)

`LegendRenderer.render(colormapData, filterOptions)`:
- Construye la barra de gradiente (32 stops CSS) desde el array `colormapData.colors[]`
- Prioridad de fuente de ticks: `colormapData.ticks` (filas de Reference) → 5 valores con espaciado automático
- El rango de filtro se muestra como marcadores de corchete (no muta `colormap.vmin/vmax`)
- `buildGradient(colors, startFraction, endFraction)` mapea la ventana del filtro en la barra de colormap completa

### 5.10 Visualización del tiempo

Los timestamps de los fotogramas se formatean en la zona horaria `America/Argentina/Buenos_Aires`. El método `setTimeDisplay` en `UIControls` utiliza esta configuración regional de forma explícita.

---

## 6. Ciclo de vida del estado de datos

### 6.1 Secuencia de inicio

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

### 6.2 Ciclo de vida del COG en la BD

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

### 6.3 Transiciones de estado

```
COGStatus enum:
  AVAILABLE  ◄── Default on INSERT
  MISSING    ◄── File was indexed but no longer exists on disk
  ERROR      ◄── Metadata extraction failed during indexing
  PENDING    (reserved, not currently used)
  PROCESSING (reserved, not currently used)
  ARCHIVED   (reserved, not currently used)
```

Los endpoints `/frames` y `/tiles` marcan un COG como `MISSING` si el archivo no se encuentra en disco al momento de servir la solicitud.

---

## 7. Manejo de errores y casos borde

- **Nunca HTTP 500:** La API envuelve todos los handlers; los archivos/registros faltantes retornan los 4xx adecuados
- **503 ante errores transitorios:** `/frames` retorna 503 (no 500) ante `RasterioIOError` (reintentable)
- **Resultados vacíos:** `/tops-cores` retorna `[]`, no 404, cuando no hay registros que coincidan
- **Agregar/quitar radar de forma incremental:** `addRadarIncremental()` / `removeRadarIncremental()` modifican la estructura `_frameImages` sin recargar todos los fotogramas ni detener la animación
- **Un archivo con error:** COGWatcher captura las excepciones por archivo; el escaneo continúa
- **Unicidad de vol_nr NULL:** PostgreSQL trata NULL != NULL, por lo que las filas legacy (vol_nr=NULL) para el mismo radar+producto+timestamp son cada una única

---

## 8. Configuración y variables de entorno

### 8.1 Configuración del Indexer

Ver §2.2 para la tabla completa de variables de entorno de `IndexerSettings`.

### 8.2 Configuración de la API

**Archivo:** [`api/app/config.py`](../api/app/config.py) — `APISettings(BaseSettings)`

| Campo | Variable de entorno | Valor por defecto | Descripción |
|-------|---------------------|-------------------|-------------|
| `db_host` | `DB_HOST` | `postgres` | Nombre de host de la BD |
| `db_port` | `DB_PORT` | `5432` | Puerto de la BD |
| `db_name` | `DB_NAME` | `radar_db` | Nombre de la BD |
| `db_user` | `DB_USER` | `radar` | Usuario de la BD |
| `db_password` | `DB_PASSWORD` | `radarpass` | Contraseña de la BD |
| `cog_base_path` | `COG_BASE_PATH` | `/product_output` | Ruta raíz a los archivos COG |
| `cors_origins` | `CORS_ORIGINS` | `*` | Orígenes permitidos separados por comas |
| `tile_render_threads` | `TILE_RENDER_THREADS` | `8` | Tamaño del pool de hilos para renderizado de tiles |
| `redis_host` | `REDIS_HOST` | `redis` | Nombre de host de Redis |
| `redis_port` | `REDIS_PORT` | `6379` | Puerto de Redis |
| `redis_enabled` | `REDIS_ENABLED` | `true` | Habilitar caché L2 de Redis |
| `redis_tile_ttl_seconds` | `REDIS_TILE_TTL_SECONDS` | `86400` | TTL para entradas de caché de COGs antiguos |
| `redis_tile_ttl_recent_seconds` | `REDIS_TILE_TTL_RECENT_SECONDS` | `3600` | TTL para entradas de caché de COGs recientes |

Ajuste de GDAL: `GDAL_CACHEMAX`, `VSI_CACHE`, `VSI_CACHE_SIZE`, `GDAL_DISABLE_READDIR_ON_OPEN`.

### 8.3 Configuración de la base de datos

**Archivo:** `database/radar_db/config.py` — `DatabaseSettings(BaseSettings)`

Variables de entorno: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`

### 8.4 Configuración del Frontend / Nginx

`ADMIN_USERNAME` y `ADMIN_PASSWORD` son leídos por `docker-entrypoint.sh` al iniciar el contenedor para generar `/etc/nginx/admin.htpasswd`. Cambiarlos requiere reconstruir o reiniciar el contenedor del frontend.

Nginx también almacena en caché local los tiles de OSM e IGN Argenmap (TTL de 30 días y 7 días respectivamente) para reducir las solicitudes externas.

---

## 9. Retención de datos y limpieza

- **Sin archivado automático.** Los registros COG se conservan en la BD indefinidamente; los archivos eliminados del disco se marcan como `MISSING`.
- **Limpieza manual:** Usar `ProductDeleter` (ver [`docs/OPERATIONS.md`](OPERATIONS.md)) o SQL directo: `DELETE FROM radar_cogs WHERE status='missing'`
- **`MARK_MISSING_FILES` del Indexer:** Establecer en `false` para deshabilitar la detección de archivos faltantes (no recomendado para producción)

---

## 10. Resumen: Diagrama del flujo de datos

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

**Versión del Documento:** 3.0.0  
**Última Actualización:** 8 de julio de 2026
