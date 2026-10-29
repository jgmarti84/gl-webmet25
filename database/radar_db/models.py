# database/radar_db/models.py
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, 
    ForeignKey, Numeric, Table, UniqueConstraint, Index, Enum as SQLEnum,
    CheckConstraint,
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy import text
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import UUID
import uuid
from decimal import Decimal
from datetime import datetime
import enum
import math

Base = declarative_base()


class COGStatus(enum.Enum):
    """Status of a COG file."""
    PENDING = "pending"
    AVAILABLE = "available"
    PROCESSING = "processing"
    ERROR = "error"
    ARCHIVED = "archived"
    MISSING = "missing"  # File was indexed but no longer exists


# Association table for estrategia-volumen relationship
estrategia_volumen = Table(
    'estrategia_volumen',
    Base.metadata,
    Column('estrategia_code', String(16), ForeignKey('estrategias.code'), primary_key=True),
    Column('volumen_id', Integer, ForeignKey('volumenes.id'), primary_key=True)
)


class Radar(Base):
    """Radar station configuration."""
    __tablename__ = 'radars'
    
    code = Column(String(16), primary_key=True)
    title = Column(String(64), nullable=False)
    description = Column(String(64))
    center_lat = Column(Numeric(12, 8), nullable=False)
    center_long = Column(Numeric(12, 8), nullable=False)
    img_radio = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    detail_view_enabled = Column(Boolean, default=False, nullable=False, server_default='false')
    point1_lat = Column(Numeric(14, 10), default=Decimal('0'))
    point1_long = Column(Numeric(14, 10), default=Decimal('0'))
    point2_lat = Column(Numeric(14, 10), default=Decimal('0'))
    point2_long = Column(Numeric(14, 10), default=Decimal('0'))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    cog_files = relationship("RadarCOG", back_populates="radar", cascade="all, delete-orphan")
    tops_and_cores = relationship("TopsAndCores", back_populates="radar", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Radar(code='{self.code}', title='{self.title}')>"
    
    def get_extent(self):
        """Calculate geographic extent of radar coverage."""
        lat_max = float(self.center_lat) + float(self.img_radio) / 111.325
        lat_min = float(self.center_lat) - float(self.img_radio) / 111.325
        kmts_grado_by_lat = math.cos(math.radians(float(self.center_lat))) * 111.325
        long_max = float(self.center_long) + float(self.img_radio) / kmts_grado_by_lat
        long_min = float(self.center_long) - float(self.img_radio) / kmts_grado_by_lat
        return lat_max, lat_min, long_max, long_min


class RadarProduct(Base):
    """Radar product type definition."""
    __tablename__ = 'radar_products'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_key = Column(String(16), unique=True, nullable=False, index=True)
    product_title = Column(String(64), nullable=False)
    product_description = Column(Text, default='')
    enabled = Column(Boolean, default=True)
    see_in_open = Column(Boolean, default=False)
    min_value = Column(Float)
    max_value = Column(Float)
    unit = Column(String(32))
    default_cmap = Column(String(64), nullable=True, comment="Default colormap name for this product")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    references = relationship("Reference", back_populates="product", cascade="all, delete-orphan")
    cog_files = relationship("RadarCOG", back_populates="product")
    colormap_options = relationship("ProductColormapOption", back_populates="product", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<RadarProduct(key='{self.product_key}')>"


class ColormapStop(Base):
    """
    Single channel breakpoint for a LinearSegmentedColormap definition.

    Each colormap is described by a set of (position, val_left, val_right) triples
    for each of the three channels r/g/b, exactly matching the format expected by
    matplotlib.colors.LinearSegmentedColormap.  When val_left != val_right the
    breakpoint models a colour discontinuity (hard jump) at that position.

    sort_order is required because the same position may appear twice in a channel
    (one row for the departing colour, one for the arriving colour), and Python dicts
    do not guarantee stable ordering when keys repeat.
    """
    __tablename__ = 'colormap_stops'

    id = Column(Integer, primary_key=True, autoincrement=True)
    cmap_name = Column(String(64), nullable=False, index=True,
                       comment="Colormap identifier, e.g. grc_th, grc_vrad")
    channel = Column(String(1), nullable=False,
                     comment="Colour channel: r, g or b")
    position = Column(Float, nullable=False,
                      comment="Normalised position in [0, 1]")
    val_left = Column(Float, nullable=False,
                      comment="Channel value approaching this position from the left (y0)")
    val_right = Column(Float, nullable=False,
                       comment="Channel value leaving this position to the right (y1); equals val_left for continuous points")
    sort_order = Column(Integer, nullable=False, default=0,
                        comment="Stable ordering within (cmap_name, channel); required when position repeats")
    is_system = Column(Boolean, nullable=False, default=True,
                       comment="System colormaps cannot be deleted via the API")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index('idx_cmap_stop_name_channel_order', 'cmap_name', 'channel', 'sort_order'),
    )

    def __repr__(self) -> str:
        return (
            f"<ColormapStop(cmap='{self.cmap_name}', ch='{self.channel}', "
            f"pos={self.position}, [{self.val_left}->{self.val_right}])>"
        )


class ProductColormapOption(Base):
    """
    Many-to-many link between a product key and the colormaps available
    in its UI dropdown.  When no rows exist for a product_key the frontend
    falls back to showing every colormap defined in colormap_stops.
    """
    __tablename__ = 'product_colormap_options'

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_key = Column(String(16), ForeignKey('radar_products.product_key', ondelete='CASCADE'),
                         nullable=False, index=True)
    cmap_name = Column(String(64), nullable=False,
                       comment="Colormap name; must match ColormapStop.cmap_name")

    product = relationship("RadarProduct", back_populates="colormap_options")

    __table_args__ = (
        UniqueConstraint('product_key', 'cmap_name', name='uq_product_colormap_option'),
    )

    def __repr__(self) -> str:
        return f"<ProductColormapOption(product='{self.product_key}', cmap='{self.cmap_name}')>"


class Reference(Base):
    """Color/value reference for product visualization."""
    __tablename__ = 'references'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey('radar_products.id', ondelete='CASCADE'), 
                       nullable=False, index=True)
    title = Column(String(64), default='')
    description = Column(String(255), default='')
    unit = Column(String(64), default='')
    value = Column(Float, default=0, nullable=False)
    color = Column(String(7), default='#000000')
    color_font = Column(String(7), default='#FFFFFF')
    
    product = relationship("RadarProduct", back_populates="references")


