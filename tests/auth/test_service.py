# tests/auth/test_service.py
from datetime import datetime, timedelta, timezone

import pytest

from api.app.auth import service
from api.app.auth.service import AuthError, RefreshRaceError
from api.app.config import settings

from .conftest import TEST_PASSWORD

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


# --- login -----------------------------------------------------------------


def test_authenticate_ok_resets_counters(make_user, test_db_session):
    user = make_user()
    user.failed_login_count = 2
    result = service.authenticate(test_db_session, "ALICE", TEST_PASSWORD, now=NOW)
    assert result.id == user.id
    assert user.failed_login_count == 0
    assert user.last_login_at == NOW


def test_authenticate_unknown_user(test_db_session):
    with pytest.raises(AuthError):
        service.authenticate(test_db_session, "nobody", TEST_PASSWORD, now=NOW)


def test_authenticate_wrong_password_counts(make_user, test_db_session):
    user = make_user()
    with pytest.raises(AuthError):
        service.authenticate(test_db_session, "alice", "wrong-password-xx", now=NOW)
    assert user.failed_login_count == 1


def test_lockout_after_max_attempts_and_unlock(make_user, test_db_session):
    user = make_user()
    for _ in range(settings.login_max_failed_attempts):
        with pytest.raises(AuthError):
            service.authenticate(test_db_session, "alice", "wrong-password-xx", now=NOW)
    assert user.locked_until == NOW + timedelta(minutes=settings.login_lockout_minutes)
    # Locked: even the right password fails
    with pytest.raises(AuthError):
        service.authenticate(test_db_session, "alice", TEST_PASSWORD, now=NOW + timedelta(minutes=1))
    # After the lockout window it works again
    later = NOW + timedelta(minutes=settings.login_lockout_minutes + 1)
    assert service.authenticate(test_db_session, "alice", TEST_PASSWORD, now=later).id == user.id


def test_inactive_user_cannot_log_in(make_user, test_db_session):
    user = make_user()
    user.is_active = False
    with pytest.raises(AuthError):
        service.authenticate(test_db_session, "alice", TEST_PASSWORD, now=NOW)


# --- sessions / refresh ------------------------------------------------------


def test_create_session_sets_expirations(make_user, test_db_session):
    user = make_user()
    session, token = service.create_session(test_db_session, user, now=NOW)
    assert session.expires_at == NOW + timedelta(hours=settings.session_idle_ttl_hours)
    assert session.absolute_expires_at == NOW + timedelta(days=settings.session_absolute_ttl_days)
    assert token and session.token_hash != token


def test_rotate_refresh_issues_new_token_in_same_family(make_user, test_db_session):
    user = make_user()
    old, token = service.create_session(test_db_session, user, now=NOW)
    later = NOW + timedelta(hours=1)
    got_user, new, new_token = service.rotate_refresh(test_db_session, token, now=later)
    assert got_user.id == user.id
    assert new.family_id == old.family_id
    assert new.absolute_expires_at == old.absolute_expires_at
    assert new.expires_at == later + timedelta(hours=settings.session_idle_ttl_hours)
    assert old.revoked_at == later and old.replaced_by == new.id
    assert new_token != token


def test_idle_expiration_never_passes_absolute(make_user, test_db_session):
    user = make_user()
    _, token = service.create_session(test_db_session, user, now=NOW)
    near_end = NOW + timedelta(days=settings.session_absolute_ttl_days) - timedelta(hours=1)
    # Keep the chain alive with refreshes every 40 h until near the absolute limit
    t = NOW
    while t + timedelta(hours=40) < near_end:
        t += timedelta(hours=40)
        _, _, token = service.rotate_refresh(test_db_session, token, now=t)
    _, new, _ = service.rotate_refresh(test_db_session, token, now=near_end)
    assert new.expires_at == new.absolute_expires_at


def test_refresh_fails_after_idle_window(make_user, test_db_session):
    user = make_user()
    _, token = service.create_session(test_db_session, user, now=NOW)
    with pytest.raises(AuthError):
        service.rotate_refresh(
            test_db_session, token, now=NOW + timedelta(hours=settings.session_idle_ttl_hours, seconds=1)
        )


def test_reuse_outside_race_window_revokes_family(make_user, test_db_session):
    user = make_user()
    _, token = service.create_session(test_db_session, user, now=NOW)
    _, new, new_token = service.rotate_refresh(test_db_session, token, now=NOW)
    with pytest.raises(AuthError) as exc:
        service.rotate_refresh(test_db_session, token, now=NOW + timedelta(seconds=30))
    assert not isinstance(exc.value, RefreshRaceError)
    test_db_session.refresh(new)
    assert new.revoked_at is not None
    with pytest.raises(AuthError):
        service.rotate_refresh(test_db_session, new_token, now=NOW + timedelta(seconds=31))


def test_reuse_inside_race_window_does_not_revoke(make_user, test_db_session):
    user = make_user()
    _, token = service.create_session(test_db_session, user, now=NOW)
    _, new, _ = service.rotate_refresh(test_db_session, token, now=NOW)
    with pytest.raises(RefreshRaceError):
        service.rotate_refresh(test_db_session, token, now=NOW + timedelta(seconds=5))
    test_db_session.refresh(new)
    assert new.revoked_at is None


def test_refresh_for_inactive_user_fails(make_user, test_db_session):
    user = make_user()
    _, token = service.create_session(test_db_session, user, now=NOW)
    user.is_active = False
    with pytest.raises(AuthError):
        service.rotate_refresh(test_db_session, token, now=NOW)


def test_unknown_refresh_token_fails(test_db_session):
    with pytest.raises(AuthError):
        service.rotate_refresh(test_db_session, "does-not-exist", now=NOW)


def test_logout_revokes_session(make_user, test_db_session):
    user = make_user()
    session, token = service.create_session(test_db_session, user, now=NOW)
    service.revoke_session_by_token(test_db_session, token, now=NOW)
    assert session.revoked_at == NOW


# --- loading the user for each request -------------------------------------------


def test_load_active_user_checks_version_and_active(make_user, test_db_session):
    user = make_user()
    assert service.load_active_user(test_db_session, user.id, 0).id == user.id
    assert service.load_active_user(test_db_session, user.id, 1) is None
    user.is_active = False
    assert service.load_active_user(test_db_session, user.id, 0) is None
    assert service.load_active_user(test_db_session, 999999, 0) is None
