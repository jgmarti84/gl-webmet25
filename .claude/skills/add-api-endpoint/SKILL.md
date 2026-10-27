---
name: add-api-endpoint
description: Add a new endpoint (or router) to the WebMet25 FastAPI backend with the mandatory 5-test API contract. Use when adding/changing a REST endpoint under api/app/routers, wiring a new router, or writing the required tests/api contract tests. Covers the router pattern, registration, the never-500 rule, pagination reuse, and the 5 required tests per endpoint.
---

# Add an API endpoint (WebMet25 FastAPI)

The API lives in `api/app/` (FastAPI + SQLAlchemy 2.0 + PostGIS via GeoAlchemy2). Endpoints
are grouped into **one router file per resource** under `api/app/routers/` and registered in
`api/app/main.py`. The full contract (DB schema, endpoint list, query params) is in
`.github/copilot-instructions.md` §"API Contract"; read it before adding/altering an endpoint.

## Invariants (enforced by review + tests)
- **Never return HTTP 500.** Handle a missing DB record / missing file on disk with an explicit
  4xx (`raise HTTPException(status_code=404, detail=...)`). A 500 is always a bug. There's a
  global exception handler (`main.py`) as a backstop — don't rely on it for expected cases.
- **DB writes are transactional.** Use a transaction block; the admin router has a
  `_commit_or_conflict(db, detail)` helper that maps `IntegrityError` → 409. Reuse it.
- **Type hints required** (mypy), `black` + `flake8` clean, Python 3.11.
- **Don't add test deps to `api/requirements.txt`** — tests have their own `tests/requirements.txt`.

## Router pattern
1. Create `api/app/routers/<resource>.py`:
   ```python
   from fastapi import APIRouter, Depends, HTTPException, Query
   from sqlalchemy.orm import Session
   from radar_db import get_db, <Model>

   router = APIRouter(tags=["<resource>"])

   @router.get("/<resource>")
   def list_<resource>(db: Session = Depends(get_db)):
       ...
   ```
2. Register it in `api/app/main.py`: add to the `from .routers import (...)` block and
   `app.include_router(<resource>_router, prefix=settings.api_prefix)` (prefix is `/api/v1`).
   Also export it from `api/app/routers/__init__.py` if that's where names are surfaced.
3. **Pagination**: reuse the `/cogs` pattern (`api/app/routers/cogs.py`) — `page` / `page_size`
   `Query` params, `offset = (page-1)*page_size`, and a response carrying `total`, `page`,
   `page_size`. (Products & admin references endpoints currently lack pagination — add it the
   same way if you touch them.)
4. **Missing file/record**: check `.first()` for `None` → 404; check `path.exists()` before
   reading a COG → 404 (see `tiles.py` / `frames.py`), never let it bubble to a 500.

## The mandatory 5-test contract (per endpoint)
Tests live in `tests/api/` — **one test file per router**, named to match
(`routers/<resource>.py` → `tests/api/test_<resource>.py`). Use `httpx`, no fixtures, read the
base URL from env. Every endpoint needs ALL five:

```python
import httpx, os
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
PREFIX = "/api/v1/<resource>"

def test_<resource>_returns_200():                # 1. status (happy path 2xx)
def test_<resource>_response_has_required_fields():  # 2. all contract fields present
def test_<resource>_returns_json():               # 3. content-type application/json
def test_<resource>_invalid_<x>_returns_404():    # 4. error path → correct 4xx (NEVER assert 500)
def test_<resource>_returns_list():               # 5. field types match the contract
```
Rules: always read `API_BASE_URL` from env (never hardcode), test happy AND error paths, never
assert a 500 (a 500 means a bug to fix, not a valid response), and don't `@pytest.mark.skip`
without a comment.

## Run
```bash
# stack must be up (run-webmet25 skill)
docker exec radar_tests pytest tests/api/test_<resource>.py -v
docker exec radar_tests pytest tests/api/ -q          # whole API suite
```
