# database/radar_db/config.py
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class DatabaseSettings(BaseSettings):
    """Database configuration loaded from environment variables."""
    
    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_name: str = Field(default="radar_db", alias="DB_NAME")
    db_user: str = Field(default="postgres", alias="DB_USER")
    db_password: str = Field(default="postgres", alias="DB_PASSWORD")
    
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra env vars
    
    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


settings = DatabaseSettings()