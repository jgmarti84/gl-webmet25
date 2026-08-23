# indexer/indexer/registrar.py
"""
COG file registration and metadata extraction.
"""
import os
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import rasterio
from rasterio.warp import transform_bounds
from shapely.geometry import box
from geoalchemy2.shape import from_shape
from sqlalchemy.orm import Session
from sqlalchemy import text

from indexer.config import settings
from indexer.parser import COGFilenameParser, ParsedCOGInfo

logger = logging.getLogger(__name__)


class COGRegistrar:
    """Handles registration of COG files in the database."""
    
    def __init__(self, session: Session, base_path: Optional[str] = None):
        self.session = session
        self.base_path = Path(base_path or settings.watch_path)
        self.parser = COGFilenameParser(str(self.base_path))
        
        # Cache for product lookups
        self._product_cache: Dict[str, int] = {}
        self._load_product_cache()
    
    def _load_product_cache(self):
        """Load product key -> id mapping."""
        from radar_db.models import RadarProduct
        products = self.session.query(RadarProduct).all()
        self._product_cache = {p.product_key: p.id for p in products}
        logger.debug(f"Loaded {len(self._product_cache)} products into cache")
    
    def get_product_id(self, product_key: str) -> Optional[int]:
        """Get product ID from key, using cache."""
        return self._product_cache.get(product_key)
    
    def _detect_cog_type(self, src) -> str:
        """
        Determine COG data type from rasterio dataset metadata/tags.

        Returns 'raw_float', 'rgba', or 'unknown'.
        """
        tags = src.tags() or {}
        data_type_tag = tags.get("radarlib_data_type", "")

        if data_type_tag == "raw_float":
            return "raw_float"
        if data_type_tag == "rgba":
            return "rgba"

        # Fallback heuristic based on band count and dtype
        if src.count >= 3 and str(src.dtypes[0]) == "uint8":
            return "rgba"
        if src.count == 1 and str(src.dtypes[0]) in ("float32", "float64"):
            return "raw_float"

        return "unknown"

    def extract_cog_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extract metadata from a COG file using rasterio."""
        metadata = {}
        
        try:
            with rasterio.open(file_path) as src:
                metadata['width'] = src.width
                metadata['height'] = src.height
                metadata['num_bands'] = src.count
                metadata['dtype'] = str(src.dtypes[0])
                metadata['crs'] = str(src.crs) if src.crs else None
                metadata['nodata_value'] = src.nodata
                metadata['resolution_x'] = src.res[0]
                metadata['resolution_y'] = src.res[1]
                metadata['compression'] = src.profile.get('compress')

                # Detect COG type and extract rendering metadata from tags
                metadata['cog_data_type'] = self._detect_cog_type(src)
                tags = src.tags() or {}
                if tags.get("radarlib_cmap"):
                    metadata['cog_cmap'] = tags["radarlib_cmap"]
                if tags.get("radarlib_vmin"):
                    try:
                        metadata['cog_vmin'] = float(tags["radarlib_vmin"])
                    except (ValueError, TypeError):
                        pass
                if tags.get("radarlib_vmax"):
                    try:
                        metadata['cog_vmax'] = float(tags["radarlib_vmax"])
                    except (ValueError, TypeError):
                        pass

                # radarlib production metadata tags (present in new-format COGs)
                if tags.get("radarlib_strategy"):
                    metadata['strategy'] = tags["radarlib_strategy"]
                if tags.get("radarlib_vol_nr"):
                    metadata['vol_nr'] = tags["radarlib_vol_nr"]
                if tags.get("radarlib_field_name"):
                    metadata['field_name'] = tags["radarlib_field_name"]
                if tags.get("radarlib_radar_coverage_m"):
                    try:
                        metadata['radar_coverage_m'] = float(tags["radarlib_radar_coverage_m"])
                    except (ValueError, TypeError):
                        logger.warning(
                            f"Invalid radarlib_radar_coverage_m value in {file_path}: "
                            f"'{tags['radarlib_radar_coverage_m']}' — skipping"
                        )

                # Bounding box in WGS84
                if src.crs:
                    try:
                        bounds = transform_bounds(src.crs, 'EPSG:4326', *src.bounds)
                        bbox_geom = box(*bounds)
                        metadata['bbox'] = from_shape(bbox_geom, srid=4326)
                    except Exception as e:
                        logger.warning(f"Could not compute bbox for {file_path}: {e}")
                
                # Statistics (optional, can be slow)
                if settings.compute_stats:
                    try:
                        data = src.read(1, masked=True)
                        if data.count() > 0:
                            metadata['data_min'] = float(data.min())
                            metadata['data_max'] = float(data.max())
                            metadata['data_mean'] = float(data.mean())
                            metadata['valid_pixel_count'] = int(data.count())
                    except Exception as e:
                        logger.warning(f"Could not compute stats for {file_path}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to read COG {file_path}: {e}")
            return {}
        
        return metadata
    
    def compute_checksum(self, file_path: Path) -> str:
        """Compute SHA256 checksum of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(8192), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def is_already_indexed(self, file_path: str) -> bool:
        """Check if a file is already in the database."""
        from radar_db.models import RadarCOG
        exists = self.session.query(RadarCOG).filter_by(file_path=file_path).first()
        return exists is not None
    
    def register_file(self, file_path: Path) -> Optional[int]:
        """
        Register a single COG file in the database.
        
        Args:
            file_path: Full path to the COG file
            
        Returns:
            ID of the registered COG, or None if registration failed
        """
        from radar_db.models import Estrategia, RadarCOG, COGStatus, Radar
        
        # Get relative path for storage
        try:
            rel_path = str(file_path.relative_to(self.base_path))
        except ValueError:
            rel_path = str(file_path)
        
        # Check if already indexed
        if self.is_already_indexed(rel_path):
            logger.debug(f"Already indexed: {rel_path}")
            return None
        
        # Parse filename/path
        parsed = self.parser.parse(str(file_path))
        if not parsed.is_valid:
            logger.warning(f"Could not parse file: {file_path} - {parsed.error}")
            return None
        
        # Validate radar exists
        radar = self.session.query(Radar).filter_by(code=parsed.radar_code).first()
        if not radar:
            logger.warning(f"Unknown radar code: {parsed.radar_code} for file {file_path}")
            return None
        
        # Get product ID
        product_id = self.get_product_id(parsed.product_key)
        if product_id is None:
            logger.warning(f"Unknown product: {parsed.product_key} for file {file_path}")
            # Continue anyway - product_id can be null

        # Check unique constraint (radar, product, time, elevation, vol_nr) to avoid
        # duplicate inserts.  vol_nr is included so that the same field produced by
        # different volumes (e.g. DBZH from vol 01 and DBZH from vol 04 at the same
        # timestamp) are correctly recognised as *different* records.
        if product_id is not None:
            query = self.session.query(RadarCOG).filter_by(
                radar_code=parsed.radar_code,
                product_id=product_id,
                observation_time=parsed.observation_time,
                elevation_angle=parsed.elevation_angle,
            )
            # vol_nr may be None for legacy files; filter explicitly only when present.
            if parsed.vol_nr is not None:
                query = query.filter(RadarCOG.vol_nr == parsed.vol_nr)
            else:
                query = query.filter(RadarCOG.vol_nr.is_(None))
            existing = query.first()
            if existing:
                logger.info(
                    f"Skipping already-recorded observation for {parsed.radar_code} "
                    f"{parsed.product_key} vol_nr={parsed.vol_nr} at {parsed.observation_time}"
                )
                return None
        
        # Extract COG metadata from GeoTIFF tags
        cog_metadata = self.extract_cog_metadata(file_path)

        # --- Resolve strategy -------------------------------------------------
        # Prefer filename-parsed value; fall back to embedded GeoTIFF tag.
        # Always pop from cog_metadata to prevent it leaking into **cog_metadata.
        strategy_from_tag = cog_metadata.pop("strategy", None)
        strategy_code = parsed.strategy or strategy_from_tag
        estrategia_code = None
        if strategy_code:
            strategy_obj = self.session.query(Estrategia).filter_by(code=strategy_code).first()
            if strategy_obj:
                estrategia_code = strategy_obj.code
            else:
                logger.warning(
                    f"Strategy '{strategy_code}' not found in database for {file_path}. "
                    f"COG will be indexed without strategy link."
                )

        # --- Resolve vol_nr ---------------------------------------------------
        vol_nr = parsed.vol_nr or cog_metadata.pop("vol_nr", None)
        cog_metadata.pop("vol_nr", None)  # prevent duplicate kwarg via **cog_metadata

        # --- Pull radar_coverage_m out of metadata dict -----------------------
        # (must not be passed via **cog_metadata — handled explicitly below)
        radar_coverage_m = cog_metadata.pop("radar_coverage_m", None)

        # --- Drop tag-only keys that have no matching DB column ---------------
        cog_metadata.pop("field_name", None)

        # Get file stats
        stat = file_path.stat()
        
        # Create record
        cog = RadarCOG(
            radar_code=parsed.radar_code,
            product_id=product_id,
            observation_time=parsed.observation_time,
            elevation_angle=parsed.elevation_angle,
            polarimetric_var=parsed.product_key,
            file_path=rel_path,
            file_name=file_path.name,
            file_size_bytes=stat.st_size,
            file_mtime=datetime.fromtimestamp(stat.st_mtime),
            status=COGStatus.AVAILABLE,
            estrategia_code=estrategia_code,
            vol_nr=vol_nr,
            radar_coverage_m=radar_coverage_m,
            **cog_metadata,
        )
        
        # Optional checksum
        if settings.compute_checksum:
            cog.file_checksum = self.compute_checksum(file_path)
        
        try:
            self.session.add(cog)
            self.session.flush()
            logger.info(
                f"Indexed: {rel_path} (ID: {cog.id}) "
                f"[radar={parsed.radar_code}, field={parsed.product_key}, "
                f"strategy={strategy_code}, vol_nr={vol_nr}, "
                f"coverage={radar_coverage_m} m]"
            )
            return cog.id
        except Exception as e:
            logger.error(f"Failed to index {rel_path}: {e}")
            self.session.rollback()
            return None
    
    def mark_missing_files(self) -> int:
        """
        Mark files in database that no longer exist on disk.
        
        Returns:
            Number of files marked as missing
        """
        from radar_db.models import RadarCOG, COGStatus
        
        count = 0
        cogs = self.session.query(RadarCOG).filter(
            RadarCOG.status == COGStatus.AVAILABLE
        ).all()
        
        for cog in cogs:
            full_path = self.base_path / cog.file_path
            if not full_path.exists():
                cog.status = COGStatus.MISSING
                count += 1
                logger.warning(f"Marked as missing: {cog.file_path}")
        
        if count > 0:
            self.session.commit()
            logger.info(f"Marked {count} files as missing")
        
        return count


