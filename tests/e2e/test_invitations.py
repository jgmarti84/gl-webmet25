# tests/e2e/test_invitations.py
"""E2E: invitations by mail (spec E). The mails are read from Mailpit, the links are opened in a real browser.

Flows: the general admin invites a company admin and the person fills the form; a company admin invites a viewer
from its panel and cancels another invitation; a link that does not work says so; the admin panel lists the pending
invitations and cancels one.

nginx limits the public endpoints to 10 requests/minute per IP (burst 5), like the registration ones, so the tests of
this file keep apart from each other (see PACE_S). Every account the tests create is deactivated at the end and every
invitation left pending is cancelled.
"""

import os
import re
import time
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, expect

from .conftest import deactivate_by_username, mailpit_clear, mailpit_message
from .test_empresa import ORG_ADMIN, ORG_ADMIN_PASSWORD, ORG_NAME, _ensure_company, _ensure_org_admin, _login

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
ADMIN_API = f"{FRONTEND_URL}/api/v1/admin"
INVITE_ORG = "E2E Invitaciones"
PASSWORD = "e2e-password-larga-1"
DOMAIN = "ejemplo.com.ar"

# Seconds between the end of a test and the start of the next one (the limit refills one request every 6 s).
PACE_S = 12
_last_test_end = [0.0]


@pytest.fixture(autouse=True)
def _pace():
    wait = PACE_S - (time.time() - _last_test_end[0])
    if wait > 0 and _last_test_end[0]:
        time.sleep(wait)
    yield
    _last_test_end[0] = time.time()


@pytest.fixture
def admin_api(browser, admin_storage_state):
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    yield context.request
    context.close()


@pytest.fixture
def person(admin_api):
    """A fresh username and mail. Whatever the test leaves behind (the account, a pending invitation) is removed."""
    stamp = int(time.time() * 1000) % 10**9
    username, email = f"e2e-inv-{stamp}", f"e2e-inv-{stamp}@{DOMAIN}"
    mailpit_clear()
    yield username, email
    deactivate_by_username(admin_api, username)
    for item in admin_api.get(f"{ADMIN_API}/invitations").json():
        if item["email"] == email:
            admin_api.post(f"{ADMIN_API}/invitations/{item['id']}/cancel")


def _invite_company(api) -> int:
    """The company the general admin invites into: created or reactivated, with room for the invited person."""
    found = next((o for o in api.get(f"{ADMIN_API}/organizations").json() if o["name"] == INVITE_ORG), None)
    if found:
        api.patch(f"{ADMIN_API}/organizations/{found['id']}", data={"is_active": True, "seat_limit": 5})
        return found["id"]
    created = api.post(f"{ADMIN_API}/organizations", data={"name": INVITE_ORG, "seat_limit": 5})
    assert created.status == 201, created.text()
    return created.json()["id"]


def _invitation_link(email: str) -> str:
    """The /invitacion link of the mail, re-based on FRONTEND_URL (the mail carries PUBLIC_BASE_URL)."""
    message = mailpit_message(email, "Te invitaron a")
    match = re.search(r"https?://[^\s\"<>]+?(/invitacion#token=[A-Za-z0-9_-]{43})", message["Text"])
    assert match, message["Text"]
    return f"{FRONTEND_URL}{match.group(1)}"


def _fill_and_submit(page: Page, username: str) -> None:
    page.fill("#invitation-form input[name=username]", username)
    page.fill("#invitation-form input[name=full_name]", "Persona E2E")
    page.fill("#invitation-form input[name=password]", PASSWORD)
    page.fill("#invitation-form input[name=repeat]", PASSWORD)
    terms = page.locator("#invitation-form input[name=accept_terms]")
    if terms.count() and terms.is_visible():
        terms.check()
    page.click("#invitation-submit")


