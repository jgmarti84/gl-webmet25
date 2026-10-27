---
name: run-webmet25
description: Build, launch, drive, screenshot, and test the WebMet25 radar visualization app (Docker Compose stack — PostGIS + Redis + FastAPI + nginx/Leaflet frontend + admin panel). Use when asked to run, start, build, launch, serve, screenshot, smoke-test, or drive WebMet25 / the radar map / the admin panel locally.
---

# Run WebMet25

WebMet25 is a multi-service **Docker Compose** app: PostGIS DB + Redis + FastAPI API +
an nginx/Leaflet web frontend (v2) + an admin SPA. You don't `npm start` it — you bring
the stack up with Compose and drive it through the browser. The browser harness already
exists and is committed: the **`radar_tests` container** has Playwright + Chromium baked
in (`tests/Dockerfile`), used by the Python e2e suite in `tests/e2e/` and by the
screenshot driver `.claude/skills/run-webmet25/screenshot.py`. The API is driven with
`curl`.

> Paths below are relative to the repo root (the unit). Commands were run on Linux/WSL
> (Ubuntu 24.04) with Docker Engine + Compose v2.

## Prerequisites

- **Docker Engine + Compose v2** (the only hard requirement — everything runs in containers).
  If `docker ps` fails with a socket permission error: `sudo usermod -aG docker $USER`
  then restart your shell/WSL session.
- No host Node or browser needed — Playwright + Chromium live inside the `radar_tests` image.

## Build & launch the drivable stack (agent path)

Brings up the API, the **v2** frontend, the test DB, and the `radar_tests` driver container.
First run builds images (api/frontend/tests — a few minutes; the tests image installs
Playwright+Chromium). Subsequent runs are cached/fast.

```bash
DC="docker compose -f docker-compose.yml -f docker-compose.devcontainer.yml"
$DC up -d --build radar_db redis db-init api frontend-v2 radar_db_test db-init-test tests
```

`db-init` / `db-init-test` are one-shot seeders — they show `Exited (0)`, which is success
(they create + seed the schema, incl. the 8 system colormaps). Wait for the API to go healthy:

```bash
until [ "$(docker inspect -f '{{.State.Health.Status}}' radar_api)" = "healthy" ]; do sleep 2; done
```

## Drive the GUI (agent path)

**Run the real-browser e2e suite** (admin panel, radar ordering, colormap creator, time wheel):

```bash
docker exec radar_tests pytest tests/e2e/ -q          # 17 passed
docker exec radar_tests pytest tests/e2e/ -v          # per-test detail
```

**Capture screenshots** of the map, admin panel, colormap creator, and time wheel. The
driver runs inside `radar_tests` (reusing its Chromium), targeting `frontend-v2:80` with
the devcontainer admin creds (`admin`/`change-me`):

```bash
docker cp .claude/skills/run-webmet25/screenshot.py radar_tests:/tmp/screenshot.py
docker exec radar_tests python /tmp/screenshot.py     # prints radar_count + time_wheel_items
docker cp radar_tests:/tmp/webmet-shots ./webmet-shots
```

Produces `webmet-map.png`, `webmet-timewheel.png`, `webmet-admin-radars.png`,
`webmet-colormap-creator.png`. Override target/creds with `FRONTEND_URL`, `ADMIN_USERNAME`,
`ADMIN_PASSWORD` env vars.

## Drive the API (curl smoke)

API is published on host `:8000`; the v2 frontend on host `:8090` (proxies `/api/v1`).

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/health          # 200
curl -s http://localhost:8000/api/v1/radars | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["radars"]),"radars")'
curl -s http://localhost:8000/api/v1/colormap/names                            # 8 system colormaps
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8090/                # 200
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8090/admin           # 401 (Basic Auth)
curl -s -o /dev/null -w '%{http_code}\n' -u admin:change-me http://localhost:8090/admin   # 200
```

## Run for a human

The **base** stack serves the v2 frontend on `http://localhost` (port 80):

```bash
docker compose up -d --build radar_db redis db-init api frontend
# → http://localhost  (admin at /admin, creds: ADMIN_USERNAME / ADMIN_PASSWORD from .env)
```

(`docker compose up -d` brings up everything incl. the `indexer`, which needs COG files —
see Gotchas. For UI work the line above is enough.)

## Tear down

```bash
docker compose -f docker-compose.yml -f docker-compose.devcontainer.yml down   # add -v to drop volumes
# (or, for the human/base stack:)  docker compose down
```