class Volumen(Base):
    """Volume scanning configuration."""
    __tablename__ = 'volumenes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    value = Column(Integer, default=0, nullable=False)
    
    estrategias = relationship("Estrategia", secondary=estrategia_volumen, 
                               back_populates="volumenes")


class Estrategia(Base):
    """Scanning strategy configuration."""
    __tablename__ = 'estrategias'
    
    code = Column(String(16), primary_key=True)
    description = Column(String(255), default='')
    
    volumenes = relationship("Volumen", secondary=estrategia_volumen,
                            back_populates="estrategias")
    cog_files = relationship("RadarCOG", back_populates="estrategia")


class RadarCOG(Base):
    """
    Cloud Optimized GeoTIFF file reference.
    
    This is the main table that gets populated by the indexer service.
    """
    __tablename__ = 'radar_cogs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    radar_code = Column(String(16), ForeignKey('radars.code', ondelete='CASCADE'),
                       nullable=False, index=True)
    product_id = Column(Integer, ForeignKey('radar_products.id', ondelete='SET NULL'),
                       index=True)
    estrategia_code = Column(String(16), ForeignKey('estrategias.code', ondelete='SET NULL'),
                            index=True)
    
    # Temporal information
    observation_time = Column(DateTime(timezone=True), nullable=False, index=True)
    processing_time = Column(DateTime(timezone=True), server_default=func.now())
    indexed_at = Column(DateTime(timezone=True), server_default=func.now(),
                       comment="When this file was indexed")
    
    # Scan parameters
    polarimetric_var = Column(String(16), default='', index=True)
    elevation_angle = Column(Float, default=0.0)
    
    # File information
    file_path = Column(String(512), nullable=False, unique=True)
    file_name = Column(String(256), nullable=False, index=True)
    file_size_bytes = Column(Integer)
    file_mtime = Column(DateTime(timezone=True), comment="File modification time")
    file_checksum = Column(String(64))
    
    # COG metadata
    crs = Column(String(64))
    resolution_x = Column(Float)
    resolution_y = Column(Float)
    width = Column(Integer)
    height = Column(Integer)
    num_bands = Column(Integer, default=1)
    dtype = Column(String(32))
    nodata_value = Column(Float)
    compression = Column(String(32))
    
    # Data statistics
    data_min = Column(Float)
    data_max = Column(Float)
    data_mean = Column(Float)
    valid_pixel_count = Column(Integer)
    
    # Spatial (PostGIS)
    bbox = Column(Geometry('POLYGON', srid=4326))
    
    # COG data type metadata (raw_float / rgba / unknown)
    cog_data_type = Column(String(16), nullable=True, comment="COG data type: raw_float, rgba, or unknown")
    cog_cmap = Column(String(64), nullable=True, comment="Default colormap stored in COG metadata")
    cog_vmin = Column(Float, nullable=True, comment="Default vmin stored in COG metadata")
    cog_vmax = Column(Float, nullable=True, comment="Default vmax stored in COG metadata")

    # radarlib production metadata (present in new-format COGs, NULL for legacy)
    vol_nr = Column(String(16), nullable=True, index=True, comment="Volume number, e.g. '01'")
    radar_coverage_m = Column(Float, nullable=True, comment="Radar coverage radius in metres from radarlib tag")

    # Status
    status = Column(SQLEnum(COGStatus), default=COGStatus.AVAILABLE, index=True)
    error_message = Column(Text)
    show_me = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    radar = relationship("Radar", back_populates="cog_files")
    product = relationship("RadarProduct", back_populates="cog_files")
    estrategia = relationship("Estrategia", back_populates="cog_files")
    
    __table_args__ = (
        Index('idx_cog_radar_product_time', 'radar_code', 'product_id', 'observation_time', 'vol_nr'),
        Index('idx_cog_bbox', 'bbox', postgresql_using='gist'),
        # vol_nr is included so that the same field from different volumes
        # (e.g. DBZH from vol 01 and DBZH from vol 04) are treated as
        # distinct records.  PostgreSQL NULLs are not considered equal in
        # UNIQUE constraints, so legacy rows (vol_nr IS NULL) remain
        # independent.
        UniqueConstraint('radar_code', 'product_id', 'observation_time', 'elevation_angle', 'vol_nr',
                        name='uq_cog_radar_product_time_elev_vol'),
    )
    
    def __repr__(self):
        return f"<RadarCOG(id={self.id}, radar='{self.radar_code}', file='{self.file_name}')>"


