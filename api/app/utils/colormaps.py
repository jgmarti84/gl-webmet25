# api/app/utils/colormaps.py
"""
Colormap utilities for radar products.

Primary source: DB (colormap_stops table), loaded via ColormapService.
Fallback chain:
  1. DB colormaps (ColormapService)
  2. Hardcoded get_cmap_*() functions below
  3. PyART colormaps (if available)
  4. matplotlib built-ins
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
                  (0.39, 0.46, 0.46),
                  (0.41, 0.98, 0.98),
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
                  (0.39, 0.46, 0.46),
                  (0.41, 0.98, 0.98),
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


def get_cmap_nws_vel():
    """
    NWS Velocity colormap for Doppler radial velocity (VRAD).
    Negative values (approaching) are rendered in greens,
    near-zero in white/grey, and positive values (receding) in reds.
    Matches the colour table used in standard NWS Level-II displays and
    closely matches PyART's NWSVel colormap.
    """
    from matplotlib.colors import to_rgb

    # (position 0..1, hex_color)  – centred on 0.5 == 0 m/s
    nwsvel_stops = [
        (0.000, '#008C00'),  # strong negative – dark green
        (0.083, '#00A800'),
        (0.167, '#00CC00'),  # bright green
        (0.250, '#00FF00'),
        (0.333, '#66FF66'),  # light green
        (0.417, '#B3FFB3'),
        (0.458, '#DFFFDF'),  # near-zero negative
        (0.500, '#FFFFFF'),  # zero – white
        (0.542, '#FFDFDF'),  # near-zero positive
        (0.583, '#FFB3B3'),
        (0.667, '#FF6666'),  # light red
        (0.750, '#FF0000'),
        (0.833, '#CC0000'),  # red
        (0.917, '#A80000'),
        (1.000, '#8C0000'),  # strong positive – dark red
    ]
    colors = [to_rgb(s[1]) for s in nwsvel_stops]
    positions = [s[0] for s in nwsvel_stops]
    n = len(nwsvel_stops)
    data = {
        'red':   [(positions[i], colors[i][0], colors[i][0]) for i in range(n)],
        'green': [(positions[i], colors[i][1], colors[i][1]) for i in range(n)],
        'blue':  [(positions[i], colors[i][2], colors[i][2]) for i in range(n)],
    }
    return LinearSegmentedColormap('grc_vrad', data)


def get_cmap_theodore16():
    """
    Theodore16 colormap for differential phase (PHIDP).
    A cyclic 16-step colormap designed for phase data (0-360°).
    Closely matches PyART's Theodore16 colormap.
    """
    from matplotlib.colors import to_rgb

    theodore16_colors = [
        '#800080',  # purple
        '#0000FF',  # blue
        '#0080FF',  # dodger blue
        '#00FFFF',  # cyan
        '#00FFAA',  # spring green
        '#00FF00',  # lime
        '#80FF00',  # chartreuse
        '#FFFF00',  # yellow
        '#FFC000',  # amber
        '#FF8000',  # orange
        '#FF4000',  # orange-red
        '#FF0000',  # red
        '#FF0080',  # rose
        '#FF00FF',  # magenta
        '#C000FF',  # violet
        '#800080',  # purple (close the cycle)
    ]
    colors = [to_rgb(c) for c in theodore16_colors]
    n = len(colors)
    positions = [i / (n - 1) for i in range(n)]
    data = {
        'red':   [(positions[i], colors[i][0], colors[i][0]) for i in range(n)],
        'green': [(positions[i], colors[i][1], colors[i][1]) for i in range(n)],
        'blue':  [(positions[i], colors[i][2], colors[i][2]) for i in range(n)],
    }
    return LinearSegmentedColormap('Theodore16', data)


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
    "ZDRo": {"vmin": -5.0, "vmax": 10.5, "cmap": "grc_zdr2"},
    "RHOHV": {"vmin": 0.0, "vmax": 1.0, "cmap": "grc_rho"},
    "RHOHVo": {"vmin": 0.0, "vmax": 1.0, "cmap": "grc_rho"},
    "KDP": {"vmin": 0.0, "vmax": 8.0, "cmap": "grc_rain"},
    "VRAD": {"vmin": -35.0, "vmax": 35.0, "cmap": "grc_vrad"},
    "VRADo": {"vmin": -35.0, "vmax": 35.0, "cmap": "grc_vrad"},
    "WRAD": {"vmin": 0.0, "vmax": 10.0, "cmap": "Oranges"},
    "WRADo": {"vmin": 0.0, "vmax": 10.0, "cmap": "Oranges"},
    "PHIDP": {"vmin": 0.0, "vmax": 360.0, "cmap": "Theodore16"},
    # Generic fallback for other products
    "COLMAX": {"vmin": -30.0, "vmax": 70.0, "cmap": "grc_th"},
    "COLMAXo": {"vmin": -30.0, "vmax": 70.0, "cmap": "grc_th"},
}

# Available colormap options for each field.
# Only colormaps that are always available (custom GRC/NWSVel/Theodore16 or
# standard matplotlib) are listed here.  PyART colormaps (pyart_*) have been
# removed because pyart is not installed in this environment and selecting
# them caused server-side errors.
FIELD_COLORMAP_OPTIONS = {
    "DBZH": ["grc_th", "grc_th2", "grc_rain"],
    "DBZHo": ["grc_th", "grc_th2", "grc_rain"],
    "DBZHF": ["grc_th", "grc_th2", "grc_rain"],
    "DBZV": ["grc_th", "grc_th2", "grc_rain"],
    "ZDR": ["grc_zdr2", "Theodore16"],
    "ZDRo": ["grc_zdr2", "Theodore16"],
    "RHOHV": ["grc_rho", "Greys", "viridis"],
    "RHOHVo": ["grc_rho", "Greys", "viridis"],
    "KDP": ["grc_rain", "grc_th", "plasma"],
    "VRAD": ["grc_vrad", "seismic", "RdBu_r"],
    "VRADo": ["grc_vrad", "seismic", "RdBu_r"],
    "WRAD": ["Oranges", "YlOrRd", "hot", "plasma"],
    "WRADo": ["Oranges", "YlOrRd", "hot", "plasma"],
    "PHIDP": ["Theodore16", "hsv", "twilight", "twilight_shifted"],
    "COLMAX": ["grc_th", "grc_th2", "grc_rain"],
    "COLMAXo": ["grc_th", "grc_th2", "grc_rain"],
}


_HARDCODED_BUILDERS = {
    "grc_th": lambda: get_cmap_grc_th(),
    "grc_th2": lambda: get_cmap_grc_th2(),
    "grc_rain": lambda: get_cmap_grc_rain(),
    "grc_rho": lambda: get_cmap_grc_rho(),
    "grc_g": lambda: get_cmap_grc_rho(),   # alias kept for back-compat
    "grc_zdr": lambda: get_cmap_grc_zdr2(),  # new canonical name
    "grc_zdr2": lambda: get_cmap_grc_zdr2(),
    "grc_vrad": lambda: get_cmap_nws_vel(),
    "grc_vrad": lambda: get_cmap_nws_vel(),
    "Theodore16": lambda: get_cmap_theodore16(),
}


def get_colormap(cmap_name: str):
    """
    Get a matplotlib colormap by name.

    Resolution order:
      1. DB (ColormapService) — covers all 8 system colormaps and any
         admin-created custom ones.
      2. Hardcoded _HARDCODED_BUILDERS — emergency fallback if the DB is
         down or the cmap has not been seeded yet.
      3. PyART colormaps (if pyart is installed).
      4. Standard matplotlib built-ins.

    Args:
        cmap_name: Name of the colormap
        
    Returns:
        matplotlib colormap object
    """
    # 1. Try DB-backed service first.
    try:
        from app.services.colormap_service import ColormapService
        cmap = ColormapService.get_instance().get_cmap(cmap_name)
        if cmap is not None:
            return cmap
    except Exception:
        pass  # DB unavailable — fall through to hardcoded builders

    # 2. Hardcoded builders (emergency fallback).
    builder = _HARDCODED_BUILDERS.get(cmap_name)
    if builder is not None:
        return builder()

    # 3. PyART colormaps.
    if cmap_name.startswith("pyart_") and PYART_AVAILABLE:
        pyart_name = cmap_name.replace("pyart_", "")
        try:
            return pyart.graph.cm.get_colormap(pyart_name)
        except (AttributeError, KeyError):
            pass

    if PYART_AVAILABLE:
        try:
            return pyart.graph.cm.get_colormap(cmap_name)
        except (AttributeError, KeyError):
            pass

    # 4. Standard matplotlib.
    return plt.get_cmap(cmap_name)


def colormap_for_field(field_key: str, override_cmap: Optional[str] = None) -> Tuple:
    """
    Get colormap configuration for a radar field/product.

    Resolution order:
      1. DB (ColormapService.default_for_product) — populated by seeds.
      2. FIELD_RENDER hardcoded dict — emergency fallback.
      3. Built-in defaults (vmin=-30, vmax=70, cmap=grc_th).

    Args:
        field_key: Product key (e.g., 'DBZH', 'VRAD')
        override_cmap: Optional colormap name to override default

    Returns:
        Tuple of (cmap_object, vmin, vmax, cmap_name)
    """
    _fallback = {"vmin": -30.0, "vmax": 70.0, "cmap": "grc_th"}

    # 1. DB via ColormapService.
    db_cmap, db_vmin, db_vmax = None, None, None
    try:
        from app.services.colormap_service import ColormapService
        db_cmap, db_vmin, db_vmax = ColormapService.get_instance().default_for_product(field_key)
    except Exception:
        pass

    if db_cmap is not None:
        vmin = db_vmin if db_vmin is not None else _fallback["vmin"]
        vmax = db_vmax if db_vmax is not None else _fallback["vmax"]
        cmap_name = override_cmap if override_cmap else db_cmap
        return get_colormap(cmap_name), vmin, vmax, cmap_name

    # 2. Hardcoded FIELD_RENDER dict.
    spec = (
        FIELD_RENDER.get(field_key)
        or FIELD_RENDER.get(field_key.upper())
        or (
            FIELD_RENDER.get(field_key[:-1]) or FIELD_RENDER.get(field_key[:-1].upper())
            if field_key.endswith("o")
            else None
        )
        or _fallback
    )
    vmin, vmax = spec["vmin"], spec["vmax"]
    cmap_name = override_cmap if override_cmap else spec["cmap"]
    return get_colormap(cmap_name), vmin, vmax, cmap_name


def colormap_options_for_field(field_key: str) -> list:
    """
    Get available colormap options for a field key.

    Resolution order:
      1. DB (ColormapService.options_for_product)
      2. FIELD_COLORMAP_OPTIONS hardcoded dict
      3. Empty list
    """
    # 1. DB.
    try:
        from app.services.colormap_service import ColormapService
        opts = ColormapService.get_instance().options_for_product(field_key)
        if opts:
            return opts
    except Exception:
        pass

    # 2. Hardcoded dict.
    options = (
        FIELD_COLORMAP_OPTIONS.get(field_key)
        or FIELD_COLORMAP_OPTIONS.get(field_key.upper())
        or (
            FIELD_COLORMAP_OPTIONS.get(field_key[:-1])
            or FIELD_COLORMAP_OPTIONS.get(field_key[:-1].upper())
            if field_key.endswith("o")
            else None
        )
    )
    return options or []


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
