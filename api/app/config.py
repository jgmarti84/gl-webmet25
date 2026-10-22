# api/app/config.py
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
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
    
    # CORS - explicit list; empty means "same as ALLOWED_ORIGINS"
    cors_origins: str = Field(default="", alias="CORS_ORIGINS")
    
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

    # UVICORN_WORKERS is read by docker-compose.yml, not here.
    # Set in .env or docker-compose environment section.
    # Default: 4. Formula: CPU_CORES // 2 (e.g. 4 on an 8-core server) for tile servers.

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

    # Auth (users + JWT)
    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_issuer: str = Field(default="webmet25", alias="JWT_ISSUER")
    jwt_audience: str = Field(default="webmet25-api", alias="JWT_AUDIENCE")
    access_token_ttl_minutes: int = Field(default=30, alias="ACCESS_TOKEN_TTL_MINUTES")
    session_idle_ttl_hours: int = Field(default=48, alias="SESSION_IDLE_TTL_HOURS")
    session_absolute_ttl_days: int = Field(default=7, alias="SESSION_ABSOLUTE_TTL_DAYS")
    cookie_secure: bool = Field(default=True, alias="COOKIE_SECURE")
    # Origins allowed to send state-changing requests (CSRF defense)
    allowed_origins: str = Field(default="", alias="ALLOWED_ORIGINS")
    login_max_failed_attempts: int = Field(default=5, alias="LOGIN_MAX_FAILED_ATTEMPTS")
    login_lockout_minutes: int = Field(default=15, alias="LOGIN_LOCKOUT_MINUTES")

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_long_enough(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET debe tener al menos 32 caracteres")
        return value

    class Config:
        env_file = ".env"
        extra = "ignore"
    
    @property
    def database_url(self) -> str:
        # Dialect is explicit: SQLAlchemy 2.1 changed the default DBAPI for a
        # bare "postgresql://" URL from psycopg2 to psycopg (v3).
        return f"postgresql+psycopg2://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def allowed_origins_list(self) -> list:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def cors_origins_list(self) -> list:
        if not self.cors_origins.strip():
            return self.allowed_origins_list
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = APISettings()