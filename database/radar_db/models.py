# database/radar_db/models.py
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, 
    ForeignKey, Numeric, Table, UniqueConstraint, Index, Enum as SQLEnum
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
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
    point1_lat = Column(Numeric(14, 10), default=Decimal('0'))
    point1_long = Column(Numeric(14, 10), default=Decimal('0'))
    point2_lat = Column(Numeric(14, 10), default=Decimal('0'))
    point2_long = Column(Numeric(14, 10), default=Decimal('0'))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    cog_files = relationship("RadarCOG", back_populates="radar", cascade="all, delete-orphan")
    
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
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    references = relationship("Reference", back_populates="product", cascade="all, delete-orphan")
    cog_files = relationship("RadarCOG", back_populates="product")
    
    def __repr__(self):
        return f"<RadarProduct(key='{self.product_key}')>"


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
        Index('idx_cog_radar_product_time', 'radar_code', 'product_id', 'observation_time'),
        Index('idx_cog_bbox', 'bbox', postgresql_using='gist'),
        UniqueConstraint('radar_code', 'product_id', 'observation_time', 'elevation_angle',
                        name='uq_cog_radar_product_time_elev'),
    )
    
    def __repr__(self):
        return f"<RadarCOG(id={self.id}, radar='{self.radar_code}', file='{self.file_name}')>"