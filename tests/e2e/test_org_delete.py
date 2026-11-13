# tests/e2e/test_org_delete.py
"""E2E: the general admin deletes institutions from the admin panel.

An institution without users is deleted after a browser confirmation. One with users opens a window with two options:
free all its users (they stay as readers with no institution) or delete them too (the button stays disabled until the
name of the institution is typed). Runs on the isolated test stack.

Every test creates the institution and the users it needs, with names of its own, and whatever is left over is
cleaned up at the end (users deactivated, the institution deleted or deactivated).
"""

import os
import time

import pytest
from playwright.sync_api import expect

from .conftest import deactivate_by_username

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
ADMIN_API = f"{FRONTEND_URL}/api/v1/admin"
PASSWORD = "e2e-borrar-clave-larga-1"


@pytest.fixture
def scene(browser, admin_storage_state):
    """The admin panel on its institutions section, the API of the same admin, and a factory of institutions."""
    stamp = int(time.time() * 1000) % 10**9
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    page = context.new_page()
    api = context.request
    created = {"orgs": [], "users": []}

    def make_org(suffix: str, with_users: bool = False) -> dict:
        name = f"E2E Borrar {suffix} {stamp}"
        org = api.post(f"{ADMIN_API}/organizations", data={"name": name, "seat_limit": 5})
        assert org.status == 201, org.text()
        org_id = org.json()["id"]
        created["orgs"].append(org_id)
        users = {}
        if with_users:
            # A reader can only join an institution that has an active admin, so the admin goes first.
            for label, role in (("jefe", "org_admin"), ("lector", "viewer")):
                username = f"e2e-borrar-{label}-{stamp}"
                body = {"username": username, "password": PASSWORD, "role": role, "organization_id": org_id}
                response = api.post(f"{ADMIN_API}/users", data=body)
                assert response.status == 201, response.text()
                created["users"].append(username)
                users[label] = {"username": username, "id": response.json()["id"]}
        return {"id": org_id, "name": name, "users": users}

    def open_panel():
        page.goto(f"{FRONTEND_URL}/admin#organizations", wait_until="networkidle")

    yield page, api, make_org, open_panel
    try:
        for username in created["users"]:
            deactivate_by_username(api, username)
        for org_id in created["orgs"]:
            if api.delete(f"{ADMIN_API}/organizations/{org_id}?users=unlink").status == 404:
                continue  # the test deleted it
    finally:
        context.close()


def _org_names(api) -> list:
    return [org["name"] for org in api.get(f"{ADMIN_API}/organizations").json()]


def _user(api, username: str):
    return next((u for u in api.get(f"{ADMIN_API}/users").json() if u["username"] == username), None)


def test_an_empty_institution_is_deleted_after_the_confirmation(scene):
    page, api, make_org, open_panel = scene
    org = make_org("vacia")
    dialogs = []
    page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.accept()))
    open_panel()
    page.locator("tr", has_text=org["name"]).locator(f"[data-delete-org='{org['id']}']").click()
    expect(page.locator("tr", has_text=org["name"])).to_have_count(0)
    assert dialogs and org["name"] in dialogs[0]  # the confirmation names the institution
    assert org["name"] not in _org_names(api)


def test_cancelling_the_confirmation_keeps_the_institution(scene):
    page, api, make_org, open_panel = scene
    org = make_org("conserva")
    page.on("dialog", lambda dialog: dialog.dismiss())
    open_panel()
    page.locator("tr", has_text=org["name"]).locator(f"[data-delete-org='{org['id']}']").click()
    page.wait_for_timeout(500)
    expect(page.locator("tr", has_text=org["name"])).to_have_count(1)
    assert org["name"] in _org_names(api)


def test_an_institution_with_users_opens_a_window_with_the_two_options(scene):
    page, api, make_org, open_panel = scene
    org = make_org("con-gente", with_users=True)
    page.on("dialog", lambda dialog: pytest.fail("a window with options was expected, not a confirmation"))
    open_panel()
    page.locator("tr", has_text=org["name"]).locator(f"[data-delete-org='{org['id']}']").click()
    body = page.locator("#form-modal-body")
    expect(body).to_be_visible()
    expect(body).to_contain_text(org["name"])
    expect(body).to_contain_text("2 usuarios")
    expect(page.locator("input[name=users_action][value=unlink]")).to_be_checked()  # the harmless option is the default
    expect(page.locator("input[name=users_action][value=delete]")).not_to_be_checked()
    expect(page.locator("#org-delete-confirm")).to_be_hidden()
    assert org["name"] in _org_names(api)  # nothing was deleted by opening the window


def test_unlinking_frees_the_users_and_deletes_the_institution(scene):
    page, api, make_org, open_panel = scene
    org = make_org("desvincula", with_users=True)
    open_panel()
    page.locator("tr", has_text=org["name"]).locator(f"[data-delete-org='{org['id']}']").click()
    page.check("input[name=users_action][value=unlink]")
    page.click("#form-modal-body button[type=submit]")
    expect(page.locator("tr", has_text=org["name"])).to_have_count(0)
    assert org["name"] not in _org_names(api)
    jefe = _user(api, org["users"]["jefe"]["username"])
    lector = _user(api, org["users"]["lector"]["username"])
    assert jefe["organization_id"] is None and jefe["role"] == "viewer" and jefe["is_active"]
    assert lector["organization_id"] is None and lector["role"] == "viewer" and lector["is_active"]


def test_deleting_the_users_too_needs_the_name_of_the_institution(scene):
    page, api, make_org, open_panel = scene
    org = make_org("borra-todo", with_users=True)
    open_panel()
    page.locator("tr", has_text=org["name"]).locator(f"[data-delete-org='{org['id']}']").click()
    page.check("input[name=users_action][value=delete]")
    confirm = page.locator("#org-delete-confirm")
    submit = page.locator("#form-modal-body button[type=submit]")
    expect(confirm).to_be_visible()
    expect(submit).to_be_disabled()
    confirm.fill("otro nombre")
    expect(submit).to_be_disabled()
    confirm.fill(org["name"])
    expect(submit).to_be_enabled()
    submit.click()
    expect(page.locator("tr", has_text=org["name"])).to_have_count(0)
    assert org["name"] not in _org_names(api)
    assert _user(api, org["users"]["jefe"]["username"]) is None
    assert _user(api, org["users"]["lector"]["username"]) is None


def test_going_back_to_unlinking_enables_the_button_again(scene):
    page, api, make_org, open_panel = scene
    org = make_org("se-arrepiente", with_users=True)
    open_panel()
    page.locator("tr", has_text=org["name"]).locator(f"[data-delete-org='{org['id']}']").click()
    page.check("input[name=users_action][value=delete]")
    expect(page.locator("#form-modal-body button[type=submit]")).to_be_disabled()
    page.check("input[name=users_action][value=unlink]")
    expect(page.locator("#org-delete-confirm")).to_be_hidden()
    expect(page.locator("#form-modal-body button[type=submit]")).to_be_enabled()
