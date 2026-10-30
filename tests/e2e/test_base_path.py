# tests/e2e/test_base_path.py
"""The site served under a base path (spec base-path), through prefix-proxy-e2e (/pfx/ -> frontend-e2e).

Every request the browser makes to the site must stay inside /pfx/: an absolute URL ("/api/...", "/css/...") written
anywhere in the frontend would escape to the root (on stage, another copy of the site) and fail these tests, even on
a screen nobody wrote a test for.
"""

import os
from typing import List
from urllib.parse import urlsplit

from playwright.sync_api import Page, expect

from .conftest import ADMIN_PASSWORD, ADMIN_USERNAME, E2E_VIEWER, E2E_VIEWER_PASSWORD, deactivate_user, ensure_viewer

PREFIX_URL = os.getenv("PREFIX_FRONTEND_URL", "http://prefix-proxy-e2e/pfx")
SITE = urlsplit(PREFIX_URL).netloc
PREFIX = urlsplit(PREFIX_URL).path  # "/pfx"


def _track(page: Page) -> List[str]:
    """Record the URL of every request the page makes from now on."""
    urls: List[str] = []
    page.on("request", lambda request: urls.append(request.url))
    return urls


def _escaped(urls: List[str]) -> List[str]:
    """Requests to this site outside the prefix (external hosts like the Leaflet CDN are fine)."""
    return [u for u in urls if urlsplit(u).netloc == SITE and not urlsplit(u).path.startswith(f"{PREFIX}/")]


def _login(page: Page, username: str, password: str) -> None:
    """Log in through the login page under the prefix and wait until it leaves it."""
    page.goto(f"{PREFIX_URL}/login", wait_until="networkidle")
    page.fill("#login-username", username)
    page.fill("#login-password", password)
    page.click("#login-submit")
    page.wait_for_url(lambda url: "/login" not in url)
    page.wait_for_load_state("networkidle")


def test_login_in_place_stays_inside_the_prefix(page: Page):
    urls = _track(page)
    page.goto(f"{PREFIX_URL}/admin", wait_until="networkidle")
    expect(page.locator("#login-form")).to_be_visible()
    assert urlsplit(page.url).path == f"{PREFIX}/admin"
    assert _escaped(urls) == [], _escaped(urls)


def test_logged_in_walk_never_leaves_the_prefix(browser):
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    urls = _track(page)
    try:
        _login(page, ADMIN_USERNAME, ADMIN_PASSWORD)
        cookies = {c["name"]: c for c in context.cookies()}
        assert "pfx_webmet_access" in cookies and cookies["pfx_webmet_access"]["path"] == "/"
        assert cookies["pfx_webmet_refresh"]["path"] == f"{PREFIX}/api/v1/auth"
        assert "webmet_access" not in cookies

        for path in ("/", "/radar.html?code=RMA1", "/cog-browser.html", "/register", "/forgot"):
            page.goto(f"{PREFIX_URL}{path}", wait_until="networkidle")

        page.goto(f"{PREFIX_URL}/admin", wait_until="networkidle")
        for section in ("users", "radars"):
            page.click(f"#sidebar-nav [data-section={section}]")
            page.wait_for_load_state("networkidle")
            assert urlsplit(page.url).path == f"{PREFIX}/admin"
            assert urlsplit(page.url).fragment == section

        # Session renewal and logout through the prefix (relative URLs, as the frontend calls them).
        assert page.evaluate("fetch('api/v1/auth/refresh', {method: 'POST'}).then(r => r.status)") == 200
        assert page.evaluate("fetch('api/v1/auth/logout', {method: 'POST'}).then(r => r.status)") == 204
        assert "pfx_webmet_access" not in {c["name"] for c in context.cookies()}

        assert _escaped(urls) == [], _escaped(urls)
    finally:
        context.close()


def test_a_viewer_sent_from_admin_lands_on_the_prefixed_map(browser, admin_storage_state):
    admin = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    viewer_id = ensure_viewer(admin.request)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    try:
        _login(page, E2E_VIEWER, E2E_VIEWER_PASSWORD)
        page.goto(f"{PREFIX_URL}/admin", wait_until="networkidle")
        assert urlsplit(page.url).path == f"{PREFIX}/"
    finally:
        context.close()
        deactivate_user(admin.request, viewer_id)
        admin.close()


def test_the_company_panel_stays_inside_the_prefix(browser, admin_storage_state):
    """/empresa (spec C, plan C-2) behind the prefix: the probe, the page, its scripts and its API calls."""
    from .test_empresa import ORG_ADMIN, ORG_ADMIN_PASSWORD, _ensure_company, _ensure_org_admin

    admin = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    org_admin_id = _ensure_org_admin(admin.request, _ensure_company(admin.request))
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    urls = _track(page)
    try:
        _login(page, ORG_ADMIN, ORG_ADMIN_PASSWORD)
        page.goto(f"{PREFIX_URL}/empresa", wait_until="networkidle")
        assert urlsplit(page.url).path == f"{PREFIX}/empresa"
        expect(page.locator("#empresa-name")).to_be_visible()
        assert _escaped(urls) == [], _escaped(urls)
    finally:
        context.close()
        deactivate_user(admin.request, org_admin_id)
        admin.close()
