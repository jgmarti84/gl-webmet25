# tests/e2e/test_org_edit_members.py
"""Adding one person to a company that already exists, from the "Editar institución" form of the admin panel.

The form has an optional block "Agregar gente a esta institución" with four options (none, invite by mail, new user,
existing user) and a role (admin of the company or reader). On save the company data is saved first and then the
person is added, so the seats can be raised and someone added in the same form.

Companies cannot be deleted, so every test makes a company of its own through the API and deactivates it (and the
users and invitations it made) at the end. Runs on the isolated test stack.
"""

import os
import time

import pytest
from playwright.sync_api import expect

from .conftest import deactivate_by_username

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
ADMIN_API = f"{FRONTEND_URL}/api/v1/admin"
PASSWORD = "e2e-alta-clave-larga-1"
SUBMIT = "#form-modal-body button[type=submit]"


@pytest.fixture
def panel(browser, admin_storage_state):
    """The admin panel on its companies section, an API client and the names this test uses (all cleaned up)."""
    stamp = int(time.time() * 1000) % 10**9
    names = {
        "org": f"E2E Gente {stamp}",
        "admin": f"e2e-gente-a-{stamp}",
        "viewer": f"e2e-gente-v-{stamp}",
        "loose": f"e2e-gente-s-{stamp}",
        "mail": f"e2e-gente-{stamp}@ejemplo.com.ar",
    }
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    page = context.new_page()
    api = context.request
    yield page, api, names
    try:
        for invitation in api.get(f"{ADMIN_API}/invitations").json():
            if invitation["email"] == names["mail"]:
                api.post(f"{ADMIN_API}/invitations/{invitation['id']}/cancel")
        for key in ("admin", "viewer", "loose"):
            deactivate_by_username(api, names[key])
        for org in api.get(f"{ADMIN_API}/organizations").json():
            if org["name"].startswith(names["org"]):
                api.patch(f"{ADMIN_API}/organizations/{org['id']}", data={"is_active": False})
    finally:
        context.close()


def _make_org(api, names, seats: int, with_admin: bool = True) -> int:
    """A company of this test, optionally with an admin that takes the first seat."""
    created = api.post(f"{ADMIN_API}/organizations", data={"name": names["org"], "seat_limit": seats})
    assert created.status == 201, created.text()
    org_id = created.json()["id"]
    if with_admin:
        body = {"username": names["admin"], "password": PASSWORD, "role": "org_admin", "organization_id": org_id}
        admin = api.post(f"{ADMIN_API}/users", data=body)
        assert admin.status == 201, admin.text()
    return org_id


def _open_edit(page, org_id: int):
    page.goto(f"{FRONTEND_URL}/admin#organizations", wait_until="networkidle")
    page.click(f"[data-edit-org='{org_id}']")


def _users(api):
    return api.get(f"{ADMIN_API}/users").json()


def _user(api, username: str):
    return next((u for u in _users(api) if u["username"] == username), None)


def _choose(page, mode: str, role: str):
    page.check(f"input[name=member_mode][value={mode}]")
    page.select_option("select[name=member_role]", role)


def test_the_edit_form_offers_the_block_with_none_selected_and_the_create_form_does_not(panel):
    page, api, names = panel
    org_id = _make_org(api, names, 3)
    _open_edit(page, org_id)
    expect(page.locator("input[name=member_mode][value=none]")).to_be_checked()
    for mode in ("invite", "new", "existing"):
        expect(page.locator(f"input[name=member_mode][value={mode}]")).to_have_count(1)
    expect(page.locator("select[name=member_role] option")).to_have_count(2)
    page.click("#close-form-modal")
    page.click("#orgs-add")
    expect(page.locator("input[name=member_mode]")).to_have_count(0)  # creating has its own admin block


def test_saving_with_none_selected_only_edits_the_company(panel):
    page, api, names = panel
    org_id = _make_org(api, names, 3)
    _open_edit(page, org_id)
    page.fill("input[name=seat_limit]", "4")
    page.click(SUBMIT)
    expect(page.locator("tr", has_text=names["org"])).to_contain_text("1 de 4")
    members = [u for u in _users(api) if u["organization_id"] == org_id]
    assert [u["username"] for u in members] == [names["admin"]]  # nobody was added


def test_a_person_is_invited_by_mail_as_company_admin(panel):
    page, api, names = panel
    org_id = _make_org(api, names, 3)
    _open_edit(page, org_id)
    _choose(page, "invite", "org_admin")
    page.fill("input[name=member_invite_email]", names["mail"])
    page.click(SUBMIT)

    expect(page.locator("tr", has_text=names["org"])).to_contain_text("(+1 invitación)")
    sent = [i for i in api.get(f"{ADMIN_API}/invitations").json() if i["email"] == names["mail"]]
    assert len(sent) == 1 and sent[0]["role"] == "org_admin" and sent[0]["organization_id"] == org_id


