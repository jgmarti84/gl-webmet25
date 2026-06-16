# E2E_TESTING.md — End-to-End (Browser) Tests

> **Purpose:** How to run WebMet25's Playwright end-to-end tests, what they cover, and how to set up an equivalent environment **outside** the project's Docker stack (e.g. on a bare machine or a different CI).

---

## 1. What these tests are

The e2e tests drive a **real headless Chromium** (via Playwright) against the running
**v2 frontend** + API, exercising behavior a unit test cannot: rendering, DOM
filtering/sorting, the colormap creator canvas + drag, and the iOS-style time wheel.

**Location:** [`tests/e2e/`](../tests/e2e/)

| File | Feature under test |
|------|--------------------|
| `test_admin_panel.py` | Admin panel: load, OHMC logo, back-to-map, per-column filters + global search, text-filter row hiding, sortable columns + ▲/▼ indicator, icon row actions, colormap creator (gradient canvas, draggable ticks, "Cerrar" label) |
| `test_radar_ordering.py` | Main map: load, radar list ordering rule (RMA before AR, `RMA00` last, active before inactive), admin link present |
| `test_time_wheel.py` | Custom time range: both wheels render (24h + 60m = 84 items), two columns + selection band, tap-to-select drives the canonical input |
| `conftest.py` | Shared fixtures: Basic-Auth context, JS-error capture, screenshot-on-failure |

> ⚠️ These tests require the **v2 frontend** — the time wheel is wired only by `js/v2/app.js`. Pointing them at a v1 frontend will fail `test_time_wheel.py`.

---

## 2. Required environment (any framework)

The tests are environment-agnostic Python + Playwright. To run them anywhere you need:

| Requirement | Notes |
|-------------|-------|
| **Python 3.11** | matches the project |
| **pip packages** | `pytest`, `pytest-asyncio`, `pytest-playwright` (see [`tests/requirements.txt`](../tests/requirements.txt)) |
| **Playwright Chromium** | `playwright install chromium` + system libs `playwright install-deps chromium` |
| **A running API** | seeded DB (radars, products, the 8 system colormaps). Reachable at `API_BASE_URL`. |
| **A running v2 frontend** | nginx serving the v2 build with the admin Basic-Auth htpasswd. Reachable at `FRONTEND_URL`. |
| **Network reachability** | the test host must reach `FRONTEND_URL` (the frontend in turn proxies `/api/v1/*` to the API). |

### Environment variables

| Var | Default (devcontainer) | Meaning |
|-----|------------------------|---------|
| `FRONTEND_URL` | `http://frontend-v2:80` | Base URL of the **v2** frontend under test |
| `API_BASE_URL` | `http://api:8000` | API base (used by the API contract tests, not strictly by e2e) |
| `ADMIN_USERNAME` | `admin` | HTTP Basic Auth user for `/admin` — **must match** the frontend's htpasswd |
| `ADMIN_PASSWORD` | `change-me` | HTTP Basic Auth password for `/admin` |

The admin panel is behind nginx Basic Auth; the frontend container generates its
`admin.htpasswd` from `ADMIN_USERNAME`/`ADMIN_PASSWORD` at startup
([`frontend/docker-entrypoint.sh`](../frontend/docker-entrypoint.sh)). The tests authenticate
with the same values via Playwright `http_credentials`, so **keep them in sync**.

---

## 3. Running inside the project (Docker — recommended)

The dev stack already ships a `tests` service (Playwright + Chromium preinstalled in
[`tests/Dockerfile`](../tests/Dockerfile)).

```bash
# From the repo root. Compose both files (base + devcontainer override).
DC="docker compose -f docker-compose.yml -f docker-compose.devcontainer.yml"

# 1. Bring up the API, a v2 frontend, the test DB, and the tests container.
$DC up -d --build radar_db redis db-init api frontend-v2 radar_db_test db-init-test tests

# 2. Run the e2e suite inside the tests container.
docker exec radar_tests pytest tests/e2e/ -v

# Run a single file / test:
docker exec radar_tests pytest tests/e2e/test_admin_panel.py -v
docker exec radar_tests pytest tests/e2e/test_time_wheel.py::test_time_wheels_render -v

# Tear down when done:
$DC down            # add -v to also drop volumes
```

