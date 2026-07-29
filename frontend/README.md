# WebMet25 Frontend

The v2 frontend is a modular vanilla ES6 application served by Nginx. It renders an animated multi-radar map using `L.imageOverlay` (one full-image PNG per radar per frame, not tile layers), with a separate one-radar detail page, an admin CRUD panel, and an alternative COG browser.

---

## Pages

| File | URL | Description |
|------|-----|-------------|
| `public/index.html` | `/` | Multi-radar animated map (v2 production) |
| `public/radar.html` | `/radar.html?code=XXX` | One-radar multi-layer detail page |
| `public/admin.html` | `/admin` | Admin CRUD SPA (nginx Basic Auth) |
| `public/cog-browser.html` | `/cog-browser.html` | Alternative COG file browser |

---

## Module Map

```
frontend/public/js/
├── admin.js              # Admin SPA orchestrator (1994 lines)
├── admin-api.js          # Admin REST client (/api/v1/admin/*)
├── shared/               # Shared by all pages
│   ├── api.js            # REST API client — /radars /products /cogs /frames /colormap /tops-cores
│   ├── controls.js       # UIControls — radar list, time wheel, badges, status messages
│   ├── legend.js         # LegendRenderer — gradient bar + ticks from colormap data
│   ├── tops-cores.js     # TopsCoresLayer — L.circleMarker for cores (blue) and tops (red)
│   ├── time-wheel.js     # TimeWheel — iOS-style HH:MM scroll picker
│   ├── cog-browser-api.js # REST client for the COG browser
│   └── cog-browser.js    # COG browser application
└── v2/                   # Production frontend (v1/ is legacy — do not extend)
    ├── app.js            # Multi-radar map orchestrator (~2526 lines)
    ├── radar-app.js      # One-radar page orchestrator (~1662 lines)
    ├── map.js            # MapManager — L.imageOverlay + SVG coverage mask (~1076 lines)
    ├── animation.js      # AnimationController — requestAnimationFrame (~429 lines)
    ├── radar-utils.js    # Shared helpers: buildGridFrames, geolocation, badge updates
    └── constants.js      # COVERAGE_MODES, MS_PER_HOUR, default values
```

---

## Architecture

### v2 Key Properties

- **No build tool, no framework.** Pure ES6 modules served directly.
- **`L.imageOverlay`** (not `L.tileLayer`) — one full PNG image per radar per frame vs. ~180 tiles.
- **`/frames/{id}/image.png`** endpoint (not `/tiles/{id}/{z}/{x}/{y}.png`) — full-image georeferenced PNG.
- **`requestAnimationFrame`** animation loop — no `setInterval`.
- **Animation continuity invariant:** all data loads go through `_loadFramesWithContinuity()`. Never call `animator.stop()` or clear layers before new frames are staged.
- **Coverage mask:** SVG rendered in `coverageMaskPane` (z-index 300) — dims outside radar coverage.
- **TopsCoresLayer:** `L.circleMarker` layer in `topsCoresPane` (z-index 450) — fire-and-forget, never blocks frame advance.
- **All UI text in Spanish (es-AR).** Never translate `console.*` debug logs.

### Coverage Modes (`v2/constants.js`)

```javascript
COVERAGE_MODES = [
    { id: 'cd',  label: 'C+D', volNrs: ['01','02'], strategy:'0315', filteredFieldsAvailable: true,  defaultProduct: 'COLMAXo' },
    { id: 'vig', label: 'VIG', volNrs: ['04'],       strategy:'0315', filteredFieldsAvailable: false, defaultProduct: 'DBZHo'  },
]
```

Mode persisted to `webmet25_coverage_mode` localStorage. Switching modes triggers a full `_loadFramesWithContinuity()` reload.

### Basemaps

Five IGN Argenmap basemaps defined in `map.js`: `argenmap`, `argenmap_gris`, `argenmap_topo`, `argenmap_oscuro`, `argenmap_hibrido`. Default: `argenmap`. Nginx proxies and caches IGN (7-day TTL) and OSM (30-day TTL) tile servers locally.

