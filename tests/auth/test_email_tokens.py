# tests/auth/test_email_tokens.py
from datetime import datetime, timedelta, timezone

import pytest

from api.app.auth import email_tokens as et
from api.app.config import settings
from radar_db.models import EmailToken

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
DAY = timedelta(hours=24)


def _pending(make_user):
    return make_user(username="pend", email="pend@ejemplo.com.ar", email_verified=False)


def test_a_token_can_be_redeemed_once(make_user, test_db_session):
    user = _pending(make_user)
    token = et.issue_token(test_db_session, user, et.PURPOSE_VERIFY, DAY, NOW)
    assert len(token) == 43
    assert et.consume_token(test_db_session, token, et.PURPOSE_VERIFY, NOW + timedelta(minutes=1)).id == user.id
    with pytest.raises(et.InvalidEmailToken):
        et.consume_token(test_db_session, token, et.PURPOSE_VERIFY, NOW + timedelta(minutes=2))


def test_an_expired_token_is_rejected(make_user, test_db_session):
    user = _pending(make_user)
    token = et.issue_token(test_db_session, user, et.PURPOSE_VERIFY, DAY, NOW)
    with pytest.raises(et.InvalidEmailToken):
        et.consume_token(test_db_session, token, et.PURPOSE_VERIFY, NOW + DAY)


def test_a_token_only_works_for_its_own_purpose(make_user, test_db_session):
    user = _pending(make_user)
    token = et.issue_token(test_db_session, user, et.PURPOSE_VERIFY, DAY, NOW)
    with pytest.raises(et.InvalidEmailToken):
        et.consume_token(test_db_session, token, et.PURPOSE_RESET, NOW)


@pytest.mark.parametrize("bad", ["", "x", "' OR '1'='1", "a" * 42, "a" * 44, "a" * 42 + "\x00", "é" * 43, "a" * 5000])
def test_malformed_tokens_are_rejected_without_a_lookup(test_db_session, bad):
    with pytest.raises(et.InvalidEmailToken):
        et.consume_token(test_db_session, bad, et.PURPOSE_VERIFY, NOW)


def test_only_the_hash_is_stored(make_user, test_db_session):
    user = _pending(make_user)
    token = et.issue_token(test_db_session, user, et.PURPOSE_VERIFY, DAY, NOW)
    row = test_db_session.query(EmailToken).one()
    assert row.token_hash == et.hash_token(token)
    assert token not in row.token_hash


def test_a_new_token_cancels_the_previous_one_of_the_same_purpose(make_user, test_db_session):
    user = _pending(make_user)
    first = et.issue_token(test_db_session, user, et.PURPOSE_VERIFY, DAY, NOW)
    second = et.issue_token(test_db_session, user, et.PURPOSE_VERIFY, DAY, NOW + timedelta(minutes=5))
    with pytest.raises(et.InvalidEmailToken):
        et.consume_token(test_db_session, first, et.PURPOSE_VERIFY, NOW + timedelta(minutes=6))
    assert et.consume_token(test_db_session, second, et.PURPOSE_VERIFY, NOW + timedelta(minutes=6)).id == user.id


def test_a_new_token_keeps_the_ones_of_other_purposes(make_user, test_db_session):
    user = _pending(make_user)
    verify = et.issue_token(test_db_session, user, et.PURPOSE_VERIFY, DAY, NOW)
    et.issue_token(test_db_session, user, et.PURPOSE_RESET, DAY, NOW + timedelta(minutes=5))
    assert et.consume_token(test_db_session, verify, et.PURPOSE_VERIFY, NOW + timedelta(minutes=6)).id == user.id


def test_hourly_cap(make_user, test_db_session, monkeypatch):
    monkeypatch.setattr(settings, "mail_max_per_hour", 3)
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 60)
    user = _pending(make_user)
    for minutes in (0, 2, 4):
        assert et.may_send_mail(test_db_session, user, NOW + timedelta(minutes=minutes))
        et.issue_token(test_db_session, user, et.PURPOSE_VERIFY, DAY, NOW + timedelta(minutes=minutes))
    assert not et.may_send_mail(test_db_session, user, NOW + timedelta(minutes=10))
    # An hour after the last one the window has moved on.
    assert et.may_send_mail(test_db_session, user, NOW + timedelta(minutes=64, seconds=1))


def test_minimum_interval(make_user, test_db_session, monkeypatch):
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 60)
    user = _pending(make_user)
    et.issue_token(test_db_session, user, et.PURPOSE_VERIFY, DAY, NOW)
    assert not et.may_send_mail(test_db_session, user, NOW + timedelta(seconds=30))
    assert et.may_send_mail(test_db_session, user, NOW + timedelta(seconds=61))


def test_notices_count_toward_the_caps(make_user, test_db_session, monkeypatch):
    monkeypatch.setattr(settings, "mail_max_per_hour", 3)
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 0)
    user = make_user(username="viva", email="viva@ejemplo.com.ar")
    for minutes in (0, 1, 2):
        et.record_notice(test_db_session, user, NOW + timedelta(minutes=minutes))
    assert not et.may_send_mail(test_db_session, user, NOW + timedelta(minutes=3))
    # A notice is not redeemable.
    row = test_db_session.query(EmailToken).first()
    assert row.used_at is not None


# --- global caps (all accounts together) -----------------------------------------


@pytest.fixture
def global_caps(monkeypatch):
    """Generous per-account caps, so only the global ones decide; returns a setter for the global ones."""
    monkeypatch.setattr(settings, "mail_max_per_hour", 100)
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 0)

    def _set(per_hour=1000, per_day=10000):
        monkeypatch.setattr(settings, "mail_max_global_per_hour", per_hour)
        monkeypatch.setattr(settings, "mail_max_global_per_day", per_day)

    return _set


def _accounts(make_user, n):
    return [make_user(username=f"cuenta{i}", email=f"cuenta{i}@ejemplo.com.ar", email_verified=False) for i in range(n)]


def test_global_hourly_cap_stops_new_mails_but_not_recovery(make_user, test_db_session, global_caps):
    # Someone signs up many different addresses: each one is a new account, so only a global cap can stop it.
    global_caps(per_hour=2)
    first, second, third = _accounts(make_user, 3)
    et.issue_token(test_db_session, first, et.PURPOSE_VERIFY, DAY, NOW)
    et.issue_token(test_db_session, second, et.PURPOSE_VERIFY, DAY, NOW)
    assert not et.may_send_mail(test_db_session, third, NOW + timedelta(minutes=1))
    # Password recovery still goes out, so real users can get back in while the sign-up is being abused.
    assert et.may_send_mail(test_db_session, third, NOW + timedelta(minutes=1), recovery=True)
    # An hour later the window has moved on.
    assert et.may_send_mail(test_db_session, third, NOW + timedelta(minutes=61))


def test_global_daily_cap_stops_every_mail(make_user, test_db_session, global_caps):
    # The daily cap stays under the provider's limit (Gmail blocks the account for a day if it is passed).
    global_caps(per_day=2)
    first, second, third = _accounts(make_user, 3)
    et.issue_token(test_db_session, first, et.PURPOSE_VERIFY, DAY, NOW)
    et.issue_token(test_db_session, second, et.PURPOSE_RESET, DAY, NOW + timedelta(hours=5))
    assert not et.may_send_mail(test_db_session, third, NOW + timedelta(hours=6))
    assert not et.may_send_mail(test_db_session, third, NOW + timedelta(hours=6), recovery=True)
    assert et.may_send_mail(test_db_session, third, NOW + timedelta(hours=24, minutes=1))
