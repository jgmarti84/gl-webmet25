# Storm tracking layer for webmet25 — integration plan

**Status:** Phases 1-2 **delivered and running on the host**; Phase 3 (sidecar) next
**Drafted:** 2026-10-15 — architecture confirmed 2026-10-19 — **updated 2026-10-20**
**Spans three repos:** `gl-radarlib` (producer), `gl-webmet25` (consumer), `gl-tracker` (tracking engine)

**Next action:** Phase 3 (§8) — the on-demand tracking sidecar.

### Delivered

| what | branch | state |
|---|---|---|
| radarlib writes NC cubes + retention | `gl-radarlib` `feat/nccube-cartesian-grids` | on host, RMA1 + RMA7 |
| webmet25 indexes them into `nccubes` | `gl-webmet25` `feat/nccube-indexer` | on host |

Neither branch is merged (2026-10-20). Phase 3 branches **from
`feat/nccube-indexer`**, since it needs the `NCCube` model.

### Confirmed on the host

- **The antenna altitude is genuinely per-radar.** RMA7 produced
  `umbral=4841` with `H0=3716`, so `alt = 3716 + 1500 - 4841 = 375 m` — not the
  `Config.radar_alt_m` fallback of 484. (The earlier RMA1 test was ambiguous:
  RMA1's real altitude *is* 484, identical to the fallback, so a missing
  attribute would have looked correct. RMA7 is what closed this.)
- **Echo top is quantised to the vertical grid.** `tope_max=4800` recurred
  exactly across volumes; 4800 = 8 x 600 = `GEOMETRY_RES_Z`. C2 decisions near
  the threshold are therefore limited by vertical grid resolution, not by
  `echotop_min_above_h0_m`. A storm "41 m short" is one grid level short.
- The gate correctly discards shallow echo. A real convective case has not yet
  been tracked end to end — worth having before the frontend exists, or an
  empty map is ambiguous between "no storms" and "broken".

### Two traps hit during rollout — both silent

- **`db-init` bypasses migrations.** It runs `manage init`, which does
  `create_all()` *and stamps head*. On a populated database that creates the
  table without ever running the migration. Run
  `manage migrate upgrade` explicitly **first**, with `--no-deps` so compose
  does not start `db-init`'s own command.
- **Images bake in code; they do not mount it.** `database/Dockerfile` does
  `COPY migrations/`, and `indexer/Dockerfile` copies both `indexer/indexer/`
  and `database/radar_db/`. A stale `db-init` image makes
  `migrate upgrade` report success and do nothing, because Alembic only sees
  the revisions baked into it. Always `docker compose build db-init` first and
  verify with
  `docker compose run --rm --no-deps db-init ls /app/migrations/versions/`.

### Confirmed decisions (2026-10-19)

| question | decision |
|---|---|
| Deployment | genpro25 and webmet25 **share a host**, exactly as they already do for GeoTIFFs. Everything belongs in `docker-compose.yml`; all paths must be configurable. |
| Product name | **NC cube** — `NCCUBE_*`, `nccube/`, `_NCCUBE.nc`, `nccubes` (§13.1) |
| Fields stored | **Configurable list**, default `["DBZH", "RHOHV"]` (§13.8) |
| Coupling to tops & cores | **None** — independent method and gate, costing 2.24 s/volume (§5) |
| Cube retention | **7 days** |
| Initial scope | **One radar** to start, so disk is not a concern yet |
| Concurrency of the tracking service | **Deferred.** Not a v1 concern; revisit if it becomes a problem (§8.3) |
| gl-tracker modifications | **Forbidden.** Consumed as a read-only library; the sidecar carries its own driver (§8.0) |
| Frontend scope | **New standalone page** for v1; single-radar only, never the multi-radar index (§9) |
| Operational precomputed tracking | **Rejected for now** — tracking is on demand only (§4.1) |
| Tracking output format | **In-memory GeoJSON per request. No SpatiaLite.** (§4.2) |

---

## 1. Goal

Expose gl-tracker's convective storm tracking in the webmet25 frontend.

The end state Javier described: a page where you pick a radar and a time range,
optionally show COLMAX underneath, and activate the tracking layer. The tracking
configuration (CAPPI altitude, dBZ threshold, minimum area, and the rest) should
eventually be tweakable from the frontend so different parameter choices can be
compared visually.

**v1 scope** (deliberately reduced): a new standalone page, similar in design to
the existing single-radar view, with a COLMAX on/off toggle and an "activate
tracking" button running the **default** configuration, with limited controls but
the config values in force displayed somewhere on screen.

---

## 2. Background: what each repo does

```
gl-radarlib (producer)
  BUFR --> CFRadial NetCDF --> [3D Cartesian grid, in memory] --> 2D COG products
                                                              \-> tops&cores GeoJSON
        |
        v  (files on disk)
gl-webmet25 (consumer)
  indexer watches dirs --> PostgreSQL/PostGIS metadata --> FastAPI --> Leaflet frontend

gl-tracker (tracking engine)
  Cartesian grid NetCDF --> gate --> detect --> classify --> track --> forecast
                        --> SpatiaLite systems-db.sqlite --> HTML map
```

The 3D Cartesian grid is the join point. gl-tracker consumes it; radarlib
already computes it and currently discards it.

---

## 3. Key findings that drive the design

These were established empirically on 2026-10-14/15. Re-measure if the hardware
or data shape changes.

### 3.1 The expensive stage already runs inside radarlib, and is thrown away

radarlib's ProductDaemon computes the full 3D Cartesian grid via
`apply_geometry()` and frees it after making the 2D products. It persists **no**
3D artifact. The docstring at `product_daemon.py:1260-1266` calls the recompute
"a deliberate documented trade-off to keep memory usage bounded" (the container
has a 3 GB limit).

Critically, the **tops & cores path already materialises DBZH-3D and RHOHV-3D
together on the same geometry** — which is exactly the pair gl-tracker needs.
Persisting them there costs one write, no extra compute.

### 3.2 Measured costs

Measured on the WSL2 dev box with `gl-tracker:dev`, RMA5 strategy 0315 vol01.

| step | cost | config-dependent? |
|---|---|---|
| geometry NPZ load (53.4 MB) | 2 s, once per process | no |
| CFRadial read (pyart) | 4 s | no |
| polar -> Cartesian interp | 6 s | no |
| write grid NetCDF | 1 s | no |
| **grid total, warm process** | **~11 s/volume** | **no** |
| gate + QC + detect + classify + track + forecast | **0.3–1.3 s/volume** | **yes — every tunable** |

Grid shape `(26, 472, 472)` float32 — 26 levels at 600 m, 472x472 at 1 km.
On-disk grid NetCDF: **15.4 MB** (zlib complevel 1). Source CFRadial: ~13 MB.

Two full tracking runs over 31 existing grids took **18 s** and **28 s** wall
(the difference is page cache). So a 4-hour window (~27 volumes at the ~9 min
cadence) is a **~20 s** computation.

### 3.3 The serving-side tracker needs neither radarlib nor pyart

Verified by running `operativo.py --una-vez --desde-cero` with
`PYTHONPATH=/workspace/gl-tracker:/workspace/gl-tracker/scripts` only —
radarlib absent. 31 volumes processed normally.

gl-tracker's only radarlib import is in `scripts/make_grid.py`. Once grids
arrive pre-made, the dependency set collapses to numpy, scipy, netCDF4,
osgeo/GDAL, rasterio.features, shapely, affine and TATHU (+ `mod_spatialite`,
rtree, scikit-image). The entire `arm-pyart`/`pyproj`/`xarray`/`matplotlib`
block in `gl-tracker/Dockerfile` exists only for gridding and can be dropped
from a serving image.

### 3.4 Which knobs live in which stage

All user-facing tunables are consumed **after** the grid NetCDF is read:
`ConvectiveFilterConfig` (`cappi_height_m`, `rhohv_qc_min`, `despeckle_min_px`,
the melting-layer band, `echotop_*`, `core_*`, `r_max_km`) is applied in
`grilla.leer()` via `fc.preparar_volumen()`, and `Config`'s detection/tracking
fields (`dbz_threshold`, `min_area_km2`, `strategy`, `overlap`,
`max_gap_tracking_min`, `forecast_intervals`) are used downstream in
`pipeline.py`.

The grid itself depends only on (volume, geometry). **Nothing a user can tweak
affects it.** This is what makes interactive parameter tuning viable: the 11
s/volume work is done once upstream, and every tweak costs only the ~0.35
s/volume analysis pass.

---

## 4. Architecture

Grid generation moves into radarlib's ProductDaemon; grids are indexed by
webmet25's existing indexer; the tracking computation runs on demand in a
separate service at serving time.

```
radarlib ProductDaemon
  (already computes DBZH-3D + RHOHV-3D for tops&cores)
  +--> NEW: write_nccube()  -->  grids/<RADAR>/YYYY/MM/DD/*_NCCUBE.nc
                                             |
  CleanupDaemon  <-- NEW retention category --+  (7 days)
                                             |
webmet25 indexer                             v
  NEW NCCubeWatcher --> PostgreSQL `nccubes` table
                                             |
                                             v
NEW tracking service (gl-tracker, slimmed)   |
  reads grid paths from PG, files from shared RO mount
  runs gate/detect/track on demand  -->  GeoJSON
                                             |
                                             v
NEW frontend page (tracking.html)
  COLMAX toggle (existing COG tiles) + tracking layer
```