## Gotchas

- **v2 vs v1.** Compose builds the frontend with `FE_VERSION=${FE_VERSION:-v2}` → you get
  **v2** by default (good). But the *Dockerfile's* `ARG FE_VERSION` defaults to **v1** — if
  you ever `docker build` the frontend image directly (no Compose), you get v1, where the
  **time wheel and admin "back to map" are NOT wired** (only `js/v2/app.js` wires them).
  Always launch via Compose, and point e2e/screenshots at a v2 frontend.
- **Two different admin logins.** The base `frontend` (:80) has **no default**:
  `ADMIN_USERNAME` / `ADMIN_PASSWORD` must be set in the repo-root `.env`, or Compose
  refuses to start. The devcontainer `frontend-v2` (:8090) and the `tests` container default
  to `admin` / `change-me`. Whoever authenticates (e2e, screenshots) must use the same pair
  as the frontend it targets.
- **Admin is behind nginx HTTP Basic Auth** (`/admin` and `/api/v1/admin/*`). The admin API
  is reachable WITHOUT auth on the API container's own port `:8000` (nginx adds the auth
  layer) — handy for scripted admin testing.
- **New colormaps need a cache flush.** The public `/colormap/*` endpoints read a 5-min TTL
  cache; after creating/editing a colormap via the admin API, `POST /api/v1/colormap/cache/invalidate`
  (the admin UI does this automatically). Otherwise the new colormap 404s on `/colormap/colors/{name}`.
- **No imagery without the indexer.** The `api`/`indexer` mount `../product_output` and
  `../tops_and_cores` (one level *above* the repo). The map shows radar/product metadata even
  when empty, but no radar frames. Don't start `indexer` unless those host dirs have COG files.
  Also: with no indexed COGs, `/products?vol_nr=…&strategy=…` returns 0, so the **field menu /
  coverage modes never populate** (availability is derived from indexed COGs, not the products
  table). To exercise dropdown/switch/field/coverage behavior without real files, seed fake
  `radar_cogs` rows:
  ```bash
  docker exec -i radar_db-gl \
    psql -U radar -d radar_prod_db < .claude/skills/run-webmet25/seed_sample_cogs.sql
  ```
  (`psql` inside the DB container connects over the local socket, so no password is needed.)
  Frame **images** still 404 (no files on disk) — fine for verifying dropdowns/switches/field
  logic. **Clear the seed before running the committed e2e suite**
  (`DELETE FROM radar_cogs WHERE file_path LIKE '/sample/%';`) — the extra rows shift init
  timing and can trip the geolocation `ipapi.co` flake in `test_main_map_loads`. Ad-hoc UI
  drivers: `verify_wave2.py` (visual), `verify_wave3.py` (field/coverage behavior) — same
  run pattern as `screenshot.py`.
- **e2e: hidden-panel elements.** The radar checkboxes live inside a `display:none` panel, so
  `wait_for_selector(..., state="attached")` — not the default *visible* — or it times out.
- **`tests/e2e/` is a package** (`__init__.py`), so `from conftest import X` won't resolve;
  each e2e file reads `FRONTEND_URL = os.getenv(...)` locally (matches the API-test convention).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker ... permission denied ... /var/run/docker.sock` | `sudo usermod -aG docker $USER`, then restart the shell/WSL session. |
| Chromium `error while loading shared libraries: libnspr4.so` (host only) | `playwright install-deps chromium` (sudo). Inside `radar_tests` it's already installed. |
| e2e `TimeoutError: waiting for locator ... to be visible` | Element is in a hidden panel — use `state="attached"`. |
| Admin page/tests get **401** | `ADMIN_USERNAME`/`ADMIN_PASSWORD` don't match the frontend's htpasswd. Sync them (rebuild/restart frontend if changed). |
| `test_time_wheels_render` fails `items=0` | `FRONTEND_URL` points at a v1 frontend — point at the v2 one. |
| New colormap 404s on `/colormap/colors/{name}` | Flush the cache: `POST /api/v1/colormap/cache/invalidate`. |
| Map radar list empty | API not seeded — ensure `db-init` ran (`docker logs radar_db_init-gl`). |

## The driver

`.claude/skills/run-webmet25/screenshot.py` — headless-Chromium screenshot + smoke driver
(runs inside `radar_tests`). The full browser regression harness is the project's own
Python+Playwright e2e suite in `tests/e2e/` (see [docs/E2E_TESTING.md](../../../docs/E2E_TESTING.md)).