def test_a_company_admin_accepts_the_invitation_and_lands_in_its_panel(browser, admin_api, person):
    username, email = person
    org_id = _invite_company(admin_api)
    created = admin_api.post(
        f"{ADMIN_API}/invitations", data={"email": email, "organization_id": org_id, "role": "org_admin"}
    )
    assert created.status == 201, created.text()
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    try:
        page.goto(_invitation_link(email), wait_until="networkidle")
        expect(page.locator("#invitation-company")).to_contain_text(INVITE_ORG)
        expect(page.locator("#invitation-email")).to_contain_text(email)
        assert "token=" not in page.url  # the token is taken out of the address bar
        _fill_and_submit(page, username)
        page.wait_for_url(lambda url: urlparse(url).path.rstrip("/").endswith("/empresa"))
        expect(page.locator("#empresa-name")).to_have_text(INVITE_ORG)
    finally:
        context.close()


def test_a_link_that_does_not_work_says_so_and_shows_no_form(page: Page):
    page.goto(f"{FRONTEND_URL}/invitacion#token={'A' * 43}", wait_until="networkidle")
    expect(page.locator("#invitation-invalid")).to_be_visible()
    expect(page.locator("#invitation-form")).to_have_count(0)


def test_the_company_admin_invites_a_viewer_from_its_panel_and_cancels_another(browser, admin_api, person):
    username, email = person
    # Not built from `email`: Mailpit matches "to:" by substring and would find the wrong mail.
    other = f"e2e-cancel-{username[-9:]}@{DOMAIN}"
    org_id = _ensure_company(admin_api)
    org_admin_id = _ensure_org_admin(admin_api, org_id)
    page = _login(browser, ORG_ADMIN, ORG_ADMIN_PASSWORD)
    page.on("dialog", lambda dialog: dialog.accept())  # Cancelar may ask "¿Seguro?"
    try:
        page.goto(f"{FRONTEND_URL}/empresa", wait_until="networkidle")
        for address in (email, other):
            page.click("#empresa-add")
            page.check("#form-modal-body input[name=create_mode][value=invite]")
            page.fill("#form-modal-body input[name=invite_email]", address)
            page.click("#form-modal-body button[type=submit]")
            expect(page.locator("#empresa-invitations")).to_contain_text(address)
        row = page.locator("#empresa-invitations tr", has_text=other)
        row.locator("[data-cancel-invitation]").click()
        expect(page.locator("#empresa-invitations")).not_to_contain_text(other)
        expect(page.locator("#empresa-invitations")).to_contain_text(email)

        context = browser.new_context(ignore_https_errors=True)
        invited = context.new_page()
        try:
            invited.goto(_invitation_link(email), wait_until="networkidle")
            expect(invited.locator("#invitation-company")).to_contain_text(ORG_NAME)
            _fill_and_submit(invited, username)
            invited.wait_for_url(lambda url: urlparse(url).path in ("/", ""))  # a viewer lands on the map
        finally:
            context.close()
    finally:
        page.close()
        deactivate_by_username(admin_api, username)
        deactivate_by_username(admin_api, ORG_ADMIN)
        admin_api.patch(f"{ADMIN_API}/users/{org_admin_id}", data={"is_active": False})


def test_the_admin_panel_lists_the_pending_invitations_and_cancels_one(browser, admin_storage_state, admin_api, person):
    _, email = person
    org_id = _invite_company(admin_api)
    created = admin_api.post(
        f"{ADMIN_API}/invitations", data={"email": email, "organization_id": org_id, "role": "org_admin"}
    )
    assert created.status == 201, created.text()
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    page = context.new_page()
    page.on("dialog", lambda dialog: dialog.accept())  # Cancelar may ask "¿Seguro?"
    try:
        page.goto(f"{FRONTEND_URL}/admin#invitations", wait_until="networkidle")
        row = page.locator("tr", has_text=email)
        expect(row).to_contain_text(INVITE_ORG)
        row.locator("[data-cancel-invitation]").click()
        expect(page.locator("tr", has_text=email)).to_have_count(0)
    finally:
        context.close()
