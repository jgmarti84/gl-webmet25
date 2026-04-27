# api/app/routers/frames.py
"""
Frames endpoint — serves an entire COG as a single georeferenced RGBA PNG.

This endpoint complements the tile endpoint by returning the full spatial
extent of a COG in one HTTP request instead of ~10 individual 256×256 tiles.
The result is equivalent to assembling all tiles, but requires 10× fewer
requests per animation frame.

Endpoint:
    GET /frames/{cog_id}/image.png

Response:
    PNG bytes (RGBA) with bbox metadata in response headers.
"""
import asyncio
import functools
import hashlib
import io
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple, cast

import numpy as np
import rasterio
from cachetools import LRUCache
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from PIL import Image
from rasterio.crs import CRS
from rasterio.warp import transform_bounds
from sqlalchemy.orm import Session

from radar_db import get_db
from ..services.tile_service import (
    _get_dataset,
    _get_tile_ttl,
    _tile_render_executor,
    CACHE_KEY_FLOAT_PRECISION,
)
from ..services.redis_client import get_redis
from ..utils.colormaps import colormap_for_field, get_colormap
from .tiles import _get_cog_by_id, CogSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/frames", tags=["Frames"])

# ---------------------------------------------------------------------------
# L1 in-memory LRU cache — independent from the tile cache so that frame
# and tile caches can be monitored and flushed separately.
# ---------------------------------------------------------------------------
_FRAME_CACHE_MAX_SIZE: int = 500

_frame_cache: LRUCache = LRUCache(maxsize=_FRAME_CACHE_MAX_SIZE)
_frame_cache_lock: threading.Lock = threading.Lock()

# ---------------------------------------------------------------------------
# WGS84 target CRS for bbox reprojection
# ---------------------------------------------------------------------------
_WGS84 = CRS.from_epsg(4326)


# ---------------------------------------------------------------------------
# Cache key helpers
# ---------------------------------------------------------------------------

def _build_frame_cache_key(
    file_path: str,
    cmap_name: str,
    cmap_vmin: float,
    cmap_vmax: float,
    filter_vmin: Optional[float],
    filter_vmax: Optional[float],
) -> tuple:
    """Build a hashable L1 cache key for a rendered frame."""
    rnd = CACHE_KEY_FLOAT_PRECISION
    return (
        file_path,
        cmap_name,
        round(cmap_vmin, rnd),
        round(cmap_vmax, rnd),
        round(filter_vmin, rnd) if filter_vmin is not None else None,
        round(filter_vmax, rnd) if filter_vmax is not None else None,
    )


def _build_frame_redis_key(cache_key: tuple) -> str:
    """Convert the frame cache key tuple into a Redis string key.

    Uses SHA-256 to produce a fixed-length key, prefixed with 'frame:'
    so frame keys are independent from tile keys (prefix 'tile:').
    """
    raw = json.dumps(list(cache_key), default=str, sort_keys=False)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"frame:{digest}"


# ---------------------------------------------------------------------------
# BBox helpers
# ---------------------------------------------------------------------------

def _get_wgs84_bounds(ds: rasterio.DatasetReader) -> Tuple[float, float, float, float]:
    """Return the dataset's spatial extent in WGS84 (EPSG:4326).

    If the dataset is already in WGS84 the bounds are returned as-is.
    Otherwise ``rasterio.warp.transform_bounds`` reprojects the native
    bounds to lat/lon degrees.

    Returns:
        (west, south, east, north) in decimal degrees.
    """
    left, bottom, right, top = ds.bounds
    src_crs = ds.crs

    if src_crs is None:
        # No CRS information — return native bounds and hope for the best.
        logger.warning(
            "FRAME dataset has no CRS metadata, returning raw bounds as WGS84: %s",
            ds.name,
        )
        return float(left), float(bottom), float(right), float(top)

    if src_crs == _WGS84:
        return float(left), float(bottom), float(right), float(top)

    west, south, east, north = transform_bounds(src_crs, _WGS84, left, bottom, right, top)
    return float(west), float(south), float(east), float(north)


# ---------------------------------------------------------------------------
# ETag / Cache-Control helpers
# ---------------------------------------------------------------------------
_RECENT_FRAME_THRESHOLD = timedelta(minutes=10)
_ETAG_FLOAT_FORMAT = f".{CACHE_KEY_FLOAT_PRECISION}f"


def _fmt_float(value: float) -> str:
    return format(value, _ETAG_FLOAT_FORMAT)


