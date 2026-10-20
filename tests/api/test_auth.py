# tests/api/test_auth.py
"""Black-box contract tests for /api/v1/auth/* against the running API.

They only open sessions for the bootstrap admin (BOOTSTRAP_ADMIN_*): they never create users and never send a
wrong password for a real account (5 failed attempts lock it). The login/refresh/logout flows need
COOKIE_SECURE=false on the API, because httpx does not send Secure cookies over plain HTTP.

Endpoints that answer 204 have no body, so the content-type, fields and data-type tests do not apply to them.
"""

import os
from typing import Optional

import httpx
import pytest

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
PREFIX = "/api/v1/auth"
ADMIN_USER = os.getenv("BOOTSTRAP_ADMIN_USERNAME")
ADMIN_PASS = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")

# skipif with a reason (not a plain skip): these tests need the admin account db-init creates from BOOTSTRAP_ADMIN_*.
needs_admin = pytest.mark.skipif(not (ADMIN_USER and ADMIN_PASS), reason="BOOTSTRAP_ADMIN_* not set")

ME_FIELDS = {"id", "username", "full_name", "role", "password_is_bootstrap"}
SENSITIVE_FIELDS = {"password_hash", "token_version", "failed_login_count", "locked_until"}
FOREIGN_ORIGIN = {"Origin": "https://evil.example"}
# Cookie names change with COOKIE_SECURE (prefixes), so garbage cookies are sent under both names.
GARBAGE_ACCESS_COOKIE = {"Cookie": "webmet_access=garbage; __Host-webmet_access=garbage"}
GARBAGE_REFRESH_COOKIE = {"Cookie": "webmet_refresh=garbage; __Secure-webmet_refresh=garbage"}


def _login(client: httpx.Client) -> httpx.Response:
    """Log in as the bootstrap admin; the session cookies stay in the client."""
    return client.post(f"{PREFIX}/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})


def _cookie_value(client: httpx.Client, suffix: str) -> Optional[str]:
    """Value of the cookie whose name ends with `suffix` (names carry a prefix when COOKIE_SECURE is on)."""
    for cookie in client.cookies.jar:
        if cookie.name.endswith(suffix):
            return cookie.value
    return None


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login
# ---------------------------------------------------------------------------


@needs_admin
def test_login_returns_200():
    """Login with the bootstrap admin must return HTTP 200."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = _login(client)
    assert response.status_code == 200


@needs_admin
def test_login_returns_json():
    """Login must return valid JSON with the correct content type."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = _login(client)
    assert "application/json" in response.headers["content-type"]


@needs_admin
def test_login_response_has_required_fields():
    """Login must return the current user with every contract field."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        data = _login(client).json()
    assert ME_FIELDS.issubset(data)


@needs_admin
def test_login_response_does_not_expose_sensitive_fields():
    """Login must never expose password hashes or lockout internals."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        data = _login(client).json()
    assert SENSITIVE_FIELDS.isdisjoint(data)


@needs_admin
def test_login_response_field_types():
    """Login field types must match the contract."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        data = _login(client).json()
    assert isinstance(data["id"], int)
    assert isinstance(data["username"], str)
    assert data["full_name"] is None or isinstance(data["full_name"], str)
    assert data["role"] in ("admin", "viewer")
    assert isinstance(data["password_is_bootstrap"], bool)


@needs_admin
def test_login_sets_httponly_samesite_strict_cookies():
    """Login must set exactly two cookies, both HttpOnly and SameSite=Strict."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = _login(client)
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    for cookie in cookies:
        assert "httponly" in cookie.lower()
        assert "samesite=strict" in cookie.lower()


@needs_admin
def test_login_scopes_refresh_cookie_to_the_auth_path():
    """The refresh cookie must only travel to /api/v1/auth; the access cookie to the whole site."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = _login(client)
    cookies = [cookie.lower() for cookie in response.headers.get_list("set-cookie")]
    assert any("refresh" in cookie and "path=/api/v1/auth" in cookie for cookie in cookies)
    assert any("access" in cookie and "path=/;" in cookie for cookie in cookies)


def test_login_with_unknown_user_is_generic_401():
    """An unknown user must get the same generic 401 as a wrong password."""
    # Unknown user on purpose: wrong passwords on the real admin would lock it.
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/login", json={"username": "no-such-user-xyz", "password": "whatever-123"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Usuario o contraseña incorrectos"


def test_login_with_unknown_user_sets_no_cookies():
    """A failed login must not set any cookie."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/login", json={"username": "no-such-user-xyz", "password": "whatever-123"})
    assert response.headers.get_list("set-cookie") == []


def test_login_missing_fields_returns_422():
    """A body without username and password must return 422."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/login", json={})
    assert response.status_code == 422


def test_login_empty_password_returns_422():
    """An empty password must return 422 before any verification."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/login", json={"username": "no-such-user-xyz", "password": ""})
    assert response.status_code == 422


def test_login_too_long_password_returns_422():
    """A password over 128 characters must return 422 (it bounds the hashing cost)."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/login", json={"username": "no-such-user-xyz", "password": "a" * 129})
    assert response.status_code == 422


def test_login_foreign_origin_returns_403():
    """A login coming from a foreign Origin must be rejected."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(
            f"{PREFIX}/login",
            json={"username": "no-such-user-xyz", "password": "whatever-123"},
            headers=FOREIGN_ORIGIN,
        )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/v1/auth/refresh
# ---------------------------------------------------------------------------


@needs_admin
def test_refresh_returns_200():
    """Refresh with a valid session must return HTTP 200."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        _login(client)
        response = client.post(f"{PREFIX}/refresh")
    assert response.status_code == 200


@needs_admin
def test_refresh_returns_json():
    """Refresh must return valid JSON with the correct content type."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        _login(client)
        response = client.post(f"{PREFIX}/refresh")
    assert "application/json" in response.headers["content-type"]


