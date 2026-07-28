# WebMet25 — Informe de Descubrimiento Técnico

> Versión en español de [DISCOVERY_REPORT.md](DISCOVERY_REPORT.md).

> Análisis técnico completo del código actual: arquitectura, esquema de base de datos, contrato de API, frontend y brechas conocidas.

---

## 1. Stack Tecnológico

### Backend
- **Python:** 3.11
- **Framework web:** FastAPI 0.109.0+
- **Servidor de app:** Uvicorn
- **ORM de base de datos:** SQLAlchemy 2.0.0+
- **Driver de base de datos:** psycopg2-binary 2.9.9+ (PostgreSQL)
- **ORM geoespacial:** GeoAlchemy2 0.14.0+ (PostGIS)
- **Migraciones:** Alembic 1.13.0+
- **Configuración:** Pydantic 2.0.0+, pydantic-settings 2.0.0+
- **Caché:** cachetools 5.0.0+ (LRU), redis 5.0.0+

### Procesamiento Geoespacial y Raster
- **Rasterio:** 1.3.0+ (lectura de COG)
- **rio-tiler:** 6.0.0+ (generación de tiles Web Mercator)
- **Shapely:** 2.0.0+ (operaciones geométricas)
- **GDAL:** paquete del sistema
- **SciPy:** 1.9.0+ (suavizado gaussiano en el endpoint de frames)

### Procesamiento de Imágenes
- **Pillow:** 10.0.0+ (codificación PNG)
- **NumPy:** 1.24.0+
- **Matplotlib:** 3.7.0+ (utilidades de colormap)

### Frontend
- **Leaflet:** 1.9.4 (CDN)
- **Mapas base:** servidor de tiles IGN Argenmap (proxy + caché nginx)
- **JavaScript:** módulos ES6 (sin herramienta de build, sin framework)
- **CSS:** CSS3 puro — tema oscuro (app principal), tema moderno claro (admin)

### Infraestructura
- **Docker:** stack de compose multi-servicio
- **Nginx:** 1.25+ — reverse proxy, Basic Auth para admin, caché local de tiles OSM/IGN
- **Redis:** 7.2 — desalojo LRU, sin persistencia, caché L2 de frames/tiles
- **PostgreSQL:** 15 + PostGIS 3.5

---

## 2. Arquitectura del Proyecto

### Estructura de Directorios

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

### Mapa de Servicios (`docker-compose.yml`)

| Contenedor | Imagen | Rol |
|-----------|-------|------|
| `radar_db` | postgis/postgis:15-3.5 | PostgreSQL + PostGIS (puerto 5433) |
| `redis` | redis:7.2-alpine | Caché L2 de frames/tiles (512 MB LRU) |
| `db-init` | database Dockerfile | Ejecución única de `init` + `seed`, luego finaliza |
| `indexer` | indexer Dockerfile | Daemon COGWatcher + TopsAndCoresWatcher |
| `api` | api Dockerfile | FastAPI + Uvicorn (puerto 8000) |
| `frontend` | frontend Dockerfile | Nginx (puerto 80) sirviendo archivos estáticos |

---

## 3. Esquema de Base de Datos

### 3.1 Modelos

Todos definidos en `database/radar_db/models.py`.

#### `radars`
| Columna | Tipo | Notas |
|--------|------|-------|
| `code` | String(16) PK | "RMA1", "AR5" |
| `title` | String(64) | Nombre para mostrar |
| `description` | String(64) | Opcional |
| `center_lat` | Numeric(12,8) | |
| `center_long` | Numeric(12,8) | |
| `img_radio` | Integer | Radio de cobertura en km |
| `is_active` | Boolean | Actualizado por `update_radar_activity()` |
| `detail_view_enabled` | Boolean | Habilita el enlace a la página de detalle `radar.html` |
| `point1_lat/long` | Numeric(14,10) | Esquina 1 del bounding box |
| `point2_lat/long` | Numeric(14,10) | Esquina 2 del bounding box |
| `created_at`, `updated_at` | DateTime(tz) | |

#### `radar_products`
| Columna | Tipo | Notas |
|--------|------|-------|
| `id` | Integer PK | |
| `product_key` | String(16) UNIQUE | "DBZH", "DBZHo", "COLMAX" |
| `product_title` | String(64) | Nombre para mostrar |
| `product_description` | Text | |
| `enabled` | Boolean | |
| `see_in_open` | Boolean | Mostrar en el toggle sin filtrar |
| `min_value`, `max_value` | Float | Rango de visualización autoritativo |
| `unit` | String(32) | "dBZ", "percent" |
| `default_cmap` | String(64) | Nombre del colormap predeterminado canónico en BD |

