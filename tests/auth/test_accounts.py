# tests/auth/test_accounts.py
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from radar_db.accounts import (
    AccountError,
    EmailTakenError,
    UsernameTakenError,
    bootstrap_admin,
    count_active_admins,
    create_user,
    find_by_identifier,
    get_user_by_email,
    normalize_email,
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


def test_normalize_email():
    assert normalize_email("  Ana@Ejemplo.COM.ar ") == "ana@ejemplo.com.ar"
    assert normalize_email("   ") is None
    assert normalize_email(None) is None


def test_create_user_is_verified_by_default(test_db_session):
    user = create_user(test_db_session, username="verif", password=TEST_PASSWORD, role="viewer")
    assert user.email_verified_at is not None


def test_create_user_can_be_pending_with_terms(test_db_session):
    user = create_user(
        test_db_session,
        username="pend",
        password=TEST_PASSWORD,
        role="viewer",
        email="PEND@ejemplo.com.ar",
        email_verified=False,
        terms_accepted=True,
    )
    assert user.email == "pend@ejemplo.com.ar"
    assert user.email_verified_at is None
    assert user.terms_accepted_at is not None


def test_create_user_rejects_a_taken_email(test_db_session):
    create_user(test_db_session, username="uno", password=TEST_PASSWORD, role="viewer", email="x@ejemplo.com.ar")
    with pytest.raises(EmailTakenError):
        create_user(test_db_session, username="dos", password=TEST_PASSWORD, role="viewer", email="X@ejemplo.com.ar")


def test_get_user_by_email_is_case_insensitive(test_db_session):
    user = create_user(test_db_session, username="uno", password=TEST_PASSWORD, role="viewer", email="x@ejemplo.com.ar")
    assert get_user_by_email(test_db_session, " X@Ejemplo.com.ar ").id == user.id
    assert get_user_by_email(test_db_session, "nadie@ejemplo.com.ar") is None
    assert get_user_by_email(test_db_session, "") is None


def test_find_by_identifier_uses_the_mail_only_when_it_has_an_at_sign(test_db_session):
    user = create_user(test_db_session, username="uno", password=TEST_PASSWORD, role="viewer", email="x@ejemplo.com.ar")
    assert find_by_identifier(test_db_session, "UNO").id == user.id
    assert find_by_identifier(test_db_session, "x@ejemplo.com.ar").id == user.id
    assert find_by_identifier(test_db_session, "uno@ejemplo.com.ar") is None
