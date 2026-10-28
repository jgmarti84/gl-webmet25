---
name: add-db-migration
description: Create and apply an Alembic database migration for WebMet25 (PostgreSQL/PostGIS). Use when adding/altering a table or column in database/radar_db/models.py, writing a migration under database/migrations/versions, or running the manage.py migrate/init commands. Covers the workflow and the PostgreSQL ENUM + Alembic-stamping gotchas that bite here.
---

# Add a DB migration (WebMet25 — Alembic + PostGIS)

The schema lives in `database/radar_db/models.py` (SQLAlchemy 2.0 + GeoAlchemy2). Migrations are
Alembic, under `database/migrations/versions/` (config in `database/alembic.ini`,
`database/migrations/env.py`). A `manage.py` CLI wraps the common ops. Full schema reference:
`.github/copilot-instructions.md` §"Database Schema" + §"Tops & Cores … Migration Notes".

## Workflow
1. Edit the model in `database/radar_db/models.py` (add column/table, FK, index, etc.).
2. Generate a migration (autogenerate compares models vs DB):
   ```bash
   python database/radar_db/manage.py migrate --autogenerate -m "add <thing>"
   # (see `manage.py migrate -h`; existing versions show the file/naming style:
   #  YYYYMMDD_<rev>_<slug>.py)
   ```
3. **Review the generated file** — autogenerate is not reliable for PostGIS geometry columns,
   server defaults, or ENUM changes. Hand-fix per the gotchas below.
4. Apply and verify:
   ```bash
   python database/radar_db/manage.py migrate        # upgrade to head
   python database/radar_db/manage.py check           # verify schema/heads
   python database/radar_db/manage.py info            # current revision
   ```
   (Inside the stack, run these in the DB/init container; see the `run-webmet25` skill.)

## Gotchas (these are real here — see existing versions/ files)
- **PostgreSQL ENUM (`cogstatus`).** When a migration references the existing enum, use
  `sqlalchemy.dialects.postgresql.ENUM(..., name="cogstatus", create_type=False)` — NOT
  `sa.Enum(..., create_type=False)`. `sa.Enum` with `create_type=False` does **not** reliably
  suppress `CREATE TYPE` inside `op.create_table`, so the migration fails on "type already
  exists". The `COGStatus` enum is shared (e.g. `TopsAndCores` reuses it) — never define a new
  enum type for it.
- **Enum labels are the member NAMES** (uppercase: `AVAILABLE`, `PENDING`, …) as stored in PG,
  even though `COGStatus` values are lowercase strings — keep that in mind for data migrations.
- **`manage.py init` stamps Alembic head after `create_all()`** — so a fresh install
  (`create_all`) and a migration-based upgrade stay in sync. Don't hand-stamp; let `init`/`migrate`
  manage the revision.
- **PostGIS geometry** columns (`Geometry('POLYGON', srid=4326)`) need GeoAlchemy2 imported in the
  migration and usually manual `op.add_column`/`op.create_table` — autogenerate may emit wrong types.
- **Transactional writes** — never write to the DB outside a transaction (applies to data
  migrations too).

## Verify
After migrating, run the API contract tests (the schema backs the endpoints) and, for schema the
frontend reads, the e2e suite — both via the `run-webmet25` skill:
```bash
docker exec radar_tests pytest tests/api/ -q
```
