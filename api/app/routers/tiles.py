# api/app/routers/tiles.py
import asyncio
import functools
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session, joinedload

from radar_db import get_db, RadarCOG
from ..services import get_tile_service, TileService, _tile_render_executor
from ..services.tile_service import read_cog_metadata, get_l1_cache_stats
from ..services.redis_client import get_redis
from ..utils.colormaps import colormap_for_field, colormap_options_for_field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tiles", tags=["Tiles"])


@dataclass(frozen=True)
class CogSnapshot:
    """
    Immutable snapshot of the RadarCOG fields needed for tile rendering.

    Stored in the TTL metadata cache instead of the live ORM object so that
    cached entries remain valid after the originating DB session is closed.
    """

    id: int
    file_path: str
    observation_time: Optional[datetime]
    polarimetric_var: Optional[str]
    # Flattened from RadarCOG.product.product_key (eager-loaded once)
    product_key: Optional[str]
    cog_data_type: Optional[str]
    cog_cmap: Optional[str]
    cog_vmin: Optional[float]
    cog_vmax: Optional[float]

# ---------------------------------------------------------------------------
# Cache tuning constants
# ---------------------------------------------------------------------------
# Maximum number of RadarCOG metadata entries to keep in memory.
COG_METADATA_CACHE_MAX_SIZE: int = 500
# Seconds before a cached metadata entry is evicted (5 minutes).
COG_METADATA_CACHE_TTL: int = 300
# Observation age (in minutes) above which a tile is considered immutable.
# Tiles older than this threshold receive a 24-hour browser/proxy cache.
RECENT_OBSERVATION_THRESHOLD_MINUTES: int = 10

# ---------------------------------------------------------------------------
# Priority 3 — COG metadata cache
# Cache RadarCOG records for 5 minutes. Metadata is stable between indexer
# runs; TTL ensures stale entries are evicted automatically.
# This cache is READ-ONLY and must NOT be used by any write (indexer) path.
# ---------------------------------------------------------------------------
_cog_metadata_cache: TTLCache = TTLCache(
    maxsize=COG_METADATA_CACHE_MAX_SIZE,
    ttl=COG_METADATA_CACHE_TTL,
)


def _get_cog_by_id(cog_id: int, db: Session) -> Optional[CogSnapshot]:
    """Return a CogSnapshot (with product key) by ID, using the TTL metadata cache.

    The cache stores plain dataclass instances — not SQLAlchemy ORM objects —
    so entries remain valid after the originating DB session is closed.
    """
    cached: Optional[CogSnapshot] = _cog_metadata_cache.get(cog_id)
    if cached is not None:
        return cached
    orm_cog = (
        db.query(RadarCOG)
        .options(joinedload(RadarCOG.product))
        .filter(RadarCOG.id == cog_id)
        .first()
    )
    if orm_cog is None:
        return None
    snapshot = CogSnapshot(
        id=orm_cog.id,
        file_path=orm_cog.file_path,
        observation_time=orm_cog.observation_time,
        polarimetric_var=orm_cog.polarimetric_var,
        product_key=orm_cog.product.product_key if orm_cog.product else None,
        cog_data_type=orm_cog.cog_data_type,
        cog_cmap=orm_cog.cog_cmap,
        cog_vmin=orm_cog.cog_vmin,
        cog_vmax=orm_cog.cog_vmax,
    )
    _cog_metadata_cache[cog_id] = snapshot
    return snapshot


# ---------------------------------------------------------------------------
# Priority 1 — Cache-Control / ETag helpers
# ---------------------------------------------------------------------------
_RECENT_THRESHOLD = timedelta(minutes=RECENT_OBSERVATION_THRESHOLD_MINUTES)

# Match the float precision used in the tile-service cache key so that the
# ETag stays consistent with the server-side cache lookup.
_ETAG_FLOAT_FORMAT = f".{4}f"  # 4 decimal places


def _fmt_float(value: float) -> str:
    """Format a float consistently for ETag generation."""
    return format(value, _ETAG_FLOAT_FORMAT)


