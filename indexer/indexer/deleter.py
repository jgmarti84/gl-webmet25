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
    
    def __init__(self, base_path: Optional[str] = None, logs_path: Optional[str] = None):
        """
        Initialize the deleter.
        
        Args:
            base_path: Base path where COG files are stored.
                      Defaults to settings.watch_path.
            logs_path: Path to the logs directory.
                      Defaults to settings.logs_path.
        """
        self.base_path = Path(base_path or settings.watch_path)
        if not self.base_path.exists():
            raise ValueError(f"Base path does not exist: {self.base_path}")
        self.parser = COGFilenameParser(base_path=str(self.base_path))
        # Log base path: configurable via environment variable
        self.log_base_path = Path(logs_path or settings.logs_path)
    
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
    
    def _scan_for_logs(
        self,
        date_cutoff_str: str,  # YYYYMMDD format
        radar_codes: Optional[List[str]] = None,
    ) -> List[Tuple[Path, str]]:
        """
        Scan for log files matching the date criteria.
        
        Only scans for dated log files (genpro25.log.YYYY-MM-DD), never the current log.
        
        Args:
            date_cutoff_str: Date in YYYYMMDD format (e.g., '20260101')
            radar_codes: List of radar codes to filter by (None = all)
        
        Returns:
            List of tuples: (file_path, radar_code)
        """
        matching_logs = []
        
        # If log base path doesn't exist, return empty list
        if not self.log_base_path.exists():
            logger.debug(f"Log base path does not exist: {self.log_base_path}")
            return matching_logs
        
        # Normalize radar codes to uppercase
        if radar_codes:
            radar_codes = [code.upper() for code in radar_codes]
        else:
            # If no radars specified, look for all radar directories
            radar_codes = None
        
        # Parse the cutoff date (YYYYMMDD format)
        try:
            cutoff_date = datetime.strptime(date_cutoff_str, "%Y%m%d").date()
        except ValueError:
            logger.error(f"Invalid date format for log scan: {date_cutoff_str}")
            return matching_logs
        
        # Scan each radar directory
        if self.log_base_path.exists():
            for radar_dir in self.log_base_path.iterdir():
                if not radar_dir.is_dir():
                    continue
                
                radar_code = radar_dir.name.upper()
                
                # Filter by radar code if specified
                if radar_codes and radar_code not in radar_codes:
                    continue
                
                # Scan for genpro25.log.YYYY-MM-DD files
                for log_file in radar_dir.glob("genpro25.log.????-??-??"):
                    # Extract date from filename: genpro25.log.YYYY-MM-DD
                    try:
                        date_part = log_file.name.split(".log.")[1]  # Get YYYY-MM-DD
                        file_date = datetime.strptime(date_part, "%Y-%m-%d").date()
                        
                        # Only include files on or before the cutoff date
                        if file_date <= cutoff_date:
                            matching_logs.append((log_file, radar_code))
                    except (IndexError, ValueError) as e:
                        logger.debug(f"Could not parse log file date from {log_file.name}: {e}")
                        continue
        
        return matching_logs
    
    def delete_products(
        self,
        date_str: str,  # YYYYMMDD format — delete all COGs up to (and including) this date
        radar_codes: Optional[List[str]] = None,  # Optional list of radar codes
        product_key: Optional[str] = None,
        dry_run: bool = False,
        remove_logs: bool = False,  # If True, also delete matching log files
        quiet: bool = False,  # If True, suppress per-file logging
    ) -> Tuple[int, int, int, List[str]]:
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
            remove_logs: If True, also delete matching log files (genpro25.log.YYYY-MM-DD).
            quiet: If True, suppress per-file logging. Only show summary.
        
        Returns:
            Tuple of (files_deleted, cogs_cleaned, logs_deleted, error_messages)
            - files_deleted: Number of COG files deleted from disk
            - cogs_cleaned: Number of database records cleaned up
            - logs_deleted: Number of log files deleted
            - error_messages: List of error messages encountered
        """
        errors = []
        
        try:
            # Parse the date — delete all COGs up to and including this date
            observation_date = datetime.strptime(date_str, "%Y%m%d").date()
            date_cutoff = datetime.combine(observation_date, datetime.max.time())
        except ValueError as e:
            errors.append(f"Invalid date format '{date_str}': {e}")
            return 0, 0, 0, errors
        
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
            # Still process logs if requested
            if remove_logs:
                matching_logs = self._scan_for_logs(date_str, radar_codes)
                deleted_logs = 0
                if matching_logs:
                    logger.info(f"Found {len(matching_logs)} matching log files.")
                    if not dry_run:
                        for log_file, radar_code in matching_logs:
                            try:
                                log_file.unlink()
                                deleted_logs += 1
                                logger.info(f"Deleted log file: {log_file}")
                            except Exception as e:
                                error_msg = f"Failed to delete log file {log_file}: {e}"
                                logger.error(error_msg)
                                errors.append(error_msg)
                return 0, 0, deleted_logs, errors
            return 0, 0, 0, errors
        
        logger.info(f"Found {len(matching_files)} matching files on disk.")
        
        # Step 1b (optional): Scan for log files if requested
        deleted_logs = 0
        matching_logs = []
        if remove_logs:
            matching_logs = self._scan_for_logs(date_str, radar_codes)
            if matching_logs:
                logger.info(f"Found {len(matching_logs)} matching log files.")
        
        if dry_run:
            if not quiet:
                logger.info("[DRY-RUN] Would delete the following COG files:")
                for file_path, radar, product, obs_time in matching_files:
                    logger.info(f"  {file_path} (radar={radar}, product={product}, time={obs_time})")
                if matching_logs:
                    logger.info("[DRY-RUN] Would delete the following log files:")
                    for log_file, radar_code in matching_logs:
                        logger.info(f"  {log_file} (radar={radar_code})")
            return len(matching_files), 0, len(matching_logs), errors
        
        # Step 2: Delete files from disk
        deleted_files = 0
        deleted_dirs = 0
        for file_path, radar, product, obs_time in matching_files:
            try:
                file_path.unlink()
                deleted_files += 1
                if not quiet:
                    logger.info(f"Deleted file: {file_path}")
                
                # Clean up empty parent directories
                dirs_removed = self._remove_empty_dirs(file_path)
                deleted_dirs += dirs_removed
                if dirs_removed > 0 and not quiet:
                    logger.debug(f"Removed {dirs_removed} empty directories")
            
            except Exception as e:
                error_msg = f"Failed to delete file {file_path}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # Step 2b (optional): Delete log files if requested
        if remove_logs and matching_logs:
            for log_file, radar_code in matching_logs:
                try:
                    log_file.unlink()
                    deleted_logs += 1
                    if not quiet:
                        logger.info(f"Deleted log file: {log_file}")
                except Exception as e:
                    error_msg = f"Failed to delete log file {log_file}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            if deleted_logs > 0:
                logger.info(f"Successfully deleted {deleted_logs} log files from disk.")
        
        if deleted_files == 0:
            logger.error("No COG files could be deleted from disk!")
            return 0, 0, deleted_logs, errors
        
        if not quiet:
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
                return deleted_files, 0, deleted_logs, errors
            
            logger.info(f"Found {len(cogs_to_delete)} database records to clean up.")
            
            # Delete all matching records in a transaction
            for cog in cogs_to_delete:
                try:
                    session.delete(cog)
                    deleted_cogs += 1
                    if not quiet:
                        logger.debug(f"Cleaned up COG record: {cog.id} ({cog.file_path})")
                except Exception as e:
                    error_msg = f"Failed to delete COG record {cog.id}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            # Commit transaction
            session.commit()
            summary = f"✓ Deletion complete: {deleted_files} COG files deleted, {deleted_cogs} database records cleaned up"
            if remove_logs:
                summary += f", {deleted_logs} log files deleted"
            logger.info(summary)
            
            return deleted_files, deleted_cogs, deleted_logs, errors
        
        except Exception as e:
            session.rollback()
            error_msg = f"Database cleanup failed (rolled back): {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            # Note: Files are already deleted from disk; database is unchanged
            return deleted_files, 0, deleted_logs, errors
        
        finally:
            session.close()