def _build_frame_headers(
    observation_time: Optional[datetime],
    cog_id: int,
    cmap: str,
    cmap_vmin: float,
    cmap_vmax: float,
    filter_vmin: Optional[float],
    filter_vmax: Optional[float],
    west: float,
    south: float,
    east: float,
    north: float,
    width: int,
    height: int,
) -> dict:
    """Build HTTP response headers for a frame response."""
    fv_min = _fmt_float(filter_vmin) if filter_vmin is not None else "none"
    fv_max = _fmt_float(filter_vmax) if filter_vmax is not None else "none"
    etag_raw = (
        f"frame-{cog_id}-{cmap}"
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
        if age > _RECENT_FRAME_THRESHOLD:
            cache_control = "public, max-age=86400, immutable"
        else:
            cache_control = "public, max-age=60, must-revalidate"
    else:
        cache_control = "public, max-age=300"

    return {
        "Cache-Control": cache_control,
        "ETag": etag,
        "Access-Control-Allow-Origin": "*",
        "X-Bbox-West": str(west),
        "X-Bbox-South": str(south),
        "X-Bbox-East": str(east),
        "X-Bbox-North": str(north),
        "X-Width": str(width),
        "X-Height": str(height),
    }


# ---------------------------------------------------------------------------
# Synchronous render function (runs inside the thread pool executor)
# ---------------------------------------------------------------------------

def _render_frame_sync(
    file_path: str,
    full_path: Path,
    cmap_name: str,
    cmap_vmin: float,
    cmap_vmax: float,
    filter_vmin: Optional[float],
    filter_vmax: Optional[float],
    observation_time: Optional[datetime] = None,
) -> Optional[bytes]:
    """Render the full COG raster extent as an RGBA PNG.

    This function is CPU-bound and is always called from within the
    ``_tile_render_executor`` thread pool — never on the event loop.

    Returns PNG bytes, or None if the file is not accessible.
    """
    cache_key = _build_frame_cache_key(
        file_path, cmap_name, cmap_vmin, cmap_vmax, filter_vmin, filter_vmax
    )

    # --- L1 check ---
    with _frame_cache_lock:
        cached_l1 = _frame_cache.get(cache_key)
    if cached_l1 is not None:
        logger.debug("FRAME L1 HIT key=%s", cache_key)
        return cached_l1

    # --- L2 check (Redis) ---
    r = get_redis()
    redis_key = _build_frame_redis_key(cache_key)
    if r is not None:
        try:
            cached_l2: Optional[bytes] = cast(Optional[bytes], r.get(redis_key))
        except Exception as exc:
            logger.warning("FRAME Redis get failed: %s", exc)
            cached_l2 = None
        if cached_l2 is not None:
            logger.debug("FRAME L2 HIT key=%s size=%dB", redis_key, len(cached_l2))
            with _frame_cache_lock:
                _frame_cache[cache_key] = cached_l2
            return cached_l2
        logger.debug("FRAME L2 MISS key=%s", redis_key)

    # --- Render ---
    if not full_path.exists():
        logger.warning("FRAME file not found: %s", full_path)
        return None

    t0 = time.monotonic()
    try:
        ds = _get_dataset(str(full_path))

        # Read band 1 as float32
        data = ds.read(1).astype(np.float32)  # (H, W)
        # rasterio dataset_mask: 0 = nodata, 255 = valid
        mask = ds.dataset_mask()              # (H, W)

        # NaN pixels are treated as nodata
        nan_pixels = np.isnan(data)

        # Normalize to [0, 1] using COLORMAP range (product defaults)
        drange = cmap_vmax - cmap_vmin
        if drange == 0.0:
            drange = 1.0
        normalized = np.clip((data - cmap_vmin) / drange, 0.0, 1.0)

        # Apply matplotlib colormap → (H, W, 4) float32 in [0, 1]
        cmap = get_colormap(cmap_name)
        rgba_float = cmap(normalized)

        # Convert to uint8
        rgba_uint8 = (rgba_float * 255).astype(np.uint8)

        # Apply nodata / NaN mask
        nodata_mask = (mask == 0) | nan_pixels
        rgba_uint8[:, :, 3] = np.where(nodata_mask, 0, rgba_uint8[:, :, 3])

        # Apply data-filter bounds (same semantics as tile endpoint)
        if filter_vmin is not None or filter_vmax is not None:
            out_of_range = np.zeros_like(data, dtype=bool)
            if filter_vmin is not None:
                out_of_range |= data < filter_vmin
            if filter_vmax is not None:
                out_of_range |= data > filter_vmax
            rgba_uint8[:, :, 3] = np.where(out_of_range, 0, rgba_uint8[:, :, 3])

        # Encode as PNG via Pillow
        pil_img = Image.fromarray(rgba_uint8, mode="RGBA")
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        buf.seek(0)
        png_bytes = buf.read()

    except Exception as exc:
        logger.error("FRAME render error for %s: %s", file_path, exc, exc_info=True)
        raise

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    # Store in L1
    with _frame_cache_lock:
        _frame_cache[cache_key] = png_bytes

    # Store in L2 (Redis)
    if r is not None:
        ttl = _get_tile_ttl(observation_time)
        try:
            r.setex(redis_key, ttl, png_bytes)
        except Exception as exc:
            logger.warning("FRAME Redis set failed: %s", exc)
        logger.info(
            "FRAME RENDER + CACHE cog=%s elapsed=%dms l2_ttl=%ds",
            file_path, elapsed_ms, ttl,
        )
    else:
        logger.info(
            "FRAME RENDER + CACHE cog=%s elapsed=%dms l2_ttl=N/A",
            file_path, elapsed_ms,
        )

    return png_bytes


# ---------------------------------------------------------------------------
# Public helper — frame L1 cache stats (imported by tiles.py)
# ---------------------------------------------------------------------------

def get_frame_l1_cache_stats() -> Dict[str, int]:
    """Return current frame L1 cache occupancy."""
    with _frame_cache_lock:
        return {"size": len(_frame_cache), "maxsize": _FRAME_CACHE_MAX_SIZE}


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------

@router.get("/{cog_id}/image.png")
async def get_frame_image(
    cog_id: int,
    colormap: Optional[str] = Query(
        None,
        description="Override colormap name (e.g., grc_th, viridis, pyart_NWSRef)",
    ),
    vmin: Optional[float] = Query(
        None,
        description=(
            "Data-filter lower bound. Pixels with values BELOW this threshold are "
            "rendered transparent. Colormap scaling always uses product defaults."
        ),
    ),
    vmax: Optional[float] = Query(
        None,
        description=(
            "Data-filter upper bound. Pixels with values ABOVE this threshold are "
            "rendered transparent. Colormap scaling always uses product defaults."
        ),
    ),
    db: Session = Depends(get_db),
) -> Response:
    """
    Return the entire COG as a single georeferenced RGBA PNG.

    Unlike the tile endpoint which returns 256×256 tiles, this endpoint
    renders the full spatial extent of the COG (typically 160×160 px) in
    a single image.  The WGS84 bounding box is returned in response headers
    so the frontend can position the image correctly with ``L.imageOverlay``.

    - **cog_id**: COG file ID
    - **colormap**: Optional colormap name override
    - **vmin**: Optional data-filter lower bound (pixels below → transparent)
    - **vmax**: Optional data-filter upper bound (pixels above → transparent)
    """
    # DB lookup (via TTL metadata cache shared with tile endpoint)
    cog: Optional[CogSnapshot] = _get_cog_by_id(cog_id, db)
    if cog is None:
        raise HTTPException(status_code=404, detail=f"COG with ID {cog_id} not found")

    product_key = cog.polarimetric_var or cog.product_key

    # Colormap scaling — always from product defaults (same as tile endpoint)
    _, default_vmin, default_vmax, default_cmap_name = colormap_for_field(
        product_key or "DBZH"
    )
    effective_cmap = colormap or default_cmap_name
    cmap_vmin = default_vmin
    cmap_vmax = default_vmax
    filter_vmin = vmin
    filter_vmax = vmax

    # Resolve full filesystem path
    from ..services import get_tile_service
    tile_service = get_tile_service()
    full_path: Path = tile_service.get_full_path(cog.file_path)

    # Offload CPU-bound rendering to the shared thread pool executor
    loop = asyncio.get_running_loop()
    try:
        frame_data: Optional[bytes] = await loop.run_in_executor(
            _tile_render_executor,
            functools.partial(
                _render_frame_sync,
                cog.file_path,
                full_path,
                effective_cmap,
                cmap_vmin,
                cmap_vmax,
                filter_vmin,
                filter_vmax,
                cog.observation_time,
            ),
        )
    except Exception as exc:
        logger.error(
            "FRAME unhandled render error cog_id=%d file=%s: %s",
            cog_id, cog.file_path, exc, exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Frame rendering failed")

    if frame_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"COG file not found on disk. Expected at: {cog.file_path}.",
        )

    # Read bbox and dimensions from the (cached) dataset — this executes in
    # the calling (event-loop) thread but _get_dataset is thread-safe per thread.
    # We need the bbox so we offload via executor as well to keep things safe.
    def _read_geo_info() -> Tuple[float, float, float, float, int, int]:
        ds = _get_dataset(str(full_path))
        west, south, east, north = _get_wgs84_bounds(ds)
        return west, south, east, north, ds.width, ds.height

    try:
        west, south, east, north, img_width, img_height = await loop.run_in_executor(
            _tile_render_executor,
            _read_geo_info,
        )
    except Exception as exc:
        logger.error(
            "FRAME failed to read geo info for cog_id=%d: %s", cog_id, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to read COG geographic metadata")

    headers = _build_frame_headers(
        cog.observation_time,
        cog_id,
        effective_cmap,
        cmap_vmin,
        cmap_vmax,
        filter_vmin,
        filter_vmax,
        west,
        south,
        east,
        north,
        img_width,
        img_height,
    )

    return Response(
        content=frame_data,
        media_type="image/png",
        headers=headers,
    )
