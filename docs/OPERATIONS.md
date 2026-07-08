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

## 4. Indexer Health Checks

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

## 5. API Health & Cache

```bash
# Health check
curl http://localhost/api/v1/health

# View frame/tile cache statistics (L1 LRU + L2 Redis)
curl http://localhost/api/v1/tiles/cache/stats

# Flush the colormap in-process cache (after editing colormaps in the admin panel)
curl -X POST http://localhost/api/v1/colormap/cache/invalidate
```

---

**Document Version:** 1.0.0  
**Last Updated:** July 8, 2026
