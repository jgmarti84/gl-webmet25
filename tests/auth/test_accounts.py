# tests/auth/test_accounts.py
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from radar_db.accounts import (
    AccountError,
    UsernameTakenError,
    bootstrap_admin,
    count_active_admins,
    create_user,
    revoke_all_sessions,
    set_password,
)
from radar_db.models import User, UserSession
from radar_db.passwords import PasswordPolicyError, verify_password

from .conftest import TEST_PASSWORD


def _open_session(db, user):
    now = datetime.now(timezone.utc)
    s = UserSession(
        user_id=user.id,
        token_hash=uuid.uuid4().hex * 2,
        expires_at=now + timedelta(hours=1),
        absolute_expires_at=now + timedelta(days=1),
        created_at=now,
    )
    db.add(s)
    db.flush()
    return s


def test_create_user_normalizes_and_hashes(test_db_session):
    user = create_user(test_db_session, username="  Alice ", password=TEST_PASSWORD, role="admin")
    assert user.username == "alice"
    assert user.role == "admin"
    assert user.token_version == 0
    assert verify_password(TEST_PASSWORD, user.password_hash)


@pytest.mark.parametrize("username", ["ab", "a" * 33, "bad name", "ñandú"])
def test_create_user_rejects_invalid_username(test_db_session, username):
    with pytest.raises(AccountError):
        create_user(test_db_session, username=username, password=TEST_PASSWORD, role="viewer")


def test_create_user_rejects_unknown_role(test_db_session):
    with pytest.raises(AccountError):
        create_user(test_db_session, username="alice", password=TEST_PASSWORD, role="root")


def test_create_user_rejects_weak_password(test_db_session):
    with pytest.raises(PasswordPolicyError):
        create_user(test_db_session, username="alice", password="short", role="viewer")


def test_create_user_rejects_duplicate(make_user, test_db_session):
    make_user(username="alice")
    with pytest.raises(UsernameTakenError):
        create_user(test_db_session, username="ALICE", password=TEST_PASSWORD, role="viewer")


def test_revoke_all_sessions_bumps_version_and_revokes(make_user, test_db_session):
    user = make_user()
    s1 = _open_session(test_db_session, user)
    s2 = _open_session(test_db_session, user)
    revoke_all_sessions(test_db_session, user)
    test_db_session.refresh(s1)
    test_db_session.refresh(s2)
    assert user.token_version == 1
    assert s1.revoked_at is not None and s2.revoked_at is not None
    assert s1.revoke_reason == "admin" and s2.revoke_reason == "admin"


def test_set_password_changes_hash_and_clears_bootstrap(make_user, test_db_session):
    user = make_user(password_is_bootstrap=True)
    user.failed_login_count = 3
    set_password(test_db_session, user, "another-long-password")
    assert verify_password("another-long-password", user.password_hash)
    assert user.password_is_bootstrap is False
    assert user.failed_login_count == 0
    assert user.token_version == 1


def test_count_active_admins_counts_only_active_admins(make_user, test_db_session):
    make_user(username="admin1", role="admin")
    inactive = make_user(username="admin2", role="admin")
    inactive.is_active = False
    make_user(username="viewer1", role="viewer")
    test_db_session.flush()
    assert count_active_admins(test_db_session) == 1


def test_bootstrap_admin_creates_when_empty(test_db_session):
    user = bootstrap_admin(test_db_session, "Admin", TEST_PASSWORD)
    assert user is not None
    assert user.username == "admin"
    assert user.role == "admin"
    assert user.password_is_bootstrap is True


def test_bootstrap_admin_noop_when_users_exist(make_user, test_db_session):
    make_user(username="someone")
    assert bootstrap_admin(test_db_session, "admin", TEST_PASSWORD) is None
    assert test_db_session.query(User).count() == 1


def test_bootstrap_admin_rejects_weak_password(test_db_session):
    with pytest.raises(PasswordPolicyError):
        bootstrap_admin(test_db_session, "admin", "short")
