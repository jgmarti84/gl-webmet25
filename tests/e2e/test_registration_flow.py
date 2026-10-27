# tests/e2e/test_registration_flow.py
"""E2E: sign up, verify the mail, log in with the mail, recover the password. The mails are read from Mailpit.

nginx limits these endpoints to 10 requests/minute per IP (burst 5). The tests of this file make 13 such requests,
so run back to back they would use up the burst and get a 429: _pace() keeps them apart (see PACE_S).
Every test account is deactivated at the end.
"""

import os
import time

import pytest
from playwright.sync_api import Page, expect

from .conftest import deactivate_by_username, link_in, mailpit_clear, mailpit_message

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
PASSWORD = "e2e-password-larga-1"
NEW_PASSWORD = "e2e-otra-password-larga-2"
DOMAIN = "ejemplo.com.ar"

# Minimum seconds between the end of a test and the start of the next one. A test makes up to 4 requests to the
# rate-limited endpoints and the limit refills one request every 6 s, so this keeps the burst from running out.
PACE_S = 12
_last_test_end = [0.0]


@pytest.fixture(autouse=True)
def _pace():
    """Wait, only as long as needed, so the previous test's requests have been refilled."""
    wait = PACE_S - (time.time() - _last_test_end[0])
    if wait > 0 and _last_test_end[0]:
        time.sleep(wait)
    yield
    _last_test_end[0] = time.time()


@pytest.fixture
def account(browser, admin_storage_state):
    """A fresh username and mail; the account is deactivated afterwards."""
    username = f"e2e-reg-{int(time.time() * 1000) % 10**9}"
    mailpit_clear()
    yield username, f"{username}@{DOMAIN}"
    admin = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    try:
        deactivate_by_username(admin.request, username)
    finally:
        admin.close()


def _sign_up(page: Page, username: str, email: str, password: str = PASSWORD, full_name: str = "") -> None:
    page.goto(f"{FRONTEND_URL}/register", wait_until="networkidle")
    page.fill("#reg-username", username)
    page.fill("#reg-email", email)
    if full_name:
        page.fill("#reg-fullname", full_name)  # optional field: most tests leave it empty
    page.fill("#reg-password", password)
    page.fill("#reg-repeat", password)
    page.check("#reg-terms")
    page.click("#register-submit")
    expect(page.locator("#register-done")).to_be_visible()


def _verify(page: Page, email: str) -> None:
    page.goto(link_in(mailpit_message(email, "Verificá tu mail")), wait_until="networkidle")
    expect(page.locator("#verify-ok")).to_be_visible()


def _log_in(page: Page, identifier: str, password: str) -> None:
    page.goto(f"{FRONTEND_URL}/login", wait_until="networkidle")
    page.fill("#login-username", identifier)
    page.fill("#login-password", password)
    page.click("#login-submit")


def test_sign_up_verify_and_log_in_with_the_mail(page: Page, account):
    username, email = account
    _sign_up(page, username, email, full_name="Ana Pérez E2E")
    expect(page.locator("#register-done-text")).to_contain_text(email)
    _verify(page, email)
    _log_in(page, email, PASSWORD)
    page.wait_for_selector("#radar-list", state="attached")
    page.click("#btn-account")
    expect(page.locator("#account-role")).to_have_text("Lector")
    # The optional full name typed at sign-up is what the account panel shows.
    expect(page.locator("#account-name")).to_have_text("Ana Pérez E2E")


def test_an_unverified_account_cannot_log_in_and_can_ask_for_a_new_mail(page: Page, account):
    username, email = account
    _sign_up(page, username, email)
    _log_in(page, username, PASSWORD)
    expect(page.locator("#login-error")).to_contain_text("verificado")
    expect(page.locator("#login-resend")).to_be_visible()
    mailpit_clear()
    page.click("#login-resend")
    expect(page.locator("#login-info")).to_be_visible()
    _verify(page, email)  # the new mail works
    _log_in(page, username, PASSWORD)
    page.wait_for_selector("#radar-list", state="attached")


def test_password_recovery(page: Page, account):
    username, email = account
    _sign_up(page, username, email)
    _verify(page, email)
    mailpit_clear()
    page.goto(f"{FRONTEND_URL}/forgot", wait_until="networkidle")
    page.fill("#forgot-email", email)
    page.click("#forgot-submit")
    expect(page.locator("#forgot-done")).to_be_visible()
    page.goto(link_in(mailpit_message(email, "Recuperá tu contraseña")), wait_until="networkidle")
    page.fill("#reset-password", NEW_PASSWORD)
    page.fill("#reset-repeat", NEW_PASSWORD)
    page.click("#reset-submit")
    expect(page.locator("#reset-ok")).to_be_visible()
    _log_in(page, username, NEW_PASSWORD)
    page.wait_for_selector("#radar-list", state="attached")


def test_the_form_checks_the_passwords_before_sending(page: Page, account):
    username, email = account
    page.goto(f"{FRONTEND_URL}/register", wait_until="networkidle")
    page.fill("#reg-username", username)
    page.fill("#reg-email", email)
    page.fill("#reg-password", PASSWORD)
    page.fill("#reg-repeat", PASSWORD + "x")
    page.check("#reg-terms")
    page.click("#register-submit")
    expect(page.locator("#register-error")).to_contain_text("no coinciden")
    expect(page.locator("#register-done")).to_be_hidden()


def test_a_registered_mail_gets_the_same_screen(page: Page, account):
    username, email = account
    _sign_up(page, username, email)
    _verify(page, email)
    _sign_up(page, f"{username}-b", email)  # same mail, other username: same "Revisá tu mail" screen
    expect(page.locator("#register-done-text")).to_contain_text(email)


def test_the_verify_page_rejects_a_garbage_link(page: Page):
    page.goto(f"{FRONTEND_URL}/verify#token=basura", wait_until="networkidle")
    expect(page.locator("#verify-error")).to_be_visible()
    assert "token" not in page.url  # the token is taken out of the address bar
