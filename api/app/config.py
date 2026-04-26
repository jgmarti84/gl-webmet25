# api/app/config.py
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class APISettings(BaseSettings):
    """API configuration."""
    
    # Database
    db_host: str = Field(default="postgres", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_name: str = Field(default="radar_db", alias="DB_NAME")
    db_user: str = Field(default="radar", alias="DB_USER")
    db_password: str = Field(default="radarpass", alias="DB_PASSWORD")
    
    # COG files location
    cog_base_path: str = Field(default="/product_output", alias="COG_BASE_PATH")
    
    # API settings
    api_title: str = "Radar Visualization API"
    api_version: str = "1.0.0"
    api_prefix: str = "/api/v1"
    
    # CORS
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")
    
    # Tile cache (optional, for future use)
    tile_cache_enabled: bool = Field(default=False, alias="TILE_CACHE_ENABLED")
    tile_cache_ttl: int = Field(default=300, alias="TILE_CACHE_TTL")

    # Thread pool size for CPU-bound tile rendering (see tile_service.py)
    tile_render_threads: int = Field(default=8, alias="TILE_RENDER_THREADS")

    # Per-thread rasterio DatasetReader LRU cache size (see tile_service.py)
    # Total open file handles = TILE_RENDER_THREADS × DATASET_CACHE_SIZE_PER_THREAD
    dataset_cache_size_per_thread: int = Field(default=32, alias="DATASET_CACHE_SIZE_PER_THREAD")

    # GDAL environment settings (applied at startup via rasterio.Env)
    gdal_cachemax: int = Field(default=256, alias="GDAL_CACHEMAX")
    vsi_cache: bool = Field(default=True, alias="VSI_CACHE")
    vsi_cache_size: int = Field(default=5000000, alias="VSI_CACHE_SIZE")
    gdal_disable_readdir_on_open: str = Field(default="EMPTY_DIR", alias="GDAL_DISABLE_READDIR_ON_OPEN")

    # Redis L2 tile cache
    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")
    # TTL for tiles from past observations (immutable, 24 h)
    redis_tile_ttl_seconds: int = Field(default=86400, alias="REDIS_TILE_TTL_SECONDS")
    # TTL for tiles from recent observations (may change, 1 h)
    redis_tile_ttl_recent_seconds: int = Field(default=3600, alias="REDIS_TILE_TTL_RECENT_SECONDS")
    # Kill-switch: set REDIS_ENABLED=false to disable Redis without redeploying
    redis_enabled: bool = Field(default=True, alias="REDIS_ENABLED")

    class Config:
        env_file = ".env"
        extra = "ignore"
    
    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def cors_origins_list(self) -> list:
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = APISettings()