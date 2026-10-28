# tests/auth/test_injection.py
"""Hostile input in every public field: never a 500, never a change in the database."""

import json
import logging

import pytest

from radar_db.models import EmailToken, User

from .conftest import TEST_EMAIL_DOMAIN, TEST_PASSWORD

URL = "/api/v1/auth"

# SQL injection, NUL and invalid UTF-8 (PostgreSQL cannot store them), huge values, odd Unicode and template syntax.
PAYLOADS = [
    "' OR '1'='1",
    "' OR 1=1 --",
    "'; DROP TABLE users;--",
    "admin'--",
    '" OR ""="',
    "1; SELECT pg_sleep(5)",
    "%27%20OR%20%271%27%3D%271",
    "a" * 5000,
    "\x00",
    "\ud800",
    "ana\x00@ejemplo.com.ar",
    "ñandú",
    "😀",
    "' UNION SELECT password_hash FROM users --",
    "${7*7}",
    "{{7*7}}",
]


@pytest.fixture(autouse=True)
def _configured(registration_on):
    """Registration and mail fully configured, so the endpoints run their real code instead of answering 503."""


@pytest.fixture
def client(app_client):
    """The real application, as wired in main.py: the 422 handler under test lives there."""
    return app_client


@pytest.fixture
def known_user(make_user):
    return make_user(username="ana", email=f"ana@{TEST_EMAIL_DOMAIN}")


def _unchanged(db, users_before, tokens_before):
    assert db.query(User).count() == users_before
    assert db.query(EmailToken).count() == tokens_before


def _no_server_error(response):
    assert response.status_code < 500, response.text


def _post(client, path, body):
    """POST a JSON body already serialized with ASCII escapes.

    client.post(json=...) encodes the body as UTF-8 itself and fails on a lone surrogate ("\\ud800") before the
    request leaves the test. Escaped by json.dumps, the invalid character does reach the API, which is the point.
    """
    return client.post(f"{URL}/{path}", content=json.dumps(body), headers={"Content-Type": "application/json"})


@pytest.mark.parametrize("payload", PAYLOADS)
def test_login_identifier_and_password(client, known_user, test_db_session, payload):
    users, tokens = test_db_session.query(User).count(), test_db_session.query(EmailToken).count()
    for body in ({"username": payload, "password": TEST_PASSWORD}, {"username": "ana", "password": payload}):
        response = _post(client, "login", body)
        _no_server_error(response)
        assert response.status_code in (401, 422)
    _unchanged(test_db_session, users, tokens)


@pytest.mark.parametrize("payload", PAYLOADS)
def test_register_fields(client, known_user, test_db_session, mailer, payload):
    base = {"username": "nuevo", "email": f"nuevo@{TEST_EMAIL_DOMAIN}", "password": TEST_PASSWORD, "accept_terms": True}
    for field in ("username", "email", "password", "full_name"):
        response = _post(client, "register", {**base, field: payload, "website": ""})
        _no_server_error(response)
        assert response.status_code in (202, 409, 422), (field, response.text)
    # The decoy field may hold anything: it does nothing.
    response = _post(client, "register", {**base, "website": payload})
    _no_server_error(response)
    # Compared in Python: querying the database with a NUL character would fail in the test itself.
    assert payload not in {user.username for user in test_db_session.query(User)}
    # Whatever got created is a pending viewer, never anything else.
    for user in test_db_session.query(User).filter(User.id != known_user.id):
        assert user.role == "viewer" and user.email_verified_at is None
    assert test_db_session.query(User).filter_by(username="ana").one().email == f"ana@{TEST_EMAIL_DOMAIN}"


@pytest.mark.parametrize("payload", PAYLOADS)
def test_tokens_and_identifiers(client, known_user, test_db_session, payload):
    users, tokens = test_db_session.query(User).count(), test_db_session.query(EmailToken).count()
    for path, body in (
        ("verify-email", {"token": payload}),
        ("reset-password", {"token": payload, "password": "otra-contrasena-larga"}),
        ("resend-verification", {"identifier": payload}),
        ("forgot-password", {"email": payload}),
    ):
        response = _post(client, path, body)
        _no_server_error(response)
        assert response.status_code in (400, 202, 422), (path, response.text)
    _unchanged(test_db_session, users, tokens)


def test_the_users_table_survives_and_the_password_is_intact(client, known_user, test_db_session):
    client.post(f"{URL}/login", json={"username": "'; DROP TABLE users;--", "password": "x" * 12})
    client.post(f"{URL}/forgot-password", json={"email": f"ana@{TEST_EMAIL_DOMAIN}'; DROP TABLE users;--"})
    assert client.post(f"{URL}/login", json={"username": "ana", "password": TEST_PASSWORD}).status_code == 200


def test_mail_header_injection_is_rejected_by_the_validation(client, mailer):
    for email in (f"a@{TEST_EMAIL_DOMAIN}\nBcc: x@{TEST_EMAIL_DOMAIN}", f"a@{TEST_EMAIL_DOMAIN}\r\nSubject: x"):
        response = client.post(
            f"{URL}/register",
            json={"username": "nuevo", "email": email, "password": TEST_PASSWORD, "accept_terms": True},
        )
        assert response.status_code == 422
    assert not mailer.sent


def test_a_hostile_looking_full_name_is_stored_as_plain_text(client, known_user, test_db_session):
    # The name is a free text field: SQL or markup in it is just text (bound parameters, escaped when shown).
    hostile = "'; DROP TABLE users;-- <img src=x onerror=alert(1)>"
    body = {"username": "nuevo", "email": f"nuevo@{TEST_EMAIL_DOMAIN}", "password": TEST_PASSWORD}
    response = _post(client, "register", {**body, "accept_terms": True, "full_name": hostile})
    assert response.status_code == 202
    assert test_db_session.query(User).filter_by(username="nuevo").one().full_name == hostile
    assert test_db_session.query(User).filter_by(username="ana").one().email == f"ana@{TEST_EMAIL_DOMAIN}"


def test_a_validation_error_does_not_echo_what_was_sent(client):
    # FastAPI's default 422 repeats the rejected value in "input": a too-long password would come back in clear,
    # and a lone surrogate could not even be encoded (that ended in a 500).
    secret = "contrasena-muy-larga-" + "z" * 200
    body = {"username": "nuevo", "email": f"nuevo@{TEST_EMAIL_DOMAIN}", "password": secret, "accept_terms": True}
    response = _post(client, "register", body)
    assert response.status_code == 422
    assert secret not in response.text
    assert all("input" not in error and "ctx" not in error for error in response.json()["detail"])


def test_the_tokens_never_reach_the_log(client, known_user, mailer, caplog):
    with caplog.at_level(logging.DEBUG):
        client.post(f"{URL}/forgot-password", json={"email": f"ana@{TEST_EMAIL_DOMAIN}"})
    token = mailer.sent[0].text.split("token=")[1].split()[0]
    assert token not in caplog.text
    assert TEST_PASSWORD not in caplog.text
