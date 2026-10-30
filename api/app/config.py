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
    db_password: str = Field(default="", alias="DB_PASSWORD")
    
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
    # Closed or expired logins older than this are deleted when that user logs in again (audit window).
    session_retention_days: int = Field(default=90, alias="SESSION_RETENTION_DAYS")
    cookie_secure: bool = Field(default=True, alias="COOKIE_SECURE")
    # Origins allowed to send state-changing requests (CSRF defense)
    allowed_origins: str = Field(default="", alias="ALLOWED_ORIGINS")
    login_max_failed_attempts: int = Field(default=5, alias="LOGIN_MAX_FAILED_ATTEMPTS")
    login_lockout_minutes: int = Field(default=15, alias="LOGIN_LOCKOUT_MINUTES")

    # "Sign in with Google": the OAuth client ID created in the Google Cloud console (Web application). It is public
    # (the login page needs it to draw the button), not a secret. Empty = the button is not offered and
    # POST /auth/google answers 503.
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")

    # Public registration and e-mail. Registration stays off until everything it needs is set.
    registration_enabled: bool = Field(default=False, alias="REGISTRATION_ENABLED")
    # Public address of the site, used to build the links inside the mails.
    public_base_url: str = Field(default="", alias="PUBLIC_BASE_URL")
    mail_host: str = Field(default="", alias="MAIL_HOST")
    mail_port: int = Field(default=587, alias="MAIL_PORT")
    mail_user: str = Field(default="", alias="MAIL_USER")
    mail_password: str = Field(default="", alias="MAIL_PASSWORD")
    mail_from: str = Field(default="", alias="MAIL_FROM")
    # How the connection to the SMTP server (MAIL_HOST, the sender's side, not the recipient's) is encrypted.
    # Use one of the two, never both:
    #   MAIL_STARTTLS=true  starts in plain text and upgrades to TLS (usual port 587). Default; fails the send
    #                       if the server does not offer it, so the password never goes out in clear.
    #   MAIL_USE_SSL=true   encrypted from the first byte (usual port 465); when on, MAIL_STARTTLS is ignored.
    # Set MAIL_STARTTLS=false only for a local test mailbox such as Mailpit, which has no encryption.
    mail_starttls: bool = Field(default=True, alias="MAIL_STARTTLS")
    mail_use_ssl: bool = Field(default=False, alias="MAIL_USE_SSL")
    # Whether the sign-up form asks the person to accept the terms and the privacy policy. Off by default: the form
    # then shows no checkbox and no legal link, and TERMS_URL / PRIVACY_URL are not needed. Turn it on (with both
    # links) before opening the sign-up to the public: it is the information and consent notice that the data
    # protection law expects when personal data is collected.
    terms_required: bool = Field(default=False, alias="TERMS_REQUIRED")
    # Links to the terms and the privacy policy shown in the sign-up form (provided by the observatory).
    # Only used when TERMS_REQUIRED=true.
    terms_url: str = Field(default="", alias="TERMS_URL")
    privacy_url: str = Field(default="", alias="PRIVACY_URL")
    email_verify_ttl_hours: int = Field(default=24, alias="EMAIL_VERIFY_TTL_HOURS")
    password_reset_ttl_minutes: int = Field(default=60, alias="PASSWORD_RESET_TTL_MINUTES")
    # Per-account sending caps (see EmailToken): at most N mails per hour, at least S seconds apart.
    mail_max_per_hour: int = Field(default=3, alias="MAIL_MAX_PER_HOUR")
    mail_min_interval_seconds: int = Field(default=60, alias="MAIL_MIN_INTERVAL_SECONDS")
    # Global caps: all the mails of the site together (every account). A fuse well above normal traffic, against
    # someone signing up many different addresses (each one a new account, so the per-account caps never apply).
    # Past the hourly cap only password recovery keeps going out; past the daily cap nothing does. Keep the daily
    # cap under the SMTP provider's limit (Gmail Workspace: about 2,000 a day; passing it blocks the account a day).
    mail_max_global_per_hour: int = Field(default=200, alias="MAIL_MAX_GLOBAL_PER_HOUR")
    mail_max_global_per_day: int = Field(default=1500, alias="MAIL_MAX_GLOBAL_PER_DAY")

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
    def google_login_available(self) -> bool:
        return bool(self.google_client_id.strip())

    @property
    def mail_configured(self) -> bool:
        # Enough to send a mail with a working link. Also what password recovery needs.
        return bool(self.mail_host and self.mail_from and self.public_base_url)

    @property
    def registration_available(self) -> bool:
        # The switch alone is not enough: without mail the verification link never arrives, and when the terms are
        # required the sign-up form needs both legal links to show what the person must accept.
        legal_links_ready = not self.terms_required or bool(self.terms_url and self.privacy_url)
        return bool(self.registration_enabled and self.mail_configured and legal_links_ready)

    @property
    def registration_warnings(self) -> list:
        """What to tell in the log at startup about the sign-up: empty when it is off or everything is in place."""
        if not self.registration_enabled:
            return []
        needed = [
            ("MAIL_HOST", self.mail_host),
            ("MAIL_FROM", self.mail_from),
            ("PUBLIC_BASE_URL", self.public_base_url),
        ]
        if self.terms_required:
            needed += [("TERMS_URL", self.terms_url), ("PRIVACY_URL", self.privacy_url)]
        missing = [name for name, value in needed if not value]
        if missing:
            return [
                "REGISTRATION_ENABLED=true but the setup is incomplete "
                f"(missing: {', '.join(missing)}): registration stays off"
            ]
        if not self.terms_required:
            # Working, but people would give their data without being shown any terms or privacy policy.
            return [
                "REGISTRATION_ENABLED=true with TERMS_REQUIRED=false: people sign up without accepting any terms "
                "or privacy policy. Set TERMS_REQUIRED=true, TERMS_URL and PRIVACY_URL before opening the "
                "sign-up to the public"
            ]
        return []

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