class TopsAndCores(Base):
    """
    Tops and Cores GeoJSON file reference.

    Indexed by the watcher from *_TOPS_CORES.geojson files produced by radarlib.
    """
    __tablename__ = 'tops_and_cores'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    radar_code = Column(String(16), ForeignKey('radars.code', ondelete='CASCADE'),
                        nullable=False, index=True)

    # Temporal information
    observation_time = Column(DateTime(timezone=True), nullable=False, index=True)

    # File information
    file_path = Column(String(512), nullable=False, unique=True)
    file_name = Column(String(256), nullable=False)

    # Feature counts
    feature_count = Column(Integer, nullable=False, default=0)
    core_count = Column(Integer, nullable=False, default=0)
    top_count = Column(Integer, nullable=False, default=0)

    # Status
    status = Column(SQLEnum(COGStatus), nullable=False, default=COGStatus.AVAILABLE, index=True)

    # Filename components
    strategy = Column(String(32), nullable=True)
    vol_nr = Column(String(16), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    radar = relationship("Radar", back_populates="tops_and_cores")

    def __repr__(self):
        return f"<TopsAndCores(id={self.id}, radar='{self.radar_code}', file='{self.file_name}')>"


USER_ROLES = ("admin", "viewer")


class User(Base):
    """Application user (admin panel and, later, private endpoints)."""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(32), nullable=False, unique=True, index=True)
    full_name = Column(String(128))
    email = Column(String(254))
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default='viewer', server_default='viewer')
    is_active = Column(Boolean, nullable=False, default=True, server_default='true')
    # Copied into each access token at login and compared on every request. Adding 1 makes all
    # the user's older tokens invalid at once (role change, deactivation, admin "revoke sessions").
    token_version = Column(Integer, nullable=False, default=0, server_default='0')
    # True while the password is still the initial one from ADMIN_PASSWORD (.env). Set on the first
    # admin; set_password turns it off. The admin panel warns while it is true.
    password_is_bootstrap = Column(Boolean, nullable=False, default=False, server_default='false')
    failed_login_count = Column(Integer, nullable=False, default=0, server_default='0')
    locked_until = Column(DateTime(timezone=True))
    last_login_at = Column(DateTime(timezone=True))
    # NULL = self-registered and still unverified: the account cannot log in. Accounts created by an
    # admin or by the server CLI are verified when they are created.
    email_verified_at = Column(DateTime(timezone=True))
    # When the person accepted the terms and privacy policy at sign-up (proof of consent).
    terms_accepted_at = Column(DateTime(timezone=True))
    # The fixed identifier ("sub") of the Google account linked to this user; NULL while none is linked. The mail of
    # a Google account can change or be reused, the sub never does, so it is what identifies the person once linked.
    google_sub = Column(String(255))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    email_tokens = relationship(
        "EmailToken", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'viewer')", name='ck_users_role'),
        # The mail is unique among the accounts that have one (stored normalized: lower case, no spaces).
        # Partial index: many accounts may have no mail at all.
        Index('uq_users_email', 'email', unique=True, postgresql_where=text("email IS NOT NULL")),
        # Same for the Google identifier: one Google account links to at most one user.
        Index('uq_users_google_sub', 'google_sub', unique=True, postgresql_where=text("google_sub IS NOT NULL")),
    )

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class UserSession(Base):
    """One row per login (rotated in place on every refresh)."""
    __tablename__ = 'user_sessions'

    # Id of the login. It travels inside the refresh token ("<id>.<secret>"): presenting an old token
    # of this login (stolen and already rotated) closes the login (stolen token detection).
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    # SHA-256 of the current refresh token; the token itself only lives in the cookie.
    token_hash = Column(String(64), nullable=False, unique=True)
    # Hash of the token before the last rotation, accepted for 10 s (two tabs refreshing at once).
    previous_token_hash = Column(String(64))
    rotated_at = Column(DateTime(timezone=True))
    refresh_count = Column(Integer, nullable=False, default=0, server_default='0')
    expires_at = Column(DateTime(timezone=True), nullable=False)
    absolute_expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))
    # Why the login was closed: logout | reuse | admin | inactive_user | password_reset | migration
    revoke_reason = Column(String(20))
    # Login time and the client that logged in (refreshes do not overwrite them).
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_used_at = Column(DateTime(timezone=True))
    user_agent = Column(String(256))
    ip = Column(String(45))

    user = relationship("User", back_populates="sessions")

    def __repr__(self):
        return f"<UserSession(id={self.id}, user_id={self.user_id}, revoked={self.revoked_at is not None})>"


