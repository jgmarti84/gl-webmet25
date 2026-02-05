# api/app/routers/radars.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from radar_db import get_db, Radar
from ..schemas import RadarResponse, RadarListResponse

router = APIRouter(prefix="/radars", tags=["Radars"])


@router.get("", response_model=RadarListResponse)
def list_radars(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """
    List all radar stations.
    
    - **active_only**: If true, only return active radars (default: true)
    """
    query = db.query(Radar)
    
    if active_only:
        query = query.filter(Radar.is_active == True)
    
    radars = query.order_by(Radar.code).all()
    
    # Convert to response with computed extent
    radar_responses = []
    for radar in radars:
        lat_max, lat_min, long_max, long_min = radar.get_extent()
        
        radar_responses.append(RadarResponse(
            code=radar.code,
            title=radar.title,
            description=radar.description,
            center_lat=float(radar.center_lat),
            center_long=float(radar.center_long),
            img_radio=radar.img_radio,
            is_active=radar.is_active,
            extent={
                "lat_max": lat_max,
                "lat_min": lat_min,
                "lon_max": long_max,
                "lon_min": long_min,
            }
        ))
    
    return RadarListResponse(
        radars=radar_responses,
        count=len(radar_responses)
    )


@router.get("/{radar_code}", response_model=RadarResponse)
def get_radar(
    radar_code: str,
    db: Session = Depends(get_db)
):
    """Get a specific radar by code."""
    radar = db.query(Radar).filter(Radar.code == radar_code).first()
    
    if not radar:
        raise HTTPException(status_code=404, detail=f"Radar '{radar_code}' not found")
    
    lat_max, lat_min, long_max, long_min = radar.get_extent()
    
    return RadarResponse(
        code=radar.code,
        title=radar.title,
        description=radar.description,
        center_lat=float(radar.center_lat),
        center_long=float(radar.center_long),
        img_radio=radar.img_radio,
        is_active=radar.is_active,
        extent={
            "lat_max": lat_max,
            "lat_min": lat_min,
            "lon_max": long_max,
            "lon_min": long_min,
        }
    )