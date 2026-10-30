# tests/auth/test_org_seat_lock.py
"""Two sign-ups at the same time for the last free seat: exactly one must succeed (SELECT ... FOR UPDATE).

Commits for real (two connections cannot share the rolled-back test transaction) and removes its users and
organization before and after running.
"""

import threading
import time

from sqlalchemy.orm import sessionmaker

from api.app.auth import organizations as orgs
from radar_db.accounts import create_user
from radar_db.models import Organization, User

from .conftest import TEST_PASSWORD

ORG_NAME = "Test Org Seat Lock"
ACTOR = "seat-lock-admin"
USERNAMES = ("seat-lock-a", "seat-lock-b")


def _cleanup(make_session) -> None:
    """Members first (their RESTRICT foreign key blocks deleting the company), then the company and the admin."""
    db = make_session()
    try:
        db.query(User).filter(User.username.in_(USERNAMES)).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.name == ORG_NAME).delete(synchronize_session=False)
        db.query(User).filter(User.username == ACTOR).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_two_sign_ups_for_the_last_seat(test_db_engine, monkeypatch):
    make_session = sessionmaker(bind=test_db_engine)
    _cleanup(make_session)
    setup = make_session()
    try:
        org = Organization(name=ORG_NAME, seat_limit=1)
        setup.add(org)
        actor = create_user(setup, username=ACTOR, password=TEST_PASSWORD, role="admin")
        setup.commit()
        org_id, actor_id = org.id, actor.id
    finally:
        setup.close()

    # Counting seats takes microseconds; pause between counting and inserting so both threads overlap.
    real_count = orgs.seats_used

    def slow_count(db, organization):
        used = real_count(db, organization)
        time.sleep(0.5)
        return used

    monkeypatch.setattr(orgs, "seats_used", slow_count)
    barrier = threading.Barrier(2)
    results = []
    lock = threading.Lock()

    def sign_up(username: str) -> None:
        db = make_session()
        outcome = "error"
        try:
            barrier.wait(timeout=10)
            data = {"username": username, "password": TEST_PASSWORD, "full_name": None, "email": None}
            # Each thread loads the admin on its own connection (objects cannot move between sessions).
            orgs.create_member(db, org_id, data, "viewer", db.get(User, actor_id))
            db.commit()
            outcome = "created"
        except orgs.OrgRuleError:
            db.rollback()
            outcome = "full"
        finally:
            db.close()
            with lock:
                results.append(outcome)

    try:
        threads = [threading.Thread(target=sign_up, args=(name,)) for name in USERNAMES]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        assert sorted(results) == ["created", "full"]
    finally:
        _cleanup(make_session)
