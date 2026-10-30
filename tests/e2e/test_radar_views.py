# tests/e2e/test_radar_views.py
"""One-radar detail views follow the user's permissions (spec C, plan C-1), on the isolated test stack.

A throwaway radar E2EV (view enabled, no data) is created through the admin API and deleted at the end, which
also deletes its permissions. The e2e viewer gets no views, then only E2EV.
"""

import os

import pytest
from playwright.sync_api import Page, expect

from .conftest import E2E_VIEWER, E2E_VIEWER_PASSWORD, deactivate_user, ensure_viewer

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
CODE = "E2EV"
ADMIN_API = f"{FRONTEND_URL}/api/v1/admin"


@pytest.fixture
def setup(browser, admin_storage_state):
    """Admin context, the E2EV radar and the e2e viewer; everything is cleaned up afterwards."""
    admin = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    api = admin.request
    api.delete(f"{ADMIN_API}/radars/{CODE}")  # leftover of an interrupted run, if any
    created = api.post(
        f"{ADMIN_API}/radars",
        data={
            "code": CODE,
            "title": "E2E vista",
            "center_lat": -31.4,
            "center_long": -64.2,
            "img_radio": 240,
            "is_active": True,
            "detail_view_enabled": True,
        },
    )
    assert created.status == 201, created.text()
    viewer_id = ensure_viewer(api)
    yield api, viewer_id
    api.delete(f"{ADMIN_API}/radars/{CODE}")
    deactivate_user(api, viewer_id)
    admin.close()


def _viewer_page(browser) -> Page:
    """A logged-in viewer page that lists inactive radars too (E2EV has no data: the indexer may mark it inactive)."""
    page = browser.new_page(ignore_https_errors=True)
    page.add_init_script("localStorage.setItem('webmet25_show_inactive_radars', 'true')")
    page.goto(f"{FRONTEND_URL}/login", wait_until="networkidle")
    page.fill("#login-username", E2E_VIEWER)
    page.fill("#login-password", E2E_VIEWER_PASSWORD)
    page.click("#login-submit")
    page.wait_for_url(lambda url: "/login" not in url)
    page.wait_for_load_state("networkidle")
    return page


def _set_views(api, viewer_id, views):
    response = api.put(f"{ADMIN_API}/users/{viewer_id}/permissions", data={"radar_detail_view": views})
    assert response.status == 200, response.text()


def test_without_the_view_there_is_no_button_and_the_page_turns_away(browser, setup):
    api, viewer_id = setup
    _set_views(api, viewer_id, [])
    page = _viewer_page(browser)
    try:
        page.wait_for_selector(f"#radar-{CODE}", state="attached")
        item = page.locator(".radar-checkbox-item", has=page.locator(f"#radar-{CODE}"))
        expect(item.locator(".radar-drill-btn")).to_have_count(0)
        page.goto(f"{FRONTEND_URL}/radar.html?code={CODE}", wait_until="networkidle")
        expect(page.locator("#radar-unavailable")).to_be_visible()
        expect(page.locator("#radar-unavailable-text")).to_have_text("No tenés acceso a la vista de este radar.")
    finally:
        page.close()


def test_with_the_view_the_button_shows_and_the_page_opens(browser, setup):
    api, viewer_id = setup
    _set_views(api, viewer_id, [CODE])
    page = _viewer_page(browser)
    try:
        page.wait_for_selector(f"#radar-{CODE}", state="attached")
        item = page.locator(".radar-checkbox-item", has=page.locator(f"#radar-{CODE}"))
        expect(item.locator(".radar-drill-btn")).to_have_count(1)
        page.goto(f"{FRONTEND_URL}/radar.html?code={CODE}", wait_until="networkidle")
        expect(page.locator("#radar-unavailable")).to_be_hidden()
    finally:
        page.close()