def _build_tile_headers(
    observation_time: Optional[datetime],
    cog_id: int,
    z: int,
    x: int,
    y: int,
    cmap: str,
    cmap_vmin: float,
    cmap_vmax: float,
    filter_vmin: Optional[float],
    filter_vmax: Optional[float],
) -> dict:
    """
    Build HTTP caching headers for a tile response.

    Past observations (> RECENT_OBSERVATION_THRESHOLD_MINUTES old) get a
    24-hour immutable cache.  Recent observations get a 60-second cache
    with must-revalidate.  An ETag is always included so clients can send
    If-None-Match for 304 responses.

    The ETag encodes both the colormap range (cmap_vmin/cmap_vmax, from
    product defaults) and the optional data-filter range (filter_vmin/
    filter_vmax, from query params) so that different filter values produce
    distinct cache entries.
    """
    fv_min = _fmt_float(filter_vmin) if filter_vmin is not None else "none"
    fv_max = _fmt_float(filter_vmax) if filter_vmax is not None else "none"
    etag_raw = (
        f"{cog_id}-{z}-{x}-{y}-{cmap}"
        f"-{_fmt_float(cmap_vmin)}-{_fmt_float(cmap_vmax)}"
        f"-{fv_min}-{fv_max}"
    )
    etag = f'"{hashlib.sha256(etag_raw.encode()).hexdigest()[:32]}"'

    if observation_time is not None:
        obs_utc = (
            observation_time.replace(tzinfo=timezone.utc)
            if observation_time.tzinfo is None
            else observation_time
        )
        age = datetime.now(timezone.utc) - obs_utc
        if age > _RECENT_THRESHOLD:
            cache_control = "public, max-age=86400, immutable"
        else:
            cache_control = "public, max-age=60, must-revalidate"
    else:
        cache_control = "public, max-age=300"

    return {
        "Cache-Control": cache_control,
        "ETag": etag,
        "Access-Control-Allow-Origin": "*",
    }


@router.get("/{cog_id}/{z}/{x}/{y}.png")
async def get_tile(
    request: Request,
    cog_id: int,
    z: int,
    x: int,
    y: int,
    colormap: Optional[str] = Query(None, description="Override colormap name (e.g., grc_th, viridis, pyart_NWSRef)"),
    # TODO: In a future version, consider renaming `vmin`/`vmax` to `filter_min`/`filter_max`
    #       to reflect their new role as data-filter bounds (not colormap-scaling limits).
    #       The colormap always spans the full product range (product defaults), not these values.
    #       Any rename must update the API contract and all frontend call sites in map.js.
    vmin: Optional[float] = Query(
        None,
        description=(
            "Data-filter lower bound. Pixels with values BELOW this threshold are rendered "
            "transparent. The colormap gradient always spans the full product value range "
            "(product defaults), not this filter bound."
        ),
    ),
    vmax: Optional[float] = Query(
        None,
        description=(
            "Data-filter upper bound. Pixels with values ABOVE this threshold are rendered "
            "transparent. The colormap gradient always spans the full product value range "
            "(product defaults), not this filter bound."
        ),
    ),
    db: Session = Depends(get_db),
    tile_service: TileService = Depends(get_tile_service)
):
    """
    Get a map tile for a specific COG file.
    
    - **cog_id**: COG file ID
    - **z**: Zoom level
    - **x**: Tile X coordinate
    - **y**: Tile Y coordinate
    - **colormap**: Optional colormap name override
    - **vmin**: Optional data-filter lower bound (pixels below are transparent)
    - **vmax**: Optional data-filter upper bound (pixels above are transparent)
    """
    # Priority 3: use metadata cache for DB lookup
    cog = _get_cog_by_id(cog_id, db)

    if not cog:
        raise HTTPException(status_code=404, detail=f"COG with ID {cog_id} not found")

    logger.info(f"Requesting tile for COG {cog_id}: {cog.file_path}")

    product_key = cog.polarimetric_var or cog.product_key
    cog_data_type = cog.cog_data_type  # may be None for legacy records

    # Colormap scaling range — always uses product defaults so that the tile
    # colors remain consistent with the legend regardless of filter values.
    # Note: cog.cog_cmap (radarlib metadata) is intentionally NOT used as a
    # fallback here, so the legend (which uses product defaults) always matches
    # the tile renderer.  A query-param override is the correct way to change
    # the colormap interactively.
    _, default_vmin, default_vmax, default_cmap_name = colormap_for_field(
        product_key or "DBZH"
    )

    effective_cmap = colormap or default_cmap_name
    # cmap_vmin / cmap_vmax are the COLORMAP scaling range (always product defaults).
    # filter_vmin / filter_vmax are the DATA FILTER range (from query params, may be None).
    cmap_vmin = default_vmin
    cmap_vmax = default_vmax
    filter_vmin = vmin   # None means no filter on this side
    filter_vmax = vmax   # None means no filter on this side

    # Priority 1: build caching headers and check ETag for conditional GET
    headers = _build_tile_headers(
        cog.observation_time, cog_id, z, x, y,
        effective_cmap, cmap_vmin, cmap_vmax, filter_vmin, filter_vmax,
    )
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == headers["ETag"]:
        return Response(status_code=304, headers=headers)

    # Build integer colormap dict (used for non-raw_float paths)
    colormap_dict = None
    if product_key:
        colormap_dict = tile_service.build_colormap_for_product(product_key, override_cmap=effective_cmap)
        logger.info(f"Built colormap '{effective_cmap}' for product '{product_key}' (COG {cog_id})")
    else:
        logger.warning(f"No product key found for COG {cog_id}. Using default colormap.")
        colormap_dict = tile_service._get_default_radar_colormap()
    
    # Generate tile (Priority 2: served from LRU cache when available)
    # CPU-bound rendering is offloaded to a thread pool so the event loop
    # is not blocked while rasterio/numpy/matplotlib work executes.
    tile_data = await asyncio.get_running_loop().run_in_executor(
        _tile_render_executor,
        functools.partial(
            tile_service.generate_tile,
            file_path=cog.file_path,
            z=z,
            x=x,
            y=y,
            colormap=colormap_dict,
            cmap_name=effective_cmap,
            cmap_vmin=cmap_vmin,
            cmap_vmax=cmap_vmax,
            filter_vmin=filter_vmin,
            filter_vmax=filter_vmax,
            cog_data_type=cog_data_type,
            observation_time=cog.observation_time,
        ),
    )
    
    if tile_data is None:
        full_path = tile_service.get_full_path(cog.file_path)
        logger.error(f"COG file not found on disk: {full_path}")
        raise HTTPException(
            status_code=404, 
            detail=f"COG file not found on disk. Expected at: {cog.file_path}."
        )
    
    return Response(
        content=tile_data,
        media_type="image/png",
        headers=headers,
    )


