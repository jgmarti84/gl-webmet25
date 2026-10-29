# tests/auth/test_google_login.py
"""Sign in with Google: POST /auth/google and the "google_client_id" option.

Google itself is never called: the tests replace the verifier (api/app/auth/google.py) with a fake that returns
the identity a real, valid token would carry, or fails like an invalid token.
"""

import pytest

from api.app.auth.google import GoogleIdentity
from radar_db.models import User

from .conftest import TEST_PASSWORD, login

BASE = "/api/v1/auth"
CLIENT_ID = "123-test.apps.googleusercontent.com"


def _identity(**overrides) -> GoogleIdentity:
    values = dict(sub="g-100", email="ana.perez@gmail.com", email_verified=True, name="Ana Pérez")
    values.update(overrides)
    return GoogleIdentity(**values)


def _google_login(client, google_verifier, identity=None):
    """Send a Google credential; the fake verifier answers with `identity` (a valid one by default)."""
    google_verifier.identity = identity or _identity()
    return client.post(f"{BASE}/google", json={"credential": "any-token"})


def _user_by_email(db, email):
    return db.query(User).filter(User.email == email).one_or_none()


# --- availability ----------------------------------------------------------------


def test_not_configured_answers_503(client, google_verifier):
    response = _google_login(client, google_verifier)
    assert response.status_code == 503
    assert "Google" in response.json()["detail"]


def test_options_offer_google_only_when_configured(client, google_on, monkeypatch):
    from api.app.config import settings

    assert client.get(f"{BASE}/options").json()["google_client_id"] == CLIENT_ID
    monkeypatch.setattr(settings, "google_client_id", "")
    assert client.get(f"{BASE}/options").json()["google_client_id"] is None


# --- a person who has no account yet ----------------------------------------------


def test_new_person_gets_a_viewer_account_and_is_logged_in(client, google_verifier, google_on, test_db_session):
    response = _google_login(client, google_verifier)
    assert response.status_code == 200
    assert response.json()["username"] == "ana.perez"
    assert response.json()["role"] == "viewer"
    assert client.get(f"{BASE}/me").status_code == 200  # the session cookies work

    user = _user_by_email(test_db_session, "ana.perez@gmail.com")
    assert user.full_name == "Ana Pérez"
    assert user.google_sub == "g-100"
    assert user.email_verified_at is not None  # Google already confirmed the mail
    assert user.terms_accepted_at is None
    assert user.last_login_at is not None


def test_the_new_account_has_no_usable_password(client, google_verifier, google_on):
    _google_login(client, google_verifier)
    client.post(f"{BASE}/logout")
    for guess in (TEST_PASSWORD, "ana.perez", "password1234"):
        response = client.post(f"{BASE}/login", json={"username": "ana.perez", "password": guess})
        assert response.status_code == 401


@pytest.mark.parametrize(
    "email, expected_start",
    [
        ("Ana.Perez@Gmail.com", "ana.perez"),  # lower case
        ("ana+news@gmail.com", "ana.news"),  # characters a username cannot have become a dot
        ("a@gmail.com", "a"),  # too short for a username: it is completed
        ("x" * 60 + "@gmail.com", "x" * 28),  # too long: it is cut
    ],
)
def test_the_username_is_built_from_the_mail(client, google_verifier, google_on, email, expected_start):
    response = _google_login(client, google_verifier, _identity(email=email))
    assert response.status_code == 200
    username = response.json()["username"]
    assert username.startswith(expected_start)
    assert 3 <= len(username) <= 32


def test_a_taken_username_gets_a_number(client, google_verifier, google_on, make_user):
    make_user(username="ana.perez")  # same name, another person (no mail)
    response = _google_login(client, google_verifier)
    assert response.status_code == 200
    assert response.json()["username"] != "ana.perez"
    assert response.json()["username"].startswith("ana.perez")


# --- a person who already has an account --------------------------------------------


