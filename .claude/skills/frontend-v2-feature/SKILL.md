---
name: frontend-v2-feature
description: Make a change to the WebMet25 v2 frontend (the Leaflet map UI + admin SPA) safely — add/modify a control, panel, basemap, layer, or animation behavior. Use when editing frontend/public (index.html, css/styles.css, js/v2/*, js/shared/*) or the admin panel. Covers the file map, the invariants that break things, the add-a-control pattern, and how to verify with the run-webmet25 stack.
---

# Frontend v2 feature work (WebMet25)

The public map UI and admin panel are **vanilla JS ES modules, no build tool** — you edit
files under `frontend/public/` and they're served statically by nginx. **v2 is production;
v1 (`js/v1/`) is legacy — don't touch it.** Deep architecture lives in
`.github/copilot-instructions.md` §"v2 Frontend Architecture" and `docs/COMPONENTS.md`;
`frontend/CLAUDE.md` has the short version that auto-loads.

## File map
```
frontend/public/
├── index.html            # ALL DOM for the public map UI; panels are STATIC HTML, hidden
│                         #   (display:none) until toggled. Selects are populated by JS.
├── admin.html            # admin SPA shell
├── css/styles.css        # public styles      css/admin.css  # admin styles
└── js/
    ├── v2/ app.js        # orchestrator (~2300 lines): the single `state` object,
    │                     #   setupEventListeners() wires everything, frame loading
    │       map.js        # MapManager: L.imageOverlay layers, BASEMAPS, coverage mask
    │       animation.js  # AnimationController: requestAnimationFrame play/pause
    ├── v1/               # LEGACY — ignore
    └── shared/ api.js controls.js legend.js time-wheel.js tops-cores.js
```
- State lives on one `state` object in `v2/app.js`. Events are wired in `setupEventListeners()`.
- `shared/controls.js` (`UIControls`) populates `<select>`s and reads control values.
- User prefs persist to `webmet25_*` localStorage keys (see the table in `frontend/CLAUDE.md`).

## Invariants (break these and things subtly break)
- **Animation continuity.** NEVER call `animator.stop()`, `animator.reset()`, or
  `clearRadarLayer()` before new frames are staged. All data loading routes through
  `_loadFramesWithContinuity(loadFn, opts)`, which fetches into a staging buffer and
  atomically `setFrames()` so playback never stutters.
- **All user-facing text is Spanish (es-AR).** Labels, titles, aria-labels, button text,
  `setStatus()`/error/`confirm()` messages. **Never** translate `console.*` logs. No i18n
  framework — edit strings in place.
- **Basemaps** only via `MapManager.setBasemap(key)`; defined in the `BASEMAPS` object in
  `v2/map.js`. To remove one, comment it out in BOTH `map.js` and the `#basemap-select`
  `<option>` in `index.html` (don't delete — keep for restore).
- **`product_key` `o`-suffix = UNFILTERED**; no suffix = filtered. The "Filtered" toggle is
  inverted (checked = filtered). `COVERAGE_MODES` maps `cd`→vols 01/02, `vig`→vol 04.

## Add-a-control pattern
1. **DOM** in `index.html` inside the right panel (`#panel-module-a/b/c`, settings). For a
   help "?" bubble, reuse the `.filter-info-tip` / `.filter-info-popup` markup.
2. **Wire** the listener in `v2/app.js` `setupEventListeners()`; keep new state on `state`.
3. **Persist** prefs to a `webmet25_*` localStorage key; add a getter/restore near the others
   (search `SETTINGS_KEY_`). Clamp restored values to the control's current min/max.
4. If it triggers a data reload, go through `_loadFramesWithContinuity` — never stop first.
5. **CSS** in `css/styles.css`. Target a specific `#id` when a shared class (e.g.
   `.control-group select`) would over-apply.

## Verify (use the run-webmet25 skill to bring up the stack)
Frontend files are **baked into the image at build** — after editing, rebuild:
```bash
DC="docker compose -f docker-compose.yml -f docker-compose.devcontainer.yml"
$DC up -d --build frontend-v2          # then wait for :8090 to return 200
```
Drive it with a Playwright script inside `radar_tests` (pattern in
`.claude/skills/run-webmet25/verify_wave2.py` — reuse/adapt it):
```bash
docker cp .claude/skills/run-webmet25/<script>.py radar_tests:/tmp/s.py
docker exec radar_tests python /tmp/s.py
docker cp radar_tests:/tmp/webmet-shots ./webmet-shots
```
Then keep the regression suite green: `docker exec radar_tests pytest tests/e2e/ -q`.

### ⚠️ No-imagery gotcha (important when verifying)
The seeded test DB has **no indexed COGs**, so `GET /products?vol_nr=…&strategy=…` returns 0
and the **field menu rows + animation frames never populate via the live path** (the products
table has 11 rows, but availability is derived from indexed COGs). To verify presentation-only
changes (widths, tooltips, button geometry, basemap render), drive the DOM directly: open the
panel, force-reveal hidden rows (`el.style.display='block'`), inject representative `<option>`s,
toggle classes (e.g. `.playing`), then measure `getBoundingClientRect()` / screenshot. To
verify true data-driven behavior you need COG files mounted for the indexer (see run-webmet25).

### e2e gotcha
Controls live in `display:none` panels — in Playwright use
`wait_for_selector(..., state="attached")`, not the default (visible), or it times out.
