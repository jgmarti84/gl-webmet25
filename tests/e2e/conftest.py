# tests/e2e/conftest.py
"""
Shared fixtures for the Playwright end-to-end tests.

These tests drive a real (headless) Chromium against the **v2 frontend**
served by nginx. They require the full stack to be running (api + db + a v2
frontend). See docs/E2E_TESTING.md for how to run them.

Environment variables (with devcontainer defaults):
    FRONTEND_URL    base URL of the running v2 frontend  (http://frontend-v2:80)
    ADMIN_USERNAME  HTTP Basic Auth user for /admin       (admin)
    ADMIN_PASSWORD  HTTP Basic Auth password for /admin    (change-me)
"""
import os
from pathlib import Path

import pytest

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")

SCREENSHOT_DIR = Path(__file__).parent / "screenshots"


@pytest.fixture(scope="session")
def frontend_url() -> str:
    """Base URL of the v2 frontend under test."""
    return FRONTEND_URL


@pytest.fixture
def browser_context_args(browser_context_args):
    """Attach HTTP Basic Auth creds so `/admin` loads without a 401.

    Harmless for the public main map, required for the admin panel.
    """
    return {
        **browser_context_args,
        "http_credentials": {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        "ignore_https_errors": True,
    }


# Console-error noise that is NOT an app bug and must not fail a test.
# The frontend's geolocation auto-init does a best-effort IP lookup against the
# third-party ipapi.co service (handled/caught in app.js — the app degrades
# gracefully). In sandboxed/CI environments that host is unreachable or
# CORS-blocked, and the BROWSER logs a console.error for the failed request that
# the app cannot suppress. Ignore only that source; real app errors still fail.
_IGNORED_CONSOLE_SUBSTRINGS = ("ipapi.co",)


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
