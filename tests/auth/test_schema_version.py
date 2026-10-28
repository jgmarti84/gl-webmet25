# tests/auth/test_schema_version.py
"""`manage init` must apply pending migrations on a versioned database instead of stamping over them."""

import pytest
from sqlalchemy import create_engine, text

from radar_db import database as database_module
from radar_db.database import _is_versioned, sync_alembic_version


class FakeCommand:
    """Stands in for alembic.command: records which of upgrade/stamp was called, and can fail the upgrade."""

    def __init__(self, fail_upgrade=False):
        self.calls = []
        self.fail_upgrade = fail_upgrade

    def upgrade(self, cfg, target):
        self.calls.append(("upgrade", target))
        if self.fail_upgrade:
            raise RuntimeError("migration failed")

    def stamp(self, cfg, target):
        self.calls.append(("stamp", target))


def test_database_with_a_version_row_is_versioned(test_db_engine):
    assert _is_versioned(test_db_engine) is True


def test_database_without_the_alembic_table_is_not_versioned():
    assert _is_versioned(create_engine("sqlite://")) is False


def test_empty_alembic_table_is_not_versioned():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    assert _is_versioned(engine) is False


def test_versioned_database_is_upgraded_not_stamped(monkeypatch, test_db_engine):
    fake = FakeCommand()
    monkeypatch.setattr(database_module, "command", fake)
    assert sync_alembic_version(test_db_engine, object()) == "upgraded"
    assert fake.calls == [("upgrade", "head")]


def test_unversioned_database_is_stamped(monkeypatch):
    fake = FakeCommand()
    monkeypatch.setattr(database_module, "command", fake)
    assert sync_alembic_version(create_engine("sqlite://"), object()) == "stamped"
    assert fake.calls == [("stamp", "head")]


def test_a_failed_upgrade_is_not_hidden_by_a_stamp(monkeypatch, test_db_engine):
    fake = FakeCommand(fail_upgrade=True)
    monkeypatch.setattr(database_module, "command", fake)
    with pytest.raises(RuntimeError):
        sync_alembic_version(test_db_engine, object())
    assert ("stamp", "head") not in fake.calls
