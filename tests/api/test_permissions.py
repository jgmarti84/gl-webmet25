# tests/api/test_permissions.py
"""Black-box contract tests for GET /api/v1/permissions/me against the running API (isolated test stack).

The rules (wildcard, view flag, per-user lists) are tested on the test database in tests/auth/test_permissions.py.
Here: status, content type, fields and types, and the 401 without a session. The admin sees every enabled view.
"""

import os

import httpx

from ._session import session_headers

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
URL = "/api/v1/permissions/me"


def test_my_permissions_without_session_returns_401():
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.get(URL).status_code == 401


def test_my_permissions_returns_200():
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.get(URL, headers=session_headers()).status_code == 200


def test_my_permissions_returns_json():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(URL, headers=session_headers())
    assert response.headers["content-type"].startswith("application/json")


def test_my_permissions_has_required_fields():
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert set(client.get(URL, headers=session_headers()).json()) == {"radar_detail_views"}


def test_my_permissions_field_types():
    with httpx.Client(base_url=API_BASE_URL) as client:
        views = client.get(URL, headers=session_headers()).json()["radar_detail_views"]
    assert isinstance(views, list)
    assert all(isinstance(code, str) and code != "*" for code in views)
