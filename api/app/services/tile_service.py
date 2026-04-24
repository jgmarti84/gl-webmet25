# api/app/services/tile_service.py
import io
import logging
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Dict, Tuple, List

import numpy as np
import rasterio
from cachetools import LRUCache
from cachetools.keys import hashkey
from PIL import Image
from rio_tiler.io import Reader
from rio_tiler.errors import TileOutsideBounds

from ..config import settings
from ..utils.colormaps import colormap_for_field, colormap_to_rio_tiler, get_colormap

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache tuning constants
# ---------------------------------------------------------------------------
# ~2 000 tiles × ~20 KB PNG ≈ 40 MB max resident size.
TILE_CACHE_MAX_SIZE: int = 2000
# Number of decimal places used when rounding vmin/vmax for cache-key comparison.
# 4 decimal places (0.0001 precision) eliminates floating-point noise while still
# distinguishing intentionally different range settings.
CACHE_KEY_FLOAT_PRECISION: int = 4

# In-process tile cache — keyed by (file_path, z, x, y, cmap_name, cmap_vmin,
# cmap_vmax, filter_vmin, filter_vmax).
# Transparent tiles (out-of-bounds) are also cached since they are valid responses.
# None values (file not found on disk) are NOT cached to allow re-indexing.
_tile_cache: LRUCache = LRUCache(maxsize=TILE_CACHE_MAX_SIZE)

# Lock that guards all reads and writes to _tile_cache.
# generate_tile() is offloaded to a ThreadPoolExecutor so multiple threads can
# access the cache concurrently; cachetools structures are not thread-safe on
# their own.
_tile_cache_lock: threading.Lock = threading.Lock()

# ---------------------------------------------------------------------------
# Thread pool executor for CPU-bound tile rendering
#
# Why a thread pool?
#   Rendering a tile involves rasterio I/O and numpy/matplotlib CPU work.
#   If run directly on the FastAPI event loop, each render blocks the loop
#   for its entire duration, serialising *all* concurrent async requests.
#   By offloading _render_tile() to a ThreadPoolExecutor we let the event
#   loop remain responsive while up to TILE_RENDER_THREADS renders execute
#   in parallel.  Python's GIL is released during the C-extension I/O work
#   performed by rasterio/GDAL, so real concurrency is achieved for the
#   I/O-heavy portions; numpy/matplotlib sections still benefit from
#   overlapping with other event-loop work.
#
# Note: Redis caching and additional Uvicorn workers are separate planned
# tasks and are intentionally out of scope here.
# ---------------------------------------------------------------------------
_tile_render_executor: ThreadPoolExecutor = ThreadPoolExecutor(
    max_workers=settings.tile_render_threads,
    thread_name_prefix="tile-render",
)

# ---------------------------------------------------------------------------
# Per-thread rasterio DatasetReader LRU cache
#
# rasterio.DatasetReader objects are NOT thread-safe — two threads cannot read
# from the same DatasetReader simultaneously without data corruption.  We
# therefore use threading.local() so that each executor thread owns an
# independent cache of open DatasetReaders.  No locking is needed because
# threads never share dataset objects.
#
# On shutdown, threading.local() caches cannot be enumerated globally.
# Dataset cleanup happens naturally as threads exit — the OS reclaims the
# underlying file handles.  No explicit shutdown cleanup is required or
# possible for threading.local() caches.
# ---------------------------------------------------------------------------
_thread_local: threading.local = threading.local()


