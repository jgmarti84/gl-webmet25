# api/app/schemas/responses.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    database: bool = True
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# RADAR SCHEMAS
# =============================================================================

class RadarResponse(BaseModel):
    """Single radar response."""
    code: str
    title: str
    description: Optional[str] = None
    center_lat: float
    center_long: float
    img_radio: int
    is_active: bool
    extent: Optional[Dict[str, float]] = None  # Computed bounding box
    
    class Config:
        from_attributes = True


class RadarListResponse(BaseModel):
    """List of radars response."""
    radars: List[RadarResponse]
    count: int


# =============================================================================
# PRODUCT SCHEMAS
# =============================================================================

class ReferenceResponse(BaseModel):
    """Color reference for legend."""
    id: int
    title: str
    description: Optional[str] = None
    unit: Optional[str] = None
    value: float
    color: str
    color_font: str
    
    class Config:
        from_attributes = True


class ProductResponse(BaseModel):
    """Single product response."""
    id: int
    product_key: str
    product_title: str
    product_description: Optional[str] = None
    enabled: bool
    see_in_open: bool
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: Optional[str] = None
    references: List[ReferenceResponse] = []
    
    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    """List of products response."""
    products: List[ProductResponse]
    count: int


# =============================================================================
# COG SCHEMAS
# =============================================================================

class COGResponse(BaseModel):
    """Single COG file response."""
    id: int
    radar_code: str
    product_key: Optional[str] = None
    product_id: Optional[int] = None
    observation_time: datetime
    elevation_angle: Optional[float] = None
    file_path: str
    file_name: str
    
    # Data statistics
    data_min: Optional[float] = None
    data_max: Optional[float] = None
    
    # Spatial info
    bbox: Optional[Dict[str, float]] = None  # {min_lat, max_lat, min_lon, max_lon}
    
    # Tile URL template
    tile_url: Optional[str] = None
    
    class Config:
        from_attributes = True


class COGListResponse(BaseModel):
    """List of COGs response."""
    cogs: List[COGResponse]
    count: int
    total: int
    page: int
    page_size: int


class TimelineResponse(BaseModel):
    """Timeline of available COGs for animation."""
    radar_code: str
    product_key: str
    times: List[datetime]
    count: int
    latest: Optional[datetime] = None
    oldest: Optional[datetime] = None


# =============================================================================
# LEGEND/COLORMAP SCHEMAS
# =============================================================================

class ColormapEntry(BaseModel):
    """Single colormap entry."""
    value: float
    color: str  # Hex color
    label: Optional[str] = None


class ColormapResponse(BaseModel):
    """Colormap for a product."""
    product_key: str
    entries: List[ColormapEntry]
    min_value: float
    max_value: float
    unit: Optional[str] = None