**Why the tracking service is separate from the webmet25 API:** TATHU +
`mod_spatialite` + rtree + scikit-image is a heavy stack to add to an image
whose job is serving tiles, and the ~20 s computation is CPU-bound and would
starve the tile render pool (`tile_render_threads`, default 8).

### 4.1 Rejected alternatives — do not re-litigate

Three other placements were analysed on 2026-10-19 and rejected. Recorded here
so a later session does not rediscover them.

**Running the tracker inside radarlib's ProductDaemon, emitting GeoJSON as an
operational product (like tops & cores).** Rejected for three reasons:

1. *Statefulness.* The tracker's memory between volumes is
   `estado_tracking.pkl` (`Estado`: `ultimo_timestamp`, `previous`,
   `historia`). ProductDaemon is stateless per volume and would have to own,
   persist and restart-proof that file per radar.
2. *Out-of-order volumes silently corrupt tracking.* radarlib's live-first
   download deliberately interleaves backfill with current data. If a
   backfilled older volume reaches the tracker after a newer one, `hueco_min`
   in `pipeline.py` goes **negative**, so the `> max_gap_tracking_min` reset
   never fires, `previous` is retained, the match test
   `(s.timestamp - s.relationships[0].timestamp) > 0` fails for everything, and
   `est.ultimo_timestamp` is rolled *backwards*. No error, no log — just a
   quietly broken track history.
3. *Image weight.* radarlib would gain TATHU (GitHub install, not PyPI), rtree
   + libspatialindex, shapely + libgeos, scikit-image, opencv-python-headless,
   rasterstats and pathos — in a container held to a 3 GB memory budget, and
   against a standing constraint not to modify its Dockerfile.

On-demand tracking eliminates (1) and (2) rather than solving them: each
request builds `Estado()` from scratch and walks its window chronologically, so
there is no persistent state to corrupt and nothing for backfill to disturb.

**Writing to PostGIS directly from radarlib via `tathu.io.pgis.Outputter`.**
Rejected: it would put webmet25's database credentials inside the radar daemon,
invert the producer -> consumer direction the whole architecture rests on, and
create a table in TATHU's schema rather than webmet25's house style.

**Loading tracked systems as feature-level PostGIS rows.** Deferred, not
rejected on merit. It is the only way to answer "the full history of track X",
"every system within 50 km last month", or "all splits this year" — none of
which are answerable by fetching GeoJSON frame by frame. The data is tiny
(§4.2) so it is affordable. But it is purely additive: the sidecar can later
run as a daemon writing the same GeoJSON that an indexer loads. **Do not build
it now.**

### 4.2 The SpatiaLite output is bypassed entirely

The tracking service returns GeoJSON built in memory. No `systems-db.sqlite` is
ever written. This is safe and cheap:

- **The database is a pure sink.** The tracker never reads it back. Writes
  happen only in `pipeline.py:62-64` (`Salidas` constructing
  `spatialite.Outputter`), and the only reader anywhere is `export_map.py`, the
  standalone HTML renderer that webmet25 replaces. All inter-volume memory
  lives in `estado_tracking.pkl`.
- **`Outputter` is a one-method interface** — `output(systems)`, called once per
  volume per table. Swapping the sink is not an algorithmic change.
- **TATHU already ships alternatives** in `tathu.io`: `vector` (OGR, so GeoJSON
  / GPKG / shapefile), `pgis`, `dataframe`, `icsv`. `vector.Outputter`
  implements the same contract.

Measured on a representative run: **163 KB of real payload inside a 6.99 MB
file** — 99 systems (107 KB geometry, 27 KB raster) plus 21 forecast rows, with
6,559 rows of `spatial_ref_sys` and SpatiaLite metadata accounting for 97.7% of
the file. Per volume the genuine payload is ~4-5 KB. You would never want to
write that file per HTTP request.

#### Fields that must survive the swap

| group | fields | keep? |
|---|---|---|
| identity | `name` (UUID), `date_time`, `event`, `relationships` | **yes — critical** |
| geometry | `geom` POLYGON, EPSG:4326 | yes |
| `STAT_ATTRS` | min, max, mean, std, median, count | yes |
| `MOVEMENT_ATTRS` | nae, velocity, u, v, direction | yes |
| `CONV_ATTRS` | is_convective, c1_core, c2_vertical, c3_polarimetric, in_domain, core_area_km2, core_max_dbz, core_rhohv_mean, echo_top_max_m, dist_centroid_km, h0_msnm | yes |
| raster clip | `raster`, `nodata`, `geotransform` | **drop** — per-system crops, no web use |

Two identity details are what make this a *tracking* product rather than a
per-frame detection product:

- **`name` is the track ID.** `ConvectiveSystem.__init__` assigns
  `uuid.uuid4()`, and on a successful match the current system **inherits the
  previous system's name** (`tathu/tracking/trackers.py:213`). Systems sharing a
  `name` across volumes are one storm.
- **`event` + `relationships` are the lineage graph.** `event` is a
  `LifeCycleEvent` (`SPONTANEOUS_GENERATION`, `NATURAL_DISSIPATION`,
  `CONTINUITY`, `SPLIT`, `MERGE`, `INTERPOLATION`); `relationships` holds the
  parent systems' names. Splits and merges are unreconstructable without both.

#### Volumes the gate discards must still be represented

The gate rejects **entire volumes**. `ResultadoGate` carries `tope_max_m`,
`umbral_m`, `n_pixeles_pasan`, `h0_msnm` and `h0_fuente` precisely so it can be
explained later why a storm never appeared (`gate.py:128-131`). The response
must therefore distinguish "filtered out" from "no data": emit an empty feature
list for that timestamp carrying `gate_passed: false` and the diagnostic
numbers, rather than omitting the timestamp.

---

## 5. Phase 1 — radarlib persists the NC cube

### Hook point — an independent sibling method

**Decided 2026-10-19: grid production is fully decoupled from tops & cores.**

A new method `_generate_nccube()` in
`gl-radarlib/src/radarlib/daemons/product_daemon.py`, a **sibling** of
`_generate_tops_and_cores` (defined at line 1249), called from its own gate
immediately after the tops & cores block ends at line 896:

```python
if self.config.add_nccubes and volume_info.get("vol_nr") == self.config.nccubes_vol_nr:
    self._generate_nccube(
        radar=radar, geom=geom, volume_info=volume_info,
        hrefl_field=hrefl_field, rhv_field=rhv_field, obs_dt=obs_dt,
    )
```

Everything needed is already in scope there — that is the argument list the
tops & cores call uses at 887-896, minus `sweep` and `filename_stem`.

The method computes its own 3D arrays via `apply_geometry`, exactly as
`_generate_tops_and_cores` does at lines 1297 and 1311.

#### Why independent, when sharing the arrays would be free

Measured on the dev box, RMA5 strategy 0315 vol01, grid `(26, 472, 472)`:

| call | cost | array |
|---|---|---|
| `apply_geometry` DBZH | 1.30 s | 23.2 MB float32 |
| `apply_geometry` RHOHV | 0.94 s | 23.2 MB float32 |
| **total cost of decoupling** | **2.24 s per volume** | 46 MB transient |

Against a ~9 minute volume cycle that is **0.4% of the duty cycle**, and the
memory is freed immediately against a 3 GB container budget.

Three reasons it is worth paying:

1. **radarlib already pays exactly this cost, deliberately.**
   `product_daemon.py:1260-1266` documents that the tops & cores 3D grids are
   "recomputed here from scratch — this is a deliberate documented trade-off to
   keep memory usage bounded", and the field loop computes and frees the same
   arrays again. A third independent recompute follows the established house
   pattern rather than inventing a new compromise.
2. **The coupling fails silently.** Sharing the hook means disabling
   `ADD_TOPS_AND_CORES` for a radar also stops grid production, with nothing
   saying why.
3. **It forces a shared `vol_nr`.** Decoupled, grids get their own
   `NCCUBE_VOL_NR` and can diverge later if needed.

### The writer already exists and was designed for this

`gl-tracker/scripts/grid_writer.py` — `write_cartesian_netcdf()`, which ports
to `src/radarlib/io/nccube_writer.py` as `write_nccube()`. Its module docstring
states it is:

> Deliberately standalone — numpy and netCDF4 only, no radarlib import — so the
> same writer can be called from this repo's scripts and, later, from radarlib's
> ProductGenerationDaemon without creating a dependency cycle.

Its input contract matches the hook point exactly: `(nz, ny, nx)` float32, NaN
= no data, **row 0 = south on input** (it performs the south->north flip
internally). Move or copy it into radarlib unchanged.

Do **not** also flip in radarlib — flipping in both places silently mirrors the
grid north-south.

### Array facts at the hook point

