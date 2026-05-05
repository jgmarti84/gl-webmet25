# indexer/indexer/parser.py
"""
Filename parser for COG files and TopsAndCores GeoJSON files.
CUSTOMIZE THIS MODULE to match your genpro25 output naming convention!
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class ParsedCOGInfo:
    """Parsed information from a COG file path."""
    radar_code: str
    product_key: str
    observation_time: datetime
    elevation_angle: float = 0.0
    is_valid: bool = True
    error: Optional[str] = None


class COGFilenameParser:
    """
    Parser for COG filenames.
    
    IMPORTANT: Customize the parse() method to match your naming convention!
    
    Common patterns supported:
    1. {radar}_{product}_{YYYYMMDD}_{HHMMSS}.tif
    2. {radar}_{product}_{YYYYMMDD}_{HHMMSS}_{elevation}.tif
    3. Path-based: /product_output/{radar}/{product}/{YYYY}/{MM}/{DD}/file.tif
    """
    
    # Example patterns - adjust to your needs!
    FILENAME_PATTERNS = [
        # Pattern 0: RMA3_20260127T230000Z_DBZHo_00.tif
        re.compile(r'^(?P<radar>[A-Z0-9]+)_(?P<datetime>\d{8}T\d{6}Z)_(?P<product>[A-Za-z0-9]+)_(?P<elev>[\d.]+)\.tif$'),
        
        # Pattern 1: RMA3_DBZH_20240115_143022.tif
        re.compile(r'^(?P<radar>[A-Z0-9]+)_(?P<product>[A-Za-z0-9]+)_(?P<date>\d{8})_(?P<time>\d{6})\.tif$'),
        
        # Pattern 2: RMA3_DBZH_20240115_143022_0.5.tif (with elevation)
        re.compile(r'^(?P<radar>[A-Z0-9]+)_(?P<product>[A-Za-z0-9]+)_(?P<date>\d{8})_(?P<time>\d{6})_(?P<elev>[\d.]+)\.tif$'),
        
        # Pattern 3: RMA3_DBZH_2024-01-15T14:30:22.tif (ISO-ish format)
        re.compile(r'^(?P<radar>[A-Z0-9]+)_(?P<product>[A-Za-z0-9]+)_(?P<datetime>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.tif$'),
    ]
    
    def __init__(self, base_path: str = "/product_output"):
        self.base_path = Path(base_path)
    
    def parse(self, file_path: str) -> ParsedCOGInfo:
        """
        Parse a COG file path to extract metadata.
        
        Args:
            file_path: Full or relative path to the COG file
            
        Returns:
            ParsedCOGInfo with extracted metadata
        """
        path = Path(file_path)
        filename = path.name
        
        # Try filename patterns first
        for pattern in self.FILENAME_PATTERNS:
            match = pattern.match(filename)
            if match:
                return self._parse_from_match(match, path)
        
        # Try to parse from directory structure
        return self._parse_from_path(path)
    
    def _parse_from_match(self, match: re.Match, path: Path) -> ParsedCOGInfo:
        """Parse from regex match."""
        groups = match.groupdict()
        
        try:
            radar_code = groups['radar']
            product_key = groups['product']

            # if "DBZH" in product_key:
            #     product_key = product_key.replace("DBZH", "TH")
            # if "ZDR" in product_key:
            #     product_key = product_key.replace("ZDR", "TDR")
            # if "DBZV" in product_key:
            #     product_key = product_key.replace("DBZV", "TV")
                
            # Parse datetime (robust to minute/second overflow)
            if 'datetime' in groups:
                # Expect formats like YYYYMMDDTHHMMSSZ or ISO-like strings
                dt_str = groups['datetime']
                # Try to extract numeric parts: YYYYMMDDTHHMMSS
                m = re.match(r"(?P<Y>\d{4})(?P<m>\d{2})(?P<d>\d{2})T(?P<H>\d{2})(?P<M>\d{2})(?P<S>\d{2})Z?", dt_str)
                if m:
                    parts = m.groupdict()
                    year = int(parts['Y']); month = int(parts['m']); day = int(parts['d'])
                    hour = int(parts['H']); minute = int(parts['M']); second = int(parts['S'])
                    base = datetime(year, month, day)
                    obs_time = base + timedelta(hours=hour, minutes=minute, seconds=second)
                else:
                    # Fallback to fromisoformat for other ISO-like strings
                    obs_time = datetime.fromisoformat(dt_str)
            else:
                date_str = groups['date']
                time_str = groups['time']
                # time_str expected as HHMMSS - parse components and normalize
                h = int(time_str[0:2]); m = int(time_str[2:4]); s = int(time_str[4:6])
                base = datetime(int(date_str[0:4]), int(date_str[4:6]), int(date_str[6:8]))
                obs_time = base + timedelta(hours=h, minutes=m, seconds=s)
            
            # Parse elevation if present
            elevation = float(groups.get('elev', 0.0))
            
            return ParsedCOGInfo(
                radar_code=radar_code,
                product_key=product_key,
                observation_time=obs_time,
                elevation_angle=elevation,
                is_valid=True
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse filename {path.name}: {e}")
            return ParsedCOGInfo(
                radar_code="",
                product_key="",
                observation_time=datetime.now(),
                is_valid=False,
                error=str(e)
            )
    
    def _parse_from_path(self, path: Path) -> ParsedCOGInfo:
        """
        Fallback: Parse from directory structure.
        
        Expected structure:
            /product_output/{radar_code}/{product_key}/.../{filename}
        """
        try:
            # Get path relative to base
            rel_path = path.relative_to(self.base_path)
            parts = rel_path.parts
            
            if len(parts) < 2:
                raise ValueError(f"Path too short to parse: {path}")
            
            radar_code = parts[0]  # First directory = radar code
            product_key = parts[1]  # Second directory = product
            
            # Try to extract datetime from filename or remaining path
            filename = path.stem
            
            # Try various datetime patterns in filename
            datetime_patterns = [
                r'(\d{8})_(\d{6})',      # YYYYMMDD_HHMMSS
                r'(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})',  # YYYYMMDDHHMMSS split
                r'(\d{14})',              # YYYYMMDDHHMMSS
            ]
            
            obs_time = None
            for pattern in datetime_patterns:
                match = re.search(pattern, filename)
                if match:
                    groups = match.groups()
                    if len(groups) == 2:
                        dt_combined = f"{groups[0]}{groups[1]}"
                        y = int(dt_combined[0:4]); mo = int(dt_combined[4:6]); d = int(dt_combined[6:8])
                        h = int(dt_combined[8:10]); mi = int(dt_combined[10:12]); s = int(dt_combined[12:14])
                        obs_time = datetime(y, mo, d) + timedelta(hours=h, minutes=mi, seconds=s)
                    elif len(groups) == 6:
                        obs_time = datetime(int(groups[0]), int(groups[1]), int(groups[2])) + \
                            timedelta(hours=int(groups[3]), minutes=int(groups[4]), seconds=int(groups[5]))
                    elif len(groups) == 1:
                        g = groups[0]
                        obs_time = datetime(int(g[0:4]), int(g[4:6]), int(g[6:8])) + \
                            timedelta(hours=int(g[8:10]), minutes=int(g[10:12]), seconds=int(g[12:14]))
                    break
            
            if obs_time is None:
                # Last resort: use file modification time
                obs_time = datetime.fromtimestamp(path.stat().st_mtime)
                logger.warning(f"Could not parse datetime from {filename}, using mtime")
            
            return ParsedCOGInfo(
                radar_code=radar_code,
                product_key=product_key,
                observation_time=obs_time,
                is_valid=True
            )
            
        except Exception as e:
            logger.error(f"Failed to parse path {path}: {e}")
            return ParsedCOGInfo(
                radar_code="",
                product_key="",
                observation_time=datetime.now(),
                is_valid=False,
                error=str(e)
            )


# Default parser instance
parser = COGFilenameParser()


def _parse_compact_datetime_utc(dt_str: str) -> datetime:
    """
    Parse a 14-digit compact datetime string (YYYYMMDDHHMMSS) into a
    timezone-aware UTC datetime.

    Uses the same overflow-tolerant approach as COGFilenameParser so that
    seconds/minutes beyond the normal range are handled via timedelta addition.

    Args:
        dt_str: String of exactly 14 digits, e.g. ``"20260505163854"``.

    Returns:
        Timezone-aware UTC :class:`datetime`.

    Raises:
        ValueError: If ``dt_str`` does not consist of exactly 14 digits.
    """
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z", dt_str)
    if not m:
        raise ValueError(
            f"Cannot parse compact datetime '{dt_str}': expected 14 digits (YYYYMMDDHHMMSS)"
        )
    year, month, day, hour, minute, second = (int(g) for g in m.groups())
    base = datetime(year, month, day, tzinfo=timezone.utc)
    return base + timedelta(hours=hour, minutes=minute, seconds=second)


@dataclass
class ParsedTopsAndCoresInfo:
    """Parsed information from a TopsAndCores GeoJSON filename."""

    radar_code: str
    strategy: str
    vol_nr: str
    observation_time: datetime  # Always timezone-aware UTC


class TopsAndCoresFilenameParser:
    """
    Parser for TopsAndCores GeoJSON filenames.

    Expected format::

        {radar_code}_{strategy}_{vol_nr}_{timestamp}_TOPS_CORES.geojson

    Where ``{timestamp}`` is ``YYYYMMDDHHMMSS`` (14 digits, no separators).

    Example::

        RMA6_A_00_20260505163854_TOPS_CORES.geojson
    """
    # _PATTERN = re.compile(
    #     r"^(?P<radar>[A-Z0-9]+)_(?P<strategy>[^_]+)_(?P<vol_nr>[^_]+)"
    #     r"_(?P<datetime>\d{14})_TOPS_CORES\.geojson$"
    # )
    _PATTERN = re.compile(r"^(?P<radar>[A-Z0-9]+)_(?P<strategy>\d{4})_(?P<vol_nr>\d{2})_(?P<datetime>\d{8}T\d{6}Z)_TOPS_CORES\.geojson$")

    def parse(self, file_path: str) -> ParsedTopsAndCoresInfo:
        """
        Parse a TopsAndCores GeoJSON filename.

        Args:
            file_path: Full path or filename of the GeoJSON file.

        Returns:
            :class:`ParsedTopsAndCoresInfo` with extracted metadata.

        Raises:
            ValueError: If the filename does not match the expected pattern.
        """
        filename = Path(file_path).name
        match = self._PATTERN.match(filename)
        if not match:
            raise ValueError(
                f"Filename '{filename}' does not match the TopsAndCores pattern "
                f"'<RADAR>_<strategy>_<vol_nr>_<YYYYMMDDHHMMSS>_TOPS_CORES.geojson'"
            )

        groups = match.groupdict()
        observation_time = _parse_compact_datetime_utc(groups["datetime"])

        return ParsedTopsAndCoresInfo(
            radar_code=groups["radar"],
            strategy=groups["strategy"],
            vol_nr=groups["vol_nr"],
            observation_time=observation_time,
        )
