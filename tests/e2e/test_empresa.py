# tests/e2e/test_empresa.py
"""Company admin panel (spec C, plan C-2) on the isolated test stack.

Uses the company "E2E Empresa" (created on the first run and reused: companies are never deleted) and the account
e2e-org-admin (reactivated each run). Users it creates are deactivated at the end, which frees their seats.
"""

import os
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect

from .conftest import E2E_VIEWER, E2E_VIEWER_PASSWORD, deactivate_by_username, deactivate_user, ensure_viewer

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
ADMIN_API = f"{FRONTEND_URL}/api/v1/admin"
ORG_NAME = "E2E Empresa"
ORG_ADMIN = "e2e-org-admin"
ORG_ADMIN_PASSWORD = "e2e-org-admin-password-1"
NEW_MEMBER = "e2e-org-member"


def _ensure_company(api) -> int:
    orgs = api.get(f"{ADMIN_API}/organizations").json()
    found = next((o for o in orgs if o["name"] == ORG_NAME), None)
    if found:
        api.patch(f"{ADMIN_API}/organizations/{found['id']}", data={"is_active": True, "seat_limit": 3})
        return found["id"]
    created = api.post(f"{ADMIN_API}/organizations", data={"name": ORG_NAME, "seat_limit": 3})
    assert created.status == 201, created.text()
    return created.json()["id"]


def _ensure_org_admin(api, org_id: int) -> int:
    users = api.get(f"{ADMIN_API}/users").json()
    found = next((u for u in users if u["username"] == ORG_ADMIN), None)
    if found is None:
        body = {"username": ORG_ADMIN, "password": ORG_ADMIN_PASSWORD, "role": "org_admin", "organization_id": org_id}
        created = api.post(f"{ADMIN_API}/users", data=body)
        assert created.status == 201, created.text()
        return created.json()["id"]
    api.patch(f"{ADMIN_API}/users/{found['id']}", data={"is_active": True})
    api.post(f"{ADMIN_API}/users/{found['id']}/reset-password", data={"password": ORG_ADMIN_PASSWORD})
    return found["id"]


def _login(browser, username: str, password: str):
    page = browser.new_page(ignore_https_errors=True)
    page.goto(f"{FRONTEND_URL}/login", wait_until="networkidle")
    page.fill("#login-username", username)
    page.fill("#login-password", password)
    page.click("#login-submit")
    page.wait_for_url(lambda url: "/login" not in url)
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def admin_api(browser, admin_storage_state):
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    yield context.request
    context.close()


def test_company_admin_sees_its_panel_and_adds_a_user(browser, admin_api):
    org_id = _ensure_company(admin_api)
    org_admin_id = _ensure_org_admin(admin_api, org_id)
    deactivate_by_username(admin_api, NEW_MEMBER)  # leftover of an interrupted run
    page = _login(browser, ORG_ADMIN, ORG_ADMIN_PASSWORD)
    try:
        expect(page.locator("#empresa-chip-link")).to_be_visible()
        page.goto(f"{FRONTEND_URL}/empresa", wait_until="networkidle")
        expect(page.locator("#empresa-name")).to_have_text(ORG_NAME)
        expect(page.locator("#empresa-seats")).to_contain_text("de 3 lugares")
        page.click("#empresa-add")
        page.fill("input[name=username]", NEW_MEMBER)
        page.fill("input[name=password]", "e2e-org-member-password-1")
        page.click("#form-modal-body button[type=submit]")
        expect(page.locator("#empresa-users")).to_contain_text(NEW_MEMBER)
    finally:
        page.close()
        deactivate_by_username(admin_api, NEW_MEMBER)
        deactivate_user(admin_api, org_admin_id)


def test_a_viewer_is_sent_from_empresa_to_the_map(browser, admin_api):
    viewer_id = ensure_viewer(admin_api)
    page = _login(browser, E2E_VIEWER, E2E_VIEWER_PASSWORD)
    try:
        page.goto(f"{FRONTEND_URL}/empresa", wait_until="networkidle")
        assert urlparse(page.url).path == "/"
    finally:
        page.close()
        deactivate_user(admin_api, viewer_id)
