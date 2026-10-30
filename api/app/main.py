# api/app/main.py
from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import json
import logging
import os
import time
import rasterio
from rasterio.env import Env

from .auth.dependencies import require_user
from .config import settings
from .mail.service import shutdown_mail_executor
from .routers import (
    admin_router,
    auth_router,
    cogs_router,
    colormap_router,
    frames_router,
    org_router,
    organizations_router,
    permissions_router,
    products_router,
    radars_router,
    registration_router,
    tiles_router,
    tops_cores_router,
    users_router,
)
from .schemas import HealthResponse
from .services.tile_service import _tile_render_executor
from .services.redis_client import get_redis, close_redis

# Setup logging. LOG_LEVEL=DEBUG shows per-tile/frame lines (default INFO).
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Radar Visualization API...")
    logger.info(f"Database: {settings.db_host}:{settings.db_port}/{settings.db_name}")
    logger.info(f"COG Base Path: {settings.cog_base_path}")

    try:
        from radar_db import db_manager
        from radar_db.accounts import count_active_admins
        with db_manager.get_session() as session:
            if count_active_admins(session) == 0:
                logger.warning(
                    "No active admin users. Create one with: "
                    "make create-admin U=<usuario> (or set ADMIN_USERNAME / ADMIN_PASSWORD and restart db-init)"
                )
    except Exception as exc:  # DB not ready must not block startup
        logger.warning(f"Could not check admin users at startup: {exc}")

    # The switch alone does not turn registration on (see Settings.registration_available): say why it is off,
    # and warn when it is on without the terms.
    for message in settings.registration_warnings:
        logger.warning(message)

    gdal_env = Env(
        GDAL_CACHEMAX=settings.gdal_cachemax,
        VSI_CACHE=settings.vsi_cache,
        VSI_CACHE_SIZE=settings.vsi_cache_size,
        GDAL_DISABLE_READDIR_ON_OPEN=settings.gdal_disable_readdir_on_open,
        GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
        GDAL_TIFF_INTERNAL_MASK="YES",
        GDAL_TIFF_OVR_BLOCKSIZE="256",
    )
    gdal_env.__enter__()
    logger.info(
        "GDAL environment configured:\n"
        f"      GDAL_CACHEMAX={settings.gdal_cachemax}MB\n"
        f"      VSI_CACHE={settings.vsi_cache}\n"
        f"      VSI_CACHE_SIZE={settings.vsi_cache_size}\n"
        f"      GDAL_DISABLE_READDIR_ON_OPEN={settings.gdal_disable_readdir_on_open}"
    )

    # Eagerly establish Redis connection so the first tile request is fast
    redis_client = get_redis()
    redis_ok = redis_client is not None
    if redis_ok:
        logger.info(
            "Redis L2 tile cache connected at %s:%d",
            settings.redis_host,
            settings.redis_port,
        )
    else:
        logger.warning("Redis unavailable — falling back to L1 cache only")

    try:
        worker_count = int(os.environ.get("UVICORN_WORKERS", "1") or "1")
    except ValueError:
        worker_count = 1
    if worker_count > 1 and not redis_ok:
        logger.warning(
            f"Running {worker_count} workers WITHOUT Redis. "
            f"Each worker has an independent L1 cache — cache hit rates "
            f"will be reduced. Start Redis to enable shared caching."
        )

    worker_id = os.getpid()
    logger.info(
        f"Worker PID={worker_id} started. "
        f"Render threads={settings.tile_render_threads} "
        f"Redis={'connected' if redis_ok else 'unavailable'}"
    )

    try:
        yield
    finally:
        # Shutdown
        logger.info("Shutting down Radar Visualization API...")
        close_redis()
        logger.info("Redis connection closed.")
        _tile_render_executor.shutdown(wait=False)
        logger.info("Tile render executor shut down.")
        # Own threads of the mail sends (see api/app/mail/service.py).
        shutdown_mail_executor()
        logger.info("Mail executor shut down.")
        # Note: per-thread rasterio DatasetReader caches (threading.local) cannot
        # be enumerated or closed globally.  Dataset cleanup happens naturally as
        # executor threads exit — the OS reclaims all underlying file handles.
        # No explicit shutdown cleanup is required or possible for threading.local
        # caches.
        gdal_env.__exit__(None, None, None)


# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="""
    API for serving radar visualization data.
    
    ## Features
    
    * **Radars**: List and query radar stations
    * **Products**: List radar products and their color scales
    * **COGs**: Query Cloud Optimized GeoTIFF metadata
    * **Tiles**: Serve map tiles from COG files
    
    ## Tile URL Format
    
    Tiles can be requested in two ways:
    
    1. By COG ID: `/api/v1/tiles/{cog_id}/{z}/{x}/{y}.png`
    2. By parameters: `/api/v1/tiles/by-params/{radar}/{product}/{timestamp}/{z}/{x}/{y}.png`
    """,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """422 for a body or parameter that fails validation, same shape as FastAPI's default minus two things.

    The default repeats each rejected value ("input") in the answer. That echoes back what was sent (a password
    typed in a wrong field, for example) and, for a character that is not valid UTF-8, the answer itself could
    not be encoded and the request ended in a 500. "input" and "ctx" are dropped, and the body is written with
    ASCII escapes so no character in a message can break it.
    """
    errors = [{key: value for key, value in error.items() if key not in ("input", "ctx")} for error in exc.errors()]
    content = json.dumps({"detail": errors}, ensure_ascii=True, default=str)
    return Response(content=content, status_code=422, media_type="application/json")


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Include routers
# Every data router needs a session (admin or viewer). admin and users enforce the admin role
# themselves, and auth handles its own public endpoints (login, refresh, logout).
_session_required = [Depends(require_user)]
app.include_router(radars_router, prefix=settings.api_prefix, dependencies=_session_required)
app.include_router(products_router, prefix=settings.api_prefix, dependencies=_session_required)
app.include_router(cogs_router, prefix=settings.api_prefix, dependencies=_session_required)
app.include_router(tiles_router, prefix=settings.api_prefix, dependencies=_session_required)
app.include_router(colormap_router, prefix=settings.api_prefix, dependencies=_session_required)
app.include_router(frames_router, prefix=settings.api_prefix, dependencies=_session_required)
app.include_router(tops_cores_router, prefix=settings.api_prefix, dependencies=_session_required)
app.include_router(admin_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
# Public (no session): sign-up, e-mail verification and password recovery.
app.include_router(registration_router, prefix=settings.api_prefix)
app.include_router(users_router, prefix=settings.api_prefix)
# The user's own permissions; the route itself requires a session (get_current_user).
app.include_router(permissions_router, prefix=settings.api_prefix)
# Company accounts: each router requires its role itself (admin / org_admin).
app.include_router(organizations_router, prefix=settings.api_prefix)
app.include_router(org_router, prefix=settings.api_prefix)


# Health check endpoints
@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """Basic health check."""
    from radar_db import check_db_connection
    from datetime import datetime

    db_ok = check_db_connection()

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        database=db_ok,
        timestamp=datetime.utcnow(),
    )


@app.get("/", tags=["Health"])
def root():
    """Root endpoint with API info."""
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "docs": "/docs",
        "health": "/health",
    }
