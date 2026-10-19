# tests/auth/test_models.py
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from radar_db.models import User, UserSession


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
        family_id=uuid.uuid4(),
        token_hash="a" * 64,
        expires_at=now + timedelta(hours=48),
        absolute_expires_at=now + timedelta(days=7),
        created_at=now,
    )
    test_db_session.add(session)
    test_db_session.flush()
    assert isinstance(session.id, uuid.UUID)
    assert session.user.username == "alice"
