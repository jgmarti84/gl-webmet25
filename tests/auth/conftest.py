# tests/auth/conftest.py
import pytest

from radar_db.accounts import create_user

TEST_PASSWORD = "correct-horse-battery"


@pytest.fixture
def make_user(test_db_session):
    """Factory that creates a user inside the rolled-back test transaction."""
    def _make(username="alice", role="viewer", password=TEST_PASSWORD, **kwargs):
        user = create_user(
            test_db_session, username=username, password=password, role=role, **kwargs
        )
        test_db_session.flush()
        return user
    return _make
