# AGENTS.md — frontend (v2)

> Conventions for the **v2** frontend (current production), for any agent or human editing here.
> Full architecture: `.github/copilot-instructions.md` §"v2 Frontend Architecture". Component
> breakdown: `docs/COMPONENTS.md`.

## File map (vanilla JS ES modules — no build tool)
```
frontend/public/
├── index.html            # all DOM for the public map UI (panels are static HTML)
├── admin.html            # admin SPA shell
├── css/styles.css        # public styles      css/admin.css  # admin styles
└── js/
    ├── v2/   app.js       # main orchestrator (~2300 lines): state, event wiring, loading
    │         map.js       # MapManager: L.imageOverlay layers, BASEMAPS, coverage mask
    │         animation.js # AnimationController: requestAnimationFrame, play/pause
    ├── v1/                # LEGACY — do not touch
    └── shared/ api.js controls.js legend.js time-wheel.js tops-cores.js
```
`v2/app.js` holds a single `state` object and wires DOM in `setupEventListeners()`.
`shared/controls.js` (`UIControls`) populates selects and reads control values.

## Invariants
- **v2 only.** v1 is legacy. Launch via Compose (builds v2); e2e/screenshots target the v2
  frontend (`frontend-v2:80`). If you `docker build` the frontend image directly you get v1.
- **Animation continuity.** Never `animator.stop()/reset()` or `clearRadarLayer()` before new
  frames are ready. Field/time-window/colormap/range changes all stage frames in the
  background via `_loadFramesWithContinuity(loadFn, opts)` then atomically `setFrames()`.
- **All user-facing text in Spanish (es-AR).** Translate `setStatus`/error/aria-label/title/
  button text. **Never** translate `console.log/warn/error`. No i18n framework — edit in place.
- **Basemaps** go through `MapManager.setBasemap(key)` — never touch `_baseLayer` directly.

## Domain conventions
- **`product_key` `o`-suffix = UNFILTERED** (e.g. `COLMAXo`, `DBZHo`). No suffix = **filtered**
  (polarimetric). The "Filtered" toggle has **inverted** logic: checked = show filtered (no
  suffix); `state.showUnfilteredProducts` is the inverse of the checkbox.
- **`COVERAGE_MODES`** (`v2/app.js`): `cd` (C+D) → volumes `01`,`02`, filtered available;
  `vig` (Vigilancia) → volume `04`, filtered NOT available. Persisted to
  `webmet25_coverage_mode`. Frame loads read `getActiveCoverageMode().volNrs`/`.strategy`.
- **Tops & Cores** only meaningful for the `COLMAX` field (`isTopsCoresAvailableForField`). `TopsCoresLayer` pre-loads data for all frames via `loadForFrames(frames)` and displays synchronously via `showFrame(frameIndex)`. Two panes: `topsCoresBlobPane` (z-440, blob polygon fills) + `topsCoresPane` (z-450, SVG core markers). No separate marker for tops — top altitude appears in the core marker tooltip.

## localStorage keys (the source of truth is the code; full table in copilot-instructions)
`webmet25_selected_basemap` (default **`argenmap`** — note: copilot-instructions historically
said OSM/`selectedBasemap`, that was stale), `webmet25_show_filtered_fields`,
`webmet25_show_inactive_radars`, `webmet25_coverage_mode` (`cd`), `webmet25_coverage_visible`,
`webmet25_coverage_opacity` (0.4), `webmet25_tops_cores_visible`, `webmet25_tops_cores_size`,
`webmet25_smooth_enabled`, `webmet25_smooth_sigma`, `webmet25_live_refresh_interval_ms`.
Time window lives in `state.activeTimeWindowHours` (default 1.5h), not localStorage.

## Adding a control (the pattern)
1. DOM in `index.html` (panels are static; selects are populated by JS).
2. Wire the listener in `app.js` `setupEventListeners()`; keep state on the `state` object.
3. Persist user prefs to a `webmet25_*` localStorage key (add a getter near the others).
4. If it triggers a data reload, route through `_loadFramesWithContinuity` — never stop first.
5. Spanish label/tooltip. Reuse the `.filter-info-tip` / `.filter-info-popup` "?" pattern.

## e2e gotcha
Radar checkboxes and other controls live in `display:none` panels. In Playwright use
`wait_for_selector(..., state="attached")`, not the default (visible), or it times out.
`tests/e2e/` is a package — each file reads `FRONTEND_URL` locally. See `docs/E2E_TESTING.md`.

## Verify changes
Use the `run-webmet25` procedure (`.claude/skills/run-webmet25/SKILL.md`): bring up the Compose stack, capture screenshots
(`screenshot.py`), and run `docker exec radar_tests pytest tests/e2e/ -q` (must stay green).
