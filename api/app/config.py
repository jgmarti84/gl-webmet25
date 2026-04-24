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