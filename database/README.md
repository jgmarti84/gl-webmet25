# Radar Database Management Guide

This guide covers how to manage the Radar COG database, including initialization, seeding, migrations, and other administrative tasks. You can run commands either **inside the container** or **from outside using Docker**.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Running Commands](#running-commands)
3. [Available Commands](#available-commands)
4. [Database Workflows](#database-workflows)
5. [Migrations](#migrations)
6. [Examples](#examples)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Inside the Container
```bash
python -m radar_db.manage --help
```

### From Outside the Container (Docker)
```bash
docker exec -it db-init python -m radar_db.manage --help
```

---

## Running Commands

### Option 1: Inside the Container (Interactive Shell)

If you're already inside the container or connected via SSH:

```bash
python -m radar_db.manage <command> [options]
```

### Option 2: From Outside (Docker Exec)

Run commands on a running container from your host machine:

```bash
docker exec -it <container_name> python -m radar_db.manage <command> [options]
```

Replace `<container_name>` with your actual container name (e.g., `radar_db`, `app`, etc.). Use `docker ps` to find it.

### Option 3: From Docker Compose

If using `docker-compose`:

```bash
docker-compose exec <service_name> python -m radar_db.manage <command> [options]
```

Replace `<service_name>` with your service name from `docker-compose.yml` (e.g., `db`, `radar-db`, etc.).

---

## Available Commands

### 1. **init** - Initialize Database Tables

Creates all database tables based on the SQLAlchemy models.

**Inside container:**
```bash
python -m radar_db.manage init
```

**From outside (Docker):**
```bash
docker exec -it <container_name> python -m radar_db.manage init
```

**When to use:** First time setup, after dropping all tables, or when schemas change.

---

### 2. **seed** - Load Seed Data

Loads initial/seed data from JSON file into the database.

**Inside container:**
```bash
python -m radar_db.manage seed
```

**From outside (Docker):**
```bash
docker exec -it <container_name> python -m radar_db.manage seed
```

**With custom seed file:**
```bash
python -m radar_db.manage seed -f /path/to/custom_seed.json
```

**When to use:** Populate database with initial data (radars, products, references, etc.).

**Note:** The seeder intelligently handles updates:
- If a record already exists, it skips it (unless values are missing)
- If new columns are added and existing records have NULL values, it updates them
- Useful for incremental seeding after schema changes

---

### 3. **check** - Test Database Connection

Verifies connectivity to the database.

**Inside container:**
```bash
python -m radar_db.manage check
```

**From outside (Docker):**
```bash
docker exec -it <container_name> python -m radar_db.manage check
```

**Output:**
```
✓ Database connection OK!
```
or
```
✗ Database connection FAILED!
```

**When to use:** Troubleshoot connection issues, verify database is running.

---

### 4. **info** - Show Database Information

Displays comprehensive database statistics and current state.

**Inside container:**
```bash
python -m radar_db.manage info
```

**From outside (Docker):**
```bash
docker exec -it <container_name> python -m radar_db.manage info
```

**Shows:**
- Database host, port, name, user
- Record counts for all tables
- Active radars with COG file counts
- Recent COG files

**When to use:** Monitor database state, verify data loads, audit records.

---

### 5. **reset** - Reset Database (DESTRUCTIVE)

⚠️ **WARNING:** Drops ALL tables and data. Use with caution!

**Inside container:**
```bash
python -m radar_db.manage reset
```

**From outside (Docker):**
```bash
docker exec -it <container_name> python -m radar_db.manage reset
```

**With options:**
```bash
# Skip confirmation prompt
python -m radar_db.manage reset --force

# Reset AND immediately reseed with initial data
python -m radar_db.manage reset --force --seed

# Combined (most common for full reset)
python -m radar_db.manage reset --force --seed
```

**When to use:** 
- Complete database refresh
- After major schema changes
- Development/testing environments
- Never in production without backup!

---

### 6. **migrate** - Run Database Migrations

Manage schema changes using Alembic.

#### Generate a New Migration
```bash
python -m radar_db.manage migrate generate -m "Add new column"
```

**Example:**
```bash
python -m radar_db.manage migrate generate -m "JM: adding point coordinates to radars"
```

#### Upgrade to Latest Schema
```bash
python -m radar_db.manage migrate upgrade
```

#### Upgrade to Specific Version
```bash
python -m radar_db.manage migrate upgrade 9f1340ae834d
```

#### Downgrade One Step
```bash
python -m radar_db.manage migrate downgrade
```

#### Downgrade to Specific Version
```bash
python -m radar_db.manage migrate downgrade 9f1340ae834d
```

#### View Migration History
```bash
python -m radar_db.manage migrate history
```

#### Show Current Migration Status
```bash
python -m radar_db.manage migrate current
```

**When to use:** Schema changes, adding/removing columns, index modifications.

---

### 7. **shell** - Interactive Python Shell

Opens an interactive Python shell with database access and all models pre-loaded.

**Inside container:**
```bash
python -m radar_db.manage shell
```

**From outside (Docker):**
```bash
docker exec -it <container_name> python -m radar_db.manage shell
```

**Available objects in shell:**
- `session` - SQLAlchemy database session
- `Radar`, `RadarProduct`, `Reference`, `RadarCOG`, `Volumen`, `Estrategia` - Model classes
- `settings` - Configuration object
- `db_manager` - Database manager

**Example queries in shell:**
```python
# List all radars
radars = session.query(Radar).all()
for r in radars:
    print(f"{r.code}: {r.title}")

# Count COG files
cog_count = session.query(RadarCOG).count()
print(f"Total COGs: {cog_count}")

# Find a specific radar
radar = session.query(Radar).filter_by(code='AR5').first()
print(radar.center_lat, radar.center_long)

# Update a record
radar.is_active = False
session.commit()
```

---

## Database Workflows

### Workflow 1: Complete Fresh Setup

```bash
# 1. Initialize tables
python -m radar_db.manage init

# 2. Load seed data
python -m radar_db.manage seed

# 3. Verify
python -m radar_db.manage info
```

### Workflow 2: Full Reset with Reseed (Recommended for Development)

```bash
python -m radar_db.manage reset --force --seed
```

This single command:
1. Drops all tables
2. Recreates all tables
3. Loads all seed data
4. Verifies completion

### Workflow 3: Schema Change (Adding a Column)

```bash
# 1. Modify your model in radar_db/models.py

# 2. Generate migration
python -m radar_db.manage migrate generate -m "Add new field to Radar"

# 3. Review the generated migration file
# Edit migrations/versions/<hash>_add_new_field_to_radar.py if needed

# 4. Run the migration
python -m radar_db.manage migrate upgrade

# 5. If you have seed data with the new field, reseed
python -m radar_db.manage seed
```

### Workflow 4: Testing Data Updates

```bash
# Open interactive shell
python -m radar_db.manage shell

# Update records directly
radar = session.query(Radar).filter_by(code='AR5').first()
radar.point1_lat = -31.7558357700
radar.point1_long = -57.8983503500
session.commit()

# Exit shell (Ctrl+D)
```

### Workflow 5: Database Troubleshooting

```bash
# 1. Check connection
python -m radar_db.manage check

# 2. View database state
python -m radar_db.manage info

# 3. Check migration status
python -m radar_db.manage migrate current

# 4. If needed, view full migration history
python -m radar_db.manage migrate history

# 5. Interactive debugging
python -m radar_db.manage shell
```

---

## Migrations

### Understanding Migrations

Migrations track schema changes over time using Alembic.

**Key files:**
- `alembic.ini` - Alembic configuration
- `migrations/env.py` - Migration environment setup
- `migrations/versions/` - Individual migration files

### Handling Migration Issues

#### Problem: "cannot drop table X because extension Y requires it"

**Solution:** The migration needs to drop the extension first.

**Fix:**
1. Edit the migration file
2. Add extension drop at the beginning:
   ```python
   op.execute("DROP EXTENSION IF EXISTS postgis_tiger_geocoder CASCADE")
   op.execute("DROP EXTENSION IF EXISTS postgis_topology CASCADE")
   ```
3. Recreate extensions in downgrade:
   ```python
   op.execute("CREATE EXTENSION IF NOT EXISTS postgis_topology")
   op.execute("CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder")
   ```

#### Problem: "Alembic cannot find alembic.ini"

**Solution:** Ensure you're running from the `/app` directory or specify the path.

---

## Examples

### Example 1: Daily Setup Routine

```bash
# From your host machine:
docker exec -it radar_db python -m radar_db.manage info

# Inside container:
python -m radar_db.manage check
python -m radar_db.manage info
```

### Example 2: Testing a Schema Change

```bash
# 1. Add new column to models.py
# 2. Generate migration
python -m radar_db.manage migrate generate -m "Add temperature field"

# 3. Run migration
python -m radar_db.manage migrate upgrade

# 4. Test with shell
python -m radar_db.manage shell
# > test_radar = session.query(Radar).first()
# > print(test_radar.new_field)  # Should be None or default
```

### Example 3: Full Development Reset

```bash
# Complete fresh start
docker exec -it radar_db python -m radar_db.manage reset --force --seed

# Verify
docker exec -it radar_db python -m radar_db.manage info
```

### Example 4: Bulk Data Inspection

```bash
# Open shell
python -m radar_db.manage shell

# List all radars with their coordinates
for r in session.query(Radar).all():
    print(f"{r.code}: ({r.center_lat}, {r.center_long})")

# Check specific radar points
ar5 = session.query(Radar).filter_by(code='AR5').first()
print(f"Point1: ({ar5.point1_lat}, {ar5.point1_long})")
print(f"Point2: ({ar5.point2_lat}, {ar5.point2_long})")
```

---

## Troubleshooting

### Issue: "Cannot connect to database"

**Check:**
1. Database service is running
2. Database environment variables are correct
3. Network connectivity (if using Docker)

**Fix:**
```bash
# Verify connection
python -m radar_db.manage check

# Check database from inside container
python -m radar_db.manage shell
# Query something simple to test
```

### Issue: "Table already exists" during init

**Solution:**
```bash
# Option 1: Reset everything
python -m radar_db.manage reset --force

# Option 2: Just reseed
python -m radar_db.manage seed
```

### Issue: Seed data not loading for new columns

**Solution:**
```bash
# Run seed again after migration
python -m radar_db.manage migrate upgrade
python -m radar_db.manage seed
```

The seeder now intelligently detects missing values and updates them.

### Issue: Migration fails partway through

**Solution:**
```bash
# Check current migration status
python -m radar_db.manage migrate current

# Check history to see where it failed
python -m radar_db.manage migrate history

# Manually rollback if needed
python -m radar_db.manage migrate downgrade

# Fix the migration and try again
python -m radar_db.manage migrate upgrade
```

---

## Environment Variables

The database connection is configured via environment variables (typically in `.env`):

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=radar_db
DB_USER=postgres
DB_PASSWORD=your_password
```

These should be set in your Docker environment or `.env` file.

---

## Database Models

The main models available are:

- **Radar** - Radar station configurations
- **RadarProduct** - Product type definitions (e.g., reflectivity, velocity)
- **Reference** - Color/value mapping for visualization
- **RadarCOG** - Cloud Optimized GeoTIFF file entries
- **Volumen** - Volume definitions
- **Estrategia** - Strategy definitions

---

## Performance Tips

1. **Use `info` command** - Check record counts before operations
2. **Use `migrate history`** - Track schema evolution
3. **Batch operations** - Use shell for bulk updates
4. **Regular backups** - Before running `reset` on production
5. **Test migrations** - On development first, then production

---

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review migration files in `migrations/versions/`
3. Use `shell` command for interactive debugging
4. Check container logs: `docker logs <container_name>`

---

## Quick Reference

| Task | Command |
|------|---------|
| Initialize tables | `python -m radar_db.manage init` |
| Load seed data | `python -m radar_db.manage seed` |
| Check connection | `python -m radar_db.manage check` |
| Show database stats | `python -m radar_db.manage info` |
| Full reset + reseed | `python -m radar_db.manage reset --force --seed` |
| Generate migration | `python -m radar_db.manage migrate generate -m "message"` |
| Run migrations | `python -m radar_db.manage migrate upgrade` |
| View migration history | `python -m radar_db.manage migrate history` |
| Interactive shell | `python -m radar_db.manage shell` |

---

**Last Updated:** January 30, 2026
