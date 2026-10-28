# tests/api/test_frames.py
"""Black-box contract tests for /api/v1/frames (read only)."""

import os

import httpx

from ._session import session_headers

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
PREFIX = "/api/v1/frames"
MISSING_COG_ID = 999999999


def test_frames_without_session_returns_401():
    """Every data endpoint requires a session (spec A)."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{PREFIX}/{MISSING_COG_ID}/image.png")
    assert response.status_code == 401


def test_frames_missing_cog_returns_404():
    """A COG that does not exist must answer a clear 404, never a 500."""
    with httpx.Client(base_url=API_BASE_URL, headers=session_headers()) as client:
        response = client.get(f"{PREFIX}/{MISSING_COG_ID}/image.png")
    assert response.status_code == 404
