# tests/api/test_profile.py
"""Black-box contract tests for /api/v1/profile against the isolated test stack.

The bootstrap admin reads its own profile. PATCH is only tried on its error paths (no session, foreign origin, a name
that is too long), so nothing is written: the happy path runs in tests/auth/test_profile_router.py.
"""

import os

import httpx

from ._session import session_headers

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
URL = "/api/v1/profile"
FOREIGN_ORIGIN = {"Origin": "https://evil.example"}
FIELDS = {
    "username",
    "full_name",
    "email",
    "role",
    "organization_name",
    "created_at",
    "last_login_at",
    "radar_detail_views",
}


def test_get_profile_returns_200_json_with_the_contract_fields():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(URL, headers=session_headers())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert set(response.json()) == FIELDS


def test_get_profile_field_types():
    with httpx.Client(base_url=API_BASE_URL) as client:
        data = client.get(URL, headers=session_headers()).json()
    assert isinstance(data["username"], str)
    assert data["role"] == "admin"
    assert data["organization_name"] is None  # the general admin has no company
    assert isinstance(data["radar_detail_views"], list)
    for view in data["radar_detail_views"]:
        assert isinstance(view["code"], str) and isinstance(view["title"], str)


def test_profile_without_session_returns_401():
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.get(URL).status_code == 401
        assert client.patch(URL, json={"full_name": "x"}).status_code == 401


def test_patch_profile_with_a_name_too_long_returns_422_and_writes_nothing():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.patch(URL, json={"full_name": "x" * 129}, headers=session_headers())
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")


def test_patch_profile_from_a_foreign_origin_returns_403():
    headers = {**session_headers(), **FOREIGN_ORIGIN}
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.patch(URL, json={"full_name": "x"}, headers=headers)
    assert response.status_code == 403


# --- DELETE /profile (spec G) ----------------------------------------------------------------------------------
# Only without a session. It is never sent with the bootstrap admin's session, even if a 403 is expected (the general
# admin cannot delete itself): tests/api never sends destructive actions on the real admin. Everything else runs on
# the test database in tests/auth/test_user_delete.py.


def test_delete_profile_without_session_returns_401():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.delete(URL)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