def _get_dataset(file_path: str) -> rasterio.DatasetReader:
    """Return an open rasterio DatasetReader for *file_path*.

    Uses a per-thread LRU cache (OrderedDict) to avoid reopening files on
    every tile request.  Thread-safe by design: each thread has its own
    independent cache stored in ``_thread_local``, so no locking is required.

    The cache owns the lifecycle of every DatasetReader it holds; callers
    must NOT close the returned dataset.  Do NOT use the returned object as
    a context manager — doing so would close the dataset and invalidate the
    cached entry.
    """
    if not hasattr(_thread_local, "dataset_cache"):
        _thread_local.dataset_cache = OrderedDict()

    cache: OrderedDict = _thread_local.dataset_cache
    thread_name = threading.current_thread().name
    cache_limit: int = settings.dataset_cache_size_per_thread

    if file_path in cache:
        ds = cache[file_path]
        if not ds.closed:
            # Valid hit — promote to most-recently-used position
            cache.move_to_end(file_path)
            logger.debug(
                "DATASET hit file_path=%s thread=%s",
                file_path,
                thread_name,
            )
            return ds
        # Stale entry (file was replaced on disk while handle was cached)
        del cache[file_path]
        logger.debug(
            "DATASET stale file_path=%s thread=%s — reopening",
            file_path,
            thread_name,
        )

    # Cache miss — open the file
    dataset = rasterio.open(file_path)

    # Evict the least-recently-used entry if the cache is at capacity
    if len(cache) >= cache_limit:
        evicted_path, evicted_ds = cache.popitem(last=False)
        try:
            evicted_ds.close()
        except Exception as e:
            logger.debug(
                "DATASET failed to close evicted dataset %s: %s",
                evicted_path,
                e,
            )
        logger.debug(
            "DATASET evict file_path=%s thread=%s",
            evicted_path,
            thread_name,
        )

    cache[file_path] = dataset
    logger.debug(
        "DATASET open file_path=%s thread=%s cache_size=%d/%d",
        file_path,
        thread_name,
        len(cache),
        cache_limit,
    )
    return dataset


def _tile_cache_key(
    file_path: str,
    z: int,
    x: int,
    y: int,
    cmap_name: Optional[str],
    cmap_vmin: Optional[float],
    cmap_vmax: Optional[float],
    filter_vmin: Optional[float],
    filter_vmax: Optional[float],
) -> tuple:
    """Build a hashable cache key for a rendered tile.

    The key encodes both the colormap range (cmap_vmin/cmap_vmax, derived from
    product defaults) and the optional data-filter range (filter_vmin/filter_vmax,
    supplied by the client).  Both affect the pixel output and must therefore be
    part of the cache key.
    """
    rnd = CACHE_KEY_FLOAT_PRECISION
    return hashkey(
        file_path,
        z,
        x,
        y,
        cmap_name or "",
        round(cmap_vmin, rnd) if cmap_vmin is not None else None,
        round(cmap_vmax, rnd) if cmap_vmax is not None else None,
        round(filter_vmin, rnd) if filter_vmin is not None else None,
        round(filter_vmax, rnd) if filter_vmax is not None else None,
    )


def detect_cog_type(file_path: str) -> str:
    """
    Detect whether a COG file is raw_float, rgba, or unknown.

    Reads the ``radarlib_data_type`` tag if present; otherwise falls back to
    a heuristic based on band count and dtype.
    """
    try:
        src = _get_dataset(file_path)
        tags = src.tags() or {}
        data_type_tag = tags.get("radarlib_data_type", "")

        if data_type_tag == "raw_float":
            return "raw_float"
        if data_type_tag == "rgba":
            return "rgba"

        if src.count >= 3 and str(src.dtypes[0]) == "uint8":
            return "rgba"
        if src.count == 1 and str(src.dtypes[0]) in ("float32", "float64"):
            return "raw_float"
    except Exception as e:
        logger.warning(f"Could not detect COG type for {file_path}: {e}")

    return "unknown"


def read_cog_metadata(file_path: str) -> Dict:
    """
    Read rendering metadata stored in COG tags (radarlib_* tags).

    Returns a dict with keys: data_type, cmap, vmin, vmax, nodata.
    """
    result = {"data_type": "unknown", "cmap": None, "vmin": None, "vmax": None, "nodata": None}
    try:
        src = _get_dataset(file_path)
        tags = src.tags() or {}
        result["data_type"] = tags.get("radarlib_data_type", detect_cog_type(file_path))
        result["cmap"] = tags.get("radarlib_cmap")
        result["nodata"] = src.nodata
        try:
            if tags.get("radarlib_vmin") is not None:
                result["vmin"] = float(tags["radarlib_vmin"])
        except (ValueError, TypeError):
            pass
        try:
            if tags.get("radarlib_vmax") is not None:
                result["vmax"] = float(tags["radarlib_vmax"])
        except (ValueError, TypeError):
            pass
    except Exception as e:
        logger.warning(f"Could not read COG metadata for {file_path}: {e}")
    return result


