# tests/api/_session.py
"""One admin session per test run, shared by every black-box API test.

Every data endpoint requires a session (spec A). This logs in once as the bootstrap admin
(BOOTSTRAP_ADMIN_*) and returns the access cookie as a header. It is a plain function, not a
pytest fixture, following the tests/api rules.
"""

import os
from typing import Dict

import httpx

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
ADMIN_USER = os.getenv("BOOTSTRAP_ADMIN_USERNAME")
ADMIN_PASS = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")

_COOKIE: Dict[str, str] = {}


def session_headers() -> Dict[str, str]:
    """Cookie header of the bootstrap admin; logs in on the first call only."""
    if not _COOKIE:
        if not (ADMIN_USER and ADMIN_PASS):
            raise RuntimeError("BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD are required by tests/api")
        with httpx.Client(base_url=API_BASE_URL) as client:
            response = client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
            assert response.status_code == 200, f"admin login failed: {response.status_code}"
            access = next(cookie for cookie in client.cookies.jar if cookie.name.endswith("webmet_access"))
            _COOKIE["value"] = f"{access.name}={access.value}"
    return {"Cookie": _COOKIE["value"]}
