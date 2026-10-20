# OPERATIONS.md — WebMet25 Operational Reference

> Covers disk management, product deletion, and other operational tasks that don't belong in the data-flow or component documentation.

---

## 1. ProductDeleter — Bulk Disk + DB Cleanup

**File:** [`indexer/indexer/deleter.py`](../indexer/indexer/deleter.py)  
**CLI wrapper:** [`scripts/delete_products.sh`](../scripts/delete_products.sh)

`ProductDeleter` deletes COG files from disk **and** their corresponding `RadarCOG` records from the database in a single transaction. Use it for routine retention management or emergency disk-space recovery.

### 1.1 What it Does

1. Scans `ROOT_RADAR_PRODUCTS_PATH` for `.tif` files matching the given criteria (date, radar codes, product keys)
2. Deletes matching files from disk; removes empty parent directories
3. Deletes matching `RadarCOG` records from the database in one transaction
4. Optionally deletes `genpro25.log.YYYY-MM-DD` log files from `LOGS_PATH`

### 1.2 Running the Deleter

```bash
# From inside the indexer container:
docker exec radar_indexer python -m indexer.deleter \
    --date 2026-04-01 \
    --radar-codes RMA1,AR5 \
    --product-keys DBZHo,COLMAXo

# Dry run (shows what would be deleted without deleting):
docker exec radar_indexer python -m indexer.deleter \
    --date 2026-04-01 \
    --dry-run

# Delete all products for a specific date across all radars:
docker exec radar_indexer python -m indexer.deleter --date 2026-04-01
```

### 1.3 Safety Notes

- Always run `--dry-run` first to verify scope before a destructive delete
- The DB delete is transactional — if the transaction fails, the filesystem deletions already made are **not** rolled back. Prefer running during low-activity periods
- `is_active` on Radar is recalculated on the next COGWatcher scan after deletion

---

## 2. Docker Disk Management

Reference commands for Docker/containerd disk cleanup. See also [`scripts/MANAGE_COMMANDS.md`](../scripts/MANAGE_COMMANDS.md).

### 2.1 Check Disk Usage

```bash
# Docker layer + volume summary
docker system df

# Detailed breakdown
docker system df -v
```

### 2.2 Prune Unused Resources

```bash
# Remove stopped containers, dangling images, unused networks (safe)
docker system prune

# Also remove unused volumes and all untagged images (destructive!)
docker system prune -a --volumes
```

### 2.3 Selective Pruning

```bash
# Prune only unused images (keeps ones used by running containers)
docker image prune -a

# Prune only volumes not attached to a running container
docker volume prune

# Remove a specific volume (destructive!)
docker volume rm webmet25_radar_db_data
```

### 2.4 containerd Snapshot Cleanup (WSL2 / Rancher Desktop)

If using containerd as the Docker runtime (Rancher Desktop on WSL2):

```bash
# List containerd namespaces
sudo ctr namespaces list

# Compact unused snapshots in the moby namespace
sudo ctr -n moby snapshots rm $(sudo ctr -n moby snapshots list -q)
```

### 2.5 Journal Log Vacuuming (WSL2)

```bash
# Show journal disk usage
journalctl --disk-usage

# Vacuum logs older than 7 days
sudo journalctl --vacuum-time=7d

# Vacuum to a size limit
sudo journalctl --vacuum-size=100M
```

---

## 3. Database Maintenance

### 3.1 Manual COG Record Cleanup

```bash
# Open an interactive DB shell
docker compose exec db-init python -m radar_db.manage shell

# Delete MISSING records older than 30 days
from datetime import datetime, timedelta
cutoff = datetime.utcnow() - timedelta(days=30)
deleted = session.query(RadarCOG).filter(
    RadarCOG.status == COGStatus.MISSING,
    RadarCOG.updated_at < cutoff
).delete()
session.commit()
print(f"Deleted {deleted} records")
```

### 3.2 Check Database State

```bash
# Row counts, active radars, recent COGs
docker compose exec db-init python -m radar_db.manage info

# Check migration status
docker compose exec db-init python -m radar_db.manage migrate current
```

### 3.3 Full Development Reset

```bash
# Drop all tables + recreate + reseed (development only — destroys all indexed data)
docker compose exec db-init python -m radar_db.manage reset --force --seed
```

---

## 4. Indexer — Missing-File Check

