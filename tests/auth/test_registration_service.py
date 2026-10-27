# tests/auth/test_registration_service.py
from datetime import datetime, timedelta, timezone

import pytest

from api.app.auth import email_tokens as et
from api.app.auth import registration
from api.app.config import settings
from radar_db.accounts import AccountError, UsernameTakenError
from radar_db.models import User
from radar_db.passwords import PasswordPolicyError, verify_password

from .conftest import TEST_PASSWORD

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
DOMAIN = "ejemplo.com.ar"


@pytest.fixture(autouse=True)
def _mail_settings(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://webmet.test")
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 60)
    monkeypatch.setattr(settings, "mail_max_per_hour", 3)


def _register(db, username="nuevo", email=f"nuevo@{DOMAIN}", password=TEST_PASSWORD, now=NOW, full_name=None):
    return registration.register(db, username=username, email=email, password=password, now=now, full_name=full_name)


def _token_in(mail):
    return mail.text.split("token=")[1].split()[0]


# --- register ----------------------------------------------------------------


def test_register_creates_a_pending_viewer_and_a_verification_mail(test_db_session):
    mails = _register(test_db_session, email=f"  Nuevo@{DOMAIN.upper()} ")
    user = test_db_session.query(User).filter_by(username="nuevo").one()
    assert user.role == "viewer"
    assert user.email == f"nuevo@{DOMAIN}"
    assert user.email_verified_at is None
    assert user.terms_accepted_at is not None
    assert user.is_active is True
    assert len(mails) == 1 and mails[0].to == f"nuevo@{DOMAIN}"
    assert "/verify#token=" in mails[0].text


def test_register_validates_username_and_password(test_db_session):
    with pytest.raises(AccountError):
        _register(test_db_session, username="a@b")
    with pytest.raises(AccountError):
        _register(test_db_session, username="x")
    with pytest.raises(PasswordPolicyError):
        _register(test_db_session, password="corta")
    with pytest.raises(PasswordPolicyError):
        _register(test_db_session, password="nuevo")
    assert test_db_session.query(User).count() == 0


def test_register_with_a_verified_mail_is_neutral_and_notifies_the_owner(make_user, test_db_session):
    make_user(username="ana", email=f"ana@{DOMAIN}")
    mails = _register(test_db_session, username="otro", email=f"ana@{DOMAIN}")
    assert test_db_session.query(User).filter_by(username="otro").count() == 0
    assert len(mails) == 1
    assert mails[0].to == f"ana@{DOMAIN}"
    assert "ya existe una con el usuario ana" in mails[0].text


def test_register_with_a_username_of_a_verified_account_is_refused(make_user, test_db_session):
    make_user(username="ana", email=f"ana@{DOMAIN}")
    with pytest.raises(UsernameTakenError):
        _register(test_db_session, username="ana", email=f"otra@{DOMAIN}")


def test_a_taken_username_says_nothing_about_the_mail(make_user, test_db_session):
    # Enumeration: with a taken username the answer must not depend on the mail. If a mail that has an account
    # got the neutral answer and an unknown one got "username taken", anyone could test which mails are registered.
    make_user(username="ana", email=f"ana@{DOMAIN}")
    make_user(username="beto", email=f"beto@{DOMAIN}")
    for mail in (f"ana@{DOMAIN}", f"beto@{DOMAIN}", f"nadie@{DOMAIN}"):
        with pytest.raises(UsernameTakenError):
            _register(test_db_session, username="ana", email=mail)


def _pending(make_user, created_at, **kwargs):
    """An unverified account created at a given time (created_at is normally the server clock)."""
    user = make_user(email_verified=False, **kwargs)
    user.created_at = created_at
    return user


EXPIRED = NOW - timedelta(hours=25)  # older than the verification link (24 h): nothing is lost by replacing it
FRESH = NOW - timedelta(hours=1)  # its link may still be in the person's inbox