@router.get("/by-params/{radar_code}/{product_key}/{timestamp}/{z}/{x}/{y}.png")
async def get_tile_by_params(
    radar_code: str,
    product_key: str,
    timestamp: str,  # ISO format or "latest"
    z: int,
    x: int,
    y: int,
    colormap: Optional[str] = Query(None, description="Override colormap"),
    vmin: Optional[float] = Query(None, description="Override minimum value"),
    vmax: Optional[float] = Query(None, description="Override maximum value"),
    db: Session = Depends(get_db),
    tile_service: TileService = Depends(get_tile_service)
):
    """
    Get a map tile by radar, product, and timestamp.
    
    - **radar_code**: Radar code (e.g., "RMA3")
    - **product_key**: Product key (e.g., "DBZH")
    - **timestamp**: ISO timestamp or "latest"
    - **z**: Zoom level
    - **x**: Tile X coordinate  
    - **y**: Tile Y coordinate
    - **colormap**: Optional colormap name override
    - **vmin**: Optional minimum value override
    - **vmax**: Optional maximum value override
    """
    from datetime import datetime
    from sqlalchemy import desc
    
    query = db.query(RadarCOG)\
        .options(joinedload(RadarCOG.product))\
        .filter(
            RadarCOG.radar_code == radar_code,
            RadarCOG.polarimetric_var == product_key
        )
    
    if timestamp.lower() == "latest":
        cog = query.order_by(desc(RadarCOG.observation_time)).first()
    else:
        try:
            ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            cog = query.filter(RadarCOG.observation_time == ts).first()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid timestamp format")
    
    if not cog:
        raise HTTPException(
            status_code=404, 
            detail=f"No COG found for {radar_code}/{product_key}/{timestamp}"
        )

    cog_data_type = cog.cog_data_type

    # Resolve effective rendering parameters.
    # Colormap scaling is always from product defaults (cmap_vmin/cmap_vmax).
    # User-supplied vmin/vmax are data-filter bounds (filter_vmin/filter_vmax).
    _, default_vmin, default_vmax, default_cmap_name = colormap_for_field(product_key)
    effective_cmap = colormap or default_cmap_name
    cmap_vmin = default_vmin
    cmap_vmax = default_vmax
    filter_vmin = vmin   # None means no filter on this side
    filter_vmax = vmax   # None means no filter on this side

    colormap_dict = tile_service.build_colormap_for_product(product_key, override_cmap=effective_cmap)
    
    tile_data = await asyncio.get_running_loop().run_in_executor(
        _tile_render_executor,
        functools.partial(
            tile_service.generate_tile,
            file_path=cog.file_path,
            z=z,
            x=x,
            y=y,
            colormap=colormap_dict,
            cmap_name=effective_cmap,
            cmap_vmin=cmap_vmin,
            cmap_vmax=cmap_vmax,
            filter_vmin=filter_vmin,
            filter_vmax=filter_vmax,
            cog_data_type=cog_data_type,
            observation_time=cog.observation_time,
        ),
    )
    
    if tile_data is None:
        raise HTTPException(status_code=404, detail="Tile not found")

    headers = _build_tile_headers(
        cog.observation_time, cog.id, z, x, y,
        effective_cmap, cmap_vmin, cmap_vmax, filter_vmin, filter_vmax,
    )
    return Response(
        content=tile_data,
        media_type="image/png",
        headers=headers,
    )


