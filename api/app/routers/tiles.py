# api/app/routers/tiles.py
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from pathlib import Path
import logging

from radar_db import get_db, RadarCOG, RadarProduct
from ..services import get_tile_service, TileService
from ..services.tile_service import read_cog_metadata
from ..utils.colormaps import colormap_for_field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tiles", tags=["Tiles"])


@router.get("/{cog_id}/{z}/{x}/{y}.png")
async def get_tile(
    cog_id: int,
    z: int,
    x: int,
    y: int,
    colormap: Optional[str] = Query(None, description="Override colormap name (e.g., grc_th, viridis, pyart_NWSRef)"),
    vmin: Optional[float] = Query(None, description="Override minimum data value for colormap scaling"),
    vmax: Optional[float] = Query(None, description="Override maximum data value for colormap scaling"),
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
    - **vmin**: Optional minimum value override for colormap scaling
    - **vmax**: Optional maximum value override for colormap scaling
    """
    # Get COG record
    cog = db.query(RadarCOG)\
        .options(joinedload(RadarCOG.product))\
        .filter(RadarCOG.id == cog_id)\
        .first()
    
    if not cog:
        raise HTTPException(status_code=404, detail=f"COG with ID {cog_id} not found")
    
    logger.info(f"Requesting tile for COG {cog_id}: {cog.file_path}")
    
    product_key = cog.polarimetric_var or (cog.product.product_key if cog.product else None)
    cog_data_type = cog.cog_data_type  # may be None for legacy records

    # Resolve effective cmap name, vmin, vmax
    # Priority: query param > COG metadata tags > product defaults
    _, default_vmin, default_vmax, default_cmap_name = colormap_for_field(
        product_key or "DBZH"
    )

    effective_cmap = colormap or cog.cog_cmap or default_cmap_name
    effective_vmin = vmin if vmin is not None else (cog.cog_vmin if cog.cog_vmin is not None else default_vmin)
    effective_vmax = vmax if vmax is not None else (cog.cog_vmax if cog.cog_vmax is not None else default_vmax)

    # Build integer colormap dict (used for non-raw_float paths)
    colormap_dict = None
    if product_key:
        colormap_dict = tile_service.build_colormap_for_product(product_key, override_cmap=colormap)
        logger.info(f"Built colormap '{effective_cmap}' for product '{product_key}' (COG {cog_id})")
    else:
        logger.warning(f"No product key found for COG {cog_id}. Using default colormap.")
        colormap_dict = tile_service._get_default_radar_colormap()
    
    # Generate tile
    tile_data = tile_service.generate_tile(
        file_path=cog.file_path,
        z=z,
        x=x,
        y=y,
        colormap=colormap_dict,
        cmap_name=effective_cmap,
        vmin=effective_vmin,
        vmax=effective_vmax,
        cog_data_type=cog_data_type,
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
        headers={
            "Cache-Control": "public, max-age=300",
            "Access-Control-Allow-Origin": "*",
        }
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

    # Resolve effective rendering parameters
    _, default_vmin, default_vmax, default_cmap_name = colormap_for_field(product_key)
    effective_cmap = colormap or cog.cog_cmap or default_cmap_name
    effective_vmin = vmin if vmin is not None else (cog.cog_vmin if cog.cog_vmin is not None else default_vmin)
    effective_vmax = vmax if vmax is not None else (cog.cog_vmax if cog.cog_vmax is not None else default_vmax)

    colormap_dict = tile_service.build_colormap_for_product(product_key, override_cmap=colormap)
    
    tile_data = tile_service.generate_tile(
        file_path=cog.file_path,
        z=z,
        x=x,
        y=y,
        colormap=colormap_dict,
        cmap_name=effective_cmap,
        vmin=effective_vmin,
        vmax=effective_vmax,
        cog_data_type=cog_data_type,
    )
    
    if tile_data is None:
        raise HTTPException(status_code=404, detail="Tile not found")
    
    return Response(
        content=tile_data,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=60",
            "Access-Control-Allow-Origin": "*",
        }
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
    from ..utils.colormaps import FIELD_COLORMAP_OPTIONS

    cog = db.query(RadarCOG)\
        .options(joinedload(RadarCOG.product))\
        .filter(RadarCOG.id == cog_id)\
        .first()

    if not cog:
        raise HTTPException(status_code=404, detail=f"COG with ID {cog_id} not found")

    product_key = cog.polarimetric_var or (cog.product.product_key if cog.product else None)

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
        "cmap": cog.cog_cmap or default_cmap_name,
        "vmin": cog.cog_vmin if cog.cog_vmin is not None else default_vmin,
        "vmax": cog.cog_vmax if cog.cog_vmax is not None else default_vmax,
        "product_key": product_key,
        "available_colormaps": FIELD_COLORMAP_OPTIONS.get(
            product_key, FIELD_COLORMAP_OPTIONS.get((product_key or "").upper(), [])
        ),
    }