- dtype `float32`, shape `(nz, ny, nx)` = `geom.grid_shape`
- plain `np.ndarray`, **not** masked; no-data is `np.nan`
- **row 0 = southernmost** (`grid_limits[1] = (y_min, y_max)`, `y_min < y_max`,
  coords via `np.linspace`). The COG writer flips for rasterio at
  `radar_grid/geotiff.py:728-729`; the NetCDF writer flips too.
- `geom.z_levels()` is metres **above the radar**, `z_min=0`, `z_max=toa`

### Three traps

1. **`geom.radar_altitude` is `0`.** Daemon-built geometries pass
   `radar_altitude=0` (`product_daemon.py:345`), so `z_levels_absolute()` equals
   `z_levels()`. Take the true antenna altitude from
   `radar.altitude["data"][0]` instead. Writing `radar_alt_m=0` makes
   `gate.h0_para_grilla()` run the C2 criterion with an ~800 m error against a
   1500 m margin — **with no visible symptom**. This is precisely the failure
   `grid_writer.py`'s docstring warns about.
2. **`_ct_rhohv_3d` can be `None`** when the volume lacks RhoHV (else-branch at
   1317-1322). Skip the write — `grilla.leer()` rejects RHOHV-less volumes
   anyway.
3. **Never re-raise, and write atomically.** Follow `field_processor.py:324-339`
   (tempfile + move) and the existing swallow-all `except` at 1355-1359.

### Scope

Gated on its own `NCCUBE_VOL_NR`, set to `"01"` — vol01 is the volume
carrying both DBZH and RHOHV under strategy 0315. vol02 (VRAD/WRAD) and vol04
(DBZH only) have no useful grid to write.

The method must additionally **skip unless both fields are present**
(`hrefl_field in radar.fields and rhv_field in radar.fields`). A grid without
RHOHV is useless downstream — `grilla.leer()` rejects it outright — so writing
nothing beats writing something half-valid.

### Dependencies — no Dockerfile change needed

`netCDF4 ^1.7.0` and `xarray` are already main dependencies
(`gl-radarlib/pyproject.toml:19-20`), installed by `app/Dockerfile`'s
`pip install -e .`. `netCDF4` is not yet imported directly anywhere in `src/`.
Use a function-local import, matching the existing style in
`_generate_tops_and_cores` (its imports are all local, lines 1281-1286).
Prefer raw `netCDF4` over `xarray` to keep the hot path light.

### Output path convention

```
{ROOT_NCCUBE_PATH}/{RADAR}/YYYY/MM/DD/{RADAR}_{strategy}_{vol_nr}_{YYYYMMDDTHHMMSSZ}_NCCUBE.nc
```

Mirrors the tops & cores builder at
`src/radarlib/io/pyart/cores_and_tops.py:450-458` and the COG builder at
`src/radarlib/utils/names_utils.py:309-321`.

### docker-compose

Add to **every** per-radar service block (template: `genpro25-rma1`,
`gl-radarlib/docker-compose.yml:56-76`):

```yaml
    volumes:
      - ../nccube/RMA1:/workspace/app/nccube/RMA1
    environment:
      ROOT_NCCUBE_PATH: "/workspace/app/nccube"
```

Host paths are siblings of the repo (`../`). **The host directory must
pre-exist** or Docker creates it root-owned — the same problem hit while
developing gl-tracker's pipeline.

---

## 6. Phase 2 — retention

**Target: `NCCUBE_RETENTION_DAYS: 7.0`** (confirmed 2026-10-19).

Important: `CleanupDaemon` is **database-driven, not directory-driven**. It
queries SQLite (`get_bufr_files_for_cleanup` /
`get_netcdf_files_for_cleanup` in `src/radarlib/state/sqlite_tracker.py:1476`
and `:1571`) and deletes the single path recorded on each row. Grids will have
no such rows.

So this needs a genuinely **new** `_cleanup_nccube_files()` that walks
`{nccube_dir}/YYYY/MM/DD/`, unlinks files past the cutoff and prunes empty day
dirs — not a copy of `_cleanup_netcdf_files`. (The COG and tops & cores output
trees are not pruned by anything today, so there is no existing example.)

Config plumbing, 5 touch points:

1. `gl-radarlib/app/config.py` `_DEFAULTS` — add `"NCCUBE_RETENTION_DAYS": 7.0`
   and `"ROOT_NCCUBE_PATH": "nccube"` (near lines 54-58). A key absent from
   `_DEFAULTS` is dropped during YAML flattening and gets no type coercion.
2. `gl-radarlib/genpro25.yml` under `DAEMON_PARAMS:` — add
   `NCCUBE_RETENTION_DAYS:` near line 38. Fractional days work
   (`timedelta(days=...)` accepts floats; the existing NetCDF/BUFR retention is
   `0.0833` = 2 h).
3. `gl-radarlib/app/main.py` — forward into `DaemonManagerConfig` (near lines
   118-122).
4. `gl-radarlib/src/radarlib/daemons/manager.py` — dataclass fields (near
   85-87), forward in `_create_cleanup_daemon()` (215-225) and
   `_create_product_daemon()` (192-213).
5. `gl-radarlib/src/radarlib/daemons/cleanup_daemon.py` — config fields (42-51),
   the new coroutine, calls in `_run_cleanup_cycle()` (159-191) and
   `run_once()` (303-330), stats keys in `__init__` (94-101).

Poll interval is `CLEANUP_POLL_INTERVAL: 1800` (30 min), `cleanup_daemon.py:44`.

### Disk budget

```
15.4 MB/volume x ~160 volumes/day = ~2.5 GB per radar per day   (2 fields)
1 radar,  7-day retention          = ~17 GB standing   <-- initial scope
10 radars, 7-day retention         = ~175 GB standing  <-- if rolled out fleet-wide
```

Those figures assume the default two fields. The cube carries a configurable
field list (§13.8) and size scales at **~7.7 MB per field**, so enabling all
five of vol01 roughly triples it (~43 GB for one radar over 7 days).

Starting with **one radar** (confirmed 2026-10-19), so ~17 GB — not a concern.
Before any fleet-wide rollout, revisit. The levers, cheapest first:

- **only write grids for radars with `detail_view_enabled`** — that column
  already exists on `radars` (migration `d4e5f6a7b8c9`) and is the most natural
  gate
- a shorter retention for radars that are not actively being studied
- store scaled `int16` instead of `float32` (roughly halves it)
- raise zlib `complevel` above 1 in `grid_writer.py` (costs CPU in the product
  hot path)

Note the tension that set this number: the storms worth studying are usually
past events, so a retention that is too short undercuts the feature's main use.
Seven days is the compromise.

---

## 7. Phase 3 — webmet25 indexes the NC cubes

Follow the TopsAndCores pattern throughout; it is the most recent and closest
analogue.

### 7.1 Model

`gl-webmet25/database/radar_db/models.py` — add `NCCube(Base)` after
`TopsAndCores` (which ends ~line 345).

- Reuse the existing `COGStatus` enum (`models.py:17-24`) — do **not** define a
  second one. PG type name is `cogstatus`, labels are uppercase member names.
- There is **no timestamp mixin**; `created_at` / `updated_at` are repeated by
  hand on every model. Copy the pattern.
- Columns, mirroring `TopsAndCores` (`models.py:304-345`): `id`, `radar_code`
  (String(16), FK `radars.code` ON DELETE CASCADE, NOT NULL, indexed),
  `observation_time` (DateTime(tz), NOT NULL, indexed), `file_path`
  (String(512), NOT NULL, unique), `file_name` (String(256), NOT NULL),
  `file_size_bytes`, `file_mtime`, `status` (SQLEnum(COGStatus), default
  AVAILABLE, indexed), `strategy` (String(32)), `vol_nr` (String(16)),
  `created_at`, `updated_at`.
- Optionally `bbox = Column(Geometry('POLYGON', srid=4326))` + GiST index, as
  `RadarCOG` has (`models.py:262`, `:290`). `TopsAndCores` has no geometry
  column. Only worth it if spatial queries are wanted; see the open question in
  §10.
- Add the back-reference on `Radar`, parallel to `models.py:58`.
- Export from `database/radar_db/__init__.py` in both the import list and
  `__all__` — that is how `from radar_db import ...` works for the API.

### 7.2 Migration

Alembic rooted at `gl-webmet25/database/`, versions in
`database/migrations/versions/`. Chain is linear; **current head is
`d4e5f6a7b8c9`** (`20260702_..._add_detail_view_enabled_to_radars`), so
`down_revision = "d4e5f6a7b8c9"`.

Use `20260505_3a7f2c91d4e8_add_tops_and_cores_table.py` as the template.
Critical detail from it:

```python
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
...
PgEnum('PENDING','AVAILABLE','PROCESSING','ERROR','ARCHIVED','MISSING',
       name='cogstatus', create_type=False)
```

`sa.Enum(..., create_type=False)` does **not** reliably suppress `CREATE TYPE`
and the migration fails with "type already exists". This is documented in
`.claude/skills/add-db-migration/SKILL.md`.

Commands:

```bash
python -m radar_db.manage migrate generate -m "add nccubes table"
python -m radar_db.manage migrate upgrade head
python -m radar_db.manage check
```

### 7.3 Parser / registrar / watcher

- `indexer/indexer/parser.py` — add `ParsedNCCubeInfo` dataclass +
  `NCCubeFilenameParser`. Regex matching `_PATTERN_NEW`'s token layout
  (`parser.py:59-66`):
  `^(?P<radar>[A-Z0-9]+)_(?P<strategy>\d{4})_(?P<vol_nr>\d{2})_(?P<datetime>\d{8}T\d{6}Z)_NCCUBE\.nc$`
  Raise `ValueError` on no match (TopsAndCores convention, `parser.py:316-320`).
  Use the overflow-tolerant datetime idiom (`parser.py:118-131`): build midnight
  then add a `timedelta`, so values like `T236000Z` do not explode.
- `indexer/indexer/registrar.py` — add `NCCubeRegistrar` at the end. Do
  not modify the `COG*` classes.
- `indexer/indexer/watcher.py` — add `NCCubeWatcher`, cloned from
  `TopsAndCoresWatcher` (`watcher.py:224-354`): `discover_files()` /
  `run_scan()` / `run_forever()`, missing-root tolerance with a one-time
  warning, in-process `_registered_files` set.
- `indexer/indexer/main.py:56-65` — start a third daemon thread. That block is
  the template.
- `indexer/indexer/config.py` — add a proper
  `nccube_dir: str = Field(default="/nccubes", alias="NCCUBE_DIR")`
  field. (Note `TOPS_AND_CORES_DIR` is read ad-hoc with `os.getenv` in
  `main.py:49` rather than via settings — an inconsistency worth not repeating.)
- `docker-compose.yml` — env var + volume on `indexer` (rw) and `api` (ro),
  matching lines 90/92-93 and 128.

### 7.4 Index from filename + stat() only — do not open the file

The indexer runs on **`python:3.11-alpine`** (`indexer/Dockerfile:2`) with no
netCDF library — `requirements.txt` has only sqlalchemy, alembic, psycopg2,
geoalchemy2, rasterio, shapely, pydantic. Adding `netCDF4` there means fighting
Alpine wheels for no benefit: radar, strategy, volume and timestamp are all in
the filename, and size/mtime come from `stat()`.

(This is the one place the grid watcher should *not* copy TopsAndCores, which
does `json.load` to count features.)

### 7.5 Deletion, not MISSING

The COG watcher marks vanished files `MISSING` in cursor-chunked batches every
cycle (`registrar.py:294-331`); TopsAndCores does a throttled full query every
20th cycle (`watcher.py:305-318`). **Nothing in webmet25 ever deletes rows
automatically** — `ProductDeleter` is a manual CLI and only handles COGs, and
`MISSING_CHECK_DAYS` (default 45) is only a query-bounding window, not
retention.

With 1-day grid retention the table would accumulate dead rows indefinitely.
Grids are ephemeral by design, so the grid watcher should **hard-delete** rows
for vanished files, and its missing-check window should be just over the
retention period (e.g. 2 days), not 45.

### 7.6 Why this phase matters for the UX

The frontend's "how far back can I go" becomes simply `min(observation_time)`
over AVAILABLE `nccubes` rows. That is what lets the UI be honest about
its own limits instead of offering ranges with no data behind them.

---

## 8. Phase 4 — tracking service

A separate container (slimmed `gl-tracker` image), proxied by nginx at
`/api/tracking/*`, reading grid paths from PostgreSQL and grid files from a
shared read-only mount.

```
nginx
  /api/v1/*        -> webmet25 API   (unchanged)
  /api/tracking/*  -> tracking service (new)
```

### 8.0 Hard constraint: gl-tracker is read-only

**Decided 2026-10-20. `gl-tracker` must not be modified.** It is consumed as a
library — eventually installed from GitLab, for now vendored into the image.
Everything the sidecar needs is therefore built *around* gl-tracker, not inside
it. In particular `operativo.py` is **not** refactored and **not** used; the
sidecar carries its own equivalent driver.

This turns out to cost almost nothing, because of one fact:

**`procesar()` only ever touches two things on its `salidas` argument** —
`salidas.systems.output(list)` (`pipeline.py:325`) and
`salidas.forecasts[lead].output(list)` (`pipeline.py:321`). Nothing else. So the
sidecar passes a **duck-typed collector** with that shape and gets results in
memory, with no SpatiaLite file and no change to gl-tracker:

```python
class _Collector:
    def __init__(self): self.rows = []
    def output(self, systems): self.rows.extend(systems)

class GeoJSONSink:                      # stands in for pipeline.Salidas
    def __init__(self, intervals):
        self.systems = _Collector()
        self.forecasts = {t: _Collector() for t in intervals}
```

`pipeline.Salidas` is never constructed, so `cfg.out_dir.mkdir()` and the
SpatiaLite outputters never happen.

#### The driver the sidecar owns

A ~40-line equivalent of `operativo.py`'s loop, living in the sidecar:

```python
cfg   = build_config(request)              # Config() + validated overrides
serie = gate.serie_h0_actual(cfg, cfg.h0_lat, cfg.h0_lon)   # None -> climatology
est   = estado_mod.Estado()                # fresh per request = --desde-cero
sink  = GeoJSONSink(cfg.forecast_intervals)

for ts, path in volumes:                   # explicit list, from Postgres
    result = pipeline.procesar(path, ts, cfg, serie, est, sink)
```

`procesar()` takes an explicit path and mutates `est`, so chronological order
across the window is the driver's responsibility — and because the list comes
from a `nccubes` query ordered by `observation_time`, the directory-glob problem
(`grilla.listar()` is non-recursive, §8.2) never arises.

#### Packaging reality

`gl-tracker` has **no `setup.py` / `pyproject.toml` / `setup.cfg`**, and its
modules are flat top-level names: `config`, `estado`, `filtro_convectivo`,
`gate`, `grilla`, `h0_wrf`, `pipeline`. Two consequences:

1. **`pip install git+...` will not work today.** It needs packaging metadata,
   which means changing gl-tracker. Until then: clone/COPY into the image and
   put its directory on `PYTHONPATH`, as the dev container already does.
2. **Namespace collision is a real hazard.** `import config` inside
   `pipeline.py` resolves against the whole `sys.path`. If the sidecar defines
   a top-level `config.py`, which module wins depends on path order. **All
   sidecar code must live inside a package** (e.g. `tracking_api/`), so its
   modules are `tracking_api.config` and can never shadow gl-tracker's.
   Reserved names to avoid at top level: `config`, `estado`,
   `filtro_convectivo`, `gate`, `grilla`, `h0_wrf`, `pipeline`, `operativo`.

### 8.1 What the sidecar builds

