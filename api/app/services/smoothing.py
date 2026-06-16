# api/app/services/smoothing.py
"""
Gaussian smoothing for 2D radar raster data.

Applied post-warp on float32 masked arrays (one band read from a COG)
before colormap mapping.  Uses a dual-filter normalised convolution so
that masked / nodata pixels never bleed into valid neighbours.

Algorithm
---------
For every position (i, j):

    smoothed(i,j) = Σ_k G(k) · data(k) / Σ_k G(k) · valid(k)

where G is the Gaussian kernel, data(k) is zero-filled at nodata pixels,
and valid(k) is 1 for valid pixels and 0 for masked/NaN pixels.
This is mathematically equivalent to a weighted average that excludes
nodata from the denominator, preventing boundary contamination.
"""

import numpy as np
from scipy.ndimage import gaussian_filter


def apply_gaussian_smoothing_masked(
    arr: np.ma.MaskedArray,
    sigma: float,
) -> np.ma.MaskedArray:
    """Apply Gaussian smoothing preserving the nodata mask.

    Args:
        arr:   Input masked array (float32, 2-D).
        sigma: Standard deviation for the Gaussian kernel in pixels.

    Returns:
        Smoothed masked array with the same shape and mask structure as *arr*.
    """
    if sigma <= 0.0:
        return arr

    original_mask: np.ndarray = np.ma.getmaskarray(arr)
    data: np.ndarray = np.ma.filled(arr, fill_value=np.nan).astype(np.float32)

    # valid(k) = 1 where data is finite and not masked
    valid: np.ndarray = ((~original_mask) & np.isfinite(data)).astype(np.float32)

    # Zero-fill non-finite cells so the convolution is numerically stable
    data_filled: np.ndarray = np.where(np.isfinite(data), data, 0.0).astype(np.float32)

    smoothed_data: np.ndarray = gaussian_filter(data_filled, sigma=sigma, mode="nearest")
    smoothed_weights: np.ndarray = gaussian_filter(valid, sigma=sigma, mode="nearest")

    with np.errstate(divide="ignore", invalid="ignore"):
        out: np.ndarray = np.where(
            smoothed_weights > 1e-6,
            smoothed_data / smoothed_weights,
            np.nan,
        )

    out = out.astype(np.float32)
    final_mask: np.ndarray = original_mask | (~np.isfinite(out))
    return np.ma.array(out, mask=final_mask)


def apply_smoothing(arr: np.ma.MaskedArray, sigma: float) -> np.ma.MaskedArray:
    """Dispatcher — currently only Gaussian is supported.

    Args:
        arr:   Input masked array.
        sigma: Gaussian standard deviation in pixels (clamped to [0.1, 3.0]).

    Returns:
        Smoothed masked array.
    """
    sigma = float(np.clip(sigma, 0.1, 3.0))
    return apply_gaussian_smoothing_masked(arr, sigma)
