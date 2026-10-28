# tests/auth/test_session_lock.py
"""Two refreshes with the same token at the same time must rotate the login once (SELECT ... FOR UPDATE).

This test commits for real (two connections cannot share the rolled-back test transaction) and deletes the
user it creates, with its sessions (ON DELETE CASCADE), before and after running.
"""

import threading
import time

from sqlalchemy.orm import sessionmaker

from api.app.auth import service
from api.app.auth.service import AuthError, RefreshRaceError
from radar_db.accounts import create_user
from radar_db.models import User, UserSession

from .conftest import TEST_PASSWORD

USERNAME = "lock-check"


def _delete_user(make_session) -> None:
    """Remove the test user and, through ON DELETE CASCADE, its sessions (leftovers of a failed run too)."""
    db = make_session()
    try:
        db.query(User).filter(User.username == USERNAME).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_two_concurrent_refreshes_rotate_once(test_db_engine, monkeypatch):
    make_session = sessionmaker(bind=test_db_engine)
    _delete_user(make_session)
    setup = make_session()
    try:
        user = create_user(setup, username=USERNAME, password=TEST_PASSWORD, role="viewer")
        session, token = service.create_session(setup, user)
        setup.commit()
        session_id = session.id
    finally:
        setup.close()

    # A refresh takes milliseconds, so two threads would rarely overlap on their own. Pause each rotation
    # between reading the row and writing it: without the lock both threads read the unrotated row and
    # both rotate; with the lock the second one waits for the first commit and sees the rotated row.
    real_build = service.build_refresh_token

    def slow_build(session_id):
        time.sleep(0.5)
        return real_build(session_id)

    monkeypatch.setattr(service, "build_refresh_token", slow_build)

    # Both threads wait at the barrier and then refresh with the same token, each on its own connection.
    barrier = threading.Barrier(2)
    results = []
    results_lock = threading.Lock()

    def refresh_once() -> None:
        db = make_session()
        outcome = "error"
        try:
            barrier.wait(timeout=10)
            service.rotate_refresh(db, token)
            db.commit()
            outcome = "rotated"
        except RefreshRaceError:
            db.rollback()
            outcome = "race"
        except AuthError:
            db.rollback()
            outcome = "auth_error"
        finally:
            db.close()
            with results_lock:
                results.append(outcome)

    try:
        threads = [threading.Thread(target=refresh_once) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert sorted(results) == ["race", "rotated"]
        check = make_session()
        try:
            assert check.get(UserSession, session_id).refresh_count == 1
        finally:
            check.close()
    finally:
        _delete_user(make_session)
