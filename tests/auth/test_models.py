# tests/auth/test_models.py
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from radar_db.models import EmailToken, User, UserSession


def _user(**overrides):
    values = dict(username="alice", password_hash="x", role="viewer")
    values.update(overrides)
    return User(**values)


def test_user_defaults(test_db_session):
    user = _user()
    test_db_session.add(user)
    test_db_session.flush()
    test_db_session.refresh(user)
    assert user.id is not None
    assert user.is_active is True
    assert user.token_version == 0
    assert user.password_is_bootstrap is False
    assert user.failed_login_count == 0


def test_username_is_unique(test_db_session):
    test_db_session.add(_user())
    test_db_session.flush()
    test_db_session.add(_user())
    with pytest.raises(IntegrityError):
        test_db_session.flush()


def test_role_check_constraint(test_db_session):
    test_db_session.add(_user(role="superuser"))
    with pytest.raises(IntegrityError):
        test_db_session.flush()


def test_session_belongs_to_user(test_db_session):
    user = _user()
    test_db_session.add(user)
    test_db_session.flush()
    now = datetime.now(timezone.utc)
    session = UserSession(
        user_id=user.id,
        token_hash="a" * 64,
        expires_at=now + timedelta(hours=48),
        absolute_expires_at=now + timedelta(days=7),
        created_at=now,
    )
    test_db_session.add(session)
    test_db_session.flush()
    assert isinstance(session.id, uuid.UUID)
    assert session.user.username == "alice"
    assert session.refresh_count == 0
    assert session.previous_token_hash is None and session.revoke_reason is None


def test_email_verification_columns_default_to_null(test_db_session):
    user = _user(email="a@ejemplo.com.ar")
    test_db_session.add(user)
    test_db_session.flush()
    assert user.email_verified_at is None
    assert user.terms_accepted_at is None


def test_email_is_unique_when_present(test_db_session):
    test_db_session.add(_user(username="uno", email="mismo@ejemplo.com.ar"))
    test_db_session.flush()
    test_db_session.add(_user(username="dos", email="mismo@ejemplo.com.ar"))
    with pytest.raises(IntegrityError):
        test_db_session.flush()


def test_users_without_email_do_not_collide(test_db_session):
    test_db_session.add(_user(username="uno"))
    test_db_session.add(_user(username="dos"))
    test_db_session.flush()


def _token(user, **overrides):
    values = dict(
        user_id=user.id,
        purpose="verify_email",
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    values.update(overrides)
    return EmailToken(**values)


def test_email_token_hash_is_unique(test_db_session):
    user = _user()
    test_db_session.add(user)
    test_db_session.flush()
    test_db_session.add(_token(user, token_hash="h" * 64))
    test_db_session.flush()
    test_db_session.add(_token(user, token_hash="h" * 64))
    with pytest.raises(IntegrityError):
        test_db_session.flush()


def test_email_token_purpose_is_checked(test_db_session):
    user = _user()
    test_db_session.add(user)
    test_db_session.flush()
    test_db_session.add(_token(user, purpose="something_else"))
    with pytest.raises(IntegrityError):
        test_db_session.flush()


def test_email_tokens_are_deleted_with_their_user(test_db_session):
    user = _user()
    test_db_session.add(user)
    test_db_session.flush()
    test_db_session.add(_token(user))
    test_db_session.flush()
    test_db_session.delete(user)
    test_db_session.flush()
    assert test_db_session.query(EmailToken).count() == 0