def test_an_expired_unverified_account_is_replaced_by_the_same_username(make_user, test_db_session):
    old = _pending(make_user, EXPIRED, username="nuevo", email=f"viejo@{DOMAIN}")
    old_id = old.id
    _register(test_db_session, username="nuevo", email=f"nuevo@{DOMAIN}")
    users = test_db_session.query(User).filter_by(username="nuevo").all()
    assert len(users) == 1 and users[0].id != old_id and users[0].email == f"nuevo@{DOMAIN}"
    assert test_db_session.query(User).filter_by(email=f"viejo@{DOMAIN}").count() == 0


def test_an_expired_unverified_account_is_replaced_by_the_same_mail(make_user, test_db_session):
    _pending(make_user, EXPIRED, username="fantasma", email=f"nuevo@{DOMAIN}")
    _register(test_db_session, username="nuevo", email=f"nuevo@{DOMAIN}")
    assert test_db_session.query(User).filter_by(username="fantasma").count() == 0
    assert test_db_session.query(User).filter_by(username="nuevo").count() == 1


def test_a_verified_username_blocks_before_anything_is_deleted(make_user, test_db_session):
    make_user(username="ana", email=f"ana@{DOMAIN}")
    _pending(make_user, EXPIRED, username="fantasma", email=f"nuevo@{DOMAIN}")
    with pytest.raises(UsernameTakenError):
        _register(test_db_session, username="ana", email=f"nuevo@{DOMAIN}")
    assert test_db_session.query(User).filter_by(username="fantasma").count() == 1


def test_a_fresh_unverified_username_cannot_be_taken(make_user, test_db_session):
    # Ana registered 1 h ago and may be about to click her link: nobody can push her out.
    _pending(make_user, FRESH, username="ana", email=f"ana@{DOMAIN}")
    with pytest.raises(UsernameTakenError):
        _register(test_db_session, username="ana", email=f"otra@{DOMAIN}")
    assert test_db_session.query(User).filter_by(username="ana", email=f"ana@{DOMAIN}").count() == 1


def test_signing_up_again_with_a_pending_mail_takes_the_latest_data(make_user, test_db_session):
    # The same pending account (same row, so its mail caps are kept) takes the username, password and name typed
    # now, and the mail goes to the address with a new link greeting the new username.
    old = _pending(make_user, FRESH, username="ana", email=f"ana@{DOMAIN}")
    old_id = old.id
    mails = _register(
        test_db_session, username="otro", email=f"ana@{DOMAIN}", password="otra-clave-larga-1", full_name="Otra Persona"
    )
    user = test_db_session.get(User, old_id)
    assert user.username == "otro" and user.full_name == "Otra Persona"
    assert verify_password("otra-clave-larga-1", user.password_hash)
    assert test_db_session.query(User).filter_by(username="ana").count() == 0
    assert len(mails) == 1 and mails[0].to == f"ana@{DOMAIN}" and "/verify#token=" in mails[0].text
    assert "Hola otro" in mails[0].text


def test_a_pending_mail_cannot_be_pre_registered_with_someone_elses_password(test_db_session):
    # Pre-hijacking: an attacker signs up first with the victim's mail. When the victim signs up with their own
    # data and clicks the mail that arrives, the account must have the victim's data, never the attacker's.
    attacker_mail = _register(
        test_db_session, username="atacante", email=f"victima@{DOMAIN}", password="clave-del-atacante-1"
    )[0]
    victim_mail = _register(
        test_db_session,
        username="victima",
        email=f"victima@{DOMAIN}",
        password="clave-de-la-victima-1",
        now=NOW + timedelta(minutes=2),
    )[0]
    # The attacker's link stopped working: it was issued for data that are no longer the account's.
    with pytest.raises(et.InvalidEmailToken):
        registration.verify_email(test_db_session, _token_in(attacker_mail), now=NOW + timedelta(minutes=3))
    registration.verify_email(test_db_session, _token_in(victim_mail), now=NOW + timedelta(minutes=3))
    user = test_db_session.query(User).filter_by(email=f"victima@{DOMAIN}").one()
    assert user.username == "victima" and user.email_verified_at is not None
    assert verify_password("clave-de-la-victima-1", user.password_hash)
    assert not verify_password("clave-del-atacante-1", user.password_hash)