class TileService:
    """Service for generating map tiles from COG files."""
    
    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path or settings.cog_base_path)
    
    def get_full_path(self, relative_path: str) -> Path:
        """Get full filesystem path for a COG file."""
        return self.base_path / relative_path

    def _generate_raw_float_tile(
        self,
        full_path: Path,
        z: int,
        x: int,
        y: int,
        cmap_name: str,
        cmap_vmin: float,
        cmap_vmax: float,
        filter_vmin: Optional[float] = None,
        filter_vmax: Optional[float] = None,
        resampling: str = "nearest",
    ) -> bytes:
        """
        Render a tile from a single-band float32 COG by normalising the data
        and applying a matplotlib colormap, returning a PNG.

        Colormap scaling vs. data filtering
        ------------------------------------
        ``cmap_vmin`` / ``cmap_vmax``   – The full product value range used to map
            data values onto the colormap gradient.  These always come from product
            defaults (or COG metadata) so that the colormap is consistent with the
            legend displayed in the UI.

        ``filter_vmin`` / ``filter_vmax`` – Optional data-filter bounds supplied by
            the client.  Pixels whose value is BELOW ``filter_vmin`` or ABOVE
            ``filter_vmax`` are rendered as fully transparent (alpha=0).  Pixels
            within the filter range are colored normally using the full colormap
            range above.  Passing ``None`` for either bound disables that side of
            the filter.
        """
        ds = _get_dataset(str(full_path))
        # Reader is instantiated with the cached dataset so it does not reopen
        # the file.  We intentionally do NOT use Reader as a context manager
        # because __exit__ calls dataset.close(), which would invalidate the
        # cached handle.  Reader holds no resources beyond the dataset itself,
        # so garbage collection after this function returns is safe.
        reader = Reader(str(full_path), dataset=ds)
        img = reader.tile(x, y, z, resampling_method=resampling, indexes=1)

        data = img.data[0].astype(np.float32)   # (H, W)
        mask = img.mask                           # (H, W) - 0 = nodata, 255 = valid

        # Treat NaN as nodata
        nan_pixels = np.isnan(data)

        # Normalize to [0, 1] using the COLORMAP range (product defaults).
        # This keeps the color scale consistent with the legend regardless of
        # any client-supplied filter values.
        drange = cmap_vmax - cmap_vmin
        if drange == 0:
            drange = 1.0
        normalized = np.clip((data - cmap_vmin) / drange, 0.0, 1.0)

        # Apply matplotlib colormap → (H, W, 4) float32 in [0, 1]
        cmap = get_colormap(cmap_name)
        rgba_float = cmap(normalized)

        # Convert to uint8
        rgba_uint8 = (rgba_float * 255).astype(np.uint8)

        # Apply nodata mask: set alpha to 0 for masked or NaN pixels
        nodata_mask = (mask == 0) | nan_pixels
        rgba_uint8[:, :, 3] = np.where(nodata_mask, 0, rgba_uint8[:, :, 3])

        # Apply data-filter: pixels outside [filter_vmin, filter_vmax] → transparent.
        # This is intentionally separate from colormap scaling so that the color
        # legend (which reflects the full cmap range) always matches the tile colors.
        # Note: NaN pixels are already transparent via nodata_mask above.
        # NumPy comparisons with NaN always return False, so NaN pixels will NOT be
        # incorrectly added to out_of_range — they remain transparent via nodata_mask.
        if filter_vmin is not None or filter_vmax is not None:
            out_of_range = np.zeros_like(data, dtype=bool)
            if filter_vmin is not None:
                out_of_range |= data < filter_vmin
            if filter_vmax is not None:
                out_of_range |= data > filter_vmax
            rgba_uint8[:, :, 3] = np.where(out_of_range, 0, rgba_uint8[:, :, 3])

        # Encode as PNG
        pil_img = Image.fromarray(rgba_uint8, mode="RGBA")
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        buf.seek(0)
        return buf.read()

    def generate_tile(
        self,
        file_path: str,
        z: int,
        x: int,
        y: int,
        colormap: Optional[Dict[int, Tuple[int, int, int, int]]] = None,
        resampling: str = "nearest",
        cmap_name: Optional[str] = None,
        cmap_vmin: Optional[float] = None,
        cmap_vmax: Optional[float] = None,
        filter_vmin: Optional[float] = None,
        filter_vmax: Optional[float] = None,
        cog_data_type: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        Generate a PNG tile from a COG file.

        For raw_float COGs the colormap is applied via numpy normalisation +
        matplotlib (honouring ``cmap_name``, ``cmap_vmin``, ``cmap_vmax``).
        For RGBA COGs the pre-coloured bands are returned as-is.
        For other / unknown single-band COGs the rio-tiler integer colormap
        dict (``colormap``) is used as before.

        Colormap vs. filter parameters
        --------------------------------
        ``cmap_vmin`` / ``cmap_vmax`` control how data values map onto the
            colormap gradient.  These should always be the product's default
            range so the rendered colors match the legend.

        ``filter_vmin`` / ``filter_vmax`` are optional data-filter bounds.
            Pixels whose value falls outside this range are rendered as fully
            transparent regardless of their colormap color.  Passing ``None``
            disables that side of the filter (no filtering on that side).

        Args:
            file_path:     Relative path to COG file
            z, x, y:       Tile coordinates
            colormap:      Integer-keyed colormap dict for non-raw_float tiles
            resampling:    Resampling method
            cmap_name:     Matplotlib/custom colormap name (raw_float only)
            cmap_vmin:     Colormap range minimum — product default value
            cmap_vmax:     Colormap range maximum — product default value
            filter_vmin:   Optional data-filter lower bound (transparent if data < this)
            filter_vmax:   Optional data-filter upper bound (transparent if data > this)
            cog_data_type: Pre-determined COG type string (skips re-detection
                           when already known from the database record)
        Returns:
            PNG image bytes or transparent tile for out-of-bounds / errors
        """
        full_path = self.get_full_path(file_path)

        if not full_path.exists():
            logger.warning(f"COG file not found: {full_path}")
            return None

        # Resolve effective rendering parameters before checking cache so the
        # key reflects what will actually be rendered.
        if cog_data_type is None:
            cog_data_type = detect_cog_type(str(full_path))

        effective_cmap = cmap_name or "grc_th"
        effective_cmap_vmin = cmap_vmin if cmap_vmin is not None else -30.0
        effective_cmap_vmax = cmap_vmax if cmap_vmax is not None else 70.0

        cache_key = _tile_cache_key(
            file_path, z, x, y, effective_cmap,
            effective_cmap_vmin, effective_cmap_vmax,
            filter_vmin, filter_vmax,
        )
        with _tile_cache_lock:
            cached = _tile_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Tile cache hit: {file_path} {z}/{x}/{y}")
            return cached

        result = self._render_tile(
            full_path,
            file_path,
            z,
            x,
            y,
            colormap,
            resampling,
            effective_cmap,
            effective_cmap_vmin,
            effective_cmap_vmax,
            filter_vmin,
            filter_vmax,
            cog_data_type,
        )

        # Cache every successful result, including transparent tiles.
        # Do not cache None (file not found) so re-indexed files are picked up.
        if result is not None:
            with _tile_cache_lock:
                _tile_cache[cache_key] = result

        return result

    def _render_tile(
        self,
        full_path: Path,
        file_path: str,
        z: int,
        x: int,
        y: int,
        colormap: Optional[Dict[int, Tuple[int, int, int, int]]],
        resampling: str,
        effective_cmap: str,
        effective_cmap_vmin: float,
        effective_cmap_vmax: float,
        filter_vmin: Optional[float],
        filter_vmax: Optional[float],
        cog_data_type: str,
    ) -> bytes:
        """Render a tile without consulting the cache. Called by ``generate_tile``."""
        try:
            if cog_data_type == "raw_float":
                return self._generate_raw_float_tile(
                    full_path, z, x, y,
                    effective_cmap,
                    effective_cmap_vmin,
                    effective_cmap_vmax,
                    filter_vmin,
                    filter_vmax,
                    resampling,
                )

            ds = _get_dataset(str(full_path))
            # Reader is instantiated with the cached dataset so it does not
            # reopen the file.  We intentionally do NOT use Reader as a context
            # manager because __exit__ calls dataset.close(), which would
            # invalidate the cached handle.  Reader holds no resources beyond
            # the dataset itself, so garbage collection is safe.
            reader = Reader(str(full_path), dataset=ds)
            num_bands = reader.dataset.count
            dtype = str(reader.dataset.dtypes[0])

            if num_bands >= 3:
                # Pre-coloured RGBA/RGB COG – passthrough
                img = reader.tile(x, y, z, resampling_method=resampling)
                logger.debug(
                    f"COG {file_path} is pre-coloured RGBA/RGB, skipping colormap"
                )
                return img.render()

            if dtype != "uint8":
                # Non-uint8 single-band data (float32, int16, …): the integer-keyed
                # colormap dict approach only works for 8-bit values (0-255).  Float or
                # scaled-integer pixel values would either be clipped to 0 by rio-tiler's
                # uint8 cast or simply not found in the dict, producing fully-transparent
                # tiles.  Route through the raw_float pipeline instead so values are
                # normalised correctly across the full data range.
                logger.debug(
                    f"COG {file_path} is single-band {dtype}, using raw_float pipeline"
                )
                return self._generate_raw_float_tile(
                    full_path, z, x, y,
                    effective_cmap,
                    effective_cmap_vmin,
                    effective_cmap_vmax,
                    filter_vmin,
                    filter_vmax,
                    resampling,
                )

            # 8-bit single-band: use rio-tiler integer colormap
            img = reader.tile(x, y, z, resampling_method=resampling, indexes=1)
            if colormap:
                return img.render(colormap=colormap)
            return img.render()

        except TileOutsideBounds:
            logger.debug(f"Tile {z}/{x}/{y} outside bounds for {file_path}")
            return self._generate_transparent_tile()
        except Exception as e:
            logger.error(
                f"Error generating tile {z}/{x}/{y} for {file_path}: {e}", exc_info=True
            )
            return self._generate_transparent_tile()
    
    def _generate_transparent_tile(self, size: int = 256) -> bytes:
        """Generate a fully transparent PNG tile."""
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer.read()
    
    def build_colormap_from_references(
        self,
        references: List[Dict],
        nodata_transparent: bool = True
    ) -> Dict[int, Tuple[int, int, int, int]]:
        """
        DEPRECATED: This method is no longer used.
        Colormaps are now defined in utils/colormaps.py based on product type.
        
        Build a rio-tiler compatible colormap from product references.
        
        Args:
            references: List of reference dicts with 'value' and 'color' keys
            nodata_transparent: If True, make values below minimum transparent
            
        Returns:
            Colormap dict for rio-tiler
        """
        logger.warning("build_colormap_from_references is deprecated. Use predefined colormaps instead.")
        
        if not references:
            return self._get_default_radar_colormap()
        
        # Sort by value
        sorted_refs = sorted(references, key=lambda r: r['value'])
        
        colormap = {}
        
        for i, ref in enumerate(sorted_refs):
            value = int(ref['value'])
            color = ref['color'].lstrip('#')
            
            # Parse hex color
            try:
                r = int(color[0:2], 16)
                g = int(color[2:4], 16)
                b = int(color[4:6], 16)
                a = 255  # Fully opaque
            except (ValueError, IndexError):
                # Default to white if parsing fails
                r, g, b, a = 255, 255, 255, 255
            
            colormap[value] = (r, g, b, a)
        
        # Interpolate values between defined points
        colormap = self._interpolate_colormap(colormap)
        
        return colormap
    
    def build_colormap_for_product(
        self,
        product_key: str,
        override_cmap: Optional[str] = None
    ) -> Dict[int, Tuple[int, int, int, int]]:
        """
        Build a rio-tiler compatible colormap for a radar product.
        Uses predefined colormaps from utils/colormaps.py.
        
        Args:
            product_key: Product key (e.g., 'DBZH', 'VRAD')
            override_cmap: Optional colormap name to override default
            
        Returns:
            Colormap dict for rio-tiler
        """
        # Get colormap configuration for this product
        cmap, vmin, vmax, cmap_name = colormap_for_field(product_key, override_cmap)
        
        # Convert to rio-tiler format
        colormap_dict = colormap_to_rio_tiler(cmap, vmin, vmax)
        
        logger.info(f"Built colormap '{cmap_name}' for product '{product_key}' (range: {vmin} to {vmax})")
        
        return colormap_dict
    
    def _interpolate_colormap(
        self, 
        colormap: Dict[int, Tuple[int, int, int, int]],
        min_val: int = -30,
        max_val: int = 80
    ) -> Dict[int, Tuple[int, int, int, int]]:
        """Interpolate colormap to fill gaps between defined values."""
        if len(colormap) < 2:
            return colormap
        
        sorted_values = sorted(colormap.keys())
        full_colormap = {}
        
        for i in range(min_val, max_val + 1):
            if i in colormap:
                full_colormap[i] = colormap[i]
            else:
                # Find surrounding values
                lower = max([v for v in sorted_values if v <= i], default=sorted_values[0])
                upper = min([v for v in sorted_values if v >= i], default=sorted_values[-1])
                
                if lower == upper:
                    full_colormap[i] = colormap[lower]
                else:
                    # Linear interpolation
                    t = (i - lower) / (upper - lower)
                    c1 = colormap[lower]
                    c2 = colormap[upper]
                    full_colormap[i] = tuple(
                        int(c1[j] + t * (c2[j] - c1[j])) for j in range(4)
                    )
        
        return full_colormap
    
    def _get_default_radar_colormap(self) -> Dict[int, Tuple[int, int, int, int]]:
        """Get default radar reflectivity colormap (NWS style)."""
        return {
            -30: (0, 0, 0, 0),       # Transparent
            -20: (128, 128, 128, 128), # Gray (light)
            -10: (192, 192, 192, 180), # Gray
            0: (149, 180, 220, 255),   # Light blue (mist)
            10: (0, 230, 138, 255),    # Light green (drizzle)
            20: (0, 173, 90, 255),     # Green (light rain)
            30: (234, 243, 40, 255),   # Yellow (moderate rain)
            40: (247, 166, 0, 255),    # Orange (heavy rain)
            50: (255, 42, 12, 255),    # Red (intense rain)
            60: (255, 42, 152, 255),   # Pink (very intense + hail)
            70: (255, 41, 227, 255),   # Magenta (severe)
        }
    
    def get_cog_info(self, file_path: str) -> Optional[Dict]:
        """Get information about a COG file."""
        full_path = self.get_full_path(file_path)
        
        if not full_path.exists():
            return None
        
        try:
            with Reader(str(full_path)) as src:
                info = src.info()
                return {
                    "bounds": info.bounds,
                    "minzoom": info.minzoom,
                    "maxzoom": info.maxzoom,
                    "band_metadata": info.band_metadata,
                    "dtype": info.dtype,
                    "nodata": info.nodata_value,
                }
        except Exception as e:
            logger.error(f"Error getting COG info for {file_path}: {e}")
            return None


# Singleton instance
_tile_service: Optional[TileService] = None


def get_tile_service() -> TileService:
    """Get or create the tile service singleton."""
    global _tile_service
    if _tile_service is None:
        _tile_service = TileService()
    return _tile_service

