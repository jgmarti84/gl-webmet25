# api/app/routers/colormap.py
"""
Colormap router - provides colormap information and options.
Based on radar-visualization-tool implementation.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List
from ..utils.colormaps import (
    FIELD_COLORMAP_OPTIONS,
    FIELD_RENDER,
    get_colormap_colors,
    colormap_for_field,
    colormap_options_for_field,
)

router = APIRouter(prefix="/colormap", tags=["Colormaps"])


@router.get("/options", response_model=Dict[str, List[str]])
async def get_colormap_options():
    """
    Get available colormap options for each field/product.
    
    Returns dictionary mapping product keys to lists of available colormaps.
    """
    return FIELD_COLORMAP_OPTIONS


@router.get("/defaults", response_model=Dict[str, str])
async def get_colormap_defaults():
    """
    Get the default colormap for each field/product.
    
    Returns dictionary mapping product keys to default colormap names.
    """
    return {field: config["cmap"] for field, config in FIELD_RENDER.items()}


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
    colormap: str = Query(None, description="Optional colormap override")
):
    """
    Get colormap information for a specific product.
    
    Args:
        product_key: Product key (e.g., 'DBZH', 'VRAD')
        colormap: Optional colormap name to override default
    
    Returns:
        Dictionary with colormap name, vmin, vmax, and color list
    """
    try:
        cmap, vmin, vmax, cmap_name = colormap_for_field(product_key, override_cmap=colormap)
        
        # Get color list
        hex_colors = get_colormap_colors(cmap_name, steps=256)
        
        return {
            "product_key": product_key.upper(),
            "colormap": cmap_name,
            "vmin": vmin,
            "vmax": vmax,
            "colors": hex_colors,
            "available_colormaps": colormap_options_for_field(product_key),
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error getting colormap info for '{product_key}': {str(e)}"
        )
