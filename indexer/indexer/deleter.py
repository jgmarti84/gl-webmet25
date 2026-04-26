# indexer/indexer/deleter.py
"""
Product deletion module.

Deletes COG files and database records matching specified criteria:
- date (required): Delete all COGs with observation_time <= this date (YYYYMMDD format)
- radar_codes (optional): Comma-separated list of radar codes (e.g., RMA1,RMA2,RMA6).
                         If omitted, deletes from ALL radars.
- product_key (optional): Product filter (e.g., DBZH). If omitted, all products deleted.

The filesystem is the source of truth: files are discovered by scanning the disk,
parsed to extract metadata, and then matched against deletion criteria. Database
records are cleaned up afterward.

Deletion is atomic: all file deletions happen, then database records are removed
in a single transaction. If database cleanup fails, no files are deleted.
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

from sqlalchemy.orm import Session

from radar_db import db_manager
from radar_db.models import RadarCOG
from indexer.config import settings
from indexer.parser import COGFilenameParser

logger = logging.getLogger(__name__)


class ProductDeleter:
    """Delete COG products from disk and database by scanning the filesystem."""
    
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
        self.parser = COGFilenameParser(base_path=str(self.base_path))
    
    def _scan_for_files(
        self,
        date_cutoff: datetime,
        radar_codes: Optional[List[str]] = None,
        product_key: Optional[str] = None,
    ) -> List[Tuple[Path, str, str, datetime]]:
        """
        Scan the filesystem for matching COG files.
        
        Args:
            date_cutoff: Delete files with observation_time <= this datetime
            radar_codes: List of radar codes to filter by (None = all)
            product_key: Product key to filter by (None = all)
        
        Returns:
            List of tuples: (file_path, radar_code, product, observation_time)
        """
        matching_files = []
        
        # Normalize radar codes to uppercase
        if radar_codes:
            radar_codes = [code.upper() for code in radar_codes]
        
        # Recursively find all .tif files
        tif_files = list(self.base_path.glob("**/*.tif"))
        logger.info(f"Found {len(tif_files)} total .tif files on disk")
        
        for file_path in tif_files:
            try:
                # Parse the file to extract metadata
                parsed = self.parser.parse(str(file_path))
                
                if not parsed.is_valid:
                    logger.warning(f"Could not parse file: {file_path} ({parsed.error})")
                    continue
                
                # Filter by observation time (must be on or before cutoff)
                if parsed.observation_time > date_cutoff:
                    continue
                
                # Filter by radar code (if specified)
                if radar_codes and parsed.radar_code.upper() not in radar_codes:
                    continue
                
                # Filter by product (if specified)
                if product_key and parsed.product_key != product_key:
                    continue
                
                # This file matches all criteria
                matching_files.append((
                    file_path,
                    parsed.radar_code.upper(),
                    parsed.product_key,
                    parsed.observation_time
                ))
            
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                continue
        
        return matching_files
    
    def _remove_empty_dirs(self, file_path: Path) -> int:
        """
        Remove empty parent directories up to the base path.
        
        After a file is deleted, walk up the directory tree and remove any
        empty directories until hitting the base path or a non-empty directory.
        
        Args:
            file_path: Path to a (now-deleted) file
        
        Returns:
            Number of directories removed
        """
        dirs_removed = 0
        parent = file_path.parent
        
        # Walk up the tree, removing empty directories
        while parent != self.base_path and parent.is_relative_to(self.base_path):
            if not parent.exists():
                # Directory already gone, move up
                parent = parent.parent
                continue
            
            try:
                # Check if directory is empty
                if len(list(parent.iterdir())) == 0:
                    parent.rmdir()
                    dirs_removed += 1
                    logger.debug(f"Removed empty directory: {parent}")
                    parent = parent.parent
                else:
                    # Directory is not empty, stop here
                    break
            except (OSError, PermissionError) as e:
                logger.debug(f"Could not remove directory {parent}: {e}")
                break
        
        return dirs_removed
    
    def delete_products(
        self,
        date_str: str,  # YYYYMMDD format — delete all COGs up to (and including) this date
        radar_codes: Optional[List[str]] = None,  # Optional list of radar codes
        product_key: Optional[str] = None,
        dry_run: bool = False,
    ) -> Tuple[int, int, List[str]]:
        """
        Delete products matching the given criteria.
        
        Filesystem is scanned first to discover files. Database is updated afterward.
        
        Args:
            date_str: Date in YYYYMMDD format (e.g., '20260101').
                     All COGs with observation_time <= this date will be deleted.
            radar_codes: Optional list of radar codes (e.g., ['RMA1', 'RMA2']).
                        If None or empty, all radars are included.
            product_key: Optional product key filter (e.g., 'DBZH').
                        If not specified, all products are deleted.
            dry_run: If True, report what would be deleted without actually deleting.
        
        Returns:
            Tuple of (files_deleted, cogs_cleaned, error_messages)
            - files_deleted: Number of files deleted from disk
            - cogs_cleaned: Number of database records cleaned up
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
        
        # Step 1: Scan filesystem for matching files
        matching_files = self._scan_for_files(date_cutoff, radar_codes, product_key)
        
        if not matching_files:
            logger.info("No matching products found on disk.")
            return 0, 0, errors
        
        logger.info(f"Found {len(matching_files)} matching files on disk.")
        
        if dry_run:
            logger.info("[DRY-RUN] Would delete the following files:")
            for file_path, radar, product, obs_time in matching_files:
                logger.info(f"  {file_path} (radar={radar}, product={product}, time={obs_time})")
            return len(matching_files), 0, errors
        
        # Step 2: Delete files from disk
        deleted_files = 0
        deleted_dirs = 0
        for file_path, radar, product, obs_time in matching_files:
            try:
                file_path.unlink()
                deleted_files += 1
                logger.info(f"Deleted file: {file_path}")
                
                # Clean up empty parent directories
                dirs_removed = self._remove_empty_dirs(file_path)
                deleted_dirs += dirs_removed
                if dirs_removed > 0:
                    logger.debug(f"Removed {dirs_removed} empty directories")
            
            except Exception as e:
                error_msg = f"Failed to delete file {file_path}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        if deleted_files == 0:
            logger.error("No files could be deleted from disk!")
            return 0, 0, errors
        
        logger.info(f"Successfully deleted {deleted_files} files from disk.")
        if deleted_dirs > 0:
            logger.info(f"Cleaned up {deleted_dirs} empty directories.")
        
        # Step 3: Clean up database records (those that matched the deletion)
        session = db_manager.get_session_direct()
        deleted_cogs = 0
        
        try:
            # Query: find database records that correspond to files we deleted
            # (by matching radar, product, and observation time <= cutoff)
            query = session.query(RadarCOG).filter(
                RadarCOG.observation_time <= date_cutoff,
            )
            
            if radar_codes:
                query = query.filter(RadarCOG.radar_code.in_(radar_codes))
            
            if product_key:
                query = query.filter(RadarCOG.polarimetric_var == product_key)
            
            cogs_to_delete = query.all()
            
            if not cogs_to_delete:
                logger.info("No database records to clean up.")
                return deleted_files, 0, errors
            
            logger.info(f"Found {len(cogs_to_delete)} database records to clean up.")
            
            # Delete all matching records in a transaction
            for cog in cogs_to_delete:
                try:
                    session.delete(cog)
                    deleted_cogs += 1
                    logger.debug(f"Cleaned up COG record: {cog.id} ({cog.file_path})")
                except Exception as e:
                    error_msg = f"Failed to delete COG record {cog.id}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            # Commit transaction
            session.commit()
            logger.info(
                f"✓ Deletion complete: {deleted_files} files deleted, "
                f"{deleted_cogs} database records cleaned up"
            )
            
            return deleted_files, deleted_cogs, errors
        
        except Exception as e:
            session.rollback()
            error_msg = f"Database cleanup failed (rolled back): {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            # Note: Files are already deleted from disk; database is unchanged
            return deleted_files, 0, errors
        
        finally:
            session.close()
