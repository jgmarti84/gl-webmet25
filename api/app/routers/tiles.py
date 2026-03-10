# api/app/routers/tiles.py
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from pathlib import Path
import logging

from radar_db import get_db, RadarCOG, RadarProduct
from ..services import get_tile_service, TileService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tiles", tags=["Tiles"])


@router.get("/{cog_id}/{z}/{x}/{y}.png")
async def get_tile(
    cog_id: int,
    z: int,
    x: int,
    y: int,
    colormap: Optional[str] = Query(None, description="Override colormap (e.g., grc_th, grc_rain, pyart_NWSRef)"),
    db: Session = Depends(get_db),
    tile_service: TileService = Depends(get_tile_service)
):
    """
    Get a map tile for a specific COG file.
    
    - **cog_id**: COG file ID
    - **z**: Zoom level
    - **x**: Tile X coordinate
    - **y**: Tile Y coordinate
    - **colormap**: Optional colormap name to override default
    """
    # Get COG record
    cog = db.query(RadarCOG)\
        .options(joinedload(RadarCOG.product))\
        .filter(RadarCOG.id == cog_id)\
        .first()
    
    if not cog:
        raise HTTPException(status_code=404, detail=f"COG with ID {cog_id} not found")
    
    # Log the file path being accessed
    logger.info(f"Requesting tile for COG {cog_id}: {cog.file_path}")
    
    # Build colormap from product key using predefined colormaps
    colormap_dict = None
    product_key = cog.polarimetric_var or (cog.product.product_key if cog.product else None)
    
    if product_key:
        colormap_dict = tile_service.build_colormap_for_product(product_key, override_cmap=colormap)
        logger.info(f"Built colormap for product '{product_key}' (COG {cog_id})")
    else:
        logger.warning(f"No product key found for COG {cog_id}. Using default colormap.")
        colormap_dict = tile_service._get_default_radar_colormap()
    
    # Generate tile
    tile_data = tile_service.generate_tile(
        file_path=cog.file_path,
        z=z,
        x=x,
        y=y,
        colormap=colormap_dict
    )
    
    if tile_data is None:
        # Only return 404 if the file itself doesn't exist
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
            "Cache-Control": "public, max-age=300",  # Cache for 5 minutes
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
    - **colormap**: Optional colormap name to override default
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
    
    # Build colormap using predefined colormaps
    colormap_dict = tile_service.build_colormap_for_product(product_key, override_cmap=colormap)
    
    # Generate tile
    tile_data = tile_service.generate_tile(
        file_path=cog.file_path,
        z=z,
        x=x,
        y=y,
        colormap=colormap_dict
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