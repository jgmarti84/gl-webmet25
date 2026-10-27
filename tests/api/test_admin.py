# tests/api/test_admin.py
"""Black-box tests of the protection of /api/v1/admin/* against the running API.

Only the protection is covered here: login, role and Origin check on the admin router. The CRUD contract of each
admin resource (fields, types, happy paths) is not covered yet; that is a known gap.

Nothing here writes to the database. Every request that would write targets an unknown id or code, or carries an
invalid body, so that if the protection ever failed the answer would be 404 or 422 and no data would change. The
collection-wide DELETEs (/cogs, /references, /tops-cores) are never sent, not even to check they are protected.
The 403 answered to a logged-in viewer needs a second account and is covered in tests/auth.
"""

import os
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
ADMIN_PREFIX = "/api/v1/admin"
AUTH_PREFIX = "/api/v1/auth"
ADMIN_USER = os.getenv("ADMIN_USERNAME")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD")

# skipif with a reason (not a plain skip): these tests need the admin account db-init creates from ADMIN_USERNAME / ADMIN_PASSWORD.
needs_admin = pytest.mark.skipif(not (ADMIN_USER and ADMIN_PASS), reason="ADMIN_USERNAME / ADMIN_PASSWORD not set")

UNKNOWN_ID = 999999999
FOREIGN_ORIGIN = {"Origin": "https://evil.example"}

# Read-only list endpoints of the admin router.
ADMIN_LIST_PATHS: List[str] = [
    "/cogs",
    "/colormap-options",
    "/colormap-stops",
    "/estrategias",
    "/products",
    "/radars",
    "/references",
    "/tops-cores",
    "/volumenes",
]

# (method, path, json body). Writes aimed at unknown targets or sent with an invalid body (see module docstring).
WRITE_REQUESTS: List[Tuple[str, str, Optional[Dict[str, Any]]]] = [
    ("POST", "/radars", {}),
    ("PUT", "/radars/NO_SUCH_RADAR", {}),
    ("PATCH", "/radars/NO_SUCH_RADAR", {}),
    ("DELETE", "/radars/NO_SUCH_RADAR", None),
    ("DELETE", f"/products/{UNKNOWN_ID}", None),
    ("PATCH", f"/cogs/{UNKNOWN_ID}", {"status": "missing"}),
    ("DELETE", f"/cogs/{UNKNOWN_ID}", None),
    ("DELETE", f"/tops-cores/{UNKNOWN_ID}", None),
    ("DELETE", f"/references/{UNKNOWN_ID}", None),
    ("DELETE", "/colormap-stops/no-such-colormap-xyz", None),
    ("POST", "/colormap-from-hex", {}),
]
WRITE_IDS = [f"{method} {path}" for method, path, _ in WRITE_REQUESTS]

_ADMIN: Dict[str, str] = {}


def _admin_cookie() -> str:
    """Cookie header of the bootstrap admin (the login happens once per test run, see tests/api/test_users.py)."""
    if not _ADMIN:
        with httpx.Client(base_url=API_BASE_URL) as client:
            response = client.post(f"{AUTH_PREFIX}/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
            assert response.status_code == 200, f"admin login failed: {response.status_code}"
            access = next(cookie for cookie in client.cookies.jar if cookie.name.endswith("webmet_access"))
            _ADMIN["cookie"] = f"{access.name}={access.value}"
    return _ADMIN["cookie"]


# ---------------------------------------------------------------------------
# GET /api/v1/admin/<resource>   (list endpoints)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ADMIN_LIST_PATHS)
def test_admin_list_endpoints_require_session(path):
    """Every admin list endpoint without a session must return 401 with a JSON detail."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{ADMIN_PREFIX}{path}")
    assert response.status_code == 401
    assert "detail" in response.json()


@needs_admin
@pytest.mark.parametrize("path", ADMIN_LIST_PATHS)
def test_admin_list_endpoints_return_200_for_admin(path):
    """Every admin list endpoint must let an admin in and return HTTP 200."""
    with httpx.Client(base_url=API_BASE_URL, headers={"Cookie": _admin_cookie()}) as client:
        response = client.get(f"{ADMIN_PREFIX}{path}")
    assert response.status_code == 200


@needs_admin
@pytest.mark.parametrize("path", ADMIN_LIST_PATHS)
def test_admin_list_endpoints_return_json_for_admin(path):
    """Every admin list endpoint must answer with valid JSON and the correct content type."""
    with httpx.Client(base_url=API_BASE_URL, headers={"Cookie": _admin_cookie()}) as client:
        response = client.get(f"{ADMIN_PREFIX}{path}")
    assert "application/json" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# POST / PUT / PATCH / DELETE /api/v1/admin/<resource>
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,body", WRITE_REQUESTS, ids=WRITE_IDS)
def test_admin_write_endpoints_require_session(method, path, body):
    """Every admin write endpoint without a session must return 401 (targets are unknown on purpose)."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.request(method, f"{ADMIN_PREFIX}{path}", json=body)
    assert response.status_code == 401


@needs_admin
@pytest.mark.parametrize("method,path,body", WRITE_REQUESTS, ids=WRITE_IDS)
def test_admin_write_endpoints_reject_foreign_origin(method, path, body):
    """Every admin write endpoint must reject a foreign Origin even with an admin session."""
    headers = {"Cookie": _admin_cookie(), **FOREIGN_ORIGIN}
    with httpx.Client(base_url=API_BASE_URL, headers=headers) as client:
        response = client.request(method, f"{ADMIN_PREFIX}{path}", json=body)
    assert response.status_code == 403
