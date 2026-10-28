# tests/api/test_tops_cores.py
"""Black-box contract tests for /api/v1/tops-cores (read only)."""

import os

import httpx

from ._session import session_headers

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
PREFIX = "/api/v1/tops-cores"


def test_tops_cores_without_session_returns_401():
    """Every data endpoint requires a session (spec A)."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    assert response.status_code == 401


def test_tops_cores_returns_200_json_list():
    """GET /tops-cores with a session and a time window returns a JSON list."""
    params = {"radar_codes": "RMA1", "time_from": "2020-01-01T00:00:00Z", "time_to": "2020-01-02T00:00:00Z"}
    with httpx.Client(base_url=API_BASE_URL, headers=session_headers()) as client:
        response = client.get(PREFIX, params=params)
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    assert isinstance(response.json(), list)


def test_tops_cores_missing_parameters_returns_422():
    """radar_codes, time_from and time_to are required: without them the answer is a clear 422."""
    with httpx.Client(base_url=API_BASE_URL, headers=session_headers()) as client:
        response = client.get(PREFIX)
    assert response.status_code == 422
