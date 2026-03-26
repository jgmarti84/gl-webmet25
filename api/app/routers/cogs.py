# api/app/routers/cogs.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import List, Optional
from datetime import datetime, timedelta

from radar_db import get_db, RadarCOG, RadarProduct, COGStatus
from ..schemas import COGResponse, COGListResponse, TimelineResponse
from ..config import settings

router = APIRouter(prefix="/cogs", tags=["COG Files"])


def cog_to_response(cog: RadarCOG, base_url: str = "") -> COGResponse:
    """Convert COG model to response schema."""
    # Get product key
    product_key = cog.polarimetric_var or (cog.product.product_key if cog.product else None)
    
    # Build tile URL template
    tile_url = f"{base_url}/api/v1/tiles/{cog.id}/{{z}}/{{x}}/{{y}}.png"
    
    # Parse bbox if available
    bbox = None
    if cog.bbox is not None:
        try:
            # GeoAlchemy2 geometry to bounds
            from shapely import wkb
            from geoalchemy2.shape import to_shape
            geom = to_shape(cog.bbox)
            bounds = geom.bounds  # (minx, miny, maxx, maxy)
            bbox = {
                "min_lon": bounds[0],
                "min_lat": bounds[1],
                "max_lon": bounds[2],
                "max_lat": bounds[3],
            }
        except Exception:
            pass
    
    return COGResponse(
        id=cog.id,
        radar_code=cog.radar_code,
        product_key=product_key,
        product_id=cog.product_id,
        observation_time=cog.observation_time,
        elevation_angle=cog.elevation_angle,
        file_path=cog.file_path,
        file_name=cog.file_name,
        data_min=cog.data_min,
        data_max=cog.data_max,
        bbox=bbox,
        tile_url=tile_url,
    )


@router.get("", response_model=COGListResponse)
def list_cogs(
    radar_code: Optional[str] = None,
    product_key: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    List COG files with filtering.
    
    - **radar_code**: Filter by radar code
    - **product_key**: Filter by product key
    - **start_time**: Filter by observation time >= start_time
    - **end_time**: Filter by observation time <= end_time
    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 50, max: 200)
    """
    query = db.query(RadarCOG).filter(RadarCOG.status == COGStatus.AVAILABLE)
    
    if radar_code:
        query = query.filter(RadarCOG.radar_code == radar_code)
    
    if product_key:
        # Match exact polarimetric_var, OR the same key with an 'o' suffix
        # (e.g. 'VRAD' should also match COGs stored as 'VRADo'), OR via the
        # product relationship for product-linked COGs.
        query = query.filter(
            (RadarCOG.polarimetric_var == product_key) |
            (RadarCOG.polarimetric_var == product_key + 'o') |
            (RadarCOG.product.has(RadarProduct.product_key == product_key))
        )
    
    if start_time:
        query = query.filter(RadarCOG.observation_time >= start_time)
    
    if end_time:
        query = query.filter(RadarCOG.observation_time <= end_time)
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * page_size
    cogs = query.order_by(desc(RadarCOG.observation_time))\
        .offset(offset)\
        .limit(page_size)\
        .all()
    
    return COGListResponse(
        cogs=[cog_to_response(cog) for cog in cogs],
        count=len(cogs),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/latest", response_model=COGResponse)
def get_latest_cog(
    radar_code: str,
    product_key: str,
    db: Session = Depends(get_db)
):
    """
    Get the most recent COG for a radar and product combination.
    """
    cog = db.query(RadarCOG)\
        .filter(
            RadarCOG.radar_code == radar_code,
            (RadarCOG.polarimetric_var == product_key) |
            (RadarCOG.polarimetric_var == product_key + 'o'),
            RadarCOG.status == COGStatus.AVAILABLE
        )\
        .order_by(desc(RadarCOG.observation_time))\
        .first()
    
    if not cog:
        raise HTTPException(
            status_code=404, 
            detail=f"No COG found for radar '{radar_code}' and product '{product_key}'"
        )
    
    return cog_to_response(cog)


@router.get("/timeline", response_model=TimelineResponse)
def get_timeline(
    radar_code: str,
    product_key: str,
    hours: int = Query(default=6, ge=1, le=48),
    db: Session = Depends(get_db)
):
    """
    Get available timestamps for animation.
    
    - **radar_code**: Radar code
    - **product_key**: Product key
    - **hours**: Number of hours to look back (default: 6, max: 48)
    """
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    cogs = db.query(RadarCOG.observation_time)\
        .filter(
            RadarCOG.radar_code == radar_code,
            (RadarCOG.polarimetric_var == product_key) |
            (RadarCOG.polarimetric_var == product_key + 'o'),
            RadarCOG.status == COGStatus.AVAILABLE,
            RadarCOG.observation_time >= cutoff_time
        )\
        .order_by(RadarCOG.observation_time)\
        .all()
    
    times = [cog.observation_time for cog in cogs]
    
    return TimelineResponse(
        radar_code=radar_code,
        product_key=product_key,
        times=times,
        count=len(times),
        latest=times[-1] if times else None,
        oldest=times[0] if times else None,
    )


@router.get("/{cog_id}", response_model=COGResponse)
def get_cog(
    cog_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific COG by ID."""
    cog = db.query(RadarCOG).filter(RadarCOG.id == cog_id).first()
    
    if not cog:
        raise HTTPException(status_code=404, detail=f"COG with ID {cog_id} not found")
    
    return cog_to_response(cog)