Always call `MapManager.setBasemap(key)` to switch — never manipulate `_baseLayer` directly.

### Radar Display Order

`sortRadarsForDisplay` in `controls.js`:
1. Active radars before inactive
2. Within each group: RMA before AR
3. Within each subgroup: numeric ascending, with RMA00 (number 0) sorted **last**
   (e.g. `RMA1…RMA17, RMA00, AR5…`)

---

## One-Radar Detail Page (`radar.html` + `radar-app.js`)

URL: `/radar.html?code=AR5[&field=DBZHo]`

- Always C+D mode (no VIG toggle)
- Multi-layer field compositor: each added field is a layer with independent colormap, range filter, opacity, and smoothing
- `showAllLayersAtFrame(index)` composites all visible layers on every animation tick
- `updateCoverageRadius()` draws SVG mask cutout + rings from active layer `coverageRadius` values
- Snapshot exports basemap + radar overlays + OHMC logo + per-layer colormap strips + timestamp
- Only accessible when `Radar.detail_view_enabled = true` (set per-radar in admin panel)

---

## Admin Panel (`admin.html` + `admin.js`)

URL: `/admin` (nginx HTTP Basic Auth — credentials set via `ADMIN_USERNAME`/`ADMIN_PASSWORD` env vars)

Sections (hash-routed via `history.replaceState`):
`dashboard`, `radars`, `products`, `references`, `cogs`, `tops-cores`, `estrategias`, `volumenes`, `colormaps`, `colormap-options`

Key behaviors:
- Django-admin-style filter bars: global search + per-column facets (text/select/boolean), live count, sortable columns
- Colormap creator/editor: live canvas gradient preview with draggable stops; edit = delete-then-recreate pattern
- "← Volver al mapa" restores main map via browser bfcache when navigated from there (`sessionStorage.webmet25_admin_from_main`)

---

## localStorage Keys (v2)

| Key | Default | Description |
|-----|---------|-------------|
| `webmet25_show_inactive_radars` | false | Show inactive radars |
| `webmet25_show_filtered_fields` | false | Show filtered (non-`o`) fields |
| `webmet25_live_refresh_interval_ms` | 60000 | Live refresh interval (ms) |
| `webmet25_radar_refresh_interval_min` | 10 | Radar status refresh (min) |
| `webmet25_coverage_visible` | false | Coverage mask toggle |
| `webmet25_coverage_opacity` | 0.4 | Coverage mask opacity |
| `webmet25_coverage_mode` | 'cd' | Active coverage mode |
| `webmet25_tops_cores_visible` | false | Tops & Cores layer |
| `webmet25_tops_cores_size` | 8 | Circle marker radius (px) |
| `webmet25_smooth_enabled` | false | Gaussian smoothing toggle |
| `webmet25_smooth_sigma` | 0.8 | Gaussian sigma |
| `webmet25_selected_basemap` | 'argenmap' | Active basemap key |

---

## Nginx Configuration Highlights

- `/admin` and `/admin/*` — Basic Auth + serve `admin.html`
- `/api/v1/admin/*` — Basic Auth + proxy to `api:8000`
- `/api/*` — proxy to `api:8000` (with `proxy_buffering off` for SSE support)
- `/osm-tiles/*` — proxy + 30-day cache to `tile.openstreetmap.org`
- `/ign-tiles/*` — proxy + 7-day cache to `wms.ign.gob.ar`
- `/health` — inline 200 OK

---

## Development & Verification

```bash
# Rebuild only the frontend image (after JS/HTML/CSS changes)
docker compose build frontend
docker compose up -d frontend

# Run a screenshot to verify visually
docker exec radar_tests python /app/.claude/skills/run-webmet25/screenshot.py

# Run e2e browser tests
docker exec radar_tests pytest tests/e2e/ -v
```

The `run-webmet25` Claude skill handles the full bring-up, screenshot, and smoke-test sequence.

---

**Version:** 2.0.0  
**Last Updated:** July 8, 2026
