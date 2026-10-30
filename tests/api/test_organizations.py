# tests/api/test_organizations.py
"""Black-box contract tests for /api/v1/admin/organizations against the isolated test stack.

The list is read completely. Writes are tested only on their error paths (unknown id, invalid body), so a
regression answers 4xx and changes nothing; the happy paths run in tests/auth/test_organizations.py.
"""

import os

import httpx

from ._session import session_headers

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
PREFIX = "/api/v1/admin/organizations"
FIELDS = {"id", "name", "seat_limit", "seats_used", "is_active", "radar_detail_views", "created_at", "updated_at"}
UNKNOWN_ID = 999999999
FOREIGN_ORIGIN = {"Origin": "https://evil.example"}


def _get(path: str) -> httpx.Response:
    with httpx.Client(base_url=API_BASE_URL) as client:
        return client.get(path, headers=session_headers())


def test_list_without_session_returns_401():
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.get(PREFIX).status_code == 401


def test_list_returns_200_json():
    response = _get(PREFIX)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


def test_list_items_have_fields_and_types():
    for org in _get(PREFIX).json():
        assert FIELDS.issubset(org)
        assert isinstance(org["id"], int) and isinstance(org["name"], str)
        assert isinstance(org["seat_limit"], int) and isinstance(org["seats_used"], int)
        assert isinstance(org["is_active"], bool) and isinstance(org["radar_detail_views"], list)


def test_unknown_organization_returns_404():
    response = _get(f"{PREFIX}/{UNKNOWN_ID}")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_patch_unknown_organization_returns_404():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.patch(f"{PREFIX}/{UNKNOWN_ID}", json={"seat_limit": 5}, headers=session_headers())
    assert response.status_code == 404


def test_create_with_invalid_body_returns_422():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(PREFIX, json={"name": "", "seat_limit": 0}, headers=session_headers())
    assert response.status_code == 422


def test_permissions_of_unknown_organization_returns_404():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.put(
            f"{PREFIX}/{UNKNOWN_ID}/permissions", json={"radar_detail_view": []}, headers=session_headers()
        )
    assert response.status_code == 404


def test_create_from_a_foreign_origin_returns_403():
    with httpx.Client(base_url=API_BASE_URL) as client:
        headers = {**session_headers(), **FOREIGN_ORIGIN}
        response = client.post(PREFIX, json={"name": "Nunca", "seat_limit": 1}, headers=headers)
    assert response.status_code == 403