def test_existing_account_with_the_same_mail_is_linked_and_logged_in(
    client, google_verifier, google_on, make_user, test_db_session
):
    existing = make_user(username="ana", email="ana.perez@gmail.com")
    response = _google_login(client, google_verifier)
    assert response.status_code == 200
    assert response.json()["username"] == "ana"  # no new account
    assert existing.google_sub == "g-100"
    assert test_db_session.query(User).count() == 1
    # The password they already had keeps working.
    client.post(f"{BASE}/logout")
    assert login(client, "ana").status_code == 200


def test_the_same_person_again_gets_the_same_account_even_if_their_mail_changed(
    client, google_verifier, google_on, test_db_session
):
    first = _google_login(client, google_verifier)
    client.post(f"{BASE}/logout")
    second = _google_login(client, google_verifier, _identity(email="ana.nueva@gmail.com"))
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert test_db_session.query(User).count() == 1


def test_the_mail_is_compared_without_case(client, google_verifier, google_on, make_user):
    make_user(username="ana", email="ana.perez@gmail.com")
    response = _google_login(client, google_verifier, _identity(email="Ana.Perez@Gmail.com"))
    assert response.json()["username"] == "ana"


def test_a_mail_linked_to_another_google_account_is_refused(client, google_verifier, google_on, make_user):
    make_user(username="ana", email="ana.perez@gmail.com", google_sub="g-OTHER")
    response = _google_login(client, google_verifier, _identity(sub="g-100"))
    assert response.status_code == 403
    assert response.json()["code"] == "google_account_mismatch"


def test_linking_an_unverified_account_drops_its_password(client, google_verifier, google_on, make_user):
    """Someone may have signed up with another person's mail and set their own password; when the real owner
    shows up with Google, that password must stop working."""
    pending = make_user(username="intruso", email="ana.perez@gmail.com", email_verified=False)
    version = pending.token_version
    response = _google_login(client, google_verifier)
    assert response.status_code == 200
    assert response.json()["username"] == "intruso"
    assert pending.email_verified_at is not None
    assert pending.token_version > version  # their sessions were closed
    client.post(f"{BASE}/logout")
    wrong = client.post(f"{BASE}/login", json={"username": "intruso", "password": TEST_PASSWORD})
    assert wrong.status_code == 401


# --- who cannot come in this way ------------------------------------------------------


def test_admins_cannot_use_google(client, google_verifier, google_on, make_user):
    admin = make_user(username="boss", role="admin", email="ana.perez@gmail.com")
    response = _google_login(client, google_verifier)
    assert response.status_code == 403
    assert response.json()["code"] == "admin_no_google"
    assert admin.google_sub is None  # nothing was linked
    assert client.get(f"{BASE}/me").status_code == 401  # and no session was opened


def test_a_deactivated_account_cannot_come_in(client, google_verifier, google_on, make_user):
    make_user(username="ana", email="ana.perez@gmail.com", is_active=False)
    response = _google_login(client, google_verifier)
    assert response.status_code == 403
    assert client.get(f"{BASE}/me").status_code == 401


def test_a_mail_google_did_not_verify_is_refused(client, google_verifier, google_on, test_db_session):
    response = _google_login(client, google_verifier, _identity(email_verified=False))
    assert response.status_code == 403
    assert test_db_session.query(User).count() == 0


def test_an_invalid_token_is_refused(client, google_verifier, google_on, test_db_session):
    google_verifier.fail = True
    response = client.post(f"{BASE}/google", json={"credential": "forged"})
    assert response.status_code == 401
    assert test_db_session.query(User).count() == 0


def test_a_missing_or_empty_credential_is_422(client, google_on):
    assert client.post(f"{BASE}/google", json={}).status_code == 422
    assert client.post(f"{BASE}/google", json={"credential": ""}).status_code == 422


def test_a_foreign_origin_is_refused(client, google_verifier, google_on):
    google_verifier.identity = _identity()
    response = client.post(f"{BASE}/google", json={"credential": "t"}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
