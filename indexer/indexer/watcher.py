# indexer/indexer/watcher.py
"""
File system watcher for new COG files.
"""
import time
import logging
from pathlib import Path
from typing import Set, Optional, List
from datetime import datetime, timedelta

from indexer.config import settings
from indexer.registrar import COGRegistrar

logger = logging.getLogger(__name__)


class COGWatcher:
    """
    Watches for new COG files and indexes them.
    
    Uses a simple polling approach which is reliable across different
    file systems and network mounts.
    """
    
    def __init__(self):
        self.base_path = Path(settings.watch_path)
        self.scan_interval = settings.scan_interval_seconds
        self.file_pattern = settings.file_pattern
        self.radar_filter = set(settings.radar_codes) if settings.radar_codes else None
        
        # Track indexed files to avoid re-processing
        self._indexed_files: Set[str] = set()
        self._last_scan: Optional[datetime] = None
    
    def discover_files(self) -> List[Path]:
        """
        Discover all COG files in the watch path.
        
        Returns:
            List of file paths
        """
        files = []
        
        if self.radar_filter:
            # Only scan specific radar directories
            for radar_code in self.radar_filter:
                radar_dir = self.base_path / radar_code
                if radar_dir.exists():
                    files.extend(radar_dir.rglob(self.file_pattern))
        else:
            # Scan all subdirectories
            files = list(self.base_path.rglob(self.file_pattern))
        
        return files
    
    def discover_new_files(self, since: Optional[datetime] = None) -> List[Path]:
        """
        Discover files modified since a given time.
        
        Args:
            since: Only return files modified after this time
            
        Returns:
            List of new file paths
        """
        all_files = self.discover_files()
        
        if since is None:
            return all_files
        
        new_files = []
        since_ts = since.timestamp()
        
        for f in all_files:
            try:
                if f.stat().st_mtime > since_ts:
                    new_files.append(f)
            except OSError:
                continue
        
        return new_files
    
    def run_scan(self, session) -> int:
        """
        Run a single scan for new files.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            Number of files indexed
        """
        registrar = COGRegistrar(session, str(self.base_path))
        
        # Find files to process
        if self._last_scan:
            # Incremental scan - only look at recently modified files
            files = self.discover_new_files(
                since=self._last_scan - timedelta(minutes=5)  # Small overlap for safety
            )
        else:
            # Full scan on first run
            files = self.discover_files()
        
        self._last_scan = datetime.now()
        
        indexed_count = 0
        for file_path in files:
            str_path = str(file_path)
            
            # Skip if we've already tried this file this session
            if str_path in self._indexed_files:
                continue
            
            result = registrar.register_file(file_path)
            if result is not None:
                indexed_count += 1
            
            self._indexed_files.add(str_path)
        
        # Optionally check for missing files
        if settings.mark_missing_files and indexed_count == 0:
            # Only do this when no new files (to avoid overhead)
            registrar.mark_missing_files()
        
        return indexed_count
    
    def run_forever(self, get_session_func):
        """
        Run the watcher continuously.
        
        Args:
            get_session_func: Function that returns a database session
        """
        logger.info(f"Starting COG watcher on {self.base_path}")
        logger.info(f"Scan interval: {self.scan_interval} seconds")
        logger.info(f"File pattern: {self.file_pattern}")
        if self.radar_filter:
            logger.info(f"Radar filter: {self.radar_filter}")
        
        while True:
            try:
                session = get_session_func()
                try:
                    count = self.run_scan(session)
                    if count > 0:
                        logger.info(f"Scan complete: indexed {count} new files")
                    session.commit()
                except Exception as e:
                    logger.error(f"Scan error: {e}")
                    session.rollback()
                finally:
                    session.close()
                    
            except Exception as e:
                logger.error(f"Session error: {e}")
            
            time.sleep(self.scan_interval)