#### `radar_cogs`
| Columna | Tipo | Notas |
|--------|------|-------|
| `id` | Integer PK | |
| `radar_code` | String FK → radars.code | |
| `product_id` | Integer FK → radar_products.id | |
| `estrategia_code` | String FK → estrategias.code | NULL para archivos legacy |
| `observation_time` | DateTime(tz) INDEX | |
| `polarimetric_var` | String(16) | Nombre exacto del campo incl. sufijo `o`, ej. "DBZHo" |
| `elevation_angle` | Float | Solo archivos legacy; NULL en producción |
| `vol_nr` | String(16) | "01", "02", "04"; NULL para legacy |
| `radar_coverage_m` | Float | Radio de cobertura en metros (del tag COG) |
| `file_path` | String UNIQUE | Ruta relativa en disco |
| `file_name` | String | Solo nombre de archivo |
| `file_size_bytes` | Integer | |
| `file_mtime` | DateTime(tz) | |
| `file_checksum` | String(64) | SHA-256 (si `COMPUTE_CHECKSUM=true`) |
| `crs` | String | "EPSG:3857" (Web Mercator) |
| `width`, `height` | Integer | Píxeles |
| `num_bands` | Integer | |
| `dtype` | String | "float32" |
| `resolution_x`, `resolution_y` | Float | Grados/metros por píxel |
| `nodata_value` | Float | |
| `compression` | String | "deflate", None |
| `cog_data_type` | String | "raw_float", "rgba", "unknown" |
| `cog_cmap` | String | Nombre del colormap del tag radarlib |
| `cog_vmin`, `cog_vmax` | Float | Rango de datos del tag radarlib |
| `data_min`, `data_max`, `data_mean` | Float | Estadísticas de banda (si se computan) |
| `valid_pixel_count` | Integer | |
| `bbox` | Geometry('POLYGON', srid=4326) | Bounding box WGS84 |
| `status` | COGStatus enum | AVAILABLE, MISSING, ERROR, PENDING, PROCESSING, ARCHIVED |
| `error_message` | Text | |
| `show_me` | Boolean | |
| `created_at`, `updated_at` | DateTime(tz) | |

**Restricción única:** `(radar_code, product_id, observation_time, elevation_angle, vol_nr)` — Las filas con vol_nr NULL son independientes entre sí (NULL ≠ NULL en PostgreSQL).

#### `tops_and_cores`
| Columna | Tipo | Notas |
|--------|------|-------|
| `id` | Integer PK | |
| `radar_code` | String FK → radars.code | |
| `observation_time` | DateTime(tz) INDEX | |
| `file_path` | String UNIQUE | |
| `file_name` | String | |
| `feature_count` | Integer | Total de features GeoJSON |
| `core_count` | Integer | Features con `type=core` |
| `top_count` | Integer | Features con `type=top` |
| `status` | COGStatus | AVAILABLE o MISSING |
| `strategy` | String(16) | ej. "0315" |
| `vol_nr` | String(16) | ej. "00" |
| `created_at`, `updated_at` | DateTime(tz) | |

#### `references`
| Columna | Tipo |
|--------|------|
| `id` | Integer PK |
| `product_id` | Integer FK → radar_products.id INDEX |
| `title`, `description`, `unit` | String |
| `value` | Float |
| `color`, `color_font` | String(7) |

#### `estrategias` / `volumenes`
`estrategias(code PK, description)` ↔ M:M mediante `estrategia_volumen` ↔ `volumenes(id PK, value int)`.

#### `colormap_stops`
| Columna | Tipo | Notas |
|--------|------|-------|
| `id` | Integer PK | |
| `cmap_name` | String | ej. "grc_th" |
| `channel` | String | "r", "g" o "b" |
| `position` | Float | 0.0 – 1.0 dentro del rango de color |
| `val_left`, `val_right` | Float | Valores físicos de datos para este segmento |
| `sort_order` | Integer | |
| `is_system` | Boolean | Colormaps del sistema → 403 al hacer DELETE |

