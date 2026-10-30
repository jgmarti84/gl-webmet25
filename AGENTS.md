# AGENTS.md — gl-webmet25

Instructions for anyone working on this repo, human or AI agent (Claude, Codex,
Copilot, …). **A lean router, not a manual:** it states the rules and points to the
deep reference.

## What this is
WebMet25 is the **data consumer** of the radar system. It ingests Cloud-Optimized
GeoTIFF (COG) files produced by **gl-radarlib** (the producer), indexes them into
PostgreSQL/PostGIS, and serves them through a FastAPI REST API and a Leaflet web
frontend. Docker Compose stack: PostGIS + Redis + FastAPI API + nginx/Leaflet
frontend + admin SPA + a file-watcher indexer.

In a multi-root workspace with gl-radarlib you may read its code directly to check the
output contract.

## Working rules (the same in gl-radarlib, gl-webmet25 and gl-tracker)
1. **Branch from `origin/dev`; open PRs into `dev`.** Never push to `dev` or `main`
   directly. `dev → main` is a separate promotion done by the maintainer. Agents never
   merge PRs.
2. **Propose → approve → apply.** For anything non-trivial, describe the change and
   wait for approval before writing it.
3. **Secrets never go into git.** Credentials live in a gitignored `.env` (copy
   `.env.example`; on an existing machine add lines, don't overwrite). Never print,
   log or paste a secret value; to compare two values, show only their length or
   SAME/DIFFERENT.
4. **Run tests in a container, not on your host** (see Testing). Static checks
   (`docker compose config`, linters) are fine on the host.
5. **Don't delete files to tidy up.** Move them into the gitignored `local/` folder.
6. **PR descriptions.** Agents always cover: what changed and why; where it was tested;
   deployment notes, in order; new `.env` keys; and whether it touches the **radarlib
   output contract**. For PRs written by people these are recommended, not required;
   the ones worth never skipping are new `.env` keys (they must exist before pulling)
   and output-contract changes.

## Read before you touch (route, don't duplicate)
- **Running / driving / testing the app** → `.claude/skills/run-webmet25/SKILL.md`
  (Compose bring-up, screenshots, e2e, curl smoke). Don't reinvent the launch sequence.
- **`.github/copilot-instructions.md`**: the full reference (DB schema, API contract,
  admin API, indexer, v2 frontend architecture, tops & cores pipeline, testing
  contract, tech debt).
- **`docs/DATA_FLOW.md`**: before changing the indexer or API.
- **`docs/COMPONENTS.md`**: before frontend/Leaflet changes.
- **`docs/DISCOVERY_REPORT.md`**: full technical analysis and known risks.
- **`docs/E2E_TESTING.md`**: how the Playwright e2e suite runs.
- **`frontend/AGENTS.md`**: v2 frontend conventions.

## Non-negotiable invariants
- **radarlib output contract.** WebMet25 depends entirely on radarlib's COG/GeoJSON
  format and file names. Never assume a different format without checking radarlib.
  COG is the production format; PNG is deprecated, so don't build on it.
- **v2 is production; v1 is legacy.** Frontend work targets `frontend/public/js/v2/`
  and `shared/`. Don't add features to `js/v1/`. Always launch via Compose (builds v2).
- **Animation continuity.** Never call `animator.stop()`, `animator.reset()` or
  `clearRadarLayer()` before new frames are staged. All loading goes through
  `_loadFramesWithContinuity(loadFn, opts)` (details in `frontend/AGENTS.md`).
- **Never return HTTP 500.** Handle missing files and records explicitly with a
  proper 4xx. A 500 is always a bug.
- **DB writes are transactional.** Never write outside a transaction block.
- **All user-facing UI text is Spanish (es-AR)**, in the map and the admin panel.
  Never translate `console.*` logs. There is no i18n framework; strings are in place.

## Coding conventions
- Python 3.11. Type hints required (mypy). **black** before commit; **flake8** clean.
- `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE_CASE` constants.
- No bare `except:`. Raise specific, descriptive exceptions.

## Testing (full contract in copilot-instructions §Testing)
- Tests live in `tests/` and run inside the `radar_tests` Docker service. Never add
  test dependencies to the api/indexer requirements.
- API contract tests (`tests/api/`, httpx), indexer unit tests (`tests/indexer/`),
  browser e2e (`tests/e2e/`, Playwright, against the **v2** frontend). One test file
  per router.
- Every endpoint needs the 5 tests: status, response fields, content type, error
  path, data types.

## Step-by-step procedures (`.claude/skills/<name>/SKILL.md`)
Claude Code loads these as skills; any other agent can read them as plain docs.
`run-webmet25` (launch/drive/screenshot/test), `frontend-v2-feature` (safe v2 frontend
changes), `add-e2e-test` (Playwright conventions), `add-api-endpoint` (router + 5-test
contract), `add-db-migration` (Alembic + PostgreSQL enum gotchas).
