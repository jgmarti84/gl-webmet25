"""Runs gl-tracker over a resolved list of volumes.

This is the sidecar's replacement for gl-tracker's ``operativo.py``. That
module is neither imported nor modified: it discovers work by globbing a
directory and owns a persistent state pickle, neither of which suits a
request-scoped service. What it does — walk volumes in order, feeding each to
``pipeline.procesar()`` while carrying tracking state forward — is reproduced
here in a few lines.

gl-tracker itself is used entirely as published. The only liberty taken is
passing a duck-typed sink in place of ``pipeline.Salidas`` (see ``sink.py``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional

# gl-tracker. Flat top-level modules by design on its side; importable here
# because everything in this service lives inside the tracking_api package and
# so cannot shadow them. See the package docstring.
import config as gl_config
import estado as gl_estado
import gate as gl_gate
import pipeline as gl_pipeline

from tracking_api.geojson import build_frame
from tracking_api.schemas import TrackingConfig
from tracking_api.sink import VolumeSink
from tracking_api.volumes import Volume

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]


def build_config(tracking_config: TrackingConfig):
    """Map the public knobs onto gl-tracker's ``Config``.

    The mapping is **not** uniform, and getting it wrong fails silently:

    * ``dbz_threshold`` and ``min_area_km2`` are top-level ``Config`` fields.
    * ``cappi_height_m`` belongs to ``ConvectiveFilterConfig`` and therefore
      goes through ``filter_overrides``.

    Setting ``det_threshold_dbz`` / ``det_min_area_km2`` via ``filter_overrides``
    would do nothing at all: ``Config.filtro()`` overwrites both from the
    top-level fields every time it is called (``config.py:161-162``).

    Only whitelisted fields are ever written — a client cannot reach arbitrary
    attributes of ``Config``.
    """
    cfg = gl_config.Config()
    cfg.dbz_threshold = float(tracking_config.dbz_threshold)
    cfg.min_area_km2 = float(tracking_config.min_area_km2)
    cfg.filter_overrides = {"cappi_height_m": float(tracking_config.cappi_height_m)}
    return cfg


def config_summary(cfg) -> Dict[str, object]:
    """The values actually in force, for display alongside the results.

    Read back off the constructed ``Config`` rather than echoed from the
    request, so what is shown is what ran — including defaults the client never
    sent.
    """
    filtro = cfg.filtro()
    return {
        "cappi_height_m": filtro.cappi_height_m,
        "dbz_threshold": cfg.dbz_threshold,
        "min_area_km2": cfg.min_area_km2,
        "strategy": cfg.strategy,
        "overlap": cfg.overlap,
        "max_gap_tracking_min": cfg.max_gap_tracking_min,
        "forecast_intervals": list(cfg.forecast_intervals),
        "solo_c2": cfg.solo_c2,
        "echotop_min_above_h0_m": filtro.echotop_min_above_h0_m,
        "rhohv_qc_min": filtro.rhohv_qc_min,
        "r_max_km": filtro.r_max_km,
    }


def run_tracking(
    volumes: List[Volume],
    cfg,
    progress: Optional[ProgressCallback] = None,
) -> List[Dict]:
    """Track a window. Returns one frame per non-lead-in volume.

    ``volumes`` must be in ascending time order — ``procesar()`` carries state
    forward in ``est`` and a reversal would silently corrupt the track history.
    ``volumes.resolve_window()`` guarantees the ordering.

    Lead-in volumes are processed but produce no frame: their only job is to
    populate ``est`` so the first returned frame already has velocity and
    forecasts rather than appearing as freshly generated systems.
    """
    if not volumes:
        return []

    # Reading WRF once per run rather than per volume; h0_wrf caches by
    # (run, point) internally. None is not an error — resolver_h0 degrades to
    # the climatological annual cycle, which is worse than the model but far
    # better than disabling the filter.
    serie = gl_gate.serie_h0_actual(cfg, cfg.h0_lat, cfg.h0_lon)
    if serie is None:
        logger.info("no usable WRF run; H0 will come from climatology")

    # Fresh state per run — equivalent to operativo.py's --desde-cero. Nothing
    # is persisted between requests, which is what makes concurrent runs with
    # different configs safe.
    est = gl_estado.Estado()

    frames: List[Dict] = []
    total = len(volumes)

    for index, volume in enumerate(volumes, start=1):
        sink = VolumeSink(cfg.forecast_intervals)
        try:
            resultado = gl_pipeline.procesar(
                Path(volume.path), volume.timestamp, cfg, serie, est, sink
            )
        except Exception as exc:
            # One unreadable cube must not lose the whole window. Tracking
            # state is left untouched, so the next volume is compared against
            # the last one that did parse.
            logger.error("volume %s failed: %s", volume.path, exc, exc_info=True)
            if not volume.lead_in:
                frames.append(_error_frame(volume, exc))
            if progress:
                progress(index, total)
            continue

        if not volume.lead_in:
            frames.append(build_frame(volume.timestamp, resultado, sink))

        if progress:
            progress(index, total)

    return frames


def _error_frame(volume: Volume, exc: Exception) -> Dict:
    """A frame standing in for a volume that could not be read."""
    return {
        "timestamp": volume.timestamp.isoformat().replace("+00:00", "Z"),
        "gate_passed": False,
        "gate": None,
        "counts": {"detected": 0, "convective": 0, "tracked": 0, "forecasts": 0},
        "tracking_restarted": False,
        "seconds": 0.0,
        "error": f"{type(exc).__name__}: {exc}",
        "features": {"type": "FeatureCollection", "features": []},
    }