def test_signing_up_again_when_capped_still_updates_and_kills_the_old_link(test_db_session):
    # With the caps used up nothing is sent, but the data change anyway, so no old link can verify the account
    # with data that are not the latest ones. The person asks for a new link later ("reenviar").
    first = _register(test_db_session, username="uno", email=f"nuevo@{DOMAIN}")[0]
    for minute in (2, 4):
        _register(test_db_session, username="uno", email=f"nuevo@{DOMAIN}", now=NOW + timedelta(minutes=minute))
    capped = _register(test_db_session, username="dos", email=f"nuevo@{DOMAIN}", now=NOW + timedelta(minutes=6))
    assert capped == []
    assert test_db_session.query(User).filter_by(email=f"nuevo@{DOMAIN}").one().username == "dos"
    with pytest.raises(et.InvalidEmailToken):
        registration.verify_email(test_db_session, _token_in(first), now=NOW + timedelta(minutes=7))


def test_signing_up_again_can_take_the_username_of_an_expired_pending_account(make_user, test_db_session):
    old = _pending(make_user, FRESH, username="ana", email=f"ana@{DOMAIN}")
    _pending(make_user, EXPIRED, username="libre", email=f"viejo@{DOMAIN}")
    _register(test_db_session, username="libre", email=f"ana@{DOMAIN}")
    assert test_db_session.get(User, old.id).username == "libre"
    assert test_db_session.query(User).filter_by(email=f"viejo@{DOMAIN}").count() == 0


def test_repeating_a_registration_cannot_flood_a_mailbox(test_db_session):
    # Without a no-replace rule each attempt would delete the pending account (and its mail count) and send again.
    sent = 0
    for minute in range(0, 20, 2):
        sent += len(_register(test_db_session, now=NOW + timedelta(minutes=minute)))
    assert sent == 3


def test_a_pending_account_becomes_replaceable_when_its_link_expires(test_db_session):
    first = _register(test_db_session, username="uno", email=f"nuevo@{DOMAIN}")
    old_id = test_db_session.query(User).filter_by(username="uno").one().id
    assert len(first) == 1
    just_before = NOW + timedelta(hours=24) - timedelta(seconds=1)
    _register(test_db_session, username="dos", email=f"nuevo@{DOMAIN}", now=just_before)
    assert test_db_session.query(User).filter_by(id=old_id).count() == 1
    _register(test_db_session, username="dos", email=f"nuevo@{DOMAIN}", now=NOW + timedelta(hours=24))
    assert test_db_session.query(User).filter_by(id=old_id).count() == 0
    assert test_db_session.query(User).filter_by(username="dos").count() == 1


def test_the_password_is_hashed_once_in_every_path(make_user, test_db_session, monkeypatch):
    calls = []
    real = registration.hash_password
    monkeypatch.setattr(registration, "hash_password", lambda password: calls.append(1) or real(password))
    _register(test_db_session, username="uno", email=f"uno@{DOMAIN}")
    make_user(username="ana", email=f"ana@{DOMAIN}")
    _register(test_db_session, username="dos", email=f"ana@{DOMAIN}", now=NOW + timedelta(minutes=5))
    assert calls == [1, 1]


def test_notices_to_a_verified_account_are_capped(make_user, test_db_session):
    make_user(username="ana", email=f"ana@{DOMAIN}")
    sent = 0
    for minute in range(0, 20, 2):
        when = NOW + timedelta(minutes=minute)
        sent += len(_register(test_db_session, username=f"user{minute}", email=f"ana@{DOMAIN}", now=when))
    assert sent == 3


# --- terms acceptance --------------------------------------------------------


def test_register_records_the_terms_acceptance_only_when_told(test_db_session):
    _register(test_db_session)
    registration.register(
        test_db_session,
        username="otro",
        email=f"otro@{DOMAIN}",
        password=TEST_PASSWORD,
        terms_accepted=False,
        now=NOW,
    )
    assert test_db_session.query(User).filter_by(username="nuevo").one().terms_accepted_at is not None
    assert test_db_session.query(User).filter_by(username="otro").one().terms_accepted_at is None


