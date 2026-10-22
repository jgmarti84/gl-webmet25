# tests/e2e/test_auth_flow.py
"""E2E: login redirect, logout and the users section."""

import os
from urllib.parse import urlparse

from playwright.sync_api import Page, expect

from .conftest import (
    ADMIN_USERNAME,
    E2E_VIEWER,
    E2E_VIEWER_PASSWORD,
    deactivate_user,
    ensure_viewer,
    login_via_form,
)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")


def test_admin_shows_login_in_place_without_session(page: Page):
    page.goto(f"{FRONTEND_URL}/admin", wait_until="networkidle")
    expect(page.locator("#login-form")).to_be_visible()
    assert urlparse(page.url).path == "/admin"


def test_wrong_password_shows_generic_error(page: Page):
    page.goto(f"{FRONTEND_URL}/login", wait_until="networkidle")
    page.fill("#login-username", "no-such-user-xyz")
    page.fill("#login-password", "whatever-123")
    page.click("#login-submit")
    expect(page.locator("#login-error")).to_have_text("Usuario o contraseña incorrectos")


def test_login_then_logout(page: Page, js_errors):
    login_via_form(page)
    expect(page.locator("#session-user")).to_be_visible()
    page.click("#logout-btn")
    page.wait_for_url("**/login**")
    page.goto(f"{FRONTEND_URL}/admin", wait_until="networkidle")
    expect(page.locator("#login-form")).to_be_visible()
    assert not js_errors, js_errors


def test_login_ignores_open_redirect_in_next(page: Page):
    """A crafted `next` must not take the user to another site after login."""
    page.goto(f"{FRONTEND_URL}/login?next=//evil.example", wait_until="networkidle")
    page.fill("#login-username", ADMIN_USERNAME)
    page.fill("#login-password", os.getenv("BOOTSTRAP_ADMIN_PASSWORD", ""))
    page.click("#login-submit")
    page.wait_for_url(lambda url: "/login" not in url)
    assert "evil.example" not in page.url
    assert urlparse(page.url).path == "/"


def test_users_section_lists_current_admin(page: Page):
    login_via_form(page)
    page.click('a[data-section="users"]')
    page.wait_for_selector("table tbody tr")
    expect(page.locator("table tbody")).to_contain_text(ADMIN_USERNAME)


def test_map_shows_login_in_place_and_opens_after_login(page: Page):
    page.goto(f"{FRONTEND_URL}/", wait_until="networkidle")
    expect(page.locator("#login-form")).to_be_visible()
    page.fill("#login-username", ADMIN_USERNAME)
    page.fill("#login-password", os.getenv("BOOTSTRAP_ADMIN_PASSWORD", ""))
    page.click("#login-submit")
    page.wait_for_selector("#radar-list", state="attached")
    expect(page.locator("#login-form")).to_have_count(0)


def test_protected_url_survives_the_login(page: Page):
    page.goto(f"{FRONTEND_URL}/cog-browser.html?probe=1&x=2", wait_until="networkidle")
    expect(page.locator("#login-form")).to_be_visible()
    page.fill("#login-username", ADMIN_USERNAME)
    page.fill("#login-password", os.getenv("BOOTSTRAP_ADMIN_PASSWORD", ""))
    page.click("#login-submit")
    page.wait_for_selector("#radar-select", state="attached")
    parsed = urlparse(page.url)
    assert (parsed.path, parsed.query) == ("/cog-browser.html", "probe=1&x=2")


def test_logout_from_the_map_shows_the_login(browser, admin_storage_state):
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    try:
        page = context.new_page()
        page.goto(f"{FRONTEND_URL}/", wait_until="networkidle")
        page.click("#btn-settings")  # the session box lives in the settings panel, hidden at start
        page.locator("#session-box-logout").click()
        expect(page.locator("#login-form")).to_be_visible()
    finally:
        context.close()


def test_viewer_is_sent_from_admin_to_the_map(browser, admin_storage_state):
    admin = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    viewer_id = ensure_viewer(admin.request)
    try:
        page = browser.new_page(ignore_https_errors=True)
        page.goto(f"{FRONTEND_URL}/login", wait_until="networkidle")
        page.fill("#login-username", E2E_VIEWER)
        page.fill("#login-password", E2E_VIEWER_PASSWORD)
        page.click("#login-submit")
        page.wait_for_url(lambda url: "/login" not in url)
        page.wait_for_load_state("networkidle")
        assert page.locator("#admin-link").get_attribute("hidden") is not None
        page.goto(f"{FRONTEND_URL}/admin", wait_until="networkidle")
        assert urlparse(page.url).path == "/"
        page.close()
    finally:
        deactivate_user(admin.request, viewer_id)
        admin.close()
