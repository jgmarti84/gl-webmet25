"""FastAPI app for the storm tracking sidecar."""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from tracking_api import volumes as volumes_mod
from tracking_api.config import settings
from tracking_api.db import check_connection, get_db
from tracking_api.schemas import (
    AvailabilityItem,
    AvailabilityResponse,
    HealthResponse,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _gl_tracker_importable() -> bool:
    """Whether gl-tracker is on the path and imports cleanly.

    Checked rather than assumed because it arrives by clone at build time, not
    as a declared dependency — a bad ref produces an image that starts fine and
    then fails on the first tracking request.
    """
    try:
        import importlib

        for name in ("config", "gate", "grilla", "pipeline", "estado"):
            importlib.import_module(name)
        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("gl-tracker is not importable: %s", exc)
        return False


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=(
        "On-demand convective storm tracking over radarlib's 3D Cartesian "
        "volumes (NC cubes). Wraps gl-tracker, which is consumed read-only."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix=settings.api_prefix, tags=["Tracking"])


@router.get("/availability", response_model=AvailabilityResponse)
def get_availability(
    radar: Optional[str] = Query(default=None, description="Radar code, e.g. RMA1"),
    db: Session = Depends(get_db),
) -> AvailabilityResponse:
    """Which radars have cubes, and over what span.

    ``min_time`` is the frontend's lower bound for its time picker: tracking
    cannot reach further back than the oldest cube surviving retention.

    Returns an empty list rather than 404 when nothing matches.
    """
    rows = volumes_mod.availability(db, radar)
    return AvailabilityResponse(
        radars=[
            AvailabilityItem(
                radar_code=r.radar_code,
                count=r.count,
                min_time=r.min_time,
                max_time=r.max_time,
            )
            for r in rows
        ]
    )


app.include_router(router)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health() -> HealthResponse:
    """Liveness plus the dependencies that fail quietly.

    A missing cube mount and an unimportable gl-tracker both leave the service
    answering requests normally while every tracking job fails, so both are
    surfaced here instead of being discovered on first use.
    """
    db_ok = check_connection()
    dir_exists = os.path.isdir(settings.nccube_dir)
    tracker_ok = _gl_tracker_importable()

    return HealthResponse(
        status="ok" if (db_ok and dir_exists and tracker_ok) else "degraded",
        database=db_ok,
        nccube_dir=settings.nccube_dir,
        nccube_dir_exists=dir_exists,
        gl_tracker_importable=tracker_ok,
        version=settings.api_version,
    )


@app.get("/", tags=["Health"])
def root():
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "docs": "/docs",
        "health": "/health",
    }