EMAIL_TOKEN_PURPOSES = ("verify_email", "reset_password", "account_exists")


class EmailToken(Base):
    """Single-use e-mail link (verify the address / reset the password) and the log of mails sent.

    Rows with purpose "account_exists" are not redeemable tokens: they are born expired, with a random
    hash, and only count toward the per-account sending caps.

    Why they exist (privacy): signing up with a mail that already has an account gets the same neutral
    answer as a new mail, so nobody can find out who has an account. The owner of that mail gets an
    "you already have an account" mail instead. That mail has no token, so this row is its only trace
    and lets the caps stop someone from flooding the owner's inbox.
    """
    __tablename__ = 'email_tokens'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    # verify_email | reset_password | account_exists (a log entry, not a token; see the class docstring)
    purpose = Column(String(32), nullable=False)
    # SHA-256 of the token; the token itself only travels in the mail.
    token_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True))

    user = relationship("User", back_populates="email_tokens")

    __table_args__ = (
        CheckConstraint(
            "purpose IN ('verify_email', 'reset_password', 'account_exists')", name='ck_email_tokens_purpose'
        ),
        # Lets the sending caps count a user's recent mails without scanning the whole table.
        Index('ix_email_tokens_user_created', 'user_id', 'created_at'),
        # Lets the global caps count the mails of the whole site in the last hour / day (no user in the filter,
        # so the index above cannot be used for it).
        Index('ix_email_tokens_created_at', 'created_at'),
    )

    def __repr__(self):
        return f"<EmailToken(user_id={self.user_id}, purpose='{self.purpose}', used={self.used_at is not None})>"