def test_a_reader_is_invited_by_mail(panel):
    page, api, names = panel
    org_id = _make_org(api, names, 3)
    _open_edit(page, org_id)
    _choose(page, "invite", "viewer")
    page.fill("input[name=member_invite_email]", names["mail"])
    page.click(SUBMIT)

    expect(page.locator("tr", has_text=names["org"])).to_contain_text("(+1 invitación)")
    sent = [i for i in api.get(f"{ADMIN_API}/invitations").json() if i["email"] == names["mail"]]
    assert len(sent) == 1 and sent[0]["role"] == "viewer"


def test_a_new_user_is_created_as_reader_and_takes_a_seat(panel):
    page, api, names = panel
    org_id = _make_org(api, names, 3)
    _open_edit(page, org_id)
    _choose(page, "new", "viewer")
    page.fill("input[name=member_username]", names["viewer"])
    page.fill("input[name=member_password]", PASSWORD)
    page.click(SUBMIT)

    expect(page.locator("tr", has_text=names["org"])).to_contain_text("2 de 3")
    created = _user(api, names["viewer"])
    assert created["role"] == "viewer" and created["organization_id"] == org_id


def test_a_new_user_is_created_as_company_admin(panel):
    page, api, names = panel
    org_id = _make_org(api, names, 3, with_admin=False)
    _open_edit(page, org_id)
    _choose(page, "new", "org_admin")
    page.fill("input[name=member_username]", names["admin"])
    page.fill("input[name=member_password]", PASSWORD)
    page.click(SUBMIT)

    expect(page.locator("tr", has_text=names["org"])).to_contain_text("1 de 3")
    created = _user(api, names["admin"])
    assert created["role"] == "org_admin" and created["organization_id"] == org_id


def test_a_loose_user_is_picked_and_moved_in_as_company_admin(panel):
    page, api, names = panel
    org_id = _make_org(api, names, 4)
    made = api.post(f"{ADMIN_API}/users", data={"username": names["loose"], "password": PASSWORD, "role": "viewer"})
    assert made.status == 201, made.text()

    _open_edit(page, org_id)
    _choose(page, "existing", "org_admin")
    search = page.locator("#member-search")
    options = page.locator("#member-list [role=option]")
    search.fill(names["loose"])
    expect(options.filter(has_text=names["loose"])).to_have_count(1)
    options.filter(has_text=names["loose"]).click()
    page.click(SUBMIT)

    expect(page.locator("tr", has_text=names["org"])).to_contain_text("2 de 4")
    moved = _user(api, names["loose"])
    assert moved["organization_id"] == org_id and moved["role"] == "org_admin"


def test_users_that_already_have_a_company_are_not_offered(panel):
    page, api, names = panel
    org_id = _make_org(api, names, 3)
    _open_edit(page, org_id)
    page.check("input[name=member_mode][value=existing]")
    page.locator("#member-search").fill(names["admin"])  # the admin of this very company
    expect(page.locator("#member-list [role=option]")).to_have_count(0)


def test_raising_the_seats_and_adding_someone_in_the_same_save(panel):
    page, api, names = panel
    org_id = _make_org(api, names, 1)  # full: the admin takes the only seat
    _open_edit(page, org_id)
    page.fill("input[name=seat_limit]", "2")
    _choose(page, "new", "viewer")
    page.fill("input[name=member_username]", names["viewer"])
    page.fill("input[name=member_password]", PASSWORD)
    page.click(SUBMIT)

    expect(page.locator("tr", has_text=names["org"])).to_contain_text("2 de 2")
    assert _user(api, names["viewer"])["organization_id"] == org_id


def test_a_full_company_shows_the_error_and_keeps_what_was_saved_first(panel):
    page, api, names = panel
    org_id = _make_org(api, names, 1)  # full
    _open_edit(page, org_id)
    page.fill("input[name=name]", f"{names['org']} nuevo")  # saved before the person is added
    _choose(page, "new", "viewer")
    page.fill("input[name=member_username]", names["viewer"])
    page.fill("input[name=member_password]", PASSWORD)
    page.click(SUBMIT)

    expect(page.locator("#form-modal-body .form-error")).to_contain_text("lugares")
    assert _user(api, names["viewer"]) is None
    saved = next(o for o in api.get(f"{ADMIN_API}/organizations").json() if o["id"] == org_id)
    assert saved["name"] == f"{names['org']} nuevo"


def test_a_reader_cannot_join_a_company_without_an_admin(panel):
    page, api, names = panel
    org_id = _make_org(api, names, 3, with_admin=False)
    _open_edit(page, org_id)
    _choose(page, "new", "viewer")
    page.fill("input[name=member_username]", names["viewer"])
    page.fill("input[name=member_password]", PASSWORD)
    page.click(SUBMIT)

    expect(page.locator("#form-modal-body .form-error")).to_contain_text("administrador")
    assert _user(api, names["viewer"]) is None


def test_choosing_an_option_without_its_data_is_an_error_and_adds_nobody(panel):
    page, api, names = panel
    org_id = _make_org(api, names, 3)
    _open_edit(page, org_id)
    _choose(page, "invite", "viewer")  # no mail typed
    page.click(SUBMIT)
    expect(page.locator("#form-modal-body .form-error")).to_be_visible()
    assert not [i for i in api.get(f"{ADMIN_API}/invitations").json() if i["email"] == names["mail"]]
