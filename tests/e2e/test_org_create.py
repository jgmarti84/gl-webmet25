# tests/e2e/test_org_create.py
"""Creating a company from the admin panel with its admin and radar views in one form (spec C, follow-up).

Companies cannot be deleted, so every test uses a company name of its own and deactivates it (and the users it made)
at the end. Runs on the isolated test stack.
"""

import os
import time

import pytest
from playwright.sync_api import expect

from .conftest import ADMIN_USERNAME, deactivate_by_username
from .test_empresa import _ensure_company

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
ADMIN_API = f"{FRONTEND_URL}/api/v1/admin"
PASSWORD = "e2e-alta-clave-larga-1"


@pytest.fixture
def panel(browser, admin_storage_state):
    """The admin panel on its companies section, plus the names this test uses (cleaned up afterwards)."""
    stamp = int(time.time() * 1000) % 10**9
    names = {"org": f"E2E Alta {stamp}", "user": f"e2e-alta-{stamp}"}
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    page = context.new_page()
    page.goto(f"{FRONTEND_URL}/admin#organizations", wait_until="networkidle")
    yield page, context.request, names
    try:
        deactivate_by_username(context.request, names["user"])
        for org in context.request.get(f"{ADMIN_API}/organizations").json():
            if org["name"] == names["org"]:
                context.request.patch(f"{ADMIN_API}/organizations/{org['id']}", data={"is_active": False})
    finally:
        context.close()


def _open_form(page, org_name: str, seats: str = "3"):
    page.click("#orgs-add")
    page.fill("input[name=name]", org_name)
    page.fill("input[name=seat_limit]", seats)


def _users(api):
    return api.get(f"{ADMIN_API}/users").json()


def test_a_company_is_created_with_a_new_admin_and_all_the_views(panel):
    page, api, names = panel
    _open_form(page, names["org"])
    # "Crear un usuario nuevo" is the option that comes selected.
    expect(page.locator("input[name=admin_mode][value=new]")).to_be_checked()
    page.fill("input[name=admin_username]", names["user"])
    page.fill("input[name=admin_password]", PASSWORD)
    page.check("input[name=all]")  # "Todas" the radars
    page.click("#form-modal-body button[type=submit]")

    row = page.locator("tr", has_text=names["org"])
    expect(row).to_contain_text("1 de 3")  # the admin took a seat
    expect(row).to_contain_text("Todas")
    created = next(u for u in _users(api) if u["username"] == names["user"])
    assert created["role"] == "org_admin" and created["organization_name"] == names["org"]


def test_a_company_is_created_without_an_admin(panel):
    page, api, names = panel
    _open_form(page, names["org"])
    page.check("input[name=admin_mode][value=none]")
    page.click("#form-modal-body button[type=submit]")
    expect(page.locator("tr", has_text=names["org"])).to_contain_text("0 de 3")


def test_an_existing_user_without_company_can_be_the_admin_and_one_with_company_is_not_offered(panel):
    page, api, names = panel
    member_name = f"{names['user']}-m"
    org_id = _ensure_company(api)  # "E2E Empresa": the member below belongs to it
    viewer = api.post(f"{ADMIN_API}/users", data={"username": names["user"], "password": PASSWORD, "role": "viewer"})
    member = api.post(
        f"{ADMIN_API}/users",
        data={"username": member_name, "password": PASSWORD, "role": "viewer", "organization_id": org_id},
    )
    assert viewer.status == 201 and member.status == 201, (viewer.text(), member.text())
    try:
        page.reload(wait_until="networkidle")
        _open_form(page, names["org"], "2")
        page.check("input[name=admin_mode][value=existing]")
        # The user is picked from a search box (typing filters the list by username, name or mail).
        search = page.locator("#org-admin-search")
        options = page.locator("#org-admin-list [role=option]")
        search.fill(names["user"])
        expect(options.filter(has_text=names["user"])).to_have_count(1)
        search.fill(member_name)
        expect(options).to_have_count(0)  # it is in another company
        search.fill(names["user"])
        options.filter(has_text=names["user"]).click()
        page.click("#form-modal-body button[type=submit]")

        expect(page.locator("tr", has_text=names["org"])).to_contain_text("1 de 2")
        promoted = next(u for u in _users(api) if u["username"] == names["user"])
        assert promoted["role"] == "org_admin" and promoted["organization_name"] == names["org"]
    finally:
        deactivate_by_username(api, member_name)  # frees the seat of "E2E Empresa"


def test_an_error_shows_inside_the_form_and_the_company_is_not_created(panel):
    page, api, names = panel
    _open_form(page, names["org"])
    page.fill("input[name=admin_username]", ADMIN_USERNAME)  # that username is taken
    page.fill("input[name=admin_password]", PASSWORD)
    page.click("#form-modal-body button[type=submit]")
    expect(page.locator("#form-modal-body .form-error")).to_be_visible()
    assert names["org"] not in [org["name"] for org in api.get(f"{ADMIN_API}/organizations").json()]
