# tests/api/test_auth.py
"""Black-box auth tests against the running API. They never create users."""
import os

import httpx
import pytest

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
ADMIN_USER = os.getenv("BOOTSTRAP_ADMIN_USERNAME")
ADMIN_PASS = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")

needs_admin = pytest.mark.skipif(
    not (ADMIN_USER and ADMIN_PASS), reason="BOOTSTRAP_ADMIN_* not set"
)


def test_admin_endpoint_requires_session():
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.get("/api/v1/admin/radars").status_code == 401


def test_login_with_unknown_user_is_generic_401():
    # Unknown user on purpose: wrong passwords on the real admin would lock it.
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post("/api/v1/auth/login", json={"username": "no-such-user-xyz", "password": "whatever-123"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Usuario o contraseña incorrectos"


def test_foreign_origin_is_rejected():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post("/api/v1/auth/logout", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


@needs_admin
def test_full_session_flow():
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS}).status_code == 200
        assert client.get("/api/v1/auth/me").json()["role"] == "admin"
        assert client.get("/api/v1/admin/radars").status_code == 200
        assert client.post("/api/v1/auth/refresh").status_code == 200
        assert client.get("/api/v1/admin/radars").status_code == 200
        assert client.post("/api/v1/auth/logout").status_code == 204
        assert client.get("/api/v1/admin/radars").status_code == 401