@router.get("/{cog_id}/metadata")
async def get_cog_rendering_metadata(
    cog_id: int,
    db: Session = Depends(get_db),
    tile_service: TileService = Depends(get_tile_service)
):
    """
    Get rendering metadata for a specific COG file.

    Returns the COG's data type (raw_float / rgba), default colormap name,
    vmin, vmax, and the list of available colormaps for the product.
    This is used by the frontend to populate colormap/range controls.
    """
    # Priority 3: use metadata cache for DB lookup
    cog = _get_cog_by_id(cog_id, db)

    if not cog:
        raise HTTPException(status_code=404, detail=f"COG with ID {cog_id} not found")

    product_key = cog.polarimetric_var or cog.product_key

    # Fall back to file-level detection when the DB column is not yet populated
    cog_data_type = cog.cog_data_type
    if cog_data_type is None:
        full_path = tile_service.get_full_path(cog.file_path)
        if full_path.exists():
            file_meta = read_cog_metadata(str(full_path))
            cog_data_type = file_meta.get("data_type", "unknown")

    _, default_vmin, default_vmax, default_cmap_name = colormap_for_field(
        product_key or "DBZH"
    )

    return {
        "cog_id": cog_id,
        "data_type": cog_data_type or "unknown",
        "cmap": default_cmap_name,
        "vmin": default_vmin,
        "vmax": default_vmax,
        "product_key": product_key,
        "available_colormaps": colormap_options_for_field(product_key or ""),
    }


@router.get("/cache/stats", tags=["Tiles"])
async def get_cache_stats():
    """
    Returns tile cache statistics for monitoring.

    Reports the current state of both cache layers:
    - L1: in-memory LRUCache (per-process, fastest)
    - L2: Redis shared cache (survives restarts, shared across workers)

    This endpoint is for monitoring only and does not require authentication.
    """
    r = get_redis()

    redis_connected = False
    redis_used_memory_human = None
    tile_keys = None

    if r is not None:
        try:
            info = r.info("memory")
            redis_used_memory_human = info.get("used_memory_human")
            redis_connected = True
        except Exception as e:
            logger.warning("Redis info failed: %s", e)

        if redis_connected:
            try:
                tile_keys = r.dbsize()
            except Exception as e:
                logger.warning("Redis dbsize failed: %s", e)

    l1_stats = get_l1_cache_stats()
    return {
        "l1_size": l1_stats["size"],
        "l1_maxsize": l1_stats["maxsize"],
        "l1_hit_rate": "N/A - not tracked",
        "redis_connected": redis_connected,
        "redis_used_memory_human": redis_used_memory_human,
        "redis_keyspace": {"tile_keys": tile_keys},
    }