**Custom admin credentials:** set them once in a repo-root `.env` (compose reads it):
```dotenv
ADMIN_USERNAME=observatorio
ADMIN_PASSWORD=your-strong-password
```
Both the `frontend-v2` and `tests` services pick these up, so auth stays consistent.

**Screenshots on failure** are written to `tests/e2e/screenshots/` (git-ignored). To copy them out of the container:
```bash
docker cp radar_tests:/app/tests/e2e/screenshots ./e2e-screenshots
```

> The whole suite is also runnable with `docker exec radar_tests pytest` (api + indexer + e2e). See [`.github/copilot-instructions.md`](../.github/copilot-instructions.md) → *Testing Strategy*.

---

## 4. Running outside Docker (bare machine / other CI)

Use this when you don't have the Docker stack — e.g. a laptop or a generic CI runner.
You still need an API + v2 frontend reachable from the test host (run them however you
like; the snippet below uses the project's own containers just for those two).

```bash
# 0. Have an API + v2 frontend running somewhere and note their URLs.
#    (Minimal project way: `docker compose up -d radar_db redis db-init api`
#     and serve the v2 frontend — see frontend/Dockerfile, FE_VERSION=v2.)

# 1. Python env
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r tests/requirements.txt

# 2. Playwright browser + OS libs
playwright install chromium
playwright install-deps chromium      # needs sudo on Debian/Ubuntu

# 3. Point the tests at your running services + admin creds
export FRONTEND_URL="http://localhost:8090"   # your v2 frontend
export ADMIN_USERNAME="admin"
export ADMIN_PASSWORD="change-me"

# 4. Run (PYTHONPATH=tests so the tests can `from conftest import ...`)
PYTHONPATH=tests pytest tests/e2e/ -v
```

### Generic CI sketch (GitHub Actions style)
```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.11" }
- run: pip install -r tests/requirements.txt
- run: playwright install --with-deps chromium
- run: PYTHONPATH=tests pytest tests/e2e/ -v
  env:
    FRONTEND_URL: http://localhost:8090
    ADMIN_USERNAME: admin
    ADMIN_PASSWORD: change-me
```
(Start the API + v2 frontend in a prior step / service container, e.g. via
`docker compose up -d`.)

### Quick local dev loop (headed / debug)
Running directly (not in the container) you can watch the browser and step through:
```bash
PYTHONPATH=tests pytest tests/e2e/ --headed --slowmo 300        # watch it run
PYTHONPATH=tests PWDEBUG=1 pytest tests/e2e/test_admin_panel.py # Playwright Inspector
```

---

## 5. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `error while loading shared libraries: libnspr4.so` | Chromium OS libs missing → `playwright install-deps chromium` (sudo). |
| Admin tests get a 401 / blank page | `ADMIN_USERNAME`/`ADMIN_PASSWORD` don't match the frontend's htpasswd. Sync them (and rebuild/restart the frontend if you changed its env). |
| `test_time_wheels_render` fails with `items=0` | `FRONTEND_URL` points at a **v1** frontend. Point it at the v2 frontend. |
| `net::ERR_CONNECTION_REFUSED` | `FRONTEND_URL` not reachable from the test host (wrong host/port, or frontend not up). |
| Radar order / empty radar list | API not seeded. Run `python -m radar_db.manage seed` (the `db-init` container does this automatically). |
| Tests hang on `networkidle` | Frontend can't reach the API (nginx `/api/v1` proxy target down). Check the API is up. |

---

**Document Version:** 1.0.0  
**Last Updated:** June 4, 2026