The indexer continuously reconciles the database against the filesystem to mark records for files that have been deleted from disk as `MISSING`. Two watchers use different strategies optimised for their respective corpus sizes.

### 4.1 How each watcher works

| Watcher | Strategy | Trigger | Cost per cycle |
|---|---|---|---|
| **COGWatcher** | Chunked cursor scan — checks `MISSING_CHECK_BATCH_SIZE` records per cycle, ordered by `id`, advancing a cursor | Every scan cycle (30 s) | ~1 s (1 000 `Path.exists()` calls) |
| **TopsAndCoresWatcher** | Full time-windowed scan — queries all `AVAILABLE` records within the retention window | Every 20 cycles (~10 min) | ~14 s (≈13 500 records at 45 days) |

The COG cursor resets to 0 when it reaches the end of the retention window, starting the next pass from the oldest record in the window. A full pass over 45 days of COG records takes approximately 31 hours at default batch size.

### 4.2 Environment variables

| Variable | Default | Description |
|---|---|---|
| `MARK_MISSING_FILES` | `true` | Master on/off switch for both checks |
| `MISSING_CHECK_DAYS` | `45` | Retention window in days. Set to ≥ the longest retention period across all radars. Changing this does not require a schema migration. |
| `MISSING_CHECK_BATCH_SIZE` | `1000` | Records per COG cursor batch. Increase to shorten the full-pass duration; decrease to reduce per-cycle overhead. |

### 4.3 Log patterns

```
# COG: files marked missing in a batch (only logged when count > 0)
Marked N COG file(s) as missing (cursor=12345678)

# COG: individual file marked missing
WARNING - Marked as missing: RMA5/2026/09/07/RMA5_0315_01_...tif

# TopsAndCores: triggered every 20 cycles
WARNING - TOPS_CORES marked as missing: /mnt/.../RMA15_..._TOPS_CORES.geojson
```

### 4.4 Tuning guidance

- **Cursor too slow** (stale MISSING records taking too long to be detected): increase `MISSING_CHECK_BATCH_SIZE` to e.g. `5000`. Each cycle will take ~5 s instead of ~1 s, reducing full-pass time to ~6 hours.
- **Extending retention in radarlib**: update `MISSING_CHECK_DAYS` to match the new maximum retention before the change takes effect, so no files fall outside the check window.
- **Disabling entirely**: set `MARK_MISSING_FILES=false`. Useful during planned maintenance that involves bulk file deletion, to avoid a flood of MISSING records before the DB is also updated.

---

## 6. Indexer Health Checks

```bash
# View real-time indexer logs
docker compose logs -f indexer

# Check if indexer is processing files (look for "Indexed COG" log lines)
docker compose logs --tail=50 indexer

# Verify the watch path is mounted and has files
docker exec radar_indexer ls -la /product_output/

# Run a single scan manually (one-shot, useful for debugging)
docker exec radar_indexer python -m indexer.main --single --debug

# Check DB connection from indexer
docker exec radar_indexer python -m indexer.manage check
```

---

## 7. API Health & Cache

```bash
# Health check
curl http://localhost/api/v1/health

# View frame/tile cache statistics (L1 LRU + L2 Redis)
curl http://localhost/api/v1/tiles/cache/stats

# Flush the colormap in-process cache. Requires an admin session (the admin panel and
# scripts/import_colormap.py already do this for you); with curl, log in first:
curl -c cj.txt -X POST http://localhost/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"<admin>","password":"<password>"}'
curl -b cj.txt -X POST http://localhost/api/v1/colormap/cache/invalidate
```

## 8. User Management

Run these from the repo root (`gl-webmet25`). They use the `db-init` image, so no extra setup is needed.

```bash
# Create an admin (prompts for the password twice, nothing is echoed)
make create-admin U=maria

# Set a new password for any user and close all their sessions
make reset-password U=maria
```

- The **first admin** is created automatically by `db-init` from `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` when there are no users. After the first start, run `make reset-password U=<that user>` and remove both variables from `.env`.
- An admin **cannot reset their own password from the panel**; use `make reset-password` on the server.
- Other users are managed from the admin panel (**Usuarios**): create, change role, activate/deactivate, reset password, close sessions. Users are never deleted, only deactivated.
- If a user is locked out after 5 failed logins, they can try again after 15 minutes, or an admin can reset their password.
- If the API starts with no active admin it logs a warning with the command to create one.

---

**Document Version:** 1.2.0  
**Last Updated:** October 20, 2026
