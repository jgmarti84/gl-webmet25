# tests/e2e/conftest.py
"""
Shared fixtures for the Playwright end-to-end tests.

These tests drive a real (headless) Chromium against the **v2 frontend**
served by nginx. They require the full stack to be running (api + db + a v2
frontend). See docs/E2E_TESTING.md for how to run them.

Environment variables (with devcontainer defaults):
    FRONTEND_URL              base URL of the running v2 frontend  (http://frontend-v2:80)
    BOOTSTRAP_ADMIN_USERNAME  admin account created by db-init     (admin)
    BOOTSTRAP_ADMIN_PASSWORD  its password (required to log in)
"""
import os
import time
from pathlib import Path

import pytest

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
ADMIN_USERNAME = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")

SCREENSHOT_DIR = Path(__file__).parent / "screenshots"


@pytest.fixture(scope="session")
def frontend_url() -> str:
    """Base URL of the v2 frontend under test."""
    return FRONTEND_URL


@pytest.fixture
def browser_context_args(browser_context_args):
    return {**browser_context_args, "ignore_https_errors": True}


def login_via_form(page, username: str = ADMIN_USERNAME, password: str = ADMIN_PASSWORD) -> None:
    """Log in through /login and wait until the admin panel is shown."""
    page.goto(f"{FRONTEND_URL}/login?next=/admin", wait_until="networkidle")
    page.fill("#login-username", username)
    page.fill("#login-password", password)
    page.click("#login-submit")
    # Not "**/admin**": it would also match the login URL itself (/login?next=/admin).
    page.wait_for_url(lambda url: "/login" not in url and "/admin" in url)


# nginx rate-limits /api/v1/auth/login (10 requests/minute per IP), so the admin
# tests share ONE login: its browser state (cookies) is reused for every test and
# renewed every 10 minutes, before the 30-minute access cookie expires. Contexts
# started from the same state must not outlive that window, otherwise two of
# them would try to refresh the same (rotating) refresh token.
_ADMIN_STATE = {"state": None, "at": 0.0}
_ADMIN_STATE_MAX_AGE_S = 600


@pytest.fixture
def admin_storage_state(browser):
    now = time.time()
    if _ADMIN_STATE["state"] is None or now - _ADMIN_STATE["at"] > _ADMIN_STATE_MAX_AGE_S:
        context = browser.new_context(ignore_https_errors=True)
        try:
            login_via_form(context.new_page())
            _ADMIN_STATE["state"] = context.storage_state()
            _ADMIN_STATE["at"] = now
        finally:
            context.close()
    return _ADMIN_STATE["state"]


# Console-error noise that is NOT an app bug and must not fail a test.
# The frontend's geolocation auto-init does a best-effort IP lookup against the
# third-party ipapi.co service (handled/caught in app.js — the app degrades
# gracefully). In sandboxed/CI environments that host is unreachable or
# CORS-blocked, and the BROWSER logs a console.error for the failed request that
# the app cannot suppress. Ignore only that source; real app errors still fail.
# "/api/v1/auth/": the browser logs every 401 of /auth/me and /auth/refresh as a
# console error; those 401s are the expected "no session yet" answer.
_IGNORED_CONSOLE_SUBSTRINGS = ("ipapi.co", "/api/v1/auth/")


def _is_ignored_console(msg) -> bool:
    text = msg.text or ""
    try:
        url = (msg.location or {}).get("url", "")
    except Exception:
        url = ""
    return any(s in text or s in url for s in _IGNORED_CONSOLE_SUBSTRINGS)


@pytest.fixture
def js_errors(page):
    """Collect page errors + console.error messages during a test.

    Usage: assert not js_errors  (at the end of a test)

    Known external-service noise (see _IGNORED_CONSOLE_SUBSTRINGS) is filtered
    out so the assertion reflects the app's own errors, not sandbox network
    limitations.
    """
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: errors.append(f"console.error: {msg.text}")
        if (msg.type == "error" and not _is_ignored_console(msg))
        else None,
    )
    return errors


# ---------------------------------------------------------------------------
# Screenshot on failure (e2e rule: always capture a screenshot when a test
# fails, for debugging). Saved to tests/e2e/screenshots/<test name>.png
# ---------------------------------------------------------------------------
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)


@pytest.fixture(autouse=True)
def _screenshot_on_failure(request):
    yield
    page = request.node.funcargs.get("page")
    rep = getattr(request.node, "rep_call", None)
    if page is not None and rep is not None and rep.failed:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        safe = request.node.name.replace("/", "_")
        try:
            page.screenshot(path=str(SCREENSHOT_DIR / f"{safe}.png"), full_page=True)
        except Exception:
            pass  # never let screenshotting mask the real failure


E2E_VIEWER = "e2e-viewer"
E2E_VIEWER_PASSWORD = "e2e-viewer-password-1"


def ensure_viewer(api) -> int:
    """Create (or reactivate) the e2e viewer through the admin API; `api` is an admin APIRequestContext."""
    users = api.get(f"{FRONTEND_URL}/api/v1/admin/users").json()
    existing = next((u for u in users if u["username"] == E2E_VIEWER), None)
    if existing is None:
        response = api.post(
            f"{FRONTEND_URL}/api/v1/admin/users",
            data={"username": E2E_VIEWER, "password": E2E_VIEWER_PASSWORD, "role": "viewer"},
        )
        assert response.status == 201, response.text()
        return response.json()["id"]
    api.patch(f"{FRONTEND_URL}/api/v1/admin/users/{existing['id']}", data={"is_active": True, "role": "viewer"})
    api.post(
        f"{FRONTEND_URL}/api/v1/admin/users/{existing['id']}/reset-password",
        data={"password": E2E_VIEWER_PASSWORD},
    )
    return existing["id"]


def deactivate_user(api, user_id: int) -> None:
    api.patch(f"{FRONTEND_URL}/api/v1/admin/users/{user_id}", data={"is_active": False})
