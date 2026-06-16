# api/app/services/colormap_service.py
"""
DB-backed colormap service.

Reads ColormapStop rows from the database and reconstructs
matplotlib LinearSegmentedColormap objects.  Results are cached
in-process with a configurable TTL so repeated requests never
hit the database more than once per interval.

Fallback chain (in order):
  1. DB: ColormapStop rows WHERE cmap_name = <requested name>
  2. Hardcoded get_cmap_<name>() functions in utils/colormaps.py
  3. matplotlib's own registered colormaps
"""

import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
from matplotlib.colors import LinearSegmentedColormap

logger = logging.getLogger(__name__)

# In-process cache TTL in seconds.  Colormaps are admin-edited rarely, so
# 5 minutes is a sensible default.  Set to 0 to disable caching.
_CACHE_TTL: int = 300


class ColormapService:
    """
    Singleton service that builds and caches colormaps from the DB.

    Usage
    -----
    service = ColormapService.get_instance()
    cmap = service.get_cmap("grc_th")                    # LinearSegmentedColormap
    names = service.list_cmap_names()                    # ["grc_th", "grc_vrad", ...]
    options = service.options_for_product("DBZH")        # ["grc_th", "grc_th2", ...]
    default, vmin, vmax = service.default_for_product("DBZH")
    service.invalidate()                                 # force cache refresh
    """

    _instance: Optional["ColormapService"] = None
    _lock: threading.Lock = threading.Lock()

    # ---------------------------------------------------------------
    # Cache state (per-instance)
    # ---------------------------------------------------------------
    def __init__(self) -> None:
        self._cmap_cache: Dict[str, LinearSegmentedColormap] = {}
        self._names_cache: Optional[List[str]] = None
        self._product_cache: Dict[str, Dict] = {}  # {product_key: {default_cmap, vmin, vmax}}
        self._options_cache: Dict[str, List[str]] = {}  # {product_key: [cmap_name, ...]}
        self._loaded_at: float = 0.0
        self._rw_lock: threading.RLock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "ColormapService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ---------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------

    def get_cmap(self, cmap_name: str) -> Optional[LinearSegmentedColormap]:
        """
        Return a matplotlib LinearSegmentedColormap for *cmap_name*.

        Returns None if the name is not found in DB and has no hardcoded
        fallback, so the caller can fall through to matplotlib's own registry.
        """
        self._maybe_load()
        with self._rw_lock:
            return self._cmap_cache.get(cmap_name)

    def list_cmap_names(self) -> List[str]:
        """Return all colormap names currently defined in the DB."""
        self._maybe_load()
        with self._rw_lock:
            return list(self._names_cache or [])

    def default_for_product(self, product_key: str) -> Tuple[Optional[str], Optional[float], Optional[float]]:
        """
        Return (default_cmap_name, vmin, vmax) for *product_key*.

        Falls back to key without 'o' suffix, then returns (None, None, None)
        if not found so the caller can use its own default.
        """
        self._maybe_load()
        with self._rw_lock:
            spec = (
                self._product_cache.get(product_key)
                or self._product_cache.get(product_key.upper())
                or (
                    self._product_cache.get(product_key[:-1])
                    if product_key.endswith("o")
                    else None
                )
            )
        if spec is None:
            return None, None, None
        return spec.get("default_cmap"), spec.get("vmin"), spec.get("vmax")

    def options_for_product(self, product_key: str) -> List[str]:
        """
        Return the list of available colormap names for *product_key*.

        If no explicit options are recorded, returns all cmap names (the
        'show everything' fallback).
        """
        self._maybe_load()
        with self._rw_lock:
            opts = (
                self._options_cache.get(product_key)
                or self._options_cache.get(product_key.upper())
                or (
                    self._options_cache.get(product_key[:-1])
                    if product_key.endswith("o")
                    else None
                )
            )
            if opts:
                return list(opts)
            return list(self._names_cache or [])

    def invalidate(self) -> None:
        """Force a full cache refresh on next access."""
        with self._rw_lock:
            self._loaded_at = 0.0
            self._cmap_cache.clear()
            self._names_cache = None
            self._product_cache.clear()
            self._options_cache.clear()
        logger.info("ColormapService cache invalidated")

    # ---------------------------------------------------------------
    # Internal loading
    # ---------------------------------------------------------------

    def _maybe_load(self) -> None:
        """Load from DB if the cache is empty or has expired."""
        now = time.monotonic()
        if _CACHE_TTL > 0 and (now - self._loaded_at) < _CACHE_TTL:
            return  # still fresh
        with self._rw_lock:
            # Double-check after acquiring the write lock.
            if _CACHE_TTL > 0 and (now - self._loaded_at) < _CACHE_TTL:
                return
            self._load_from_db()
            self._loaded_at = time.monotonic()

    def _load_from_db(self) -> None:
        """
        Pull all ColormapStop, RadarProduct, and ProductColormapOption rows
        from the database and populate the in-process caches.
        """
        try:
            from radar_db.database import db_manager
            from radar_db.models import ColormapStop, RadarProduct, ProductColormapOption

            with db_manager.get_session() as session:
                # ── 1. Build colormaps from stop rows ──────────────────────
                stops = session.query(ColormapStop).order_by(
                    ColormapStop.cmap_name,
                    ColormapStop.channel,
                    ColormapStop.sort_order,
                ).all()

                channel_map = {"r": "red", "g": "green", "b": "blue"}
                raw: Dict[str, Dict[str, list]] = {}
                for s in stops:
                    if s.cmap_name not in raw:
                        raw[s.cmap_name] = {"red": [], "green": [], "blue": []}
                    ch = channel_map.get(s.channel)
                    if ch:
                        raw[s.cmap_name][ch].append(
                            (s.position, s.val_left, s.val_right)
                        )

                new_cmap_cache: Dict[str, LinearSegmentedColormap] = {}
                for cmap_name, channels in raw.items():
                    try:
                        # channels has the correct runtime shape; cast to
                        # satisfy strict type checkers.
                        from typing import cast, Any
                        cmap = LinearSegmentedColormap(
                            cmap_name, cast(Any, channels)
                        )
                        new_cmap_cache[cmap_name] = cmap
                    except Exception as exc:
                        logger.warning(
                            f"ColormapService: could not build cmap '{cmap_name}': {exc}"
                        )

                # ── 2. Product defaults (default_cmap, vmin, vmax) ────────
                products = session.query(
                    RadarProduct.product_key,
                    RadarProduct.default_cmap,
                    RadarProduct.min_value,
                    RadarProduct.max_value,
                ).all()

                new_product_cache: Dict[str, Dict] = {}
                for row in products:
                    new_product_cache[row.product_key] = {
                        "default_cmap": row.default_cmap,
                        "vmin": row.min_value,
                        "vmax": row.max_value,
                    }

                # ── 3. Per-product colormap options ───────────────────────
                options_rows = session.query(
                    ProductColormapOption.product_key,
                    ProductColormapOption.cmap_name,
                ).all()

                new_options_cache: Dict[str, List[str]] = {}
                for row in options_rows:
                    new_options_cache.setdefault(row.product_key, []).append(
                        row.cmap_name
                    )

            self._cmap_cache = new_cmap_cache
            self._names_cache = sorted(new_cmap_cache.keys())
            self._product_cache = new_product_cache
            self._options_cache = new_options_cache

            logger.info(
                f"ColormapService loaded {len(new_cmap_cache)} colormaps, "
                f"{len(new_product_cache)} products from DB"
            )

        except Exception as exc:
            # Never crash the API on a cache-load failure — the caller will
            # fall through to the hardcoded function fallbacks.
            logger.error(
                f"ColormapService._load_from_db failed: {exc}", exc_info=True
            )
