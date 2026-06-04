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


@pytest.fixture
def js_errors(page):
    """Collect page errors + console.error messages during a test.

    Usage: assert not js_errors  (at the end of a test)
    """
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: errors.append(f"console.error: {msg.text}") if msg.type == "error" else None,
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
