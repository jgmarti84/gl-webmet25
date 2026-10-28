# tests/api/test_registration.py
"""Black-box contract tests for the public registration endpoints.

They never create data: only the options, validation errors, unusable tokens and mails of accounts that do
not exist (nothing is written and nothing is sent).
"""

import os

import httpx
import pytest

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
PREFIX = "/api/v1/auth"
FOREIGN_ORIGIN = {"Origin": "https://evil.example"}


def _options() -> dict:
    with httpx.Client(base_url=API_BASE_URL) as client:
        return client.get(f"{PREFIX}/options").json()


def _need(feature: str) -> None:
    # The stack decides what is on: skip (with the reason) when this environment has the feature off.
    if not _options()[feature]:
        pytest.skip(f"{feature} is off in this environment")


def test_options_returns_200_json():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{PREFIX}/options")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]


def test_options_field_types():
    data = _options()
    assert isinstance(data["registration"], bool)
    assert isinstance(data["password_recovery"], bool)
    assert isinstance(data["terms_required"], bool)
    assert data["terms_url"] is None or isinstance(data["terms_url"], str)
    assert data["privacy_url"] is None or isinstance(data["privacy_url"], str)


def test_register_with_invalid_data_returns_422():
    _need("registration")
    body = {"username": "ab", "email": "no-es-un-mail", "password": "corta", "accept_terms": True}
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/register", json=body)
    assert response.status_code == 422


def test_register_without_the_terms_returns_422():
    _need("registration")
    # Only when this environment asks for the terms: without TERMS_REQUIRED the same request would create an account.
    _need("terms_required")
    body = {
        "username": "sin-terminos",
        "email": "sin-terminos@ejemplo.com.ar",
        "password": "una-clave-larga-1",
        "accept_terms": False,
    }
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/register", json=body)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_register_with_a_too_long_full_name_returns_422():
    # The name is optional, but 128 characters is the limit: a longer one is refused and nothing is created.
    _need("registration")
    body = {
        "username": "nombre-largo",
        "email": "nombre-largo@ejemplo.com.ar",
        "password": "una-clave-larga-1",
        "accept_terms": True,
        "full_name": "x" * 129,
    }
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/register", json=body)
    assert response.status_code == 422


def test_register_foreign_origin_returns_403():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/register", json={}, headers=FOREIGN_ORIGIN)
    assert response.status_code == 403


def test_verify_email_with_a_garbage_token_returns_400():
    _need("password_recovery")
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/verify-email", json={"token": "basura"})
    assert response.status_code == 400
    assert "detail" in response.json()


def test_reset_password_with_a_garbage_token_returns_400():
    _need("password_recovery")
    body = {"token": "basura", "password": "una-clave-larga-1"}
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/reset-password", json=body)
    assert response.status_code == 400


def test_forgot_password_for_an_unknown_mail_returns_202():
    _need("password_recovery")
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/forgot-password", json={"email": "nadie-seguro-98765@ejemplo.com.ar"})
    assert response.status_code == 202
    assert isinstance(response.json()["detail"], str)


def test_forgot_password_with_a_malformed_mail_returns_422():
    _need("password_recovery")
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/forgot-password", json={"email": "no-es-un-mail"})
    assert response.status_code == 422


def test_resend_verification_for_an_unknown_account_returns_202():
    _need("password_recovery")
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/resend-verification", json={"identifier": "nadie-seguro-98765"})
    assert response.status_code == 202


def test_a_validation_error_does_not_echo_the_value_sent():
    # The 422 must not repeat what was sent ("input"): a password typed in a wrong field would come back in clear.
    _need("registration")
    secret = "una-clave-muy-larga-" + "z" * 200
    body = {"username": "sin-eco", "email": "sin-eco@ejemplo.com.ar", "password": secret, "accept_terms": True}
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/register", json=body)
    assert response.status_code == 422
    assert secret not in response.text
