# tests/e2e/test_mail_templates.py
"""E2E: the general admin edits the text of a mail from the admin panel (spec F).

The section "Textos de los mails" lists the four mails; picking one shows its fields, the markers that can be
inserted and a preview. The flows: open it, change the subject and see it in the preview, save, reload and find it
saved, then restore the original. The e2e stack is isolated, and the test restores the mail at the end whatever
happens.
"""

import os

import pytest
from playwright.sync_api import Page, expect

from .conftest import answer_confirmation, open_nav_group

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
API = f"{FRONTEND_URL}/api/v1/admin/mail-templates"
KEY = "verify_email"
NEW_SUBJECT = "Asunto de prueba e2e {usuario}"


@pytest.fixture
def browser_context_args(browser_context_args, admin_storage_state):
    """Start already logged in as the general admin (one shared login, see conftest)."""
    return {**browser_context_args, "storage_state": admin_storage_state}


@pytest.fixture
def restore_at_the_end(browser, admin_storage_state):
    """Whatever the test does, the mail goes back to its original text."""
    yield
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    try:
        context.request.delete(f"{API}/{KEY}")
    finally:
        context.close()


def _open(page: Page) -> None:
    page.goto(f"{FRONTEND_URL}/admin#mails", wait_until="networkidle")
    expect(page.locator("#mail-list")).to_be_visible()


def _pick(page: Page, key: str) -> None:
    page.click(f"#mail-list [data-mail-key={key}]")
    expect(page.locator("#mail-form input[name=subject]")).to_be_visible()


def test_the_section_lists_the_four_mails(page: Page):
    _open(page)
    expect(page.locator("#mail-list [data-mail-key]")).to_have_count(4)
    open_nav_group(page, "mails")
    expect(page.locator("#sidebar-nav [data-section=mails]")).to_be_visible()


def test_a_change_shows_in_the_preview_is_saved_and_can_be_restored(page: Page, restore_at_the_end):
    _open(page)
    _pick(page, KEY)
    original = page.locator("#mail-form input[name=subject]").input_value()

    page.fill("#mail-form input[name=subject]", NEW_SUBJECT)
    expect(page.locator("#mail-preview-subject")).to_contain_text("Asunto de prueba e2e ana.perez")  # example data

    page.click("#mail-save")
    expect(page.locator("#mail-list [data-mail-key=verify_email]")).to_contain_text("personalizado")

    page.reload(wait_until="networkidle")
    _pick(page, KEY)
    expect(page.locator("#mail-form input[name=subject]")).to_have_value(NEW_SUBJECT)

    page.click("#mail-restore")
    answer_confirmation(page)  # "Restaurar" asks for confirmation
    expect(page.locator("#mail-form input[name=subject]")).to_have_value(original)
    expect(page.locator("#mail-list [data-mail-key=verify_email]")).not_to_contain_text("personalizado")


def test_a_marker_the_mail_does_not_have_is_refused_with_a_message(page: Page, restore_at_the_end):
    _open(page)
    _pick(page, KEY)
    page.fill("#mail-form textarea[name=body]", "Hola {no_existe}")
    page.click("#mail-save")
    expect(page.locator("#mail-error")).to_contain_text("no_existe")
    expect(page.locator("#mail-list [data-mail-key=verify_email]")).not_to_contain_text("personalizado")


def test_a_marker_button_inserts_the_marker_in_the_focused_field(page: Page):
    _open(page)
    _pick(page, KEY)
    page.fill("#mail-form textarea[name=body]", "")
    page.click("#mail-form textarea[name=body]")
    page.click("#mail-placeholders [data-placeholder=usuario]")
    expect(page.locator("#mail-form textarea[name=body]")).to_have_value("{usuario}")


def test_the_preview_is_an_iframe_with_no_permissions(page: Page):
    _open(page)
    _pick(page, KEY)
    frame = page.locator("#mail-preview")
    expect(frame).to_be_visible()
    # sandbox="" is the strictest: no scripts, no same origin, no forms, no navigation.
    assert frame.get_attribute("sandbox") == ""
