---
name: add-e2e-test
description: Add or run a Playwright browser end-to-end test for the WebMet25 v2 frontend (the Leaflet map UI or admin panel). Use when asked to write an e2e/browser test, add a regression test for a frontend behavior, or test the map/admin UI in a real browser. Covers the tests/e2e conventions, the hidden-panel + auth gotchas, and how to drive data-dependent behavior with seeded COGs.
---

# Add an e2e test (WebMet25 v2 frontend)

Browser e2e tests live in `tests/e2e/` and run with **pytest + Playwright** inside the
`radar_tests` container (Chromium + libs baked into `tests/Dockerfile`). They target the
**v2 frontend** (`FRONTEND_URL`, default `http://frontend-v2:80`). How to run the suite
(Docker / bare / CI) is in `docs/E2E_TESTING.md`; use the `run-webmet25` skill to bring the
stack up first.

## Conventions (match the existing files)
- **One test file per area** (`test_admin_panel.py`, `test_radar_ordering.py`, `test_time_wheel.py`).
- `tests/e2e/` is a **package** — `from conftest import X` won't resolve. Each file reads its
  own `FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend:80")` at module top.
- The shared `tests/e2e/conftest.py` provides the Playwright context with `http_credentials`
  (admin Basic Auth), a `js_errors` fixture (fails the test on `console.error`), and
  screenshot-on-failure. Take `page` (and `js_errors` when relevant) as fixture args.
- Prefer `page.eval_on_selector[_all]` for reading DOM/state; assert on observable DOM.

## Gotchas (these will bite you)
- **Hidden panels.** Radar checkboxes, the field menu, settings, etc. live in `display:none`
  panels. Use `page.wait_for_selector(sel, state="attached")` (NOT the default visible) or open
  the panel first (`#btn-module-a/b/c`, `#btn-settings`). For a control inside a hidden panel,
  either open the panel or drive it via JS: `page.eval_on_selector(sel, "e => e.click()")` and
  fire input/change with `e.dispatchEvent(new Event('change', {bubbles:true}))`.
- **`js_errors` is strict.** It fails on any `console.error`. The app's geolocation auto-init
  fetches `ipapi.co`, which is CORS/network-blocked in the sandbox and logs a `console.error`;
  because the page is loaded with `wait_until="networkidle"`, that error can land before your
  assertion and make `test_main_map_loads`-style tests flaky/red. Don't add new external
  network calls on load; if asserting "no JS errors", be aware of this pre-existing source.
- **Admin auth.** `/admin` and `/api/v1/admin/*` are behind nginx Basic Auth; the conftest
  context already carries `http_credentials`. Creds default to `admin`/`change-me` (devcontainer).

## Data-dependent behavior (no COG imagery by default)
The seeded DB has **no indexed COGs**, so `/products?vol_nr=…&strategy=…` returns 0 → the field
menu / animation never populate via the live path (the products table has rows, but availability
is derived from indexed COGs). To exercise field/coverage/animation behavior:
- Seed sample rows: `.claude/skills/run-webmet25/seed_sample_cogs.sql`
  (inserts `radar_cogs` rows so the product dropdown + coverage modes populate; frame **images**
  still 404 because no files exist on disk — fine for dropdown/switch/field-selection logic).
- **Clear the seed before running the committed suite** (`DELETE FROM radar_cogs WHERE file_path
  LIKE '/sample/%';`) — the extra rows shift init timing and can trip the geolocation flake above.
- For ad-hoc verification, the `run-webmet25` skill has reusable drivers
  (`verify_wave2.py`, `verify_wave3.py`) showing the JS-dispatch + read-via-eval patterns.

## Skeleton
```python
import os
from playwright.sync_api import Page

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend:80")

def test_<area>_<behavior>(page: Page):
    page.goto(f"{FRONTEND_URL}/", wait_until="networkidle")
    page.wait_for_selector("#radar-list .radar-checkbox-item", state="attached")
    # open the relevant panel, drive controls, assert on observable DOM/state
    ...
```

## Run
```bash
docker exec radar_tests pytest tests/e2e/ -q          # whole suite (keep green)
docker exec radar_tests pytest tests/e2e/test_<area>.py -v
```
