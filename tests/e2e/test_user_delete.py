# tests/e2e/test_user_delete.py
"""E2E: deleting users (spec G).

The general admin deletes a user from "Editar usuario" (a red button at the bottom of the form, not in the table);
a person deletes their own account from "Mi perfil"; an institution admin that is the only admin of an institution with
other users is told to name another admin first. The browser asks for a manual confirmation each time.

Every account these tests create is deleted by the test itself, and whatever is left over is deactivated at the end.
"""

import os
import time

import pytest
from playwright.sync_api import expect

from .conftest import deactivate_by_username
from .test_empresa import ORG_ADMIN, ORG_ADMIN_PASSWORD, _ensure_company, _ensure_org_admin, _login

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
ADMIN_API = f"{FRONTEND_URL}/api/v1/admin"
PASSWORD = "e2e-password-larga-1"


@pytest.fixture
def admin_api(browser, admin_storage_state):
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    yield context.request
    context.close()


@pytest.fixture
def person(admin_api):
    """A fresh viewer. The test deletes it; if it did not, it is deactivated at the end."""
    username = f"e2e-del-{int(time.time() * 1000) % 10**9}"
    created = admin_api.post(f"{ADMIN_API}/users", data={"username": username, "password": PASSWORD, "role": "viewer"})
    assert created.status == 201, created.text()
    yield username, created.json()["id"]
    deactivate_by_username(admin_api, username)


def _exists(api, username: str) -> bool:
    return any(u["username"] == username for u in api.get(f"{ADMIN_API}/users").json())


def test_the_admin_deletes_a_user_from_the_edit_form(browser, admin_storage_state, admin_api, person):
    username, user_id = person
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    page = context.new_page()
    dialogs = []
    page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.accept()))
    try:
        page.goto(f"{FRONTEND_URL}/admin#users", wait_until="networkidle")
        row = page.locator("tr", has_text=username)
        # There is no delete button in the table row: it is inside the edit form.
        expect(row.locator("[data-delete-user]")).to_have_count(0)
        row.locator(f"[data-edit-user='{user_id}']").click()
        page.click("#user-delete")
        expect(page.locator("tr", has_text=username)).to_have_count(0)
        assert dialogs and username in dialogs[0]  # the confirmation names the user
        assert not _exists(admin_api, username)
    finally:
        context.close()


def test_the_admin_does_not_get_a_delete_button_for_its_own_account(browser, admin_storage_state):
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    page = context.new_page()
    try:
        page.goto(f"{FRONTEND_URL}/admin#users", wait_until="networkidle")
        own_row = page.locator("tr", has_text=os.getenv("ADMIN_USERNAME", "admin")).first
        own_row.locator("[data-edit-user]").click()
        expect(page.locator("#form-modal-body")).to_be_visible()
        expect(page.locator("#user-delete")).to_have_count(0)
    finally:
        context.close()


def test_a_person_deletes_their_own_account_from_my_profile_and_lands_on_the_login(browser, admin_api, person):
    username, _ = person
    page = _login(browser, username, PASSWORD)
    page.on("dialog", lambda dialog: dialog.accept())  # the manual confirmation
    try:
        page.goto(f"{FRONTEND_URL}/perfil", wait_until="networkidle")
        page.click("#profile-delete")
        page.wait_for_url(lambda url: "/login" in url)
        expect(page.locator("#login-form")).to_be_visible()
        assert not _exists(admin_api, username)
    finally:
        page.close()


def test_cancelling_the_confirmation_deletes_nothing(browser, admin_api, person):
    username, _ = person
    page = _login(browser, username, PASSWORD)
    page.on("dialog", lambda dialog: dialog.dismiss())
    try:
        page.goto(f"{FRONTEND_URL}/perfil", wait_until="networkidle")
        page.click("#profile-delete")
        page.wait_for_timeout(500)
        assert "/perfil" in page.url and _exists(admin_api, username)
    finally:
        page.close()


def test_the_only_admin_of_an_institution_with_other_users_is_told_to_name_another(browser, admin_api, person):
    username, _ = person
    org_id = _ensure_company(admin_api)
    org_admin_id = _ensure_org_admin(admin_api, org_id)
    admin_api.patch(f"{ADMIN_API}/users/{_user_id(admin_api, username)}", data={"organization_id": org_id})
    page = _login(browser, ORG_ADMIN, ORG_ADMIN_PASSWORD)
    page.on("dialog", lambda dialog: dialog.accept())
    try:
        page.goto(f"{FRONTEND_URL}/empresa#perfil", wait_until="networkidle")
        page.click("#profile-delete")
        expect(page.locator("#profile-delete-error")).to_contain_text("administrador")
        assert _exists(admin_api, ORG_ADMIN)  # nothing was deleted
    finally:
        page.close()
        admin_api.patch(f"{ADMIN_API}/users/{org_admin_id}", data={"is_active": False})


def test_a_general_admin_sees_a_note_instead_of_the_delete_button_in_its_profile(browser, admin_storage_state):
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    page = context.new_page()
    try:
        page.goto(f"{FRONTEND_URL}/admin#profile", wait_until="networkidle")
        expect(page.locator("#profile-delete")).to_have_count(0)
        expect(page.locator("#profile-delete-note")).to_contain_text("administrador general")
    finally:
        context.close()


def _user_id(api, username: str) -> int:
    return next(u["id"] for u in api.get(f"{ADMIN_API}/users").json() if u["username"] == username)
