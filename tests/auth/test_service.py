# tests/auth/test_service.py
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from api.app.auth import service
from api.app.auth.security import build_refresh_token, hash_refresh_token, parse_refresh_token
from api.app.auth.service import AuthError, RefreshRaceError
from api.app.config import settings
from radar_db.models import UserSession

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

IDLE = timedelta(hours=settings.session_idle_ttl_hours)


def _rows_of(db, user):
    """How many user_sessions rows the user has (one per login, whatever the number of refreshes)."""
    return db.query(UserSession).filter(UserSession.user_id == user.id).count()


def test_create_session_stores_the_login(make_user, test_db_session):
    user = make_user()
    session, token = service.create_session(test_db_session, user, user_agent="ua-login", ip="10.0.0.1", now=NOW)
    assert session.expires_at == NOW + IDLE
    assert session.absolute_expires_at == NOW + timedelta(days=settings.session_absolute_ttl_days)
    assert parse_refresh_token(token) == session.id
    assert session.token_hash == hash_refresh_token(token)
    assert session.refresh_count == 0 and session.previous_token_hash is None
    assert (session.ip, session.user_agent) == ("10.0.0.1", "ua-login")


def test_rotate_refresh_updates_the_same_row(make_user, test_db_session):
    user = make_user()
    session, token = service.create_session(test_db_session, user, user_agent="ua-login", ip="10.0.0.1", now=NOW)
    old_hash = session.token_hash
    later = NOW + timedelta(hours=1)
    got_user, rotated, new_token = service.rotate_refresh(
        test_db_session, token, user_agent="ua-other", ip="10.0.0.2", now=later
    )
    assert got_user.id == user.id and rotated.id == session.id
    assert _rows_of(test_db_session, user) == 1
    assert rotated.previous_token_hash == old_hash
    assert rotated.token_hash == hash_refresh_token(new_token) != old_hash
    assert parse_refresh_token(new_token) == session.id
    assert rotated.rotated_at == later and rotated.last_used_at == later
    assert rotated.refresh_count == 1
    assert rotated.expires_at == later + IDLE
    assert (rotated.ip, rotated.user_agent) == ("10.0.0.1", "ua-login")  # login data is kept


def test_idle_expiration_never_passes_absolute(make_user, test_db_session):
    user = make_user()
    _, token = service.create_session(test_db_session, user, now=NOW)
    near_end = NOW + timedelta(days=settings.session_absolute_ttl_days) - timedelta(hours=1)
    # Keep the login alive with refreshes every 40 h until near the absolute limit
    t = NOW
    while t + timedelta(hours=40) < near_end:
        t += timedelta(hours=40)
        _, _, token = service.rotate_refresh(test_db_session, token, now=t)
    _, session, _ = service.rotate_refresh(test_db_session, token, now=near_end)
    assert session.expires_at == session.absolute_expires_at


def test_refresh_fails_after_idle_window(make_user, test_db_session):
    user = make_user()
    _, token = service.create_session(test_db_session, user, now=NOW)
    with pytest.raises(AuthError, match="vencida"):
        service.rotate_refresh(test_db_session, token, now=NOW + IDLE + timedelta(seconds=1))


def test_old_token_of_an_expired_login_is_not_reuse(make_user, test_db_session):
    user = make_user()
    session, token = service.create_session(test_db_session, user, now=NOW)
    service.rotate_refresh(test_db_session, token, now=NOW)
    with pytest.raises(AuthError, match="vencida"):
        service.rotate_refresh(test_db_session, token, now=NOW + IDLE + timedelta(seconds=1))
    assert user.token_version == 0
    assert session.revoked_at is None


def test_reuse_inside_race_window_changes_nothing(make_user, test_db_session):
    user = make_user()
    session, token = service.create_session(test_db_session, user, now=NOW)
    service.rotate_refresh(test_db_session, token, now=NOW)
    before = (session.token_hash, session.previous_token_hash, session.refresh_count)
    with pytest.raises(RefreshRaceError):
        service.rotate_refresh(test_db_session, token, now=NOW + timedelta(seconds=5))
    assert (session.token_hash, session.previous_token_hash, session.refresh_count) == before
    assert session.revoked_at is None
    assert user.token_version == 0


def test_reuse_outside_race_window_closes_the_login(make_user, test_db_session):
    user = make_user()
    session, token = service.create_session(test_db_session, user, now=NOW)
    _, _, new_token = service.rotate_refresh(test_db_session, token, now=NOW)
    with pytest.raises(AuthError) as exc:
        service.rotate_refresh(test_db_session, token, now=NOW + timedelta(seconds=30))
    assert not isinstance(exc.value, RefreshRaceError)
    assert session.revoked_at == NOW + timedelta(seconds=30)
    assert session.revoke_reason == "reuse"
    assert user.token_version == 1
    # The attacker's (current) token is dead too
    with pytest.raises(AuthError):
        service.rotate_refresh(test_db_session, new_token, now=NOW + timedelta(seconds=31))


def test_reuse_invalidates_access_tokens_issued_before(make_user, test_db_session):
    user = make_user()
    _, token = service.create_session(test_db_session, user, now=NOW)
    version_in_access_token = user.token_version
    service.rotate_refresh(test_db_session, token, now=NOW)
    with pytest.raises(AuthError):
        service.rotate_refresh(test_db_session, token, now=NOW + timedelta(seconds=30))
    assert service.load_active_user(test_db_session, user.id, version_in_access_token) is None


def test_invented_secret_with_a_real_session_id_is_reuse(make_user, test_db_session):
    user = make_user()
    session, _ = service.create_session(test_db_session, user, now=NOW)
    forged = build_refresh_token(session.id)  # same id, another random secret
    with pytest.raises(AuthError):
        service.rotate_refresh(test_db_session, forged, now=NOW)
    assert session.revoke_reason == "reuse"
    assert user.token_version == 1


def test_refresh_for_inactive_user_closes_the_login(make_user, test_db_session):
    user = make_user()
    session, token = service.create_session(test_db_session, user, now=NOW)
    user.is_active = False
    with pytest.raises(AuthError):
        service.rotate_refresh(test_db_session, token, now=NOW)
    assert session.revoke_reason == "inactive_user"


def test_refresh_on_a_closed_login_has_no_side_effects(make_user, test_db_session):
    user = make_user()
    session, token = service.create_session(test_db_session, user, now=NOW)
    service.revoke_session_by_token(test_db_session, token, now=NOW)
    with pytest.raises(AuthError):
        service.rotate_refresh(test_db_session, token, now=NOW + timedelta(minutes=1))
    assert session.revoke_reason == "logout"
    assert user.token_version == 0


@pytest.mark.parametrize(
    "token",
    ["does-not-exist", "a.b", f"{uuid.uuid4().hex}.{'x' * 43}", f"{uuid.uuid4()}.{'x' * 43}"],
)
def test_malformed_or_unknown_refresh_token_fails(test_db_session, token):
    with pytest.raises(AuthError):
        service.rotate_refresh(test_db_session, token, now=NOW)


def test_logout_with_the_current_token_closes_the_login(make_user, test_db_session):
    user = make_user()
    session, token = service.create_session(test_db_session, user, now=NOW)
    service.revoke_session_by_token(test_db_session, token, now=NOW)
    assert session.revoked_at == NOW and session.revoke_reason == "logout"


def test_logout_with_the_previous_token_closes_the_login(make_user, test_db_session):
    user = make_user()
    session, token = service.create_session(test_db_session, user, now=NOW)
    service.rotate_refresh(test_db_session, token, now=NOW)
    service.revoke_session_by_token(test_db_session, token, now=NOW + timedelta(seconds=2))
    assert session.revoke_reason == "logout"


def test_logout_with_an_unknown_token_changes_nothing(make_user, test_db_session):
    user = make_user()
    session, _ = service.create_session(test_db_session, user, now=NOW)
    service.revoke_session_by_token(test_db_session, build_refresh_token(session.id), now=NOW)
    service.revoke_session_by_token(test_db_session, "garbage", now=NOW)
    assert session.revoked_at is None
    assert user.token_version == 0


# --- loading the user for each request -------------------------------------------


def test_load_active_user_checks_version_and_active(make_user, test_db_session):
    user = make_user()
    assert service.load_active_user(test_db_session, user.id, 0).id == user.id
    assert service.load_active_user(test_db_session, user.id, 1) is None
    user.is_active = False
    assert service.load_active_user(test_db_session, user.id, 0) is None
    assert service.load_active_user(test_db_session, 999999, 0) is None
