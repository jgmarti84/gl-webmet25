# api/app/routers/tiles.py
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.orm import Session, joinedload
from typing import Optional
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
    db: Session = Depends(get_db),
    tile_service: TileService = Depends(get_tile_service)
):
    """
    Get a map tile for a specific COG file.
    
    - **cog_id**: COG file ID
    - **z**: Zoom level
    - **x**: Tile X coordinate
    - **y**: Tile Y coordinate
    """
    # Get COG record
    cog = db.query(RadarCOG)\
        .options(joinedload(RadarCOG.product).joinedload(RadarProduct.references))\
        .filter(RadarCOG.id == cog_id)\
        .first()
    
    if not cog:
        raise HTTPException(status_code=404, detail=f"COG with ID {cog_id} not found")
    
    # Log the file path being accessed
    logger.info(f"Requesting tile for COG {cog_id}: {cog.file_path}")
    
    # Build colormap from product references
    colormap = None
    if cog.product and cog.product.references:
        references = [
            {'value': ref.value, 'color': ref.color}
            for ref in cog.product.references
        ]
        colormap = tile_service.build_colormap_from_references(references)
    
    # Generate tile
    tile_data = tile_service.generate_tile(
        file_path=cog.file_path,
        z=z,
        x=x,
        y=y,
        colormap=colormap
    )
    
    if tile_data is None:
        # Check if file exists to provide better error message
        from pathlib import Path
        full_path = tile_service.get_full_path(cog.file_path)
        if not full_path.exists():
            logger.error(f"COG file not found on disk: {full_path}")
            raise HTTPException(
                status_code=404, 
                detail=f"COG file not found on disk. Expected at: {cog.file_path}. "
                       f"Please ensure COG files are available in the configured path."
            )
        else:
            raise HTTPException(status_code=404, detail="Tile not found or outside bounds")
    
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
    """
    from datetime import datetime
    from sqlalchemy import desc
    
    query = db.query(RadarCOG)\
        .options(joinedload(RadarCOG.product).joinedload(RadarProduct.references))\
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
    
    # Build colormap
    colormap = None
    if cog.product and cog.product.references:
        references = [
            {'value': ref.value, 'color': ref.color}
            for ref in cog.product.references
        ]
        colormap = tile_service.build_colormap_from_references(references)
    
    # Generate tile
    tile_data = tile_service.generate_tile(
        file_path=cog.file_path,
        z=z,
        x=x,
        y=y,
        colormap=colormap
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