# --- full name (optional) ----------------------------------------------------


def test_register_saves_the_normalized_full_name(test_db_session):
    _register(test_db_session, full_name="  Ana   Pérez ")
    assert test_db_session.query(User).filter_by(username="nuevo").one().full_name == "Ana Pérez"


def test_register_without_a_full_name_stores_null(test_db_session):
    _register(test_db_session)
    _register(test_db_session, username="otro", email=f"otro@{DOMAIN}", full_name="   ")
    assert test_db_session.query(User).filter_by(username="nuevo").one().full_name is None
    assert test_db_session.query(User).filter_by(username="otro").one().full_name is None


def test_the_full_name_is_ignored_when_the_mail_has_a_verified_account(make_user, test_db_session):
    owner = make_user(username="ana", email=f"ana@{DOMAIN}", full_name="Ana Original")
    _register(test_db_session, username="otro", email=f"ana@{DOMAIN}", full_name="Otra Persona")
    assert owner.full_name == "Ana Original"
    assert test_db_session.query(User).filter_by(username="otro").count() == 0


def test_a_replaced_expired_account_takes_the_new_full_name(make_user, test_db_session):
    _pending(make_user, EXPIRED, username="nuevo", email=f"viejo@{DOMAIN}", full_name="Nombre Viejo")
    _register(test_db_session, full_name="Nombre Nuevo")
    assert test_db_session.query(User).filter_by(username="nuevo").one().full_name == "Nombre Nuevo"


# --- verify ------------------------------------------------------------------


def test_verify_marks_the_mail_as_verified(test_db_session):
    token = _token_in(_register(test_db_session)[0])
    registration.verify_email(test_db_session, token, now=NOW + timedelta(minutes=5))
    user = test_db_session.query(User).filter_by(username="nuevo").one()
    assert user.email_verified_at == NOW + timedelta(minutes=5)


def test_verify_token_is_single_use_and_expires(test_db_session):
    token = _token_in(_register(test_db_session)[0])
    registration.verify_email(test_db_session, token, now=NOW + timedelta(minutes=5))
    with pytest.raises(et.InvalidEmailToken):
        registration.verify_email(test_db_session, token, now=NOW + timedelta(minutes=6))
    token2 = _token_in(_register(test_db_session, username="otro", email=f"otro@{DOMAIN}")[0])
    with pytest.raises(et.InvalidEmailToken):
        registration.verify_email(test_db_session, token2, now=NOW + timedelta(hours=25))


# --- resend ------------------------------------------------------------------


def test_resend_sends_a_new_link_and_cancels_the_old_one(test_db_session):
    first = _token_in(_register(test_db_session)[0])
    mails = registration.resend_verification(test_db_session, "nuevo", now=NOW + timedelta(minutes=5))
    assert len(mails) == 1
    with pytest.raises(et.InvalidEmailToken):
        registration.verify_email(test_db_session, first, now=NOW + timedelta(minutes=6))
    registration.verify_email(test_db_session, _token_in(mails[0]), now=NOW + timedelta(minutes=6))


def test_resend_accepts_the_mail_and_ignores_everything_else(make_user, test_db_session):
    _register(test_db_session)
    make_user(username="ana", email=f"ana@{DOMAIN}")
    later = NOW + timedelta(minutes=5)
    assert len(registration.resend_verification(test_db_session, f"NUEVO@{DOMAIN}", now=later)) == 1
    assert registration.resend_verification(test_db_session, "ana", now=later) == []
    assert registration.resend_verification(test_db_session, "nadie", now=later) == []
    assert registration.resend_verification(test_db_session, "nadie@x.com", now=later) == []


def test_resend_respects_the_interval(test_db_session):
    _register(test_db_session)
    assert registration.resend_verification(test_db_session, "nuevo", now=NOW + timedelta(seconds=20)) == []
    assert len(registration.resend_verification(test_db_session, "nuevo", now=NOW + timedelta(seconds=90))) == 1


