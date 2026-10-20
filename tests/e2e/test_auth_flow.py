# tests/e2e/test_auth_flow.py
"""E2E: login redirect, logout and the users section."""
import os

from playwright.sync_api import Page, expect

from .conftest import ADMIN_USERNAME, login_via_form

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")


def test_admin_redirects_to_login_without_session(page: Page):
    page.goto(f"{FRONTEND_URL}/admin", wait_until="networkidle")
    page.wait_for_url("**/login**")
    expect(page.locator("#login-form")).to_be_visible()


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
    page.wait_for_url("**/login**")
    assert not js_errors, js_errors


def test_login_ignores_open_redirect_in_next(page: Page):
    """A crafted `next` must not take the user to another site after login."""
    page.goto(f"{FRONTEND_URL}/login?next=//evil.example", wait_until="networkidle")
    page.fill("#login-username", ADMIN_USERNAME)
    page.fill("#login-password", os.getenv("BOOTSTRAP_ADMIN_PASSWORD", ""))
    page.click("#login-submit")
    page.wait_for_url(lambda url: "/login" not in url)
    assert "evil.example" not in page.url
    assert "/admin" in page.url


def test_users_section_lists_current_admin(page: Page):
    login_via_form(page)
    page.click('a[data-section="users"]')
    page.wait_for_selector("table tbody tr")
    expect(page.locator("table tbody")).to_contain_text(ADMIN_USERNAME)
