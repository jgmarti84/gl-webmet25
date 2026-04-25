# indexer/indexer/deleter.py
"""
Product deletion module.

Deletes COG files and database records matching specified criteria:
- date (required): Delete all COGs with observation_time <= this date (YYYYMMDD format)
- radar_codes (optional): Comma-separated list of radar codes (e.g., RMA1,RMA2,RMA6).
                         If omitted, deletes from ALL radars.
- product_key (optional): Product filter (e.g., DBZH). If omitted, all products deleted.

Deletion is atomic: files and database records are deleted together within
a transaction. If the file deletion fails, the database transaction is rolled back.
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

from sqlalchemy.orm import Session

from radar_db import db_manager
from radar_db.models import RadarCOG
from indexer.config import settings

logger = logging.getLogger(__name__)


class ProductDeleter:
    """Delete COG products from disk and database by date and optional radar/product filters."""
    
    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize the deleter.
        
        Args:
            base_path: Base path where COG files are stored.
                      Defaults to settings.watch_path.
        """
        self.base_path = Path(base_path or settings.watch_path)
        if not self.base_path.exists():
            raise ValueError(f"Base path does not exist: {self.base_path}")
    
    def delete_products(
        self,
        date_str: str,  # YYYYMMDD format — delete all COGs up to (and including) this date
        radar_codes: Optional[List[str]] = None,  # Optional list of radar codes
        product_key: Optional[str] = None,
        dry_run: bool = False,
    ) -> Tuple[int, int, List[str]]:
        """
        Delete products matching the given criteria.
        
        Args:
            date_str: Date in YYYYMMDD format (e.g., '20260101').
                     All COGs with observation_time <= this date will be deleted.
            radar_codes: Optional list of radar codes (e.g., ['RMA1', 'RMA2']).
                        If None or empty, all radars are included.
            product_key: Optional product key filter (e.g., 'DBZH').
                        If not specified, all products are deleted.
            dry_run: If True, report what would be deleted without actually deleting.
        
        Returns:
            Tuple of (cogs_deleted, files_deleted, error_messages)
            - cogs_deleted: Number of database records deleted
            - files_deleted: Number of files deleted from disk
            - error_messages: List of error messages encountered
        """
        errors = []
        
        try:
            # Parse the date — delete all COGs up to and including this date
            observation_date = datetime.strptime(date_str, "%Y%m%d").date()
            date_cutoff = datetime.combine(observation_date, datetime.max.time())
        except ValueError as e:
            errors.append(f"Invalid date format '{date_str}': {e}")
            return 0, 0, errors
        
        # Normalize radar codes to uppercase
        if radar_codes:
            radar_codes = [code.upper() for code in radar_codes]
        
        radar_display = ", ".join(radar_codes) if radar_codes else "ALL"
        
        logger.info(
            f"{'[DRY-RUN] ' if dry_run else ''}Deleting products: "
            f"date_up_to={date_str} radars={radar_display} product={product_key or 'ALL'}"
        )
        
        # Query database for matching records
        session = db_manager.get_session_direct()
        try:
            # All COGs with observation_time <= date_cutoff
            query = session.query(RadarCOG).filter(
                RadarCOG.observation_time <= date_cutoff,
            )
            
            # Filter by specific radars if provided
            if radar_codes:
                query = query.filter(RadarCOG.radar_code.in_(radar_codes))
            
            # Filter by product if provided
            if product_key:
                query = query.filter(RadarCOG.polarimetric_var == product_key)
            
            cogs_to_delete = query.all()
            
            if not cogs_to_delete:
                logger.info("No matching products found.")
                return 0, 0, errors
            
            logger.info(f"Found {len(cogs_to_delete)} matching COG records in database.")
            
            # List files to delete
            files_to_delete = []
            for cog in cogs_to_delete:
                file_path = self.base_path / cog.file_path
                if file_path.exists():
                    files_to_delete.append((cog, file_path))
                else:
                    logger.warning(f"File not found on disk: {file_path}")
            
            logger.info(f"Found {len(files_to_delete)} files to delete from disk.")
            
            if dry_run:
                logger.info("[DRY-RUN] Would delete the following:")
                for cog, file_path in files_to_delete:
                    logger.info(f"  DB: {cog}")
                    logger.info(f"  FS: {file_path}")
                session.close()
                return len(cogs_to_delete), len(files_to_delete), errors
            
            # Perform the deletion
            deleted_cogs = 0
            deleted_files = 0
            
            try:
                # Delete files from disk first
                for cog, file_path in files_to_delete:
                    try:
                        file_path.unlink()
                        deleted_files += 1
                        logger.info(f"Deleted file: {file_path}")
                    except Exception as e:
                        error_msg = f"Failed to delete file {file_path}: {e}"
                        logger.error(error_msg)
                        errors.append(error_msg)
                
                # Delete from database
                for cog in cogs_to_delete:
                    try:
                        session.delete(cog)
                        deleted_cogs += 1
                        logger.info(f"Deleted COG record: {cog.id} ({cog.file_path})")
                    except Exception as e:
                        error_msg = f"Failed to delete COG record {cog.id}: {e}"
                        logger.error(error_msg)
                        errors.append(error_msg)
                
                # Commit transaction
                session.commit()
                logger.info(
                    f"✓ Deletion complete: {deleted_cogs} database records, "
                    f"{deleted_files} files"
                )
            
            except Exception as e:
                session.rollback()
                error_msg = f"Transaction failed, rolled back: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                return 0, 0, errors
            
            return deleted_cogs, deleted_files, errors
        
        finally:
            session.close()