1. **Validated config per request.** `Config` is a dataclass with a
   `filter_overrides: dict` field designed for exactly this (its docstring:
   "cuando el filtro descarta un volumen entero hay que poder reconstruir
   despues con que numeros lo descarto"). Whitelist the exposed fields — never
   let a web client set arbitrary attributes.
2. **Volume resolution from Postgres** — query `nccubes` by radar and window,
   ordered by `observation_time`, returning file paths read from the shared
   read-only mount.
3. **Systems/forecasts -> GeoJSON.** `scripts/export_map.py`'s `load_systems()`
   / `load_forecasts()` document the attribute-to-GeoJSON mapping; the sidecar
   reimplements it against live `ConvectiveSystem` objects instead of DB rows.
   Preserve `name` (track id), `event` and `relationships` — see §4.2.
4. **Stateless per request.** A fresh `Estado()` each time, which is what
   removes the corruption risks in §4.1.
5. **A slimmed image.** `arm-pyart`, `pyproj`, `pandas`, `pytz`, `cachetools`,
   `xarray`, `psutil` and `matplotlib` exist in `gl-tracker/Dockerfile` only for
   the gridding step, which radarlib now does. Build the sidecar image from that
   Dockerfile's remaining stack rather than editing it in place.

### Known limitation: H0 falls back to climatology

`gate.resolver_h0()` returns `(value, source)` and degrades to
`h0_climatologico()` when no usable WRF run is present. Without wrfout access
the tracking service will run every volume on climatology — about **750 m** off
the model value at RMA1, against C2's 1500 m margin.

This is a deliberate design (the alternative, passing `None`, silently disabled
the filter entirely and let every object pass), and `h0_fuente` is recorded per
system so runs stay auditable. Worth surfacing in the UI; worth revisiting if
wrfout can be mounted.

### Caching — build it in from the start

Key results on `(radar, window, config-hash)`. The default config will be the
overwhelmingly common request, so even a small cache makes the common path feel
instant while genuine config tweaks stay honest. This is the mitigation for
having no precomputed operational layer (§4.1).

The single-frame detection preview (§9) is sub-second and needs no cache.

### 8.2 The non-recursive glob, and why the sidecar sidesteps it

`grilla.listar()` uses `cfg.grilla_raiz.glob(cfg.grilla_glob)` with
`grilla_glob = "*.nc"` — **non-recursive** (`gl-tracker/grilla.py:93`). Cubes
live in `{RADAR}/YYYY/MM/DD/`, so a flat glob finds nothing. This bit during
host testing and currently requires pointing `GRIDS_DIR` at a single day
directory to use `pipeline.sh track` manually.

The sidecar never calls `listar()` — it passes explicit paths from Postgres
straight to `procesar()`. So this needs no fix for Phase 3. It remains a
papercut for manual testing only, and fixing it would mean changing gl-tracker
(`grilla_glob = "**/*.nc"`), which §8.0 forbids for now.

### 8.3 Concurrency — deferred, by decision

Explicitly **out of scope for v1** (confirmed 2026-10-19). Recorded so it is not
forgotten:

- on-demand means N users x a CPU-bound ~20 s job, with no limit today
- each request reads ~27 x 15 MB of grid files — fine warm, slower cold
- when it becomes a problem, the fix is a small worker pool (1-2) with a queue,
  not an unbounded thread pool

Until then, the cache above is the main thing keeping load down.

---

## 9. Phase 5 — the frontend page

A **new standalone page** (`frontend/public/tracking.html`), styled after
`radar.html` — not a modification of the existing single-radar view.
Confirmed 2026-10-20.

### Why tracking is single-radar, not a v1 simplification

Tracking belongs to the one-radar view and will never appear on the multi-radar
index. That is a property of the data, not a scoping choice:

- Every cube is gridded through **one radar's geometry**, with that radar's
  antenna as the grid origin. There is no mosaic.
- The gate and the convective filter are **radar-relative**: `r_max_km`,
  `dist_centroid_km` and the echo-top reference are all measured from that
  antenna.
- A storm sitting in the overlap between two radars is tracked **twice**, as two
  independent tracks with different `name` UUIDs. Rendering both radars at once
  would duplicate it on screen, with two separate forecast fans.

Unifying tracks across radars would require mosaicking the volumes before
detection — a different project.

### Build the layer as a module, not as page code

v1 is a standalone page, but the intent is to fold tracking into `radar.html`
as a toggleable layer later. That migration is cheap **only if the layer is
written as a self-contained module from the start** — `js/shared/tracking.js`
owning fetch, render and frame-sync, with `tracking.html` acting as a thin host
that wires it up. `js/shared/tops-cores.js` is exactly this shape already and is
the model to follow.

Written as page-scoped code instead, folding it into `radar.html` means a
rewrite rather than a few lines of wiring.

Contents:

- radar selector + time window, bounded by the oldest available grid
- COLMAX on/off toggle
- "activate tracking" button
- a read-only panel showing the config values in force

**COLMAX costs no backend work.** radarlib already produces it
(`ADD_COLMAX: True`, `genpro25.yml:136`), so it is an ordinary indexed COG
served by the existing frames/tiles API.

**The tracking layer is closely modelled on
`frontend/public/js/shared/tops-cores.js`** (324 lines), which already fetches
GeoJSON per observation time, renders it on Leaflet and syncs it to the
animation frame. The frame-sync problem is already solved there.

What to render from the tracker output: system polygons (styled by convective
verdict), forecast polygons at the 9/18/.../63 min lead times, centroid
trajectories, and attribute popups (max dBZ, area, echo top, velocity,
direction, c1/c2/c3). Skip the `raster` column — it holds a per-system raster
clip not useful on the web.

### Later: interactive config tuning

Once v1 works, the tweakable-config goal needs two feedback tiers, because the
full pass over a window is ~20 s:

- **detection-only preview on the current frame** — sub-second, no tracking, no
  sequence needed. Responds live to slider drags. Shows polygons + convective
  verdict for the frame on screen.
- **full tracking over the window** — ~20 s, fills in track IDs, velocity and
  forecasts behind the preview.

Note the tracking pass is inherently **sequential and stateful**
(`est.previous`, `est.historia`, `est.ultimo_timestamp`, and
`max_gap_tracking_min` resetting trajectories), so it cannot be computed for one
frame in isolation or parallelised across frames. The detection preview can,
because it does not track.

---

## 10. Decisions

### Settled 2026-10-19

| # | question | decision |
|---|---|---|
| 1 | Deployment topology | genpro25 and webmet25 **share a host**, as they already do for GeoTIFFs. All of it in `docker-compose.yml`, all paths configurable. |
| 2 | Disk budget / retention | **7 days**, **one radar** initially (~17 GB). Revisit before fleet-wide rollout. (§6) |
| 3 | Concurrency | **Deferred.** (§8.3) |
| 4 | Tracking output | **In-memory GeoJSON per request, no SpatiaLite.** (§4.2) |
| 5 | Operational precomputed tracking | **Not now.** On demand only. (§4.1) |

### Still open

1. **Grid rows: hard-delete or MISSING?** Recommendation is hard-delete, since
   grids are ephemeral and nothing in webmet25 prunes automatically. (§7.5)
2. **`bbox` geometry column on `nccubes`?** Only if spatial queries are
   wanted. `TopsAndCores` does without one. Computing it requires the grid
   extent, which is *not* available from the filename — it would force the
   indexer to open the NetCDF, which §7.4 deliberately avoids. Recommendation:
   omit, or derive from the radar's known coverage instead.
3. **Does the tracking service have wrfout access** in its deployment, or does
   it run on climatology permanently? (§8)
4. **Which radar is first?** Determines the geometry file and the compose block
   to add in Phase 1.

---

## 11. Reference: file/line index

### gl-radarlib

| what | where |
|---|---|
| hook point for grid persistence | `src/radarlib/daemons/product_daemon.py:1349` |
| `_generate_tops_and_cores` def | `product_daemon.py:1249` |
| DBZH-3D / RHOHV-3D creation | `product_daemon.py:1297` / `:1311` |
| `finally` that frees them | `product_daemon.py:1360-1364` |
| gate (vol01 + flag) | `product_daemon.py:886` |
| `geom` lookup | `product_daemon.py:815` |
| `apply_geometry` | `src/radarlib/radar_grid/interpolate.py:24-122` |
| geometry NPZ save/load | `src/radarlib/radar_grid/geometry.py:235` / `:252` |
| COG writer's south->north flip | `src/radarlib/radar_grid/geotiff.py:728-729` |
| tops&cores path builder | `src/radarlib/io/pyart/cores_and_tops.py:450-458` |
| COG path builder | `src/radarlib/utils/names_utils.py:309-321` |
| CleanupDaemon | `src/radarlib/daemons/cleanup_daemon.py` (poll default `:44`) |
| cleanup SQL | `src/radarlib/state/sqlite_tracker.py:1476`, `:1571` |
| config defaults | `app/config.py` `_DEFAULTS` (~48-65) |
| daemon config assembly | `app/main.py:97-124` |
| daemon manager | `src/radarlib/daemons/manager.py:85-87`, `:192-213`, `:215-225` |
| retention / flags | `genpro25.yml:33-34`, `:38-39`, `:136` |
| per-radar compose block | `docker-compose.yml:56-76` |
| deps (netCDF4 present) | `pyproject.toml:14-20` |

### gl-webmet25

| what | where |
|---|---|
| indexer entrypoint / thread wiring | `indexer/indexer/main.py:39-69`, template at `:56-65` |
| `TopsAndCoresWatcher` | `indexer/indexer/watcher.py:224-354` |
| `COGWatcher` | `indexer/indexer/watcher.py:26-221` |
| parsers | `indexer/indexer/parser.py:59-66`, `:281-330` |
| registrars | `indexer/indexer/registrar.py` (TopsAndCores `:352-367`, `:458-483`) |
| indexer settings | `indexer/indexer/config.py` |
| indexer base image | `indexer/Dockerfile:2` (`python:3.11-alpine`) |
| models | `database/radar_db/models.py` (`COGStatus` `:17-24`, `RadarCOG` `:209-301`, `TopsAndCores` `:304-345`) |
| exports | `database/radar_db/__init__.py:1-22` |
| migration head | `d4e5f6a7b8c9` in `database/migrations/versions/` |
| migration template | `database/migrations/versions/20260505_3a7f2c91d4e8_add_tops_and_cores_table.py` |
| API router registration | `api/app/routers/` + `api/app/main.py:159-166` |
| tops&cores router (GeoJSON serving precedent) | `api/app/routers/tops_cores.py` |
| frontend GeoJSON layer precedent | `frontend/public/js/shared/tops-cores.js` |
| single-radar page | `frontend/public/radar.html`, `frontend/public/js/v2/radar-app.js` |
| compose (indexer/api mounts) | `docker-compose.yml:73-100`, `:105-148` |

### gl-tracker

| what | where |
|---|---|
| the NetCDF writer to move into radarlib | `scripts/grid_writer.py` |
| grid reader + QC/detection-field stage | `grilla.py` (`leer()` at `:205`) |
| per-volume tracking pipeline | `pipeline.py` (`procesar()`) |
| batch entry point (needs refactor) | `operativo.py` |
| all tunables | `config.py` (`Config`), `filtro_convectivo.py` (`ConvectiveFilterConfig:47`) |
| H0 resolution + climatology fallback | `gate.py:76` (`resolver_h0`), `:101` (`h0_para_grilla`) |
| SpatiaLite -> GeoJSON extraction | `scripts/export_map.py` (`load_systems`, `load_forecasts`) |
| gridding step (becomes obsolete for serving) | `scripts/make_grid.py` |
| dev image | `Dockerfile` |

---

## 12. Suggested sequencing

Phases 1-2 are self-contained in radarlib and independently verifiable: once
they run, point the existing `gl-tracker` pipeline at the produced grids and
confirm the format round-trips before any webmet25 code is touched. That
checkpoint is worth having before starting Phase 3.

```
Phase 1 (radarlib: write grids)      --> verify with gl-tracker directly
Phase 2 (radarlib: retention)        --> verify dir pruning
Phase 3 (webmet25: index grids)      --> verify rows appear/disappear
Phase 4 (tracking service)           --> verify via curl
Phase 5 (frontend page)
```

### How to re-run the measurements in §3.2

```bash
# grid build (one volume, cold)
docker run --rm \
  -v "$HOME/gl-tracker:/workspace/gl-tracker" \
  -v "$HOME/gl-radarlib:/workspace/gl-radarlib" \
  -v "$HOME/geometry:/workspace/geometry:ro" \
  -v "$HOME/radar_data:/workspace/radar_data" \
  -v "$HOME/grids:/workspace/grids" \
  -e PYTHONPATH=/workspace/gl-tracker:/workspace/gl-tracker/scripts:/workspace/gl-radarlib/src \
  -w /workspace/gl-tracker \
  gl-tracker:dev python scripts/make_grid.py /workspace/radar_data/<FILE>.nc --overwrite

# tracking over existing grids, WITHOUT radarlib on the path
docker run --rm \
  -v "$HOME/gl-tracker:/workspace/gl-tracker" \
  -v "$HOME/grids:/workspace/grids:ro" \
  -v "$HOME/tracking_out:/workspace/tracking_out" \
  -e PYTHONPATH=/workspace/gl-tracker:/workspace/gl-tracker/scripts \
  -e GRILLA_RAIZ=/workspace/grids -e TRACKING_OUT=/workspace/tracking_out \
  -w /workspace/gl-tracker \
  gl-tracker:dev python operativo.py --una-vez --desde-cero
```

---

## 13. Phase 1 implementation plan — radarlib writes NC cubes

All changes are in **`gl-radarlib`**. Nothing in webmet25 or gl-tracker is
touched by this phase. The deliverable is: grids appearing on disk under
`../nccube/<RADAR>/YYYY/MM/DD/`, pruned after 7 days, with the format verified to
round-trip through the existing gl-tracker pipeline.

### 13.1 What changes

| # | file | change | why |
|---|---|---|---|
| 1 | `src/radarlib/io/nccube_writer.py` *(new)* | port of `gl-tracker/scripts/grid_writer.py`, generalised to a field mapping (§13.8) | the NetCDF format definition; written to be standalone for exactly this move |
| 2 | `src/radarlib/daemons/product_daemon.py` | new `_generate_nccube()` + its own gate after line 896 | independent of tops & cores (§5) |
| 3 | `app/config.py` | 5 new `_DEFAULTS` keys | config must exist in `_DEFAULTS` or it is dropped in flattening |
| 4 | `genpro25.yml` | enable flag, vol_nr, field list, retention | operator-facing knobs |
| 5 | `app/main.py` | pass new config into `DaemonManagerConfig` | plumbing |
| 6 | `src/radarlib/daemons/manager.py` | dataclass fields + forward to both daemons | plumbing |
| 7 | `src/radarlib/daemons/cleanup_daemon.py` | new `_cleanup_nccube_files()` | retention; must be directory-based, not DB-based |
| 8 | `docker-compose.yml` | mount + env per radar service | make the output reachable from the host |

Naming: the product is the **NC cube** — `NCCUBE_*` config keys, `nccube/`
output tree, `_NCCUBE.nc` files, `nccubes` table, `NCCube*` classes. Chosen
because "grid" is heavily overloaded in radarlib (`radar_grid`, `GridGeometry`,
`grid_shape`, `apply_geometry`, `ROOT_GEOMETRY_PATH`) and because
`NETCDF_RETENTION_DAYS` already exists and means the CFRadial **polar** volumes
— reusing any `NETCDF_*` key would be actively dangerous.

**No Dockerfile change, no new dependency.** `netCDF4 ^1.7.0` is already a main
dependency (`pyproject.toml:19`), installed by `app/Dockerfile`'s
`pip install -e .`.

### 13.2 How it will be controlled

Three new config keys, following the existing `ADD_TOPS_AND_CORES` /
`ROOT_TOPS_AND_CORES_PATH` / `NETCDF_RETENTION_DAYS` pattern exactly:

| key | default in `_DEFAULTS` | set in `genpro25.yml` | meaning |
|---|---|---|---|
| `ADD_NCCUBE` | `False` | `True` | master on/off, per radar |
| `NCCUBE_VOL_NR` | `"01"` | `"01"` | which volume — independent of tops & cores |
| `NCCUBE_FIELDS` | `["DBZH", "RHOHV"]` | `["DBZH", "RHOHV"]` | which fields to interpolate and store (§13.8) |
| `ROOT_NCCUBE_PATH` | `"nccube"` | — (compose env) | output root |
| `NCCUBE_RETENTION_DAYS` | `7.0` | `7.0` | age cutoff for the pruner |

Precedence is `_DEFAULTS` -> flattened `genpro25.yml` -> env overrides
(`app/config.py:141-169`, coercing by the `_DEFAULTS` type). So compose env vars
win, which is how `ROOT_NCCUBE_PATH` gets set per container. **A key absent from
`_DEFAULTS` is silently dropped during YAML flattening and gets no type
coercion** — this is the single easiest mistake to make here.

`ADD_NCCUBE` defaulting to `False` means the change is inert until
switched on, so it can be merged ahead of the rollout and enabled for one radar.

Per-radar compose block (template: `genpro25-rma1`, `docker-compose.yml:56-76`):

```yaml
    volumes:
      - ../nccube/RMA1:/workspace/app/nccube/RMA1
    environment:
      ROOT_NCCUBE_PATH: "/workspace/app/nccube"
```

**The host directory must pre-exist**, or Docker creates it root-owned — the
same problem already hit while developing gl-tracker's pipeline.

### 13.3 The write itself

A new method `_generate_nccube()`, sibling to `_generate_tops_and_cores`,
called from its own gate right after line 896 (see §5 for the call signature).

Body, mirroring the structure of `_generate_tops_and_cores`:

1. function-local imports, house style: `apply_geometry`, `get_field_data` from
   `radarlib.radar_grid`; `write_nccube` from the new module
2. skip unless **both** `hrefl_field` and `rhv_field` are in `radar.fields`
3. `apply_geometry` each field -> two `(nz, ny, nx)` float32 arrays
4. build coordinates from `geom` (as lines 1325-1331 do)
5. write, temp file + atomic move as `field_processor.py:324-339` does
6. `try/except Exception: log` — **never** let a grid write break COG production
7. `finally: del` both arrays + `gc.collect()`, matching the pattern at 1360-1364

Values to pass:

| writer arg | source | note |
|---|---|---|
| `dbzh`, `rhohv` | `apply_geometry(geom, get_field_data(radar, <field>))` | float32 `(nz,ny,nx)`, NaN fill, **row 0 = south** |
| `x_km`, `y_km` | `np.linspace(min, max, n) / 1000.0` from `geom.grid_limits[2]` / `[1]` | **grid_limits are in metres; the writer wants km** |
| `z_m` | `geom.z_levels()` | metres above the antenna |
| `radar_lat`, `radar_lon` | `radar.latitude["data"].data[0]`, `.longitude...` | as used at 1339-1340 |
| `radar_alt_m` | **`radar.altitude["data"][0]`** | **NOT `geom.radar_altitude`** — see below |
| `timestamp` | `obs_dt` | tz-aware UTC |
| `referencia_z` | `"radar"` | matches `z_levels()` being antenna-relative |

#### The one trap that fails silently

`geom.radar_altitude` is **`0`** for daemon-built geometries
(`product_daemon.py:345`), so `z_levels_absolute()` equals `z_levels()`. The
true antenna altitude must come from `radar.altitude`.

Measured on the dev box for RMA5, confirming it empirically:

```
radar.altitude      = 836.0 m
geom.radar_altitude =   0.0 m
```

Two distinct ways to get this wrong, both silent:

- **Writing `radar_alt_m=0`** makes the tracker's `gate.h0_para_grilla()`
  evaluate C2 with an ~836 m error against a 1500 m margin.
- **Omitting the attribute entirely** is worse. `grilla.leer()` does
  `alt0 = float(getattr(nc, "radar_alt_m", cfg.radar_alt_m))`, and
  `Config.radar_alt_m` defaults to `484.0` — **RMA1's altitude, applied to
  whatever radar is being processed** (352 m wrong for RMA5). There is no
  warning on this path.

Neither produces an error or a log line; the filter just silently retains or
discards the wrong storms. `grid_writer.py`'s docstring documents the whole
chain; read it before writing the call.

The webmet25 sidecar may additionally resolve altitude from the `radars` table
as a cross-check — but as a second source of truth, not as a reason to omit the
one that is free to write here.

Second trap: `grid_writer` performs the south->north flip internally. Do **not**
also flip in radarlib — flipping twice mirrors the grid north-south, which also
has no obvious symptom.

### 13.4 Scope

Gated on `ADD_NCCUBE` and its own `NCCUBE_VOL_NR` (`"01"`),
independent of tops & cores — see §5 for the measurement behind that decision
(2.24 s/volume, 0.4% of the duty cycle).

Additionally skip unless **both** `hrefl_field` and `rhv_field` are in
`radar.fields`: a grid without RHOHV is rejected by `grilla.leer()` downstream,
so writing nothing beats writing something half-valid.

### 13.5 Retention

`CleanupDaemon` is **database-driven, not directory-driven**: it queries SQLite
for rows and deletes the path recorded on each
(`sqlite_tracker.py:1476`, `:1571`). Grids will have no such rows, so this needs
a genuinely **new** `_cleanup_nccube_files()` that walks
`{nccube_dir}/YYYY/MM/DD/`, unlinks past the cutoff and prunes empty day dirs —
not a copy of `_cleanup_netcdf_files`.

Note there is no existing example to crib from: the COG and tops & cores output
trees are not pruned by anything today.

Honour the existing conventions: `dry_run` short-circuit, `max_files_per_cycle`
cap, stats counters in `__init__`, and calls from both `_run_cleanup_cycle()`
and `run_once()`. Poll interval is the shared `CLEANUP_POLL_INTERVAL` (1800 s).

### 13.6 Verification

The phase is done when all four pass:

1. **Grids appear** under `../nccube/<RADAR>/YYYY/MM/DD/` with the expected
   name, ~15 MB each, roughly one per vol01 cycle (~9 min).
2. **Format round-trips.** Point the existing gl-tracker pipeline at the
   produced grids and confirm it tracks them — this is the real acceptance test
   and it needs no new code:
   ```bash
   GRIDS_DIR=../nccube/<RADAR> ./scripts/pipeline.sh track
   ```
   Expect sane `detectados`/`convectivos` lines, not `ValueError` or an
   all-NaN complaint.
3. **Antenna altitude is right.** `ncdump -h` the grid and check `radar_alt_m`
   is the real antenna altitude, **not 0**. This is the silent failure from
   §13.3 and deserves its own explicit check.
4. **Retention prunes.** Set `NCCUBE_RETENTION_DAYS` low temporarily (e.g.
   `0.01`), confirm old files vanish and empty day dirs are removed, then set it
   back to `7.0`.

A fifth check worth doing once: compare a CAPPI slice of the written grid
against the COLMAX COG for the same volume to confirm georeferencing and
orientation agree. A north-south mirror would otherwise pass checks 1-4
unnoticed.

### 13.7 Suggested order of work

```
1. nccube_writer.py into radarlib               (no behaviour change)
2. config keys + plumbing, ADD_NCCUBE=False  (still inert)
3. the write call + guards                      (enable for one radar, verify 1-3)
4. compose mount + env                           (grids reach the host)
5. cleanup category                              (verify 4)
```

Steps 1-2 are safe to merge independently: with the flag off, nothing changes.

### 13.8 Configurable fields

**Decided 2026-10-19: the cube stores a configurable field list, not a
hardcoded DBZH + RHOHV pair.**

The tracker needs exactly two fields, but strategy 0315 vol01 carries five —
`genpro25.yml` `VOLUME_TYPES["0315"]["01"]` declares `DBZH, ZDR, RHOHV, PHIDP,
KDP`. ZDR, KDP and PHIDP are what hail detection, hydrometeor classification
and attenuation correction need, so the cube should be able to carry them
without a format change later.

#### Config

```yaml
NCCUBE_FIELDS: ["DBZH", "RHOHV"]     # default; the tracker's hard requirement
```

#### Writer signature change

`grid_writer.write_cartesian_netcdf()` currently takes `dbzh` and `rhohv` as
positional arrays and hardcodes two `_field(...)` calls. Generalise to a
mapping:

```python
write_nccube(
    path,
    fields: dict[str, np.ndarray],   # {"DBZH": arr, "RHOHV": arr, ...}
    x_km, y_km, z_m,
    radar_lat, radar_lon, radar_alt_m,
    timestamp, referencia_z="radar",
)
```

Everything else is unchanged — same shape validation, same south->north flip,
same global attributes. Each array is validated against `(nz, ny, nx)` and
written with the existing zlib settings.

Per-field `long_name` and `units` come from a module-level map in the writer,
defaulting to empty with a warning for unknown fields:

| field | long_name | units |
|---|---|---|
| `DBZH` | Horizontal reflectivity factor | dBZ |
| `RHOHV` | Cross-correlation ratio | 1 |
| `ZDR` | Differential reflectivity | dB |
| `KDP` | Specific differential phase | deg/km |
| `PHIDP` | Differential phase | deg |

#### Field name resolution

Configured names are *logical* names; the actual keys in `radar.fields` are
whatever pyart is configured to use. Resolve through pyart's
`get_field_name(<standard_name>)` — the same call `product_daemon.py:791` uses
for `rhv_field`. The standard-name mapping is already established in-repo at
`deprecated_generators.py:116-122`:

```
cross_correlation_ratio        -> RHOHV
differential_reflectivity      -> ZDR
differential_phase             -> PHIDP
specific_differential_phase    -> KDP
velocity                       -> VRAD
spectrum_width                 -> WRAD
```

Note `hrefl_field` comes from `fields["hrefl_field"]` (line 786), not from
`get_field_name` — handle it as the existing code does rather than assuming.

#### Validation rules

1. **Skip fields absent from `radar.fields`**, with a warning naming the field
   and the volume. Do not fail the whole cube for one missing optional field.
2. **DBZH and RHOHV are mandatory.** If either is missing after resolution,
   write nothing — a cube without them is useless to the tracker and
   `grilla.leer()` rejects it. This is the same guard as §13.4, now expressed
   over the configured list.
3. Warn at startup if `NCCUBE_FIELDS` omits DBZH or RHOHV — that is almost
   certainly a misconfiguration.

#### Cost scales linearly — watch the disk

Per field, measured: **~1.1 s** of `apply_geometry`, **23.2 MB** transient,
**~7.7 MB** on disk after compression.

| fields | CPU/volume | file | 1 radar, 7 days |
|---|---|---|---|
| 2 (DBZH, RHOHV) | 2.24 s | 15.4 MB | ~17 GB |
| 5 (all of vol01) | ~5.6 s | ~38 MB | ~43 GB |

CPU stays negligible against a ~9 min cycle even at five fields. **Disk does
not** — going to five fields roughly triples the standing footprint. Revisit
retention if the field list grows.

#### Backward compatibility

Adding fields is safe for the tracker: `grilla.leer()` reads only the two
variables it names (`cfg.var_dbzh` / `cfg.var_rhohv`, with alias fallbacks) and
ignores everything else in the file. Cubes written with more fields stay
readable by the existing pipeline with no change.

---

## 14. Phase 3 implementation plan — the tracking sidecar

Branches from **`feat/nccube-indexer`** (needs the `NCCube` model). `gl-tracker`
is **not modified** — see §8.0.

### 14.1 Tracking semantics, measured

Three different depths, often conflated. Establishing them is what justifies the
design below.

| what | depth | source |
|---|---|---|
| **Association** (which storm is which) | **1 previous volume** | `est.previous` holds only the immediately preceding frame |
| **Velocity / direction / forecasts** | **up to 4 volumes** | `velocity_history_len=4`, weights `[0.2, 0.3, 0.5, 1.0]` |
| minimum for any velocity | 2 volumes | `MIN_POINTS_FOR_FIT = 2` |
| gap that resets everything | 20 min | `max_gap_tracking_min` -> `previous = []` |

State is bounded: nothing older than 4 volumes is read. But **track identity is
a chain** — a system's `name` UUID is inherited at each match, so a storm alive
two hours carries an id handed down through ~13 volumes.

**Consequence: a cold start has a warm-up.** Begin at 14:00 and every system in
that frame is `SPONTANEOUS_GENERATION` with no velocity and no forecast — not
because nothing was there, but because there is no previous frame. Full-quality
4-point fits need **4 volumes (~36 min)**.

So the resolver silently prepends up to 4 volumes before the requested start and
the driver discards their output (§14.6).

### 14.2 Where the time goes, measured

31 volumes, warm page cache:

| stage | ms/vol | share |
|---|---|---|
| `grilla.leer()` — read cube + QC + echo top | **262** | **85%** |
| `gate.evaluar()` | 1 | <1% |
| detect + classify + track + forecast | 47 | 15% |
| total | **310** | |

**Tracking is not the slow part.** `leer()` is a pure function of
`(cube file, filter config)` — independent of neighbouring volumes. That is the
hook for every future optimisation (§14.9), and the reason the job/poll shape is
worth having even though v1 runs straight through.

### 14.3 Layout — and the namespace rule

```
gl-webmet25/tracking/
  Dockerfile
  requirements.txt
  tracking_api/              <- EVERYTHING lives in this package
    __init__.py
    main.py                  FastAPI app + routes
    config.py                sidecar settings      (= tracking_api.config, safe)
    schemas.py               request/response models
    jobs.py                  job store + runner
    volumes.py               nccubes -> ordered paths, incl. lead-in
    driver.py                the operativo.py replacement
    sink.py                  duck-typed Salidas stand-in
    geojson.py               ConvectiveSystem -> GeoJSON
```

**Nothing may be a top-level module.** gl-tracker's modules are flat names —
`config`, `estado`, `filtro_convectivo`, `gate`, `grilla`, `h0_wrf`, `pipeline`,
`operativo`. When `pipeline.py` does `import config`, resolution walks
`sys.path`; a top-level `config.py` in the sidecar would shadow it depending on
path order. Keeping all sidecar code inside `tracking_api/` makes the collision
impossible. (`radar_db/config.py` is fine — it is inside a package too.)

### 14.4 The sink — proven, not assumed

`procesar()` touches exactly two things on `salidas`:
`salidas.systems.output(list)` (`pipeline.py:325`) and
`salidas.forecasts[lead].output(list)` (`pipeline.py:321`).

```python
class _Collector:
    def __init__(self): self.rows = []
    def output(self, systems): self.rows.extend(systems)

class VolumeSink:                       # stands in for pipeline.Salidas
    def __init__(self, intervals):
        self.systems = _Collector()
        self.forecasts = {t: _Collector() for t in intervals}
```

Verified 2026-10-20: 33 systems collected across 31 volumes, no SpatiaLite file,
no gl-tracker change.

**Build one sink per volume**, not one per job. The accumulating alternative
forces regrouping afterwards, and forecast systems carry
`timestamp = base + lead` rather than the base time, so regrouping them means
subtracting the lead back out. A fresh sink per volume keeps the association
explicit and costs nothing.

### 14.5 The driver

~40 lines in `tracking_api/driver.py`, replacing `operativo.py`:

```python
cfg   = build_config(request)                 # §14.7
serie = gate.serie_h0_actual(cfg, cfg.h0_lat, cfg.h0_lon)   # None -> climatology
est   = estado_mod.Estado()                   # fresh per job == --desde-cero

for ts, path, is_lead_in in volumes:          # ordered, from Postgres
    sink   = VolumeSink(cfg.forecast_intervals)
    result = pipeline.procesar(path, ts, cfg, serie, est, sink)
    if not is_lead_in:
        emit(ts, result, sink)                # -> GeoJSON, progress tick
```

`procesar()` returns a `Resultado` carrying the gate verdict, the counts and the
per-volume timing — exactly what the per-volume response needs. It mutates
`est`, so chronological order is the driver's responsibility; the resolver
guarantees it.

Passing `serie=None` is supported and falls back to climatology.

### 14.6 Volume resolution

```sql
-- the window
SELECT file_path, observation_time FROM nccubes
WHERE radar_code = :radar AND status = 'AVAILABLE'
  AND observation_time BETWEEN :start AND :end
ORDER BY observation_time;

-- the lead-in: up to 4 volumes strictly before the window
SELECT file_path, observation_time FROM nccubes
WHERE radar_code = :radar AND status = 'AVAILABLE'
  AND observation_time < :start
ORDER BY observation_time DESC LIMIT 4;
```

Lead-in rows are processed and their output discarded. If they sit more than
`max_gap_tracking_min` before the window start, `procesar()` resets tracking on
its own — no special handling needed, the gap logic covers it.

`GET /availability` answers the frontend's time-picker bound from
`min(observation_time)`.

### 14.7 Config mapping — one trap

```python
class TrackingConfig(BaseModel):          # v1 surface
    cappi_height_m: float = Field(2500.0, ge=500,  le=15000)
    dbz_threshold:  float = Field(35.0,   ge=0,    le=75)
    min_area_km2:   float = Field(50.0,   ge=1,    le=10000)
```

Mapping is **not** uniform:

- `dbz_threshold`, `min_area_km2` -> **top-level `Config` fields**
- `cappi_height_m` -> **`Config.filter_overrides`**

Putting `det_threshold_dbz` / `det_min_area_km2` into `filter_overrides` does
nothing: `Config.filtro()` overwrites both from the top-level fields
(`config.py:161-162`). Whitelist strictly — never `setattr` from client input.

### 14.8 API

```
POST /api/tracking/jobs            {radar, start, end, config?} -> {job_id, status}
GET  /api/tracking/jobs/{job_id}   -> {status, progress, result?, error?}
GET  /api/tracking/availability    ?radar=RMA1 -> {min_time, max_time, count}
```

States: `pending` -> `running` -> `done` | `error`. Progress is
`volumes_done / volumes_total`.

Job/poll rather than one synchronous call, because a 20 s request has nowhere to
put progress or partial results, and it forecloses the incremental path in
§14.9. **v1 job store is in-memory** — jobs vanish on restart, which is
acceptable while concurrency is deferred (§8.3) but should be stated in the UI.

Per-volume result shape:

```json
{
  "timestamp": "2026-10-20T18:27:24Z",
  "gate_passed": true,
  "gate": {"tope_max_m": 4800, "umbral_m": 4841, "n_pixeles_pasan": 0,
           "h0_msnm": 3716, "h0_fuente": "climatologia"},
  "counts": {"detectados": 1, "convectivos": 0, "rastreados": 0, "forecasts": 0},
  "features": { "type": "FeatureCollection", "features": [...] }
}
```

Features carry `kind: "system" | "forecast"`, `lead_min` on forecasts, and the
identity trio `name` / `event` / `relationships` (§4.2). Geometry via OGR's
`ExportToJson()`.

**Gate-failed volumes still return an entry** — zero features plus the verdict,
so the UI distinguishes "filtered" from "no data".

### 14.9 Caching

**v1:** cache completed job results on `(radar, window, config-hash)`, LRU
bounded. The default config will dominate requests, so this alone makes the
common path instant.

**v2 (not now):** cache `leer()` output per `(cube, filter-config-hash)`. From
§14.2 that turns a tracking-only reparameterisation into **~47 ms/vol** — a
4-hour window re-tracks in ~1.5 s — and a live request with one new volume into
~0.31 s. Needs an explicit memory bound: a prepared volume holds the detection
field and echo-top arrays, order ~1 MB each.

### 14.10 Container, compose, nginx

`tracking/Dockerfile` — gl-tracker's stack minus the gridding-only packages
(`arm-pyart`, `pyproj`, `pandas`, `pytz`, `cachetools`, `xarray`, `psutil`,
`matplotlib`), plus FastAPI/uvicorn and `COPY database/radar_db/` (the same
pattern `indexer/Dockerfile` uses).

gl-tracker enters by pinned clone, since it has no packaging metadata (§8.0):

```dockerfile
ARG GL_TRACKER_REF=main
RUN git clone --depth 1 --branch ${GL_TRACKER_REF} \
      https://github.com/jgmarti84/gl-tracker.git /opt/gl-tracker
ENV PYTHONPATH=/app:/opt/gl-tracker
```

When gl-tracker gains a `pyproject.toml`, this becomes a one-line
`pip install git+...` swap.

compose:

```yaml
  tracking:
    build: {context: ./, dockerfile: ./tracking/Dockerfile}
    container_name: radar_tracking
    environment: {DB_HOST: radar_db, ..., NCCUBE_DIR: /nccube}
    volumes: ["../nccube:/nccube:ro"]
    depends_on: {radar_db: {condition: service_healthy}}
```

nginx: a `location /api/tracking/` block proxying to `tracking:8001`. nginx
prefix matching picks the longest match, so it wins over the existing `/api/`
block regardless of order. Raise `proxy_read_timeout` there — polling is cheap,
but the job POST should not inherit a short default.

### 14.11 Verification

1. Unit: config mapping (especially that `cappi_height_m` lands in
   `filter_overrides` and `dbz_threshold` does not), volume resolution including
   lead-in, GeoJSON serialisation preserving `name`/`event`/`relationships`,
   sink shape.
2. Integration: submit a job over real host cubes; assert per-volume entries
   exist for gate-failed volumes too.
3. Identity: a storm spanning several volumes keeps one `name`; the first
   returned frame is *not* all `SPONTANEOUS_GENERATION` when lead-in volumes
   exist.
4. `docker exec radar_tests pytest tests/api/ -q` — no regression.

### 14.12 Order of work

```
1. tracking/ skeleton + Dockerfile + compose      (service starts, /health)
2. volumes.py + /availability                     (DB reachable, no tracker yet)
3. sink.py + driver.py + geojson.py               (unit-testable, no HTTP)
4. jobs.py + POST/GET routes                      (end to end)
5. nginx route + cache
```

Step 3 is the risky one and is fully testable offline against the cubes already
on disk.
