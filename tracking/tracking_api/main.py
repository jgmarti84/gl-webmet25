"""FastAPI app for the storm tracking sidecar."""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from tracking_api import volumes as volumes_mod
from tracking_api.config import settings
from tracking_api.db import check_connection, get_db, session_scope
from tracking_api.jobs import Job, JobStatus, cache_key, store
from tracking_api.schemas import (
    AvailabilityItem,
    AvailabilityResponse,
    HealthResponse,
    JobCreated,
    JobProgress,
    JobResult,
    VolumeWindow,
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


def _execute(job: Job) -> None:
    """Run one job. Executes on the worker thread, not the request thread.

    Imports the driver lazily so that a broken gl-tracker clone surfaces as a
    failed job with a clear message, rather than preventing the whole service
    from starting — /health already reports that condition separately.
    """
    from tracking_api.driver import build_config, config_summary, run_tracking
    from tracking_api.schemas import TrackingConfig

    cfg = build_config(TrackingConfig(**job.config))
    job.config_in_force = config_summary(cfg)

    with session_scope() as session:
        vols = volumes_mod.resolve_window(session, job.radar, job.start, job.end)

    if not vols:
        job.frames = []
        job.volumes_total = 0
        return

    missing = volumes_mod.missing_on_disk(vols)
    if missing:
        # Retention and the indexer's prune pass are not synchronised, so a row
        # can briefly outlive its file. Failing up front beats dying midway.
        raise FileNotFoundError(
            f"{len(missing)} cube(s) indexed but not on disk, first: {missing[0].path}"
        )

    job.volumes_total = len(vols)

    def progress(done: int, total: int) -> None:
        job.volumes_done = done

    job.frames = run_tracking(vols, cfg, progress=progress)


@router.post("/jobs", response_model=JobCreated, status_code=202)
def submit_job(request: VolumeWindow) -> JobCreated:
    """Queue a tracking run over a radar and time window.

    Returns 202 immediately; poll ``/jobs/{job_id}`` for the result. Tracking a
    window is seconds of CPU, so a synchronous response would have nowhere to
    report progress and would sit on an open connection throughout.

    An identical run already in the cache is returned straight away with
    ``cached: true`` and no work queued.
    """
    config = request.config.model_dump()
    key = cache_key(request.radar, request.start, request.end, config)

    hit = store.find_cached(key)
    if hit is not None:
        return JobCreated(
            job_id=hit.job_id, status=hit.status.value, radar=hit.radar,
            start=hit.start, end=hit.end, volumes_total=hit.volumes_total,
            cached=True,
        )

    job = store.create(request.radar, request.start, request.end, config)

    def run_and_cache(j: Job) -> None:
        _execute(j)
        j.cached = False
        store.put_cached(key, j)

    store.submit(job, run_and_cache)

    return JobCreated(
        job_id=job.job_id, status=job.status.value, radar=job.radar,
        start=job.start, end=job.end, volumes_total=job.volumes_total,
    )


@router.get("/jobs/{job_id}", response_model=JobResult)
def get_job(job_id: str) -> JobResult:
    """Poll a job.

    ``frames`` is null until the job finishes, so polling stays cheap. A 404
    means the job is unknown *or* was evicted — the store is in-memory and does
    not survive a restart, so a client should treat it as "resubmit".
    """
    job = store.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown job. The job store is in-memory; resubmit the request.",
        )

    return JobResult(
        job_id=job.job_id,
        status=job.status.value,
        radar=job.radar,
        start=job.start,
        end=job.end,
        progress=JobProgress(
            volumes_total=job.volumes_total,
            volumes_done=job.volumes_done,
            fraction=job.progress,
        ),
        created_at=job.created_at,
        finished_at=job.finished_at,
        cached=job.cached,
        error=job.error,
        config_in_force=job.config_in_force,
        frames=job.frames if job.status is JobStatus.DONE else None,
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
