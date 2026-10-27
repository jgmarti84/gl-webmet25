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
| `test_registration_flow.py` | Public sign-up: sign up (with the optional full name, which the account panel then shows), verify the mail from its link, log in with the mail; an unverified account cannot log in and can ask for a new mail; password recovery end to end; the form checks the passwords; a registered mail gets the same screen; a garbage verification link. The mails are read from Mailpit (see below) |
| `conftest.py` | Shared fixtures: login helper + shared admin session, JS-error capture, screenshot-on-failure |

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
| **A running v2 frontend** | nginx serving the v2 build. Reachable at `FRONTEND_URL`. |
| **An admin account** | created by `db-init` from `ADMIN_USERNAME` / `ADMIN_PASSWORD` (see below). |
| **Network reachability** | the test host must reach `FRONTEND_URL` (the frontend in turn proxies `/api/v1/*` to the API). |

### Environment variables

| Var | Default (devcontainer) | Meaning |
|-----|------------------------|---------|
| `FRONTEND_URL` | `http://frontend-e2e:80` | Base URL of the **v2** frontend under test (code default: `http://frontend-v2:80`) |
| `API_BASE_URL` | `http://api-e2e:8000` | API base (used by the API contract tests, not strictly by e2e; code default: `http://api:8000`) |
| `ADMIN_USERNAME` | `admin` | Username of the admin account the tests log in with |
| `ADMIN_PASSWORD` | *(none)* | Its password — required, tests cannot log in without it |
| `MAILPIT_URL` | `http://mailpit:8025` | Local mailbox the registration tests read the verification and reset mails from |

**Which database each suite writes to.** `tests/api` and `tests/e2e` are black-box: they go through a running API
and frontend, and they write (the e2e viewer, the admin's sessions). In the dev stack they run against an isolated
copy, never against your main database:

| Suites | Target | Database |
|---|---|---|
| `tests/auth`, `tests/indexer` | in process | `radar_test_db` (empty; every test rolls back) |
| `tests/api`, `tests/e2e` | `api-e2e`, `frontend-e2e` | `radar_e2e_db` in its own container `radar_db_e2e` (initialized by `db-init-e2e`, COGs loaded by `indexer-e2e`) |
| your own use | `api`, `frontend-v2` | `radar_prod_db` (no test touches it) |

`api-e2e` answers to the name `api` inside the private `e2e` network, so `frontend-e2e` runs the normal frontend image
with its normal `nginx.conf`. The test services publish no ports.

> **Never point `API_BASE_URL` or `FRONTEND_URL` at stage or the operational server:** the suites create the user
> `e2e-viewer` and admin sessions in whatever database is behind them.

Every page requires a login. The tests sign in through the `/login` form with the account that
`db-init` creates from the same `ADMIN_USERNAME` / `ADMIN_PASSWORD` variables of your `.env`. The map, radar detail and admin tests
start already logged in (`browser_context_args` with the shared `admin_storage_state`). One test creates the viewer
`e2e-viewer` through the admin API (or reactivates it) and deactivates it at the end.

nginx limits `/api/v1/auth/login` to 10 requests/minute per IP, so the admin panel tests **share one
login**: its browser state is reused by every test and renewed every 10 minutes (the access cookie
lives 30). Do not re-run the suite more than a few times per minute. Keep `ACCESS_TOKEN_TTL_MINUTES` at 15 or more
while running the suites: the shared login is reused for up to 10 minutes and `tests/api` logs in once per run.

**Registration tests and the local mailbox.** `api-e2e` has the sign-up on and sends its mails to **Mailpit** (container `mailpit` of the dev stack, the same one the main API uses; screen at `http://localhost:8025`). `test_registration_flow.py` empties the mailbox, reads the mail through Mailpit's HTTP API (`MAILPIT_URL`) and opens its link against `FRONTEND_URL`. Things to know:

- nginx limits the sign-up endpoints (`register`, `verify-email`, `resend-verification`, `forgot-password`, `reset-password`) to 10 requests/minute per IP, burst 5, in a counter of its own. The file makes 13 such requests, so its tests pace themselves (12 s between tests). If a `429` still shows up, wait a minute and re-run the test that failed.
- `api-e2e` uses `MAIL_MIN_INTERVAL_SECONDS=0`: the tests ask for a second mail to the same account right after the first, and with a wait the API answers 202 but sends nothing. The interval itself is covered by `tests/auth`.
- Every account the tests create (`e2e-reg-*`) is deactivated at the end through the admin API.
- Mails use the domain `ejemplo.com.ar`: addresses on `.test` or `.local` are rejected by the mail validation.

---

## 3. Running inside the project (Docker — recommended)

The dev stack already ships a `tests` service (Playwright + Chromium preinstalled in
[`tests/Dockerfile`](../tests/Dockerfile)).

```bash
# From the repo root. Compose both files (base + devcontainer override).
DC="docker compose -f docker-compose.yml -f docker-compose.devcontainer.yml"

# 1. Bring up the dev stack, the isolated test stack and the tests container (same as `make dev-up`).
$DC up -d --build radar_db redis db-init api frontend-v2 radar_db_test db-init-test radar_db_e2e db-init-e2e api-e2e frontend-e2e indexer-e2e tests

# 2. Run the e2e suite inside the tests container.
docker exec radar_tests pytest tests/e2e/ -v

# Run a single file / test:
docker exec radar_tests pytest tests/e2e/test_admin_panel.py -v
docker exec radar_tests pytest tests/e2e/test_time_wheel.py::test_time_wheels_render -v

# Stop when done (keeps containers and the test databases for the next run):
$DC stop
```

**Admin credentials:** set them once in a repo-root `.env` (compose reads it):
```dotenv
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-strong-password   # 12+ characters
```
`db-init` (main stack) and `db-init-e2e` (test stack) create the account from them and the `tests` service reads the
same values, so they stay consistent.

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
export ADMIN_PASSWORD="your-strong-password"

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
    ADMIN_PASSWORD: ${{ secrets.E2E_ADMIN_PASSWORD }}
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
| Admin tests end up on `/login`, or get 401 / 429 | `ADMIN_USERNAME` / `ADMIN_PASSWORD` don't match an existing admin account, or `/api/v1/auth/login` was rate limited (10/min per IP): wait a minute and re-run. |
| `test_time_wheels_render` fails with `items=0` | `FRONTEND_URL` points at a **v1** frontend. Point it at the v2 frontend. |
| `net::ERR_CONNECTION_REFUSED` | `FRONTEND_URL` not reachable from the test host (wrong host/port, or frontend not up). |
| Radar order / empty radar list | API not seeded. Run `python -m radar_db.manage seed` (the `db-init` container does this automatically). |
| Tests hang on `networkidle` | Frontend can't reach the API (nginx `/api/v1` proxy target down). Check the API is up. |
| Registration test: `No llegó un mail a …` | Mailpit is not running or `MAILPIT_URL` is wrong, or the API did not send (a mail cap, or the sign-up is off: `GET /api/v1/auth/options` on `api-e2e` must show `registration: true`). Look at `http://localhost:8025`. |
| Registration test: a locator is not visible after a request | nginx answered `429` (the sign-up endpoints allow 10 requests/minute per IP). Wait a minute and re-run that test. |

---

**Document Version:** 1.2.0  
**Last Updated:** October 27, 2026