8 colormaps del sistema: `grc_th`, `grc_th2`, `grc_rain`, `grc_g`, `grc_rho`, `grc_zdr`, `grc_vrad`, `Theodore16`.

#### `product_colormap_options`
`(id PK, product_key FK, cmap_name)` — UniqueConstraint `(product_key, cmap_name)`.

### 3.2 Valores del Enum `COGStatus`

| Valor | Significado |
|-------|---------|
| `AVAILABLE` | Archivo indexado y accesible |
| `MISSING` | Previamente indexado; el archivo ya no está en disco |
| `ERROR` | Extracción de metadatos falló durante la indexación |
| `PENDING` | Reservado; no se usa actualmente |
| `PROCESSING` | Reservado; no se usa actualmente |
| `ARCHIVED` | Reservado; no se usa actualmente |

---

## 4. Indexador

### 4.1 Flujo de Ejecución

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

### 4.2 Parseo de Nombres de Archivo

`COGFilenameParser` intenta el Patrón 0 primero; si falla, recurre al Patrón 1 (legacy):

| Patrón | Formato | Notas |
|---------|--------|-------|
| 0 (producción) | `{RADAR}_{strategy}_{vol_nr}_{YYYYMMDDTHHMMSSZ}_{FIELD}[o].tif` | Metadatos completos |
| 1 (legacy) | `{RADAR}_{YYYYMMDDTHHMMSSZ}_{FIELD}[o]_{elev}.tif` | strategy=None, vol_nr=None; se registra WARNING |

`TopsAndCoresFilenameParser` parsea: `{RADAR}_{strategy}_{vol_nr}_{YYYYMMDDHHMMSS}_TOPS_CORES.geojson` (sin `T` ni `Z`).

### 4.3 Registro en Base de Datos

`COGRegistrar.register_file()`:
1. Parsear nombre de archivo → validar código de radar en BD, validar clave de producto en BD
2. Abrir con `rasterio` → extraer CRS, bounds, dimensiones, dtype, tags
3. Transformar bounds a WGS84 (GeoAlchemy2 `from_shape`)
4. INSERT `RadarCOG` con `status=AVAILABLE` (ON CONFLICT vía file_path UNIQUE: actualizar metadatos)
5. Si `MARK_MISSING_FILES=true`: comparar rutas indexadas con disco; marcar ausentes como `MISSING`

### 4.4 Eliminador de Productos (`indexer/indexer/deleter.py`)

`ProductDeleter.delete_products(date, radar_codes, product_keys)`:
- Escanea el filesystem buscando archivos `.tif` que cumplan los criterios
- Elimina archivos del disco; elimina directorios padres vacíos
- Elimina los registros `RadarCOG` correspondientes en la BD en una sola transacción
- Opcionalmente elimina archivos de log `genpro25.log.YYYY-MM-DD`

Consultar [`docs/OPERATIONS.md`](OPERATIONS.md) para más información.

---

## 5. Contrato de API