class TopsAndCoresRegistrar:
    """Handles registration of TopsAndCores GeoJSON files in the database."""

    def __init__(self, session: Session):
        self.session = session

    def register(self, file_path: str, parsed) -> None:
        """
        Register a single TopsAndCores GeoJSON file in the database.

        Args:
            file_path: Absolute path to the GeoJSON file on disk.
            parsed:    :class:`~indexer.parser.ParsedTopsAndCoresInfo` returned
                       by :class:`~indexer.parser.TopsAndCoresFilenameParser`.
        """
        from radar_db.models import TopsAndCores, COGStatus

        # Check if already indexed and AVAILABLE → nothing to do
        existing = self.session.query(TopsAndCores).filter_by(
            file_path=file_path
        ).first()

        if existing is not None:
            if existing.status == COGStatus.AVAILABLE:
                logger.debug(
                    f"TOPS_CORES already indexed (AVAILABLE): {file_path}"
                )
                return
            if existing.status == COGStatus.ERROR:
                logger.debug(
                    f"TOPS_CORES previously failed (ERROR), skipping: {file_path}"
                )
                return
            # Fall through to update records that are in a non-AVAILABLE state

        # Parse GeoJSON to obtain feature counts and observation_time
        feature_count = 0
        core_count = 0
        top_count = 0
        observation_time = parsed.observation_time
        status = COGStatus.AVAILABLE

        try:
            import json
            import os as _os

            if _os.path.getsize(file_path) == 0:
                raise ValueError("GeoJSON file is empty")

            with open(file_path, "r", encoding="utf-8") as fh:
                geojson = json.load(fh)

            features = geojson.get("features", [])
            feature_count = len(features)

            for feat in features:
                props = feat.get("properties") or {}
                feat_type = props.get("type", "")
                if feat_type == "core":
                    core_count += 1
                elif feat_type == "top":
                    top_count += 1

            # Prefer observation_time from the first feature's properties
            if features:
                raw_time = (features[0].get("properties") or {}).get(
                    "observation_time"
                )
                if raw_time:
                    from datetime import timezone as _tz

                    parsed_obs = datetime.fromisoformat(raw_time)
                    if parsed_obs.tzinfo is None:
                        parsed_obs = parsed_obs.replace(tzinfo=_tz.utc)
                    observation_time = parsed_obs

        except ValueError as e:
            logger.warning(
                f"Skipping TOPS_CORES file (bad content): {file_path} — {e}"
            )
            status = COGStatus.ERROR
        except Exception:
            logger.error(
                f"Failed to parse GeoJSON for TOPS_CORES file: {file_path}",
                exc_info=True,
            )
            status = COGStatus.ERROR

        if existing is not None:
            # Update existing record
            existing.observation_time = observation_time
            existing.feature_count = feature_count
            existing.core_count = core_count
            existing.top_count = top_count
            existing.status = status
        else:
            record = TopsAndCores(
                radar_code=parsed.radar_code,
                observation_time=observation_time,
                file_path=file_path,
                file_name=str(file_path).split("/")[-1],
                feature_count=feature_count,
                core_count=core_count,
                top_count=top_count,
                status=status,
                strategy=parsed.strategy,
                vol_nr=parsed.vol_nr,
            )
            self.session.add(record)

        try:
            self.session.flush()
        except Exception as e:
            logger.error(f"Failed to flush TopsAndCores record for {file_path}: {e}")
            self.session.rollback()
            return

        if status == COGStatus.AVAILABLE:
            logger.info(
                f"TOPS_CORES indexed radar={parsed.radar_code} "
                f"time={observation_time} "
                f"cores={core_count} tops={top_count}"
            )

    def mark_missing(self, file_path: str) -> None:
        """
        Mark a registered TopsAndCores file as MISSING.

        Args:
            file_path: Absolute path previously stored in ``file_path`` column.
        """
        from radar_db.models import TopsAndCores, COGStatus

        record = self.session.query(TopsAndCores).filter_by(
            file_path=file_path
        ).first()

        if record is None:
            logger.debug(f"TOPS_CORES mark_missing: record not found for {file_path}")
            return

        record.status = COGStatus.MISSING
        try:
            self.session.flush()
            logger.warning(f"TOPS_CORES marked as missing: {file_path}")
        except Exception as e:
            logger.error(
                f"Failed to mark TopsAndCores as missing for {file_path}: {e}"
            )
            self.session.rollback()
