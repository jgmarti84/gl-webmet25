"""Sidecar settings.

Note the module name: this is ``tracking_api.config``, which is distinct from
gl-tracker's top-level ``config`` module holding its ``Config`` dataclass. Both
can be imported in the same process precisely because this one lives inside a
package — see the package docstring.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class TrackingSettings(BaseSettings):
    """Configuration for the tracking sidecar."""

    # Database — same variables the api and indexer services use
    db_host: str = Field(default="radar_db", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_name: str = Field(default="radar_db", alias="DB_NAME")
    db_user: str = Field(default="radar", alias="DB_USER")
    db_password: str = Field(default="radarpass", alias="DB_PASSWORD")

    # Where the NC cubes are mounted (read-only). Paths stored in the nccubes
    # table are absolute as seen by the indexer; this is here so the service can
    # report whether the mount is actually present.
    nccube_dir: str = Field(default="/nccube", alias="NCCUBE_DIR")

    # API
    api_title: str = "Radar Storm Tracking API"
    api_version: str = "0.1.0"
    api_prefix: str = "/api/tracking"

    # CORS
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")

    # How many volumes to process before the requested window so that velocity
    # and forecasts are warmed up by the time the first returned frame is
    # reached. Matches gl-tracker's Config.velocity_history_len.
    lead_in_volumes: int = Field(default=4, alias="LEAD_IN_VOLUMES")

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def database_url(self) -> str:
        # Dialect is explicit: SQLAlchemy 2.1 changed the default DBAPI for a
        # bare "postgresql://" URL from psycopg2 to psycopg (v3).
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def cors_origins_list(self) -> list:
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = TrackingSettings()
