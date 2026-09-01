# indexer/indexer/watcher.py
"""
File system watcher for new COG files.
"""
import time
import logging
from pathlib import Path
from typing import Set, Optional, List
from datetime import datetime, timedelta, timezone

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
    
    def _active_day_dirs(self) -> List[Path]:
        """Return per-radar day directories for today and yesterday.

        Files are stored under <base>/<RADAR>/YYYY/MM/DD/, so scanning only
        those two leaves instead of rglob-ing the entire tree cuts traversal
        from O(all-time files) to O(two-days files).
        """
        now = datetime.now()
        dirs: List[Path] = []
        for offset in (0, 1):
            day = now - timedelta(days=offset)
            day_suffix = Path(str(day.year)) / f"{day.month:02d}" / f"{day.day:02d}"
            if self.radar_filter:
                for radar_code in self.radar_filter:
                    d = self.base_path / radar_code / day_suffix
                    if d.exists():
                        dirs.append(d)
            else:
                dirs.extend(
                    d for d in self.base_path.glob(f"*/{day_suffix}")
                    if d.is_dir()
                )
        return dirs

    def discover_files(self) -> List[Path]:
        """
        Discover COG files in today's and yesterday's day directories.

        Returns:
            List of file paths
        """
        files = []
        for day_dir in self._active_day_dirs():
            files.extend(day_dir.rglob(self.file_pattern))
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
    
    def update_radar_activity(self, session) -> None:
        """
        Update the is_active flag on every Radar based on recent COG availability.

        A radar is considered active if it has at least one RadarCOG with
        observation_time within the last RADAR_ACTIVE_THRESHOLD_HOURS hours.
        This is called at the end of every scan cycle.
        """
        from radar_db.models import Radar, RadarCOG, COGStatus

        threshold_hours = settings.radar_active_threshold_hours
        cutoff = datetime.now(timezone.utc) - timedelta(hours=threshold_hours)

        radars = session.query(Radar).all()
        for radar in radars:
            has_recent = session.query(RadarCOG).filter(
                RadarCOG.radar_code == radar.code,
                RadarCOG.status == COGStatus.AVAILABLE,
                RadarCOG.observation_time >= cutoff,
            ).first() is not None

            if radar.is_active != has_recent:
                radar.is_active = has_recent
                logger.info(
                    f"Radar {radar.code} is_active set to {has_recent} "
                    f"(threshold: {threshold_hours}h)"
                )

    def run_scan(self, session) -> int:
        """
        Run a single scan for new files.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            Number of files indexed
        """
        registrar = COGRegistrar(session, str(self.base_path))

        # Stamp the scan start time BEFORE the rglob so that the next scan's
        # "since" threshold is relative to when this traversal began, not ended.
        # Without this, files that arrive during the first (rglob_duration - 5min)
        # of a slow scan fall into a permanent dead zone.
        scan_start = datetime.now()

        # Find files to process
        if self._last_scan:
            # Incremental scan - only look at recently modified files
            files = self.discover_new_files(
                since=self._last_scan - timedelta(minutes=5)  # Small overlap for safety
            )
        else:
            # Full scan on first run
            files = self.discover_files()

        self._last_scan = scan_start
        
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
        
        # Update radar activity status at the end of every scan cycle
        self.update_radar_activity(session)

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


class TopsAndCoresWatcher:
    """
    Watches for new TopsAndCores GeoJSON files and registers them.

    Files must match the pattern ``*_TOPS_CORES.geojson`` and live under
    ``tops_and_cores_dir`` (recursively).

    Uses the same polling approach and scan interval as :class:`COGWatcher`.
    """

    _FILE_PATTERN = "*_TOPS_CORES.geojson"

    def __init__(self, tops_and_cores_dir: str):
        self.tops_and_cores_dir = Path(tops_and_cores_dir)
        self.scan_interval = settings.scan_interval_seconds
        self._warned_missing_dir: bool = False

    def discover_files(self) -> list:
        """
        Recursively discover all ``*_TOPS_CORES.geojson`` files.

        Returns:
            List of :class:`~pathlib.Path` objects.
        """
        return list(self.tops_and_cores_dir.rglob(self._FILE_PATTERN))

    def run_scan(self, session) -> int:
        """
        Run a single scan cycle.

        Args:
            session: SQLAlchemy session (managed by the caller).

        Returns:
            Number of newly registered files.
        """
        from indexer.parser import TopsAndCoresFilenameParser
        from indexer.registrar import TopsAndCoresRegistrar
        from radar_db.models import TopsAndCores, COGStatus

        if not self.tops_and_cores_dir.exists():
            if not self._warned_missing_dir:
                logger.warning(
                    f"TOPS_AND_CORES_DIR does not exist: {self.tops_and_cores_dir}. "
                    f"Skipping scan. This warning will not repeat."
                )
                self._warned_missing_dir = True
            return 0

        # Reset warning if the directory reappears
        self._warned_missing_dir = False

        files = self.discover_files()
        logger.debug(f"TOPS_CORES scan: found {len(files)} candidate file(s)")

        filename_parser = TopsAndCoresFilenameParser()
        registrar = TopsAndCoresRegistrar(session)

        registered_count = 0

        for file_path in files:
            str_path = str(file_path)
            try:
                parsed = filename_parser.parse(str_path)
            except ValueError as exc:
                logger.warning(f"TOPS_CORES skipping unrecognised file: {file_path} — {exc}")
                continue

            registrar.register(str_path, parsed)
            registered_count += 1

        # Mark files no longer on disk as MISSING
        available_records = session.query(TopsAndCores).filter(
            TopsAndCores.status == COGStatus.AVAILABLE
        ).all()

        for record in available_records:
            if not Path(record.file_path).exists():
                registrar.mark_missing(record.file_path)

        return registered_count

    def run_forever(self, get_session_func) -> None:
        """
        Run the watcher continuously using the same loop pattern as
        :class:`COGWatcher`.

        Args:
            get_session_func: Callable that returns a new SQLAlchemy session.
        """
        logger.info(
            f"Starting TopsAndCores watcher on {self.tops_and_cores_dir}"
        )
        logger.info(f"Scan interval: {self.scan_interval} seconds")

        while True:
            try:
                session = get_session_func()
                try:
                    count = self.run_scan(session)
                    if count > 0:
                        logger.info(
                            f"TopsAndCores scan complete: processed {count} file(s)"
                        )
                    session.commit()
                except Exception as e:
                    logger.error(f"TopsAndCores scan error: {e}")
                    session.rollback()
                finally:
                    session.close()

            except Exception as e:
                logger.error(f"TopsAndCores session error: {e}")

            time.sleep(self.scan_interval)