@needs_admin
def test_refresh_response_has_required_fields():
    """Refresh must return the current user with every contract field."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        _login(client)
        data = client.post(f"{PREFIX}/refresh").json()
    assert ME_FIELDS.issubset(data)
    assert SENSITIVE_FIELDS.isdisjoint(data)


@needs_admin
def test_refresh_response_field_types():
    """Refresh field types must match the contract."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        _login(client)
        data = client.post(f"{PREFIX}/refresh").json()
    assert isinstance(data["id"], int)
    assert isinstance(data["username"], str)
    assert data["role"] in ("admin", "viewer")
    assert isinstance(data["password_is_bootstrap"], bool)


@needs_admin
def test_refresh_rotates_the_refresh_cookie():
    """Every refresh must replace the refresh token with a new one."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        _login(client)
        before = _cookie_value(client, "webmet_refresh")
        client.post(f"{PREFIX}/refresh")
        after = _cookie_value(client, "webmet_refresh")
    assert before and after
    assert before != after


def test_refresh_without_cookie_returns_401():
    """Refresh without a session must return 401 with a JSON detail."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/refresh")
    assert response.status_code == 401
    assert "detail" in response.json()


def test_refresh_with_garbage_cookie_returns_401():
    """Refresh with an unknown token must return 401."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/refresh", headers=GARBAGE_REFRESH_COOKIE)
    assert response.status_code == 401


def test_refresh_foreign_origin_returns_403():
    """A refresh coming from a foreign Origin must be rejected."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/refresh", headers=FOREIGN_ORIGIN)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/v1/auth/logout   (204: no body)
# ---------------------------------------------------------------------------


@needs_admin
def test_logout_returns_204():
    """Logout with a valid session must return HTTP 204."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        _login(client)
        response = client.post(f"{PREFIX}/logout")
    assert response.status_code == 204


def test_logout_without_session_returns_204():
    """Logout is idempotent: without a session it must still return 204."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/logout")
    assert response.status_code == 204


@needs_admin
def test_logout_expires_the_auth_cookies():
    """Logout must expire both auth cookies."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        _login(client)
        response = client.post(f"{PREFIX}/logout")
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    for cookie in cookies:
        assert "max-age=0" in cookie.lower()


@needs_admin
def test_logout_revokes_the_refresh_token():
    """After logout the old refresh token must no longer work, even if somebody kept a copy."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        _login(client)
        old_refresh = _cookie_value(client, "webmet_refresh")
        client.post(f"{PREFIX}/logout")
        replay = client.post(
            f"{PREFIX}/refresh",
            headers={"Cookie": f"webmet_refresh={old_refresh}; __Secure-webmet_refresh={old_refresh}"},
        )
    assert replay.status_code == 401


def test_logout_foreign_origin_returns_403():
    """A logout coming from a foreign Origin must be rejected."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/logout", headers=FOREIGN_ORIGIN)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/auth/me
# ---------------------------------------------------------------------------


@needs_admin
def test_me_returns_200():
    """/auth/me with a valid session must return HTTP 200."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        _login(client)
        response = client.get(f"{PREFIX}/me")
    assert response.status_code == 200


@needs_admin
def test_me_returns_json():
    """/auth/me must return valid JSON with the correct content type."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        _login(client)
        response = client.get(f"{PREFIX}/me")
    assert "application/json" in response.headers["content-type"]


@needs_admin
def test_me_response_has_required_fields():
    """/auth/me must return every contract field."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        _login(client)
        data = client.get(f"{PREFIX}/me").json()
    assert ME_FIELDS.issubset(data)


@needs_admin
def test_me_does_not_expose_sensitive_fields():
    """/auth/me must never expose password hashes or lockout internals."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        _login(client)
        data = client.get(f"{PREFIX}/me").json()
    assert SENSITIVE_FIELDS.isdisjoint(data)


@needs_admin
def test_me_response_field_types():
    """/auth/me field types must match the contract."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        _login(client)
        data = client.get(f"{PREFIX}/me").json()
    assert isinstance(data["id"], int)
    assert isinstance(data["username"], str)
    assert data["full_name"] is None or isinstance(data["full_name"], str)
    assert data["role"] in ("admin", "viewer")
    assert isinstance(data["password_is_bootstrap"], bool)


@needs_admin
def test_me_matches_the_login_response():
    """/auth/me must describe the same user that logged in."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        login_data = _login(client).json()
        me_data = client.get(f"{PREFIX}/me").json()
    assert me_data == login_data


def test_me_without_session_returns_401():
    """/auth/me without a session must return 401."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{PREFIX}/me")
    assert response.status_code == 401
    assert "detail" in response.json()


def test_me_with_garbage_access_cookie_returns_401():
    """/auth/me with a forged access cookie must return 401."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{PREFIX}/me", headers=GARBAGE_ACCESS_COOKIE)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Full flow and admin protection
# ---------------------------------------------------------------------------


def test_admin_endpoint_requires_session():
    """An admin endpoint without a session must return 401."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.get("/api/v1/admin/radars").status_code == 401


@needs_admin
def test_full_session_flow():
    """login -> me -> admin endpoint -> refresh -> logout -> admin endpoint closed again."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert _login(client).status_code == 200
        assert client.get(f"{PREFIX}/me").json()["role"] == "admin"
        assert client.get("/api/v1/admin/radars").status_code == 200
        assert client.post(f"{PREFIX}/refresh").status_code == 200
        assert client.get("/api/v1/admin/radars").status_code == 200
        assert client.post(f"{PREFIX}/logout").status_code == 204
        assert client.get("/api/v1/admin/radars").status_code == 401
