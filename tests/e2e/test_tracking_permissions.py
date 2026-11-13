# tests/e2e/test_tracking_permissions.py
"""Who may use the storm tracking tool: nginx gates the service, and the radar view shows the button.

nginx: the tool for everything under /api/tracking/, and the radar's view too for the per-radar routes. The test stack
has no tracking service, so a request nginx lets through answers 502 and one it stops answers 403: that difference is
what the first tests check. The last ones look at the button of the radar view with the e2e viewer.

A throwaway radar E2EP (view enabled, no data) is created through the admin API and deleted at the end.
"""

import os

import pytest
from playwright.sync_api import expect

from .conftest import E2E_VIEWER, E2E_VIEWER_PASSWORD, deactivate_user, ensure_viewer

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
ADMIN_API = f"{FRONTEND_URL}/api/v1/admin"
CODE = "E2EP"


@pytest.fixture
def viewer(browser, admin_storage_state):
    """The e2e viewer (logged in through the API), an admin API to change its permissions and the radar E2EP."""
    admin = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    api = admin.request
    api.delete(f"{ADMIN_API}/radars/{CODE}")  # leftover of an interrupted run, if any
    created = api.post(
        f"{ADMIN_API}/radars",
        data={
            "code": CODE,
            "title": "E2E permisos",
            "center_lat": -31.4,
            "center_long": -64.2,
            "img_radio": 240,
            "is_active": True,
            "detail_view_enabled": True,
        },
    )
    assert created.status == 201, created.text()
    viewer_id = ensure_viewer(api)
    context = browser.new_context(ignore_https_errors=True)
    login = context.request.post(
        f"{FRONTEND_URL}/api/v1/auth/login", data={"username": E2E_VIEWER, "password": E2E_VIEWER_PASSWORD}
    )
    assert login.status == 200, login.text()
    yield api, viewer_id, context
    context.close()
    api.delete(f"{ADMIN_API}/radars/{CODE}")
    deactivate_user(api, viewer_id)
    admin.close()


def _set(api, viewer_id, views, tracking):
    body = {"radar_detail_view": views, "tools": {"tracking": tracking}}
    response = api.put(f"{ADMIN_API}/users/{viewer_id}/permissions", data=body)
    assert response.status == 200, response.text()


def test_without_the_tool_nginx_answers_403(viewer):
    api, viewer_id, context = viewer
    _set(api, viewer_id, [CODE], False)
    assert context.request.get(f"{FRONTEND_URL}/api/tracking/radars/{CODE}/availability").status == 403
    assert context.request.get(f"{FRONTEND_URL}/api/tracking/jobs/abc").status == 403


def test_with_the_tool_but_not_the_view_the_radar_route_is_403(viewer):
    api, viewer_id, context = viewer
    _set(api, viewer_id, [], True)
    assert context.request.post(f"{FRONTEND_URL}/api/tracking/radars/{CODE}/jobs", data={}).status == 403
    # A route without a radar in the URL only needs the tool: nginx lets it through (502: no service in this stack).
    assert context.request.get(f"{FRONTEND_URL}/api/tracking/jobs/abc").status == 502


def test_with_the_tool_and_the_view_nginx_lets_it_through(viewer):
    api, viewer_id, context = viewer
    _set(api, viewer_id, [CODE], True)
    # 502: nginx passed the request on and found no tracking service in the test stack.
    assert context.request.get(f"{FRONTEND_URL}/api/tracking/radars/{CODE}/availability").status == 502


def test_the_tracking_page_turns_away_whoever_lacks_the_tool(viewer):
    api, viewer_id, context = viewer
    _set(api, viewer_id, [CODE], False)
    for path in ("/tracking", "/tracking.html"):
        response = context.request.get(f"{FRONTEND_URL}{path}", max_redirects=0)
        assert response.status == 302, path
    _set(api, viewer_id, [CODE], True)
    assert context.request.get(f"{FRONTEND_URL}/tracking.html", max_redirects=0).status == 200


def _fake_availability(page) -> None:
    """The test stack has no tracking service: fake the answer that makes the radar view show the button."""
    page.route(
        f"**/api/tracking/radars/{CODE}/availability",
        lambda route: route.fulfill(
            json={"radar_code": CODE, "count": 5, "min_time": None, "max_time": None, "max_last_n": 10}
        ),
    )


def test_the_button_needs_the_tool_and_the_view(viewer):
    api, viewer_id, context = viewer
    page = context.new_page()
    _fake_availability(page)
    try:
        for views, tracking, shown in (
            ([CODE], False, False),  # the view alone is not enough
            ([], True, False),  # the tool alone does not open the radar view at all
            ([CODE], True, True),
        ):
            _set(api, viewer_id, views, tracking)
            page.goto(f"{FRONTEND_URL}/radar.html?code={CODE}", wait_until="networkidle")
            if shown:
                expect(page.locator("#btn-tracking")).to_be_visible()
            else:
                expect(page.locator("#btn-tracking")).to_be_hidden()
    finally:
        page.close()
