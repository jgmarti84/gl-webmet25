# tests/auth/test_registration_router.py
import pytest

from api.app.config import settings
from radar_db.models import User

from .conftest import TEST_EMAIL_DOMAIN, TEST_PASSWORD, login, register_payload, token_from

URL = "/api/v1/auth"
DOMAIN = TEST_EMAIL_DOMAIN
NEW_PASSWORD = "otra-contrasena-larga"

pytestmark = pytest.mark.usefixtures("registration_on")


def _register(client, **overrides):
    return client.post(f"{URL}/register", json=register_payload(**overrides))


# --- options -----------------------------------------------------------------


def test_options_when_everything_is_configured(client):
    response = client.get(f"{URL}/options")
    assert response.status_code == 200
    assert response.json() == {
        "registration": True,
        "password_recovery": True,
        "terms_required": True,
        "terms_url": "https://webmet.test/terminos",
        "privacy_url": "https://webmet.test/privacidad",
    }


def test_options_when_the_mail_is_not_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "mail_host", "")
    body = client.get(f"{URL}/options").json()
    assert body["registration"] is False
    assert body["password_recovery"] is False


def test_options_with_the_switch_off(client, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", False)
    body = client.get(f"{URL}/options").json()
    assert body["registration"] is False
    assert body["password_recovery"] is True


def test_options_without_the_terms(client, monkeypatch):
    # The default: TERMS_REQUIRED is off. The sign-up is on without any legal link and the options say so.
    monkeypatch.setattr(settings, "terms_required", False)
    monkeypatch.setattr(settings, "terms_url", "")
    monkeypatch.setattr(settings, "privacy_url", "")
    assert client.get(f"{URL}/options").json() == {
        "registration": True,
        "password_recovery": True,
        "terms_required": False,
        "terms_url": None,
        "privacy_url": None,
    }


def test_options_hide_the_links_when_the_terms_are_not_required(client, monkeypatch):
    # The links are configured but TERMS_REQUIRED is off: the pages must not get them to show.
    monkeypatch.setattr(settings, "terms_required", False)
    body = client.get(f"{URL}/options").json()
    assert body["terms_required"] is False
    assert body["terms_url"] is None and body["privacy_url"] is None


# --- register ----------------------------------------------------------------


def test_register_creates_a_pending_account_and_sends_the_mail(client, mailer, test_db_session):
    response = _register(client)
    assert response.status_code == 202
    assert "mail" in response.json()["detail"]
    assert not response.cookies
    user = test_db_session.query(User).filter_by(username="nuevo").one()
    assert user.role == "viewer" and user.email_verified_at is None
    assert [m.to for m in mailer.sent] == [f"nuevo@{DOMAIN}"]


def test_register_saves_the_full_name(client, test_db_session):
    assert _register(client, full_name="  Ana   Pérez ").status_code == 202
    assert test_db_session.query(User).filter_by(username="nuevo").one().full_name == "Ana Pérez"


def test_the_full_name_is_optional(client, test_db_session):
    assert _register(client).status_code == 202  # the payload has no full_name at all
    assert _register(client, username="otro", email=f"otro@{DOMAIN}", full_name="").status_code == 202
    assert test_db_session.query(User).filter_by(username="nuevo").one().full_name is None
    assert test_db_session.query(User).filter_by(username="otro").one().full_name is None


def test_a_too_long_full_name_is_a_422(client, mailer, test_db_session):
    assert _register(client, full_name="x" * 129).status_code == 422
    assert test_db_session.query(User).count() == 0 and not mailer.sent


def test_register_requires_the_terms(client, mailer, test_db_session):
    response = _register(client, accept_terms=False)
    assert response.status_code == 422
    assert "términos" in response.json()["detail"]
    assert test_db_session.query(User).count() == 0 and not mailer.sent


@pytest.mark.parametrize(
    "bad",
    [
        {"username": "ab"},
        {"username": "con@arroba"},
        {"username": "x" * 33},
        {"email": "no-es-un-mail"},
        {"email": ""},
        {"password": "corta"},
        {"password": "      "},
        {"password": "nuevo"},
    ],
)
def test_register_rejects_invalid_data(client, mailer, test_db_session, bad):
    assert _register(client, **bad).status_code == 422
    assert test_db_session.query(User).count() == 0 and not mailer.sent


def test_the_acceptance_is_recorded_when_the_terms_are_required(client, test_db_session):
    assert _register(client).status_code == 202
    assert test_db_session.query(User).filter_by(username="nuevo").one().terms_accepted_at is not None


def test_register_without_terms_when_they_are_not_required(client, mailer, monkeypatch, test_db_session):
    monkeypatch.setattr(settings, "terms_required", False)
    monkeypatch.setattr(settings, "terms_url", "")
    monkeypatch.setattr(settings, "privacy_url", "")
    payload = register_payload()
    del payload["accept_terms"]  # the page does not even send it
    assert client.post(f"{URL}/register", json=payload).status_code == 202
    assert _register(client, username="otro", email=f"otro@{DOMAIN}", accept_terms=False).status_code == 202
    users = {u.username: u for u in test_db_session.query(User).all()}
    # Nothing was accepted, so no consent is recorded.
    assert users["nuevo"].terms_accepted_at is None and users["otro"].terms_accepted_at is None
    assert len(mailer.sent) == 2


def test_register_rejects_a_missing_field(client):
    payload = register_payload()
    del payload["email"]
    assert client.post(f"{URL}/register", json=payload).status_code == 422


@pytest.mark.parametrize(
    "bad",
    [
        {"username": "nu\x00evo"},
        {"email": "nuevo\x00@ejemplo.com.ar"},
        {"password": "contrasena-larga\x00-con-nulo"},
        {"website": "\x00"},
        {"full_name": "Ana\x00 Pérez"},
    ],
)
def test_a_null_character_is_a_422_not_a_500(client, mailer, test_db_session, bad):
    # PostgreSQL cannot store "\x00": without the up-front check the driver would fail with a 500.
    assert _register(client, **bad).status_code == 422
    assert test_db_session.query(User).count() == 0 and not mailer.sent


def test_the_decoy_field_makes_register_do_nothing(client, mailer, test_db_session):
    response = _register(client, website="http://spam.example")
    assert response.status_code == 202
    assert test_db_session.query(User).count() == 0 and not mailer.sent


def test_register_is_unavailable_when_it_is_off(client, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", False)
    assert _register(client).status_code == 503


def test_a_taken_username_is_a_409(client, make_user):
    make_user(username="nuevo", email=f"otro@{DOMAIN}")
    response = _register(client)
    assert response.status_code == 409
    assert "usuario" in response.json()["detail"]


def test_a_registered_mail_gets_the_same_answer_as_a_new_one(client, make_user, mailer):
    fresh = _register(client)
    make_user(username="ana", email=f"ana@{DOMAIN}")
    repeated = _register(client, username="otra", email=f"ana@{DOMAIN}")
    assert (repeated.status_code, repeated.json()) == (fresh.status_code, fresh.json())
    assert [m.to for m in mailer.sent] == [f"nuevo@{DOMAIN}", f"ana@{DOMAIN}"]
    assert "ya existe una con el usuario ana" in mailer.sent[1].text


# --- verify ------------------------------------------------------------------


def test_the_link_of_the_mail_verifies_the_account_and_opens_the_login(client, mailer):
    _register(client)
    assert client.post(f"{URL}/login", json={"username": "nuevo", "password": TEST_PASSWORD}).status_code == 403
    token = token_from(mailer.sent[0])
    assert client.post(f"{URL}/verify-email", json={"token": token}).status_code == 204
    assert client.post(f"{URL}/login", json={"username": "nuevo", "password": TEST_PASSWORD}).status_code == 200
    client.cookies.clear()
    by_mail = client.post(f"{URL}/login", json={"username": f"NUEVO@{DOMAIN}", "password": TEST_PASSWORD})
    assert by_mail.status_code == 200


@pytest.mark.parametrize("bad", ["", "x", "' OR '1'='1", "a" * 43, "a" * 500])
def test_verify_with_a_bad_token_is_always_the_same_400(client, bad):
    response = client.post(f"{URL}/verify-email", json={"token": bad})
    assert response.status_code == 400
    assert response.json()["detail"] == "El link no es válido o ya venció. Pedí uno nuevo."


def test_a_verification_link_works_once(client, mailer):
    _register(client)
    token = token_from(mailer.sent[0])
    assert client.post(f"{URL}/verify-email", json={"token": token}).status_code == 204
    assert client.post(f"{URL}/verify-email", json={"token": token}).status_code == 400


# --- resend ------------------------------------------------------------------


def test_resend_is_always_a_202_and_only_mails_a_pending_account(client, make_user, mailer, monkeypatch):
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 0)
    _register(client)
    make_user(username="ana", email=f"ana@{DOMAIN}")
    sent_before = len(mailer.sent)
    for identifier in ("nuevo", f"nuevo@{DOMAIN}", "ana", "nadie", f"nadie@{DOMAIN}"):
        assert client.post(f"{URL}/resend-verification", json={"identifier": identifier}).status_code == 202
    assert len(mailer.sent) - sent_before == 2
    assert all(m.to == f"nuevo@{DOMAIN}" for m in mailer.sent)


def test_the_new_link_cancels_the_old_one(client, mailer, monkeypatch):
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 0)
    _register(client)
    client.post(f"{URL}/resend-verification", json={"identifier": "nuevo"})
    old, new = token_from(mailer.sent[0]), token_from(mailer.sent[1])
    assert client.post(f"{URL}/verify-email", json={"token": old}).status_code == 400
    assert client.post(f"{URL}/verify-email", json={"token": new}).status_code == 204


def test_resend_respects_the_minimum_interval(client, mailer):
    _register(client)
    client.post(f"{URL}/resend-verification", json={"identifier": "nuevo"})
    assert len(mailer.sent) == 1


@pytest.mark.parametrize(
    "path, body", [("resend-verification", {"identifier": "a\x00b"}), ("verify-email", {"token": "a\x00"})]
)
def test_null_characters_in_the_other_bodies_are_a_422(client, path, body):
    assert client.post(f"{URL}/{path}", json=body).status_code == 422


# --- forgot / reset ----------------------------------------------------------


def test_forgot_password_is_neutral(client, make_user, mailer):
    make_user(username="ana", email=f"ana@{DOMAIN}")
    known = client.post(f"{URL}/forgot-password", json={"email": f"ana@{DOMAIN}"})
    unknown = client.post(f"{URL}/forgot-password", json={"email": f"nadie@{DOMAIN}"})
    assert (known.status_code, known.json()) == (unknown.status_code, unknown.json()) == (202, known.json())
    assert [m.to for m in mailer.sent] == [f"ana@{DOMAIN}"]


def test_the_full_recovery_flow(client, make_user, mailer):
    make_user(username="ana", email=f"ana@{DOMAIN}")
    login(client, "ana")
    client.post(f"{URL}/forgot-password", json={"email": f"ana@{DOMAIN}"})
    token = token_from(mailer.sent[0])
    reset = client.post(f"{URL}/reset-password", json={"token": token, "password": NEW_PASSWORD})
    assert reset.status_code == 204
    assert client.post(f"{URL}/refresh").status_code == 401  # the old session was closed
    assert client.post(f"{URL}/login", json={"username": "ana", "password": TEST_PASSWORD}).status_code == 401
    assert client.post(f"{URL}/login", json={"username": "ana", "password": NEW_PASSWORD}).status_code == 200