### 5.1 Endpoints Públicos

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/v1/health` | Control de salud: estado de BD + timestamp |
| GET | `/api/v1/radars` | Listar radares (`?active_only=true`) |
| GET | `/api/v1/radars/{code}` | Obtener un radar |
| GET | `/api/v1/products` | Listar productos (`?enabled_only=true&vol_nr=01&strategy=0315`) |
| GET | `/api/v1/products/{key}` | Obtener un producto |
| GET | `/api/v1/products/{key}/colormap` | **Obsoleto** — usar `/colormap/info/{key}` |
| GET | `/api/v1/cogs` | Lista paginada de COGs (filtros: radar_code, product_key, strategy, vol_nr[], start_time, end_time, page, page_size) |
| GET | `/api/v1/cogs/latest` | COG más reciente para radar+producto |
| GET | `/api/v1/cogs/timeline` | Timestamps disponibles (`?radar_code&product_key&hours`) |
| GET | `/api/v1/cogs/{id}` | Obtener un COG |
| GET | `/api/v1/frames/{id}/image.png` | PNG de imagen completa COG (`?colormap&vmin&vmax&filter_vmin&filter_vmax&smooth&smooth_sigma`) |
| GET | `/api/v1/tiles/{id}/{z}/{x}/{y}.png` | Tile Web Mercator (`?colormap&vmin&vmax`) |
| GET | `/api/v1/tiles/by-params/{radar}/{product}/{timestamp}/{z}/{x}/{y}.png` | Tile por parámetros |
| GET | `/api/v1/tiles/{id}/metadata` | Metadatos de renderizado del tile |
| GET | `/api/v1/tiles/cache/stats` | Estadísticas de caché |
| GET | `/api/v1/colormap/names` | Todos los nombres de colormaps |
| GET | `/api/v1/colormap/options` | Opciones de colormap por producto |
| GET | `/api/v1/colormap/defaults` | Colormap predeterminado por producto |
| GET | `/api/v1/colormap/colors/{name}` | Lista de colores hex (`?steps=256`) |
| GET | `/api/v1/colormap/info/{key}` | Información completa del colormap para un producto |
| POST | `/api/v1/colormap/cache/invalidate` | Vaciar caché de colormaps en proceso |
| GET | `/api/v1/tops-cores` | Consultar metadatos (requerido: `radar_codes[]`, `time_from`, `time_to`) |
| GET | `/api/v1/tops-cores/{id}/features` | FeatureCollection GeoJSON en bruto |

### 5.2 Endpoints de Administración (`/api/v1/admin/*`, Basic Auth nginx)

| Recurso | Operaciones |
|----------|-----------|
| `/admin/radars` | GET, GET/{code}, POST, PUT/{code}, PATCH/{code}, DELETE/{code} |
| `/admin/products` | GET, GET/{id}, POST, PUT/{id}, PATCH/{id}, DELETE/{id} |
| `/admin/references` | GET (`?product_id`), GET/{id}, POST, PUT/{id}, DELETE/{id}, DELETE masivo por `product_id` |
| `/admin/cogs` | GET (paginado+filtrado), GET/{id}, PATCH/{id} (estado), DELETE/{id}, DELETE masivo |
| `/admin/estrategias` | GET, GET/{code}, POST, PUT/{code}, DELETE/{code} |
| `/admin/volumenes` | GET, GET/{id}, POST, PUT/{id}, DELETE/{id} |
| `/admin/tops-cores` | GET (paginado), GET/{id}, PATCH/{id} (estado), DELETE/{id}, DELETE masivo |
| `/admin/colormap-stops` | GET resúmenes, GET/{name}, POST (una fila), DELETE/{name} (→ 403 si es del sistema) |
| `/admin/colormap-from-hex` | POST (crear desde array de stops + product_keys) → 409 si ya existe el nombre |
| `/admin/colormap-options` | GET (`?product_key`), POST, DELETE/{id} |

### 5.3 Modelos de Respuesta (Esquemas Clave)

**`RadarResponse`:** `code`, `title`, `description`, `center_lat`, `center_long`, `img_radio`, `is_active`, `detail_view_enabled`, `extent` (dict bbox)

**`COGResponse`:** `id`, `radar_code`, `product_key`, `product_id`, `observation_time`, `elevation_angle`, `file_path`, `file_name`, `data_min`, `data_max`, `bbox`, `tile_url`, `cog_data_type`, `cog_cmap`, `cog_vmin`, `cog_vmax`, `strategy`, `vol_nr`, `radar_coverage_m`

**`TopsAndCoresRecord`:** `id`, `radar_code`, `observation_time`, `file_name`, `feature_count`, `core_count`, `top_count`, `status`, `strategy`, `vol_nr`

---

## 6. Arquitectura del Frontend

### 6.1 v2 vs v1

| Aspecto | v1 (legacy, `js/v1/`) | v2 (producción, `js/v2/`) |
|--------|-----------------------|--------------------------|
| Capa de radar | `L.tileLayer` | `L.imageOverlay` |
| Endpoint | `/tiles/{id}/{z}/{x}/{y}.png` | `/frames/{id}/image.png` |
| Animación | opacity toggle con `setInterval` | `requestAnimationFrame` |
| Objetos DOM | ~180 TileLayers por sesión | 1 overlay por radar+producto |
| Peticiones HTTP | ~1800 por sesión | ~180 por sesión |
| Máscara de cobertura | Ninguna | Panel SVG (z-index 300) |
| Tops & Cores | Ninguno | Rellenos de polígono blob (z-index 440) + marcadores SVG de núcleos (z-index 450); pre-cargados al inicio |
| Página un radar | Ninguna | `radar.html` + `radar-app.js` |
| Panel de administración | Ninguno | SPA separada en `/admin` |

### 6.2 Invariantes de Diseño Clave

1. **Continuidad de la animación:** Todas las cargas de datos pasan por `_loadFramesWithContinuity()` — la animación nunca se detiene durante la carga. Nunca llamar a `animator.stop()`, `animator.reset()`, ni limpiar capas antes de tener los nuevos frames listos.

2. **UI en español:** Todo el texto visible al usuario está en español (es-AR). Los logs de depuración `console.*` se mantienen en inglés.

3. **Modo de cobertura:** `COVERAGE_MODES` en `constants.js` define qué valores de `vol_nr` corresponden a cada modo. El modo se persiste en `webmet25_coverage_mode`.

4. **Normalización del colormap vs filtro:** Los parámetros `filter_vmin`/`filter_vmax` del endpoint `/frames` aplican máscara alfa a los píxeles fuera del rango — NO cambian la normalización del colormap. La normalización del colormap siempre usa los valores predeterminados del producto.

5. **Mapa base:** El predeterminado es `argenmap` (IGN). Siempre usar `MapManager.setBasemap(key)`.

6. **Orden de radares:** `sortRadarsForDisplay` en `controls.js` — activos antes que inactivos; RMA antes que AR; ascendente numérico con RMA00 (número 0) al final.

### 6.3 Claves de localStorage (v2)

| Clave | Tipo | Predeterminado | Descripción |
|-----|------|---------|-------------|
| `webmet25_show_inactive_radars` | boolean | false | Mostrar radares inactivos |
| `webmet25_show_filtered_fields` | boolean | false | Mostrar campos filtrados (sin sufijo `o`) |
| `webmet25_live_refresh_interval_ms` | number | 300000 | Intervalo de refresco en vivo (ms) |
| `webmet25_radar_refresh_interval_min` | number | 10 | Refresco de estado de radar (min) |
| `webmet25_coverage_visible` | boolean | false | Toggle de máscara de cobertura |
| `webmet25_coverage_opacity` | number | 0.4 | Opacidad de máscara de cobertura |
| `webmet25_coverage_mode` | string | 'cd' | Id del modo de cobertura activo |
| `webmet25_tops_cores_visible` | boolean | false | Toggle de capa Tops & Cores |
| `webmet25_tops_cores_size` | number | 8 | Radio del marcador circular (px) |
| `webmet25_smooth_enabled` | boolean | false | Toggle de suavizado gaussiano |
| `webmet25_smooth_sigma` | number | 0.8 | Valor sigma gaussiano |
| `webmet25_selected_basemap` | string | 'argenmap' | Clave del mapa base activo |

### 6.4 Tamaños de Módulos

| Archivo | Líneas | Rol |
|------|-------|------|
| `v2/app.js` | 2526 | Orquestador del mapa multi-radar |
| `v2/radar-app.js` | 1662 | Página de detalle de un radar |
| `v2/map.js` | 1076 | MapManager + máscara de cobertura |
| `js/admin.js` | 1994 | SPA de administración |
| `v2/animation.js` | 429 | AnimationController |
| `shared/controls.js` | 602 | UIControls |
| `shared/tops-cores.js` | 255 | TopsCoresLayer |
| `shared/api.js` | 213 | Cliente REST |
| `shared/legend.js` | 217 | LegendRenderer |
| `v2/radar-utils.js` | 225 | Helpers compartidos |

---

## 7. Configuración de Nginx

`frontend/nginx.conf` (comportamientos clave):

- `GET /` → sirve `index.html` (fallback SPA mediante `try_files`)
- `GET /admin` y `GET /admin/*` → HTTP Basic Auth (`admin.htpasswd`), sirve `admin.html`
- `POST,GET /api/v1/admin/*` → Basic Auth + `proxy_pass http://api:8000`
- `GET /api/*` → `proxy_pass http://api:8000`, `proxy_buffering off` (soporte SSE/streaming)
- `GET /osm-tiles/*` → proxy a `tile.openstreetmap.org`, caché local de 30 días (zona máx. 1 GB)
- `GET /ign-tiles/*` → proxy a `wms.ign.gob.ar`, caché local de 7 días (misma zona)
- `GET /health` → responde 200 OK inline (sin necesidad de llamar a la API)
- gzip habilitado para text/css/json/js/xml

El proxy local de tiles permite que los tiles de los mapas base se cacheen en el servidor desde la primera petición, reduciendo la dependencia externa y la latencia.

**Versión del documento:** 2.0.0  
**Fecha:** 8 de julio de 2026
