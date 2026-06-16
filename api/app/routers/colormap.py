# api/app/routers/colormap.py
"""
Colormap router - provides colormap information and options.

Colormap data is served from the DB via ColormapService.
The hardcoded FIELD_RENDER / FIELD_COLORMAP_OPTIONS dicts in
utils/colormaps.py remain as an emergency fallback only.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import Dict, List
from ..utils.colormaps import (
    FIELD_COLORMAP_OPTIONS,
    FIELD_RENDER,
    get_colormap_colors,
    colormap_for_field,
    colormap_options_for_field,
)
from ..services.colormap_service import ColormapService
from radar_db.database import get_db
from radar_db.models import RadarProduct

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/colormap", tags=["Colormaps"])


@router.get("/names", response_model=List[str])
async def list_colormap_names():
    """
    List all colormap names available in the DB.
    """
    return ColormapService.get_instance().list_cmap_names()


@router.get("/options", response_model=Dict[str, List[str]])
async def get_colormap_options():
    """
    Get available colormap options for each field/product.

    Values come from the DB (ProductColormapOption rows) first; the
    hardcoded FIELD_COLORMAP_OPTIONS dict is used as a fallback when
    the DB is unavailable.
    """
    svc = ColormapService.get_instance()
    # Build the response from every product that has options in the DB.
    db_names = svc.list_cmap_names()
    if db_names:
        # Pull options per product key from the hardcoded dict as the
        # authoritative key-list; values come from the service (DB or fallback).
        result: Dict[str, List[str]] = {}
        for field_key in FIELD_COLORMAP_OPTIONS:
            opts = svc.options_for_product(field_key)
            result[field_key] = opts if opts else FIELD_COLORMAP_OPTIONS.get(field_key, [])
        return result
    # DB unavailable: fall back to hardcoded dict entirely.
    return FIELD_COLORMAP_OPTIONS


@router.get("/defaults", response_model=Dict[str, str])
async def get_colormap_defaults():
    """
    Get the default colormap for each field/product.

    Values come from RadarProduct.default_cmap (DB) first; the
    hardcoded FIELD_RENDER dict is used as a fallback.
    """
    svc = ColormapService.get_instance()
    result: Dict[str, str] = {}
    for field_key, hardcoded in FIELD_RENDER.items():
        db_cmap, _, _ = svc.default_for_product(field_key)
        result[field_key] = db_cmap if db_cmap else hardcoded["cmap"]
    return result


@router.post("/cache/invalidate", status_code=200)
async def invalidate_colormap_cache():
    """
    Force a full refresh of the in-process colormap cache.

    Call this after seeding or editing colormap stops in the DB so
    that the API picks up the changes without restarting.
    """
    ColormapService.get_instance().invalidate()
    return {"message": "Colormap cache invalidated."}


@router.get("/colors/{cmap_name}")
async def get_colormap_color_list(
    cmap_name: str,
    steps: int = Query(256, ge=2, le=1024, description="Number of color steps")
):
    """
    Get a list of RGB hex colors for the specified colormap.
    
    Args:
        cmap_name: Name of the colormap (e.g., 'grc_th', 'pyart_NWSRef')
        steps: Number of color steps to generate (default: 256)
    
    Returns:
        List of hex color strings: ['#RRGGBB', ...]
    """
    try:
        hex_colors = get_colormap_colors(cmap_name, steps)
        return {"colors": hex_colors, "steps": steps, "colormap": cmap_name}
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error getting colormap '{cmap_name}': {str(e)}"
        )


@router.get("/info/{product_key}")
async def get_product_colormap_info(
    product_key: str,
    colormap: str = Query(None, description="Optional colormap override"),
    db: Session = Depends(get_db),
):
    """
    Get colormap information for a specific product.

    Returns colormap name, vmin, vmax, color list, available colormaps, and
    ticks sourced from the Reference table (value + color per tick).
    Ticks are sorted ascending by value. If no Reference rows exist for this
    product the 'ticks' list will be empty and the legend will auto-generate
    evenly-spaced ticks client-side.
    """
    try:
        cmap, vmin, vmax, cmap_name = colormap_for_field(product_key, override_cmap=colormap)
        hex_colors = get_colormap_colors(cmap_name, steps=256)

        # Reference ticks — look up both exact key and without 'o' suffix.
        lookup_key = product_key.upper()
        product = (
            db.query(RadarProduct)
            .options(joinedload(RadarProduct.references))
            .filter(RadarProduct.product_key == lookup_key)
            .first()
        )
        if product is None and lookup_key.endswith("O"):
            product = (
                db.query(RadarProduct)
                .options(joinedload(RadarProduct.references))
                .filter(RadarProduct.product_key == lookup_key[:-1])
                .first()
            )

        ticks = []
        if product and product.references:
            ticks = [
                {"value": r.value, "color": r.color}
                for r in sorted(product.references, key=lambda r: r.value)
            ]

        return {
            "product_key": lookup_key,
            "colormap": cmap_name,
            "vmin": vmin,
            "vmax": vmax,
            "colors": hex_colors,
            "ticks": ticks,
            "available_colormaps": colormap_options_for_field(product_key),
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error getting colormap info for '{product_key}': {str(e)}"
        )