def test_a_weak_new_password_is_a_422_and_the_link_still_works(client, make_user, mailer):
    make_user(username="ana", email=f"ana@{DOMAIN}")
    client.post(f"{URL}/forgot-password", json={"email": f"ana@{DOMAIN}"})
    token = token_from(mailer.sent[0])
    assert client.post(f"{URL}/reset-password", json={"token": token, "password": "corta"}).status_code == 422
    assert client.post(f"{URL}/reset-password", json={"token": token, "password": NEW_PASSWORD}).status_code == 204


def test_a_reset_link_works_once(client, make_user, mailer):
    make_user(username="ana", email=f"ana@{DOMAIN}")
    client.post(f"{URL}/forgot-password", json={"email": f"ana@{DOMAIN}"})
    token = token_from(mailer.sent[0])
    body = {"token": token, "password": NEW_PASSWORD}
    assert client.post(f"{URL}/reset-password", json=body).status_code == 204
    assert client.post(f"{URL}/reset-password", json=body).status_code == 400


def test_a_verification_token_does_not_reset_a_password(client, mailer):
    _register(client)
    token = token_from(mailer.sent[0])
    assert client.post(f"{URL}/reset-password", json={"token": token, "password": NEW_PASSWORD}).status_code == 400


def test_recovery_is_unavailable_without_the_mail_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "mail_host", "")
    assert client.post(f"{URL}/forgot-password", json={"email": f"ana@{DOMAIN}"}).status_code == 503
    assert client.post(f"{URL}/verify-email", json={"token": "a" * 43}).status_code == 503


def test_a_foreign_origin_is_refused(client):
    response = client.post(
        f"{URL}/forgot-password", json={"email": f"ana@{DOMAIN}"}, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
