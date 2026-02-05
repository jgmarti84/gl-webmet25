# COG File Setup for Radar Visualization

## Overview

The radar visualization system uses **Cloud Optimized GeoTIFF (COG)** files to display radar imagery. The tile service (`/api/v1/tiles/{cog_id}/{z}/{x}/{y}.png`) reads these COG files and generates PNG tiles on-the-fly for display on the Leaflet map.

## Important: COG Files Must Exist

**The system requires actual COG `.tif` files to be present on disk.** The database only stores metadata about the files - the actual TIF files must exist in the configured location.

## Troubleshooting "404 Tile Not Found" Errors

If you see errors like `GET /api/v1/tiles/1388/8/84/146.png 404 (Not Found)`, this means:

1. **COG record exists in database** (ID 1388) ← Indexed by the indexer service
2. **BUT the actual `.tif` file is missing** from disk ← File hasn't been generated yet

### Solution

Ensure COG files are being generated and placed in the `product_output` directory:

```bash
# Check if directory exists
ls -lah ./product_output/

# Expected structure:
product_output/
├── RMA3/
│   ├── COLMAX/
│   │   ├── 2026-02-05_12-00-00.tif  ← Actual COG files
│   │   ├── 2026-02-05_12-05-00.tif
│   │   └── ...
│   └── ...
└── ...
```

## How the System Works

```
1. COG Generator Service → Generates .tif files → ./product_output/
2. Indexer Service → Watches directory → Indexes to database
3. API Service → Reads database + .tif files → Generates PNG tiles
4. Frontend → Requests tiles → Displays on map
```

**Key Point**: Both steps 1 and 2 must complete for tiles to work!

## Quick Diagnostics

```bash
# 1. Check if COG files exist
docker compose exec api ls -lah /product_output/RMA3/COLMAX/

# 2. Check database records
docker compose exec radar_db psql -U radar -d radar_prod_db -c \
  "SELECT id, file_path, observation_time FROM radar_cogs WHERE radar_code='RMA3' AND polarimetric_var='COLMAX' ORDER BY observation_time DESC LIMIT 5;"

# 3. Verify paths match
# Database file_path should match actual files in /product_output/

# 4. Test tile generation directly
COG_ID=1388  # Replace with actual ID
curl -I "http://localhost:8000/api/v1/tiles/${COG_ID}/8/84/146.png"
```

## Configuration

The COG base path is configured in `docker-compose.yml`:

```yaml
api:
  environment:
    COG_BASE_PATH: /product_output  # Path inside container
  volumes:
    - ${PRODUCT_OUTPUT_PATH:-./product_output}:/product_output:ro
```

## For Development/Testing

If you don't have real radar data yet, you can:

1. **Use the genpro25 service** (if configured) to generate COG files
2. **Create test COG files** using GDAL
3. **Wait for the data ingestion service** to populate files

See the main project README for more details on data generation.
