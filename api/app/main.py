# api/app/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time

from .config import settings
from .routers import radars_router, products_router, cogs_router, tiles_router, colormap_router
from .schemas import HealthResponse
from .services.tile_service import _tile_render_executor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Radar Visualization API...")
    logger.info(f"Database: {settings.db_host}:{settings.db_port}/{settings.db_name}")
    logger.info(f"COG Base Path: {settings.cog_base_path}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Radar Visualization API...")
    _tile_render_executor.shutdown(wait=False)
    logger.info("Tile render executor shut down.")


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


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Include routers
app.include_router(radars_router, prefix=settings.api_prefix)
app.include_router(products_router, prefix=settings.api_prefix)
app.include_router(cogs_router, prefix=settings.api_prefix)
app.include_router(tiles_router, prefix=settings.api_prefix)
app.include_router(colormap_router, prefix=settings.api_prefix)


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
        timestamp=datetime.utcnow()
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