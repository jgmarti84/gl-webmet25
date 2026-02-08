# api/app/utils/colormaps.py
"""
Colormap utilities for radar products.
Based on radar-visualization-tool colormaps.
"""

from matplotlib.colors import LinearSegmentedColormap
from typing import Dict, Tuple, Optional
import matplotlib.pyplot as plt
import numpy as np

# Import pyart if available for additional colormaps
try:
    import pyart
    PYART_AVAILABLE = True
except ImportError:
    PYART_AVAILABLE = False


def get_cmap_grc_rain():
    """Green-Red-Cyan colormap for rain products."""
    cmp_rain = {
        'red': [(0.0, 1, 1),
                (0.01, 0.95, 0.95),
                (0.1, 0.24, 0.24),
                (0.2, 0.22, 0.22),
                (0.3, 0.04, 0.04),
                (0.55, 0.95, 0.95),
                (0.80, 1, 1),
                (0.95, 1, 1),
                (1, 1, 1)],
        'green': [(0.0, 1, 1),
                  (0.01, 0.97, 0.97),
                  (0.1, 0.46, 0.46),
                  (0.2, 0.98, 0.98),
                  (0.3, 0.62, 0.62),
                  (0.55, 1, 1),
                  (0.80, 0, 0),
                  (0.95, 0, 0),
                  (1, 1, 1)],
        'blue':  [(0.0, 1, 1),
                  (0.01, 0.95, 0.95),
                  (0.1, 0.88, 0.88),
                  (0.2, 0.52, 0.52),
                  (0.3, 0.27, 0.27),
                  (0.55, 0, 0),
                  (0.80, 0, 0),
                  (0.95, 1, 1),
                  (1, 1, 1)],
    }
    return LinearSegmentedColormap('grc_rain', cmp_rain)


def get_cmap_grc_th2():
    """Green-Red-Cyan colormap variant 2 for reflectivity."""
    grc_th2 = {
        'red': [(0.0, 1, 1),
                (0.27, 0.95, 0.95),
                (0.4, 0.24, 0.24),
                (0.45, 0.22, 0.22),
                (0.55, 0.04, 0.04),
                (0.6, 0.95, 0.95),
                (0.84, 1, 1),
                (1, 1, 1)],
        'green': [(0.0, 1, 1),
                  (0.27, 0.97, 0.97),
                  (0.4, 0.46, 0.46),
                  (0.4, 0.98, 0.98),
                  (0.55, 0.62, 0.62),
                  (0.6, 1, 1),
                  (0.84, 0, 0),
                  (1, 0, 0)],
        'blue':  [(0.0, 1, 1),
                  (0.27, 0.95, 0.95),
                  (0.4, 0.78, 0.78),
                  (0.4, 0.52, 0.52),
                  (0.55, 0.27, 0.27),
                  (0.6, 0, 0),
                  (0.84, 0, 0),
                  (1, 1, 1)],
    }
    return LinearSegmentedColormap('grc_th2', grc_th2)


def get_cmap_grc_th():
    """Green-Red-Cyan colormap for reflectivity (DBZH)."""
    grc_th = {
        'red': [(0.0, 1, 1),
                (0.2, 0.95, 0.95),
                (0.4, 0.24, 0.24),
                (0.45, 0.22, 0.22),
                (0.55, 0.04, 0.04),
                (0.63, 0.95, 0.95),
                (0.85, 1, 1),
                (1, 1, 1)],
        'green': [(0.0, 1, 1),
                  (0.2, 0.97, 0.97),
                  (0.4, 0.46, 0.46),
                  (0.4, 0.98, 0.98),
                  (0.55, 0.62, 0.62),
                  (0.63, 1, 1),
                  (0.85, 0, 0),
                  (1, 0, 0)],
        'blue':  [(0.0, 1, 1),
                  (0.2, 0.95, 0.95),
                  (0.4, 0.78, 0.78),
                  (0.4, 0.52, 0.52),
                  (0.55, 0.27, 0.27),
                  (0.63, 0, 0),
                  (0.85, 0, 0),
                  (1, 1, 1)],
    }
    return LinearSegmentedColormap('grc_th', grc_th)


def get_cmap_grc_rho():
    """Green-Red-Cyan colormap for RHOHV (correlation coefficient)."""
    grc_rho_data = {
        'red': [(0, 0, 0),
                (0.5, 0.3, 0.3),
                (0.725, 0, 0),
                (0.75, 1, 1),
                (0.9, 1, 1),
                (0.95, 0.67, 0.67),
                (0.985, 0.67, 0.67),
                (1, 1, 1)],
        'green': [(0, 0.2, 0.2),
                  (0.5, 0.57, 0.57),
                  (0.725, 0.81, 0.81),
                  (0.75, 1, 1),
                  (0.9, 0.55, 0.55),
                  (0.95, 0, 0),
                  (0.985, 0, 0),
                  (1, 0, 0)],
        'blue':  [(0, 0.7, 0.7),
                  (0.5, 1, 1),
                  (0.725, 0, 0),
                  (0.75, 0, 0),
                  (0.9, 0.45, 0.45),
                  (0.95, 0, 0),
                  (0.985, 0, 0),
                  (1, 1, 1)],
    }
    return LinearSegmentedColormap('grc_rho', grc_rho_data)


def get_cmap_grc_zdr2():
    """Green-Red-Cyan colormap for ZDR (differential reflectivity)."""
    from matplotlib.colors import to_rgb
    
    hex_colors = [
        '#2c2c2c', '#8a8a8a', '#e6e6e6', '#00FFFF',
        '#94CDFF', '#0055FF', '#489D39', '#F9EA3C',
        '#FF8345', '#FF212C', '#FF078B'
    ]
    
    # Convert hex to RGB (0-1)
    rgb_colors = [to_rgb(c) for c in hex_colors]
    n = len(rgb_colors)
    
    # Define equidistant positions
    positions = [i / (n - 1) for i in range(n)]
    
    grc_zdr_data = {
        'red':   [(positions[i], rgb_colors[i][0], rgb_colors[i][0]) for i in range(n)],
        'green': [(positions[i], rgb_colors[i][1], rgb_colors[i][1]) for i in range(n)],
        'blue':  [(positions[i], rgb_colors[i][2], rgb_colors[i][2]) for i in range(n)],
    }
    
    return LinearSegmentedColormap('grc_zdr2', grc_zdr_data)


# Field rendering configuration - defines default colormaps and ranges for each product
FIELD_RENDER = {
    "DBZH": {"vmin": -30.0, "vmax": 70.0, "cmap": "grc_th"},
    "DBZHo": {"vmin": -30.0, "vmax": 70.0, "cmap": "grc_th"},
    "DBZHF": {"vmin": -30.0, "vmax": 70.0, "cmap": "grc_th"},
    "DBZV": {"vmin": -30.0, "vmax": 70.0, "cmap": "grc_th"},
    "ZDR": {"vmin": -5.0, "vmax": 10.5, "cmap": "grc_zdr2"}, 
    "RHOHV": {"vmin": 0.0, "vmax": 1.0, "cmap": "grc_rho"}, 
    "RHOHVo": {"vmin": 0.0, "vmax": 1.0, "cmap": "grc_rho"}, 
    "KDP": {"vmin": 0.0, "vmax": 8.0, "cmap": "grc_rain"},
    "VRAD": {"vmin": -35.0, "vmax": 35.0, "cmap": "NWSVel"},
    "WRAD": {"vmin": 0.0, "vmax": 10.0, "cmap": "Oranges"},
    "PHIDP": {"vmin": 0.0, "vmax": 360.0, "cmap": "Theodore16"},
    # Generic fallback for other products
    "COLMAX": {"vmin": -30.0, "vmax": 70.0, "cmap": "grc_th"},
}

# Available colormap options for each field
FIELD_COLORMAP_OPTIONS = {
    "DBZH": ["grc_th", "grc_th2", "grc_rain", "pyart_NWSRef", "pyart_HomeyerRainbow"],
    "DBZHo": ["grc_th", "grc_th2", "grc_rain", "pyart_NWSRef", "pyart_HomeyerRainbow"],
    "DBZHF": ["grc_th", "grc_th2", "grc_rain", "pyart_NWSRef", "pyart_HomeyerRainbow"],
    "DBZV": ["grc_th", "grc_th2", "grc_rain", "pyart_NWSRef", "pyart_HomeyerRainbow"],
    "ZDR": ["grc_zdr2", "pyart_RefDiff", "pyart_Theodore16"],
    "RHOHV": ["grc_rho", "pyart_RefDiff", "Greys", "viridis"],
    "RHOHVo": ["grc_rho", "pyart_RefDiff", "Greys", "viridis"],
    "KDP": ["grc_rain", "grc_th", "pyart_Theodore16", "plasma"],
    "VRAD": ["NWSVel", "pyart_BuDRd18", "seismic", "RdBu_r"],
    "WRAD": ["Oranges", "YlOrRd", "hot", "plasma"],
    "PHIDP": ["Theodore16", "hsv", "twilight", "twilight_shifted"],
    "COLMAX": ["grc_th", "grc_th2", "grc_rain", "pyart_NWSRef", "pyart_HomeyerRainbow"],
}


def get_colormap(cmap_name: str):
    """
    Get a matplotlib colormap by name.
    Supports custom GRC colormaps, PyART colormaps, and standard matplotlib colormaps.
    
    Args:
        cmap_name: Name of the colormap
        
    Returns:
        matplotlib colormap object
    """
    # Custom GRC colormaps
    if cmap_name == "grc_th":
        return get_cmap_grc_th()
    elif cmap_name == "grc_th2":
        return get_cmap_grc_th2()
    elif cmap_name == "grc_rain":
        return get_cmap_grc_rain()
    elif cmap_name == "grc_rho":
        return get_cmap_grc_rho()
    elif cmap_name == "grc_zdr2":
        return get_cmap_grc_zdr2()
    
    # PyART colormaps
    elif cmap_name.startswith("pyart_") and PYART_AVAILABLE:
        pyart_name = cmap_name.replace("pyart_", "")
        try:
            return pyart.graph.cm.get_colormap(pyart_name)
        except (AttributeError, KeyError):
            pass
    
    # Standard matplotlib/PyART colormaps
    if PYART_AVAILABLE:
        try:
            return pyart.graph.cm.get_colormap(cmap_name)
        except (AttributeError, KeyError):
            pass
    
    # Fallback to matplotlib
    return plt.get_cmap(cmap_name)


def colormap_for_field(field_key: str, override_cmap: Optional[str] = None) -> Tuple:
    """
    Get colormap configuration for a radar field/product.
    
    Args:
        field_key: Product key (e.g., 'DBZH', 'VRAD')
        override_cmap: Optional colormap name to override default
        
    Returns:
        Tuple of (cmap_object, vmin, vmax, cmap_name)
    """
    field_upper = field_key.upper()
    
    # Get defaults for this field
    spec = FIELD_RENDER.get(field_upper, {"vmin": -30.0, "vmax": 70.0, "cmap": "grc_th"})
    vmin, vmax = spec["vmin"], spec["vmax"]
    cmap_name = override_cmap if override_cmap else spec["cmap"]
    
    # Get the colormap object
    cmap = get_colormap(cmap_name)
    
    return cmap, vmin, vmax, cmap_name


def colormap_to_rio_tiler(cmap, vmin: float, vmax: float, steps: int = 256) -> Dict[int, Tuple[int, int, int, int]]:
    """
    Convert a matplotlib colormap to rio-tiler format.
    
    Args:
        cmap: Matplotlib colormap object
        vmin: Minimum value
        vmax: Maximum value
        steps: Number of color steps (default: 256)
        
    Returns:
        Dict mapping values to RGBA tuples for rio-tiler
    """
    # Generate normalized values
    normalized_values = np.linspace(0, 1, steps)
    
    # Get RGBA colors from colormap
    rgba_colors = cmap(normalized_values)
    
    # Map to actual data values
    data_values = np.linspace(vmin, vmax, steps)
    
    # Build rio-tiler compatible colormap
    colormap_dict = {}
    for i, val in enumerate(data_values):
        r, g, b, a = rgba_colors[i]
        colormap_dict[int(val)] = (
            int(r * 255),
            int(g * 255),
            int(b * 255),
            int(a * 255)
        )
    
    return colormap_dict


def get_colormap_colors(cmap_name: str, steps: int = 256) -> list:
    """
    Get a list of hex color strings for a colormap.
    
    Args:
        cmap_name: Name of the colormap
        steps: Number of color steps
        
    Returns:
        List of hex color strings
    """
    cmap = get_colormap(cmap_name)
    
    # Generate normalized values
    normalized_values = np.linspace(0, 1, steps)
    
    # Get RGBA colors
    rgba_colors = cmap(normalized_values)
    
    # Convert to hex
    hex_colors = [
        "#{:02x}{:02x}{:02x}".format(
            int(r * 255), int(g * 255), int(b * 255)
        )
        for r, g, b, a in rgba_colors
    ]
    
    return hex_colors
