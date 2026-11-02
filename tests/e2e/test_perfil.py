# tests/e2e/test_perfil.py
"""The profile page (spec D) on the isolated test stack: a viewer reaches it from the chip, a company admin sees the
company card, and without a session the login is shown in place.

Reuses the e2e viewer and the company "E2E Empresa" with its admin (see test_empresa.py).
"""

import os
import re
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect

from .conftest import E2E_VIEWER, E2E_VIEWER_PASSWORD, deactivate_user, ensure_viewer
from .test_empresa import (
    ORG_ADMIN,
    ORG_ADMIN_PASSWORD,
    ORG_NAME,
    _ensure_company,
    _ensure_org_admin,
    _login,
)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")


@pytest.fixture
def admin_api(browser, admin_storage_state):
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    yield context.request
    context.close()


def test_a_viewer_reaches_its_profile_from_the_chip_and_changes_its_name(browser, admin_api):
    viewer_id = ensure_viewer(admin_api)
    page = _login(browser, E2E_VIEWER, E2E_VIEWER_PASSWORD)
    try:
        expect(page.locator("#profile-chip-link")).to_be_visible()
        expect(page.locator("#admin-chip-link")).to_be_hidden()
        expect(page.locator("#empresa-chip-link")).to_be_hidden()
        page.click("#profile-chip-link")
        page.wait_for_url(lambda url: urlparse(url).path == "/perfil")
        expect(page.locator("#perfil-username")).to_have_text(f"@{E2E_VIEWER}")
        expect(page.locator("#perfil-company")).to_be_hidden()  # only company admins get the company card

        page.click("#perfil-edit-name")
        page.fill("input[name=full_name]", "E2E Lector")
        page.click("#form-modal-body button[type=submit]")
        expect(page.locator("#perfil-name")).to_have_text("E2E Lector")
        expect(page.locator("#perfil-avatar")).to_have_text("EL")
    finally:
        page.close()
        deactivate_user(admin_api, viewer_id)


def test_a_name_that_is_too_long_shows_the_error_inside_the_modal(browser, admin_api):
    viewer_id = ensure_viewer(admin_api)
    page = _login(browser, E2E_VIEWER, E2E_VIEWER_PASSWORD)
    try:
        page.goto(f"{FRONTEND_URL}/perfil", wait_until="networkidle")
        page.click("#perfil-edit-name")
        # maxlength="128" stops typing at 128, so it is removed to get past it.
        page.evaluate("document.querySelector('input[name=full_name]').removeAttribute('maxlength')")
        page.fill("input[name=full_name]", "x" * 129)
        page.click("#form-modal-body button[type=submit]")
        expect(page.locator("#form-modal-body .form-error")).to_be_visible()
        expect(page.locator("#form-modal")).not_to_have_class(re.compile(r"\bhidden\b"))  # the modal stays open
    finally:
        page.close()
        deactivate_user(admin_api, viewer_id)


def test_a_company_admin_has_its_profile_inside_the_company_panel(browser, admin_api):
    org_id = _ensure_company(admin_api)
    org_admin_id = _ensure_org_admin(admin_api, org_id)
    page = _login(browser, ORG_ADMIN, ORG_ADMIN_PASSWORD)
    try:
        expect(page.locator("#empresa-chip-link")).to_be_visible()
        expect(page.locator("#profile-chip-link")).to_be_hidden()
        page.goto(f"{FRONTEND_URL}/empresa", wait_until="networkidle")
        page.click("#sidebar-nav [data-section=perfil]")
        # Same page (the panel), another section: the address keeps /empresa and gets the section in the hash.
        assert urlparse(page.url).path == "/empresa" and urlparse(page.url).fragment == "perfil"
        expect(page.locator("#perfil-username")).to_have_text(f"@{ORG_ADMIN}")
        expect(page.locator("#perfil-company")).to_be_visible()
        expect(page.locator("#perfil-company-name")).to_have_text(ORG_NAME)
        expect(page.locator("#empresa-section-usuarios")).to_be_hidden()
        # Back to the users of the company.
        page.click("#sidebar-nav [data-section=usuarios]")
        expect(page.locator("#empresa-section-usuarios")).to_be_visible()
        expect(page.locator("#perfil-content")).to_be_hidden()
    finally:
        page.close()
        deactivate_user(admin_api, org_admin_id)


def test_a_company_admin_changes_its_name_from_the_company_panel(browser, admin_api):
    org_id = _ensure_company(admin_api)
    org_admin_id = _ensure_org_admin(admin_api, org_id)
    page = _login(browser, ORG_ADMIN, ORG_ADMIN_PASSWORD)
    try:
        page.goto(f"{FRONTEND_URL}/empresa#perfil", wait_until="networkidle")
        page.click("#perfil-edit-name")
        page.fill("input[name=full_name]", "Jefa E2E")
        page.click("#form-modal-body button[type=submit]")
        expect(page.locator("#perfil-name")).to_have_text("Jefa E2E")
        expect(page.locator("#session-user")).to_have_text("Jefa E2E")
    finally:
        page.close()
        deactivate_user(admin_api, org_admin_id)


def test_the_general_admin_has_its_profile_inside_the_admin_panel(browser, admin_storage_state):
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    page = context.new_page()
    try:
        page.goto(f"{FRONTEND_URL}/admin", wait_until="networkidle")
        page.click("#sidebar-nav [data-section=profile]")
        assert urlparse(page.url).path == "/admin" and urlparse(page.url).fragment == "profile"
        expect(page.locator("#perfil-username")).to_be_visible()
        expect(page.locator("#section-title")).to_have_text("Mi perfil")
        expect(page.locator("#perfil-company")).to_have_count(0)  # the general admin has no company
        # The other sections keep working after visiting the profile.
        page.click("#sidebar-nav [data-section=users]")
        expect(page.locator("#section-title")).to_have_text("Usuarios")
    finally:
        context.close()


def test_the_profile_page_sends_admins_to_their_panels(browser, admin_storage_state, admin_api):
    # General admin: /perfil lands on the profile section of the admin panel.
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    page = context.new_page()
    try:
        page.goto(f"{FRONTEND_URL}/perfil", wait_until="networkidle")
        page.wait_for_url(lambda url: urlparse(url).path == "/admin")
        assert urlparse(page.url).fragment == "profile"
    finally:
        context.close()
    # Company admin: the same, to the company panel.
    org_id = _ensure_company(admin_api)
    org_admin_id = _ensure_org_admin(admin_api, org_id)
    page = _login(browser, ORG_ADMIN, ORG_ADMIN_PASSWORD)
    try:
        page.goto(f"{FRONTEND_URL}/perfil", wait_until="networkidle")
        page.wait_for_url(lambda url: urlparse(url).path == "/empresa")
        assert urlparse(page.url).fragment == "perfil"
    finally:
        page.close()
        deactivate_user(admin_api, org_admin_id)


def test_without_a_session_the_login_is_shown_in_place(page):
    page.goto(f"{FRONTEND_URL}/perfil", wait_until="networkidle")
    expect(page.locator("#login-form")).to_be_visible()
    assert urlparse(page.url).path == "/perfil"
