# api/app/services/tile_service.py
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from functools import lru_cache
import numpy as np

import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rio_tiler.io import Reader
from rio_tiler.errors import TileOutsideBounds
from rio_tiler.colormap import cmap as rio_cmap

from ..config import settings
from ..utils.colormaps import colormap_for_field, colormap_to_rio_tiler

logger = logging.getLogger(__name__)


class TileService:
    """Service for generating map tiles from COG files."""
    
    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path or settings.cog_base_path)
    
    def get_full_path(self, relative_path: str) -> Path:
        """Get full filesystem path for a COG file."""
        return self.base_path / relative_path
    
    def generate_tile(
        self,
        file_path: str,
        z: int,
        x: int,
        y: int,
        colormap: Optional[Dict[int, Tuple[int, int, int, int]]] = None,
        resampling: str = "nearest"
    ) -> Optional[bytes]:
        """
        Generate a PNG tile from a COG file.
        
        Args:
            file_path: Relative path to COG file
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate
            colormap: Optional colormap dict {value: (r, g, b, a)}
            resampling: Resampling method
            
        Returns:
            PNG image bytes or transparent tile if tile is outside bounds
        """
        full_path = self.get_full_path(file_path)
        
        if not full_path.exists():
            logger.warning(f"COG file not found: {full_path}")
            return None
        
        try:
            with Reader(str(full_path)) as src:
                # Check number of bands - Reader.dataset.count
                num_bands = src.dataset.count
                
                # Get tile data, specifying band 1 only if multi-band
                if num_bands > 1:
                    # Multi-band COG - read only first band
                    img = src.tile(x, y, z, resampling_method=resampling, indexes=1)
                else:
                    img = src.tile(x, y, z, resampling_method=resampling)
                
                # Apply colormap if provided
                if colormap:
                    rendered = img.render(colormap=colormap)
                else:
                    # Use default rendering
                    rendered = img.render()
                
                return rendered
                
        except TileOutsideBounds:
            # Return transparent tile for areas outside the COG
            logger.debug(f"Tile {z}/{x}/{y} outside bounds for {file_path}")
            return self._generate_transparent_tile()
        except Exception as e:
            logger.error(f"Error generating tile {z}/{x}/{y} for {file_path}: {e}", exc_info=True)
            # Return transparent tile on error instead of None
            # This prevents 404 errors and allows the map to function
            return self._generate_transparent_tile()
    
    def _generate_transparent_tile(self, size: int = 256) -> bytes:
        """Generate a fully transparent PNG tile."""
        from PIL import Image
        import io
        
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer.read()
    
    def build_colormap_from_references(
        self,
        references: List[Dict],
        nodata_transparent: bool = True
    ) -> Dict[int, Tuple[int, int, int, int]]:
        """
        DEPRECATED: This method is no longer used.
        Colormaps are now defined in utils/colormaps.py based on product type.
        
        Build a rio-tiler compatible colormap from product references.
        
        Args:
            references: List of reference dicts with 'value' and 'color' keys
            nodata_transparent: If True, make values below minimum transparent
            
        Returns:
            Colormap dict for rio-tiler
        """
        logger.warning("build_colormap_from_references is deprecated. Use predefined colormaps instead.")
        
        if not references:
            return self._get_default_radar_colormap()
        
        # Sort by value
        sorted_refs = sorted(references, key=lambda r: r['value'])
        
        colormap = {}
        
        for i, ref in enumerate(sorted_refs):
            value = int(ref['value'])
            color = ref['color'].lstrip('#')
            
            # Parse hex color
            try:
                r = int(color[0:2], 16)
                g = int(color[2:4], 16)
                b = int(color[4:6], 16)
                a = 255  # Fully opaque
            except (ValueError, IndexError):
                # Default to white if parsing fails
                r, g, b, a = 255, 255, 255, 255
            
            colormap[value] = (r, g, b, a)
        
        # Interpolate values between defined points
        colormap = self._interpolate_colormap(colormap)
        
        return colormap
    
    def build_colormap_for_product(
        self,
        product_key: str,
        override_cmap: Optional[str] = None
    ) -> Dict[int, Tuple[int, int, int, int]]:
        """
        Build a rio-tiler compatible colormap for a radar product.
        Uses predefined colormaps from utils/colormaps.py.
        
        Args:
            product_key: Product key (e.g., 'DBZH', 'VRAD')
            override_cmap: Optional colormap name to override default
            
        Returns:
            Colormap dict for rio-tiler
        """
        # Get colormap configuration for this product
        cmap, vmin, vmax, cmap_name = colormap_for_field(product_key, override_cmap)
        
        # Convert to rio-tiler format
        colormap_dict = colormap_to_rio_tiler(cmap, vmin, vmax)
        
        logger.info(f"Built colormap '{cmap_name}' for product '{product_key}' (range: {vmin} to {vmax})")
        
        return colormap_dict
    
    def _interpolate_colormap(
        self, 
        colormap: Dict[int, Tuple[int, int, int, int]],
        min_val: int = -30,
        max_val: int = 80
    ) -> Dict[int, Tuple[int, int, int, int]]:
        """Interpolate colormap to fill gaps between defined values."""
        if len(colormap) < 2:
            return colormap
        
        sorted_values = sorted(colormap.keys())
        full_colormap = {}
        
        for i in range(min_val, max_val + 1):
            if i in colormap:
                full_colormap[i] = colormap[i]
            else:
                # Find surrounding values
                lower = max([v for v in sorted_values if v <= i], default=sorted_values[0])
                upper = min([v for v in sorted_values if v >= i], default=sorted_values[-1])
                
                if lower == upper:
                    full_colormap[i] = colormap[lower]
                else:
                    # Linear interpolation
                    t = (i - lower) / (upper - lower)
                    c1 = colormap[lower]
                    c2 = colormap[upper]
                    full_colormap[i] = tuple(
                        int(c1[j] + t * (c2[j] - c1[j])) for j in range(4)
                    )
        
        return full_colormap
    
    def _get_default_radar_colormap(self) -> Dict[int, Tuple[int, int, int, int]]:
        """Get default radar reflectivity colormap (NWS style)."""
        return {
            -30: (0, 0, 0, 0),       # Transparent
            -20: (128, 128, 128, 128), # Gray (light)
            -10: (192, 192, 192, 180), # Gray
            0: (149, 180, 220, 255),   # Light blue (mist)
            10: (0, 230, 138, 255),    # Light green (drizzle)
            20: (0, 173, 90, 255),     # Green (light rain)
            30: (234, 243, 40, 255),   # Yellow (moderate rain)
            40: (247, 166, 0, 255),    # Orange (heavy rain)
            50: (255, 42, 12, 255),    # Red (intense rain)
            60: (255, 42, 152, 255),   # Pink (very intense + hail)
            70: (255, 41, 227, 255),   # Magenta (severe)
        }
    
    def get_cog_info(self, file_path: str) -> Optional[Dict]:
        """Get information about a COG file."""
        full_path = self.get_full_path(file_path)
        
        if not full_path.exists():
            return None
        
        try:
            with Reader(str(full_path)) as src:
                info = src.info()
                return {
                    "bounds": info.bounds,
                    "minzoom": info.minzoom,
                    "maxzoom": info.maxzoom,
                    "band_metadata": info.band_metadata,
                    "dtype": info.dtype,
                    "nodata": info.nodata_value,
                }
        except Exception as e:
            logger.error(f"Error getting COG info for {file_path}: {e}")
            return None


# Singleton instance
_tile_service: Optional[TileService] = None


def get_tile_service() -> TileService:
    """Get or create the tile service singleton."""
    global _tile_service
    if _tile_service is None:
        _tile_service = TileService()
    return _tile_service