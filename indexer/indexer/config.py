# indexer/indexer/config.py
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import List
import os


class IndexerSettings(BaseSettings):
    """Indexer service configuration."""
    
    # Database (same as radar_db)
    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_name: str = Field(default="radar_db", alias="DB_NAME")
    db_user: str = Field(default="postgres", alias="DB_USER")
    db_password: str = Field(default="postgres", alias="DB_PASSWORD")
    
    # Indexer specific
    watch_path: str = Field(default="/product_output", alias="WATCH_PATH")
    scan_interval_seconds: int = Field(default=30, alias="SCAN_INTERVAL")
    file_pattern: str = Field(default="*.tif", alias="FILE_PATTERN")
    
    # Raw radar codes string from env (we parse it in the property).
    # Keep this as a string to avoid pydantic attempting to `json.loads` the env value
    # which raises JSONDecodeError for empty values.
    radar_codes_raw: str = Field(default='', alias="RADAR_CODES")

    @property
    def radar_codes(self) -> List[str]:
        """Return parsed radar codes as a list.

        Supports:
        - empty string -> []
        - JSON array string like '["RMA3","RMA4"]'
        - CSV string like 'RMA3,RMA4'
        - bracketed CSV like '[RMA3,RMA4]'
        """
        v = self.radar_codes_raw
        if v is None:
            return []
        if isinstance(v, (list, tuple)):
            return list(v)
        if not isinstance(v, str):
            return []

        s = v.strip()
        if s == '':
            return []

        # Try JSON array first
        if s.startswith('[') and s.endswith(']'):
            try:
                import json
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except Exception:
                # fall back to lenient parsing below
                s = s[1:-1].strip()

        parts = []
        for item in s.split(','):
            item = item.strip().strip('"\'')
            if item:
                parts.append(item)
        return parts
    # Processing
    compute_stats: bool = Field(default=True, alias="COMPUTE_STATS")
    compute_checksum: bool = Field(default=False, alias="COMPUTE_CHECKSUM")
    
    # Radar activity detection
    radar_active_threshold_hours: int = Field(default=2, alias="RADAR_ACTIVE_THRESHOLD_HOURS")

    # Cleanup
    mark_missing_files: bool = Field(default=True, alias="MARK_MISSING_FILES")
    
    class Config:
        env_file = ".env"
        extra = "ignore"
    
    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


settings = IndexerSettings()