"""Admin request/response schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AdminBulkDeleteResponse(BaseModel):
    """Bulk delete operation result."""

    deleted_count: int = Field(description="Number of deleted records")


class AdminPaginatedResponse(BaseModel):
    """Pagination metadata for list responses."""

    page: int = Field(description="Current page number")
    page_size: int = Field(description="Page size used in query")
    total: int = Field(description="Total matching records before pagination")


class AdminRadarBase(BaseModel):
    """Shared radar fields for admin requests."""

    title: str = Field(description="Radar display title", max_length=64)
    description: Optional[str] = Field(
        default=None, description="Radar description", max_length=64
    )
    center_lat: float = Field(description="Radar center latitude")
    center_long: float = Field(description="Radar center longitude")
    img_radio: int = Field(description="Radar coverage radius")
    is_active: bool = Field(description="Whether radar is active")
    detail_view_enabled: bool = Field(default=False, description="Whether the one-radar detail view is accessible")
    point1_lat: float = Field(default=0, description="Boundary point 1 latitude")
    point1_long: float = Field(default=0, description="Boundary point 1 longitude")
    point2_lat: float = Field(default=0, description="Boundary point 2 latitude")
    point2_long: float = Field(default=0, description="Boundary point 2 longitude")


class AdminRadarCreate(AdminRadarBase):
    """Create radar payload."""

    code: str = Field(description="Unique radar code", max_length=16)


class AdminRadarUpdate(AdminRadarBase):
    """Full radar update payload."""


class AdminRadarPatch(BaseModel):
    """Partial radar update payload."""

    title: Optional[str] = Field(
        default=None, description="Radar display title", max_length=64
    )
    description: Optional[str] = Field(
        default=None, description="Radar description", max_length=64
    )
    center_lat: Optional[float] = Field(
        default=None, description="Radar center latitude"
    )
    center_long: Optional[float] = Field(
        default=None, description="Radar center longitude"
    )
    img_radio: Optional[int] = Field(default=None, description="Radar coverage radius")
    is_active: Optional[bool] = Field(
        default=None, description="Whether radar is active"
    )
    detail_view_enabled: Optional[bool] = Field(
        default=None, description="Whether the one-radar detail view is accessible"
    )
    point1_lat: Optional[float] = Field(
        default=None, description="Boundary point 1 latitude"
    )
    point1_long: Optional[float] = Field(
        default=None, description="Boundary point 1 longitude"
    )
    point2_lat: Optional[float] = Field(
        default=None, description="Boundary point 2 latitude"
    )
    point2_long: Optional[float] = Field(
        default=None, description="Boundary point 2 longitude"
    )


class AdminRadarResponse(AdminRadarBase):
    """Radar admin response."""

    code: str = Field(description="Unique radar code")
    created_at: Optional[datetime] = Field(
        default=None, description="Record creation time"
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Record update time"
    )

    class Config:
        from_attributes = True


class AdminRadarProductBase(BaseModel):
    """Shared product fields."""

    product_key: str = Field(description="Unique product key", max_length=16)
    product_title: str = Field(description="Product title", max_length=64)
    product_description: Optional[str] = Field(
        default="", description="Product description"
    )
    enabled: bool = Field(description="Whether product is enabled")
    see_in_open: bool = Field(description="Whether product is shown in open view")
    min_value: Optional[float] = Field(
        default=None, description="Minimum product value"
    )
    max_value: Optional[float] = Field(
        default=None, description="Maximum product value"
    )
    unit: Optional[str] = Field(default=None, description="Product unit")
    default_cmap: Optional[str] = Field(
        default=None, description="Default colormap name for this product", max_length=64
    )


class AdminRadarProductCreate(AdminRadarProductBase):
    """Create product payload."""


class AdminRadarProductUpdate(AdminRadarProductBase):
    """Full product update payload."""


class AdminRadarProductPatch(BaseModel):
    """Partial product update payload."""

    product_key: Optional[str] = Field(
        default=None, description="Unique product key", max_length=16
    )
    product_title: Optional[str] = Field(
        default=None, description="Product title", max_length=64
    )
    product_description: Optional[str] = Field(
        default=None, description="Product description"
    )
    enabled: Optional[bool] = Field(
        default=None, description="Whether product is enabled"
    )
    see_in_open: Optional[bool] = Field(
        default=None, description="Whether product is shown in open view"
    )
    min_value: Optional[float] = Field(
        default=None, description="Minimum product value"
    )
    max_value: Optional[float] = Field(
        default=None, description="Maximum product value"
    )
    unit: Optional[str] = Field(default=None, description="Product unit")
    default_cmap: Optional[str] = Field(
        default=None, description="Default colormap name for this product", max_length=64
    )


class AdminRadarProductResponse(AdminRadarProductBase):
    """Product admin response."""

    id: int = Field(description="Product ID")
    created_at: Optional[datetime] = Field(
        default=None, description="Record creation time"
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Record update time"
    )

    class Config:
        from_attributes = True


class AdminReferenceBase(BaseModel):
    """Shared reference fields."""

    product_id: int = Field(description="Associated product ID")
    title: Optional[str] = Field(
        default="", description="Reference title", max_length=64
    )
    description: Optional[str] = Field(
        default="", description="Reference description", max_length=255
    )
    unit: Optional[str] = Field(default="", description="Reference unit", max_length=64)
    value: float = Field(description="Reference scalar value")
    color: str = Field(description="Background color in hex format")
    color_font: str = Field(description="Font color in hex format")


class AdminReferenceCreate(AdminReferenceBase):
    """Create reference payload."""


class AdminReferenceUpdate(AdminReferenceBase):
    """Full reference update payload."""


class AdminReferenceResponse(AdminReferenceBase):
    """Reference admin response."""

    id: int = Field(description="Reference ID")

    class Config:
        from_attributes = True


class AdminCOGResponse(BaseModel):
    """COG admin response."""

    id: int = Field(description="COG ID")
    radar_code: str = Field(description="Radar code")
    product_id: Optional[int] = Field(default=None, description="Product ID")
    product_key: Optional[str] = Field(default=None, description="Resolved product key")
    observation_time: datetime = Field(description="Observation timestamp")
    file_path: str = Field(description="Absolute file path")
    file_name: str = Field(description="File name")
    file_size_bytes: Optional[int] = Field(
        default=None, description="File size in bytes"
    )
    file_checksum: Optional[str] = Field(default=None, description="File checksum")
    status: str = Field(description="COG status value")
    vol_nr: Optional[str] = Field(default=None, description="Volume number")
    polarimetric_var: Optional[str] = Field(
        default=None, description="Polarimetric variable"
    )
    indexed_at: Optional[datetime] = Field(default=None, description="Indexing time")
    error_message: Optional[str] = Field(
        default=None, description="Latest ingestion error"
    )
    created_at: Optional[datetime] = Field(
        default=None, description="Record creation time"
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Record update time"
    )


class AdminCOGPatchStatus(BaseModel):
    """COG status update payload."""

    status: str = Field(description="New COG status value")


class AdminCOGListResponse(AdminPaginatedResponse):
    """Paginated COG list response."""

    items: List[AdminCOGResponse] = Field(description="Current page COG records")


class AdminEstrategiaCreate(BaseModel):
    """Create strategy payload."""

    code: str = Field(description="Unique strategy code", max_length=16)
    description: Optional[str] = Field(
        default="", description="Strategy description", max_length=255
    )
    volumen_ids: List[int] = Field(
        default_factory=list, description="Linked volumen IDs"
    )


class AdminEstrategiaUpdate(BaseModel):
    """Update strategy payload."""

    description: Optional[str] = Field(
        default="", description="Strategy description", max_length=255
    )
    volumen_ids: List[int] = Field(
        default_factory=list, description="Linked volumen IDs"
    )


class AdminEstrategiaResponse(BaseModel):
    """Strategy admin response."""

    code: str = Field(description="Unique strategy code")
    description: Optional[str] = Field(default="", description="Strategy description")
    volumen_ids: List[int] = Field(
        default_factory=list, description="Linked volumen IDs"
    )
    volumen_values: List[int] = Field(
        default_factory=list, description="Linked volumen values"
    )

    class Config:
        from_attributes = True


class AdminVolumenCreate(BaseModel):
    """Create volumen payload."""

    value: int = Field(description="Volumen numeric value")


class AdminVolumenUpdate(BaseModel):
    """Update volumen payload."""

    value: int = Field(description="Volumen numeric value")


class AdminVolumenResponse(BaseModel):
    """Volumen admin response."""

    id: int = Field(description="Volumen ID")
    value: int = Field(description="Volumen numeric value")

    class Config:
        from_attributes = True


class AdminTopsAndCoresResponse(BaseModel):
    """Tops and cores admin response."""

    id: int = Field(description="Record ID")
    radar_code: str = Field(description="Radar code")
    observation_time: datetime = Field(description="Observation timestamp")
    file_path: str = Field(description="Absolute file path")
    file_name: str = Field(description="File name")
    feature_count: int = Field(description="Total features")
    core_count: int = Field(description="Core count")
    top_count: int = Field(description="Top count")
    status: str = Field(description="Record status")
    strategy: Optional[str] = Field(default=None, description="Strategy code")
    vol_nr: Optional[str] = Field(default=None, description="Volume number")
    created_at: Optional[datetime] = Field(
        default=None, description="Record creation time"
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Record update time"
    )


class AdminTopsAndCoresPatchStatus(BaseModel):
    """Tops and cores status update payload."""

    status: str = Field(description="New tops-and-cores status")


class AdminTopsAndCoresListResponse(AdminPaginatedResponse):
    """Paginated tops and cores list response."""

    items: List[AdminTopsAndCoresResponse] = Field(description="Current page records")


# ── Colormap admin schemas ─────────────────────────────────────────────────


class AdminColormapSummary(BaseModel):
    """Summary of a single colormap (one row per distinct cmap_name)."""

    cmap_name: str = Field(description="Colormap identifier")
    stop_count: int = Field(description="Total stop rows across all channels")
    is_system: bool = Field(description="System colormaps cannot be deleted")


class AdminColormapStopResponse(BaseModel):
    """Single colormap stop row."""

    id: int
    cmap_name: str
    channel: str
    position: float
    val_left: float
    val_right: float
    sort_order: int
    is_system: bool

    class Config:
        from_attributes = True


class AdminColormapStopCreate(BaseModel):
    """Create a single colormap stop."""

    cmap_name: str = Field(description="Colormap identifier", max_length=64)
    channel: str = Field(description="Colour channel: r, g or b", max_length=1)
    position: float = Field(description="Normalised position in [0, 1]")
    val_left: float = Field(description="Channel value approaching this position")
    val_right: float = Field(description="Channel value leaving this position")
    sort_order: int = Field(default=0, description="Stable ordering within (cmap_name, channel)")
    is_system: bool = Field(default=False, description="Mark as system colormap")


class AdminProductColormapOptionResponse(BaseModel):
    """Product colormap option row."""

    id: int
    product_key: str
    cmap_name: str

    class Config:
        from_attributes = True


class AdminProductColormapOptionCreate(BaseModel):
    """Create a product colormap option."""

    product_key: str = Field(description="Product key", max_length=16)
    cmap_name: str = Field(description="Colormap name", max_length=64)


class AdminColormapHexStop(BaseModel):
    """A single (position, hex_color) stop for colormap creation."""

    position: float = Field(description="Normalised position in [0, 1]", ge=0.0, le=1.0)
    color: str = Field(description="Hex color string, e.g. #FF0000", max_length=7)


class AdminColormapCreateFromHex(BaseModel):
    """Create a new colormap from a list of hex color stops."""

    cmap_name: str = Field(description="New colormap name (must be unique)", max_length=64)
    stops: List[AdminColormapHexStop] = Field(
        description="List of (position, hex_color) stops. Minimum 2.",
        min_length=2,
    )
    product_keys: List[str] = Field(
        default_factory=list,
        description="Product keys to add this colormap as an option for",
    )
