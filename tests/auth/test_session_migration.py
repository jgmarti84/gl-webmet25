# tests/auth/test_session_migration.py
"""The one-row-per-login migration, run against the old user_sessions table in a throwaway schema.

Everything happens inside one transaction that is rolled back: the test database is left untouched.
"""

import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

MIGRATION = Path("/app/migrations/versions/20261027_a8b9c0d1e2f3_one_session_row_per_login.py")
SCHEMA = "session_migration_check"
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

# The user_sessions table as the previous migration (e7f8a9b0c1d2) left it, in its own schema.
# SET LOCAL makes every unqualified name in this transaction (and in the migration) resolve to that schema.
OLD_TABLES = f"""
CREATE SCHEMA {SCHEMA};
SET LOCAL search_path TO {SCHEMA};
CREATE TABLE users (id integer PRIMARY KEY);
CREATE TABLE user_sessions (
    id uuid PRIMARY KEY,
    user_id integer NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    family_id uuid NOT NULL,
    token_hash varchar(64) NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    absolute_expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    replaced_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    user_agent varchar(256),
    ip varchar(45)
);
CREATE INDEX ix_user_sessions_family_id ON user_sessions (family_id);
INSERT INTO users VALUES (1);
"""

COLUMNS = "SELECT column_name FROM information_schema.columns WHERE table_schema = :s AND table_name = 'user_sessions'"


def _load_migration():
    """Import the migration file by path (the versions folder is not a package)."""
    spec = importlib.util.spec_from_file_location("one_session_row_per_login", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, step) -> None:
    """Run upgrade() or downgrade() with alembic's `op` bound to this connection."""
    with Operations.context(MigrationContext.configure(conn)):
        step()


def _insert_family(conn, rows: int, *, still_open: bool) -> list:
    """One login rotated rows-1 times: a row every 30 min, each closed 30 min later except, maybe, the last."""
    family_id = uuid.uuid4()
    ids = []
    for i in range(rows):
        session_id = uuid.uuid4()
        created = T0 + timedelta(minutes=30 * i)
        revoked = None if (still_open and i == rows - 1) else created + timedelta(minutes=30)
        conn.execute(
            text(
                "INSERT INTO user_sessions (id, user_id, family_id, token_hash, expires_at, absolute_expires_at,"
                " revoked_at, created_at, last_used_at, user_agent, ip)"
                " VALUES (:id, 1, :family, :hash, :expires, :absolute, :revoked, :created, :created, 'ua', :ip)"
            ),
            {
                "id": session_id,
                "family": family_id,
                "hash": uuid.uuid4().hex * 2,
                "expires": created + timedelta(hours=48),
                "absolute": T0 + timedelta(days=7),
                "revoked": revoked,
                "created": created,
                "ip": f"10.0.0.{i}",
            },
        )
        ids.append(session_id)
    return ids


def _columns(conn) -> set:
    return set(conn.execute(text(COLUMNS), {"s": SCHEMA}).scalars())


@pytest.fixture
def old_schema(test_db_engine):
    """A connection inside a transaction with the old tables in their own schema; rolled back at the end."""
    conn = test_db_engine.connect()
    transaction = conn.begin()
    conn.execute(text(OLD_TABLES))
    try:
        yield conn
    finally:
        transaction.rollback()
        conn.close()


def test_upgrade_leaves_one_row_per_login(old_schema):
    conn = old_schema
    open_ids = _insert_family(conn, 3, still_open=True)
    closed_ids = _insert_family(conn, 2, still_open=False)

    _run(conn, _load_migration().upgrade)

    rows = {r["id"]: r for r in conn.execute(text("SELECT * FROM user_sessions")).mappings()}
    assert set(rows) == {open_ids[0], closed_ids[0]}  # the login (oldest) row of each family

    opened = rows[open_ids[0]]
    assert opened["refresh_count"] == 2
    assert opened["last_used_at"] == T0 + timedelta(minutes=60)
    assert opened["revoke_reason"] == "migration" and opened["revoked_at"] is not None
    assert opened["ip"] == "10.0.0.0"  # login data kept

    closed = rows[closed_ids[0]]
    assert closed["refresh_count"] == 1
    assert closed["revoked_at"] == T0 + timedelta(minutes=60)  # when the last token of the login closed
    assert closed["revoke_reason"] is None

    columns = _columns(conn)
    assert {"previous_token_hash", "rotated_at", "refresh_count", "revoke_reason"} <= columns
    assert not {"family_id", "replaced_by"} & columns


def test_downgrade_and_upgrade_again(old_schema):
    conn = old_schema
    _insert_family(conn, 2, still_open=True)
    migration = _load_migration()

    _run(conn, migration.upgrade)
    _run(conn, migration.downgrade)
    columns = _columns(conn)
    assert {"family_id", "replaced_by"} <= columns
    assert "refresh_count" not in columns
    assert conn.execute(text("SELECT bool_and(family_id = id) FROM user_sessions")).scalar() is True

    _run(conn, migration.upgrade)
    assert conn.execute(text("SELECT count(*) FROM user_sessions")).scalar() == 1
    _run(conn, migration.upgrade)  # a second upgrade on the new shape is a no-op
