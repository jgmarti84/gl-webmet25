"""Display geometry: holes filled, edges smoothed.

gl-tracker builds each system's polygon from the grid pixels above the
threshold, so the outline is a staircase of pixel edges and can contain holes
(pixels inside the storm that fell below the threshold). Forecasts are shifted
and scaled copies of those polygons, so they inherit both.

This module only changes what is *drawn*. Tracking (matching, velocities,
areas and every other property) runs on gl-tracker's original geometry before
any of this happens, so the numbers in a feature's properties still describe
the raw polygon.

Two steps, per polygon part:

1. **Fill holes.** Keep only the exterior ring: a core is the whole area its
   outline encloses.
2. **Smooth the edge.** Resample the ring at a uniform spacing in kilometres,
   then apply a circular Gaussian filter to the x and y coordinates. This is
   Gaussian smoothing along the outline (the closed-curve equivalent of
   blurring an image), so the pixel staircase becomes a smooth curve while the
   overall shape is kept. A Gaussian shrinks a closed curve slightly (more
   where it bends tightly), so ``sigma_km`` should stay around one pixel.

If smoothing yields an invalid or degenerate polygon, the filled (unsmoothed)
polygon is returned instead: a drawable shape beats a missing one.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

import numpy as np
from shapely.geometry import MultiPolygon, Polygon, mapping, shape

logger = logging.getLogger(__name__)

#: Kilometres per degree of latitude (and of longitude at the equator). The
#: local equirectangular frame is accurate to well under a pixel over a storm.
_KM_PER_DEG = 111.32

#: A smoothed polygon smaller than this fraction of the original is treated as
#: degenerate and replaced by the unsmoothed one.
_MIN_AREA_RATIO = 0.5


def fill_holes(geom):
    """The geometry with every interior ring removed (Polygon or MultiPolygon)."""
    if isinstance(geom, Polygon):
        return Polygon(geom.exterior)
    if isinstance(geom, MultiPolygon):
        return MultiPolygon([Polygon(p.exterior) for p in geom.geoms])
    return geom


def _gaussian_kernel(sigma_pts: float) -> np.ndarray:
    radius = max(1, int(math.ceil(3 * sigma_pts)))
    offsets = np.arange(-radius, radius + 1, dtype=float)
    kernel = np.exp(-0.5 * (offsets / sigma_pts) ** 2)
    return kernel / kernel.sum()


def _circular_filter(values: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Convolve a closed sequence with `kernel`, wrapping around the ends.

    Built from rolls rather than padding, so it is correct even when the ring
    has fewer points than the kernel is wide.
    """
    radius = len(kernel) // 2
    out = np.zeros_like(values)
    for k, weight in zip(range(-radius, radius + 1), kernel):
        out += weight * np.roll(values, k)
    return out


def _smooth_ring(coords: np.ndarray, sigma_km: float, step_km: float) -> Optional[np.ndarray]:
    """Smooth one closed ring of (lon, lat) points. None if it cannot be done."""
    pts = coords[:-1] if np.allclose(coords[0], coords[-1]) else coords
    if len(pts) < 3:
        return None

    # Local metric frame centred on the ring.
    lon0, lat0 = pts[:, 0].mean(), pts[:, 1].mean()
    kx = _KM_PER_DEG * math.cos(math.radians(lat0))
    xy = np.column_stack(((pts[:, 0] - lon0) * kx, (pts[:, 1] - lat0) * _KM_PER_DEG))

    # Uniform resampling along the perimeter, so sigma means the same distance
    # everywhere regardless of how the vertices were spaced.
    closed = np.vstack((xy, xy[:1]))
    seg = np.hypot(*np.diff(closed, axis=0).T)
    perimeter = seg.sum()
    if perimeter <= 0:
        return None
    cum = np.concatenate(([0.0], np.cumsum(seg)))
    n = max(8, int(math.ceil(perimeter / step_km)))
    s = np.linspace(0.0, perimeter, n, endpoint=False)
    x = np.interp(s, cum, closed[:, 0])
    y = np.interp(s, cum, closed[:, 1])

    kernel = _gaussian_kernel(sigma_km / (perimeter / n))
    x, y = _circular_filter(x, kernel), _circular_filter(y, kernel)

    lon = x / kx + lon0
    lat = y / _KM_PER_DEG + lat0
    ring = np.column_stack((lon, lat))
    return np.vstack((ring, ring[:1]))


def smooth_polygon(poly: Polygon, sigma_km: float, step_km: Optional[float] = None) -> Polygon:
    """`poly` (holes already filled) with a Gaussian-smoothed exterior."""
    if sigma_km <= 0 or poly.is_empty:
        return poly
    step_km = step_km or sigma_km / 3.0
    ring = _smooth_ring(np.asarray(poly.exterior.coords, dtype=float), sigma_km, step_km)
    if ring is None:
        return poly
    smoothed = Polygon(ring)
    if not smoothed.is_valid:
        smoothed = smoothed.buffer(0)
    if (
        smoothed.is_empty
        or not isinstance(smoothed, (Polygon, MultiPolygon))
        or smoothed.area < _MIN_AREA_RATIO * poly.area
    ):
        return poly
    return smoothed


def display_geometry(geometry: Dict[str, Any], sigma_km: float) -> Dict[str, Any]:
    """A GeoJSON geometry dict, holes filled and edges smoothed.

    Anything that is not a Polygon or MultiPolygon, or fails to parse, is
    returned unchanged.
    """
    try:
        geom = shape(geometry)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("could not parse geometry for display: %s", exc)
        return geometry
    if not isinstance(geom, (Polygon, MultiPolygon)) or geom.is_empty:
        return geometry

    filled = fill_holes(geom)
    if isinstance(filled, Polygon):
        out = smooth_polygon(filled, sigma_km)
    else:
        parts: List[Polygon] = []
        for part in filled.geoms:
            smoothed = smooth_polygon(part, sigma_km)
            parts.extend(smoothed.geoms if isinstance(smoothed, MultiPolygon) else [smoothed])
        out = MultiPolygon(parts)
    return mapping(out)
