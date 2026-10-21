"""Request and response models."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Service liveness, plus the two things that silently break it."""

    status: str
    database: bool
    #: The cube mount. Present but empty is a different failure from absent,
    #: and both look like "no data" from the frontend.
    nccube_dir: str
    nccube_dir_exists: bool
    gl_tracker_importable: bool
    version: str


class AvailabilityItem(BaseModel):
    """Cube coverage for one radar."""

    radar_code: str
    count: int
    min_time: Optional[datetime] = None
    max_time: Optional[datetime] = None


class AvailabilityResponse(BaseModel):
    radars: List[AvailabilityItem]


class TrackingConfig(BaseModel):
    """The tunables exposed to clients.

    Deliberately a whitelist. gl-tracker's ``Config`` carries many more fields,
    and letting a client set arbitrary attributes on it would be both a
    correctness and a security problem.

    Mapping into ``Config`` is **not** uniform — see `build_config`:
      * ``dbz_threshold`` / ``min_area_km2`` are top-level ``Config`` fields
      * ``cappi_height_m`` belongs in ``Config.filter_overrides``
    """

    cappi_height_m: float = Field(
        2500.0, ge=500.0, le=15000.0,
        description="Altitude of the CAPPI used for detection, metres above the antenna.",
    )
    dbz_threshold: float = Field(
        35.0, ge=0.0, le=75.0,
        description="Reflectivity threshold for detecting a system.",
    )
    min_area_km2: float = Field(
        50.0, ge=1.0, le=10000.0,
        description="Minimum area for a detected system to be kept.",
    )


class VolumeWindow(BaseModel):
    """A tracking request."""

    radar: str = Field(..., description="Radar code, e.g. RMA1")
    start: datetime = Field(..., description="Window start (UTC, inclusive)")
    end: datetime = Field(..., description="Window end (UTC, inclusive)")
    config: TrackingConfig = Field(default_factory=TrackingConfig)


class JobCreated(BaseModel):
    """Acknowledgement of a submitted job."""

    job_id: str
    status: str
    radar: str
    start: datetime
    end: datetime
    volumes_total: int
    #: True when an identical run was already cached and no work was queued.
    cached: bool = False


class JobProgress(BaseModel):
    volumes_total: int
    volumes_done: int
    fraction: float


class JobResult(BaseModel):
    """A job's state, and its frames once finished.

    ``frames`` stays null until the job completes, so a client can poll without
    transferring a partial payload each time.
    """

    job_id: str
    status: str
    radar: str
    start: datetime
    end: datetime
    progress: JobProgress
    created_at: datetime
    finished_at: Optional[datetime] = None
    cached: bool = False
    error: Optional[str] = None
    #: The configuration actually in force, read back off gl-tracker's Config
    #: rather than echoed from the request — so it includes defaults the client
    #: never sent, and is what the UI should display.
    config_in_force: Optional[dict] = None
    frames: Optional[List[dict]] = None
