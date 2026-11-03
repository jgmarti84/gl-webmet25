# tests/api/test_org.py
"""Black-box contract tests for /api/v1/org against the isolated test stack.

The bootstrap admin is not a company admin, so every /org endpoint must answer it 403; without a session, 401.
That covers the error paths without writing anything. The happy paths run in tests/auth/test_organizations.py.
"""

import os

import httpx
import pytest

from ._session import session_headers

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")

ENDPOINTS = [
    ("get", "/api/v1/org", None),
    ("get", "/api/v1/org/users", None),
    ("post", "/api/v1/org/users", {"username": "nadie", "password": "x"}),
    ("patch", "/api/v1/org/users/999999999", {"full_name": "x"}),
    ("put", "/api/v1/org/users/999999999/permissions", {"radar_detail_view": []}),
]


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_org_without_session_returns_401(method, path, body):
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.request(method, path, json=body).status_code == 401


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_org_for_the_general_admin_returns_403_json(method, path, body):
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.request(method, path, json=body, headers=session_headers())
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/json")