# --- forgot / reset ----------------------------------------------------------


def test_forgot_sends_a_reset_link_to_a_verified_account(make_user, test_db_session):
    make_user(username="ana", email=f"ana@{DOMAIN}")
    mails = registration.forgot_password(test_db_session, f"Ana@{DOMAIN}", now=NOW)
    assert len(mails) == 1 and "/reset#token=" in mails[0].text


def test_forgot_for_an_unverified_account_sends_the_verification_instead(test_db_session):
    _register(test_db_session)
    mails = registration.forgot_password(test_db_session, f"nuevo@{DOMAIN}", now=NOW + timedelta(minutes=5))
    assert len(mails) == 1 and "/verify#token=" in mails[0].text


def test_forgot_ignores_unknown_inactive_and_capped_accounts(make_user, test_db_session):
    user = make_user(username="ana", email=f"ana@{DOMAIN}")
    assert registration.forgot_password(test_db_session, f"nadie@{DOMAIN}", now=NOW) == []
    user.is_active = False
    assert registration.forgot_password(test_db_session, f"ana@{DOMAIN}", now=NOW) == []
    user.is_active = True
    assert len(registration.forgot_password(test_db_session, f"ana@{DOMAIN}", now=NOW)) == 1
    assert registration.forgot_password(test_db_session, f"ana@{DOMAIN}", now=NOW + timedelta(seconds=10)) == []


def test_reset_changes_the_password_closes_sessions_and_unlocks(make_user, test_db_session):
    from api.app.auth import service

    user = make_user(username="ana", email=f"ana@{DOMAIN}")
    session, refresh = service.create_session(test_db_session, user, now=NOW)
    user.failed_login_count = 4
    user.locked_until = NOW + timedelta(minutes=10)
    token = _token_in(registration.forgot_password(test_db_session, f"ana@{DOMAIN}", now=NOW)[0])
    registration.reset_password(test_db_session, token, "otra-contrasena-larga", now=NOW + timedelta(minutes=2))
    assert user.locked_until is None and user.failed_login_count == 0
    # The user closed their own logins: the audit trail must not say an admin did it.
    test_db_session.refresh(session)  # revoke_all_sessions uses a bulk UPDATE
    assert session.revoke_reason == "password_reset"
    with pytest.raises(service.AuthError):
        service.rotate_refresh(test_db_session, refresh, now=NOW + timedelta(minutes=3))
    later = NOW + timedelta(minutes=3)
    assert service.authenticate(test_db_session, "ana", "otra-contrasena-larga", now=later).id == user.id


def test_a_weak_password_does_not_spend_the_token(make_user, test_db_session):
    make_user(username="ana", email=f"ana@{DOMAIN}")
    token = _token_in(registration.forgot_password(test_db_session, f"ana@{DOMAIN}", now=NOW)[0])
    with pytest.raises(PasswordPolicyError):
        registration.reset_password(test_db_session, token, "corta", now=NOW + timedelta(minutes=2))
    registration.reset_password(test_db_session, token, "otra-contrasena-larga", now=NOW + timedelta(minutes=3))


def test_reset_token_is_single_use_and_verifies_the_mail(test_db_session):
    _register(test_db_session)
    user = test_db_session.query(User).filter_by(username="nuevo").one()
    token = et.issue_token(test_db_session, user, et.PURPOSE_RESET, timedelta(hours=1), NOW + timedelta(minutes=5))
    registration.reset_password(test_db_session, token, "otra-contrasena-larga", now=NOW + timedelta(minutes=6))
    assert user.email_verified_at is not None
    with pytest.raises(et.InvalidEmailToken):
        registration.reset_password(test_db_session, token, "otra-contrasena-larga2", now=NOW + timedelta(minutes=7))


def test_a_verification_token_cannot_reset_a_password(test_db_session):
    token = _token_in(_register(test_db_session)[0])
    with pytest.raises(et.InvalidEmailToken):
        registration.reset_password(test_db_session, token, "otra-contrasena-larga", now=NOW + timedelta(minutes=2))
