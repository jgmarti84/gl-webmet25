"""Tests for the NC cube registrar.

Two behaviours here differ from the COG/TopsAndCores registrars and are the
reason this file exists: the file is never opened (metadata comes from the name
plus stat()), and rows for vanished files are deleted rather than marked
MISSING.
"""

from datetime import datetime, timezone

import pytest

from indexer.parser import NCCubeFilenameParser
from indexer.registrar import NCCubeRegistrar
from radar_db.models import NCCube, COGStatus

CUBE_NAME = "RMA1_0315_01_20260401T205000Z_NCCUBE.nc"


@pytest.fixture()
def cube_file(tmp_path):
    """A plausible cube on disk. Contents are irrelevant — never opened."""
    day = tmp_path / "RMA1" / "2026" / "04" / "01"
    day.mkdir(parents=True)
    path = day / CUBE_NAME
    path.write_bytes(b"\x89HDF\r\n\x1a\n" + b"0" * 2048)
    return path


def _register(session, path):
    parsed = NCCubeFilenameParser().parse(str(path))
    NCCubeRegistrar(session).register(str(path), parsed)
    return session.query(NCCube).filter_by(file_path=str(path)).first()


def test_register_creates_record(test_db_session, cube_file):
    assert _register(test_db_session, cube_file) is not None


def test_register_sets_radar_code(test_db_session, cube_file):
    assert _register(test_db_session, cube_file).radar_code == "RMA1"


def test_register_sets_observation_time_from_filename(test_db_session, cube_file):
    record = _register(test_db_session, cube_file)
    assert record.observation_time == datetime(2026, 4, 1, 20, 50, 0, tzinfo=timezone.utc)


def test_register_sets_strategy_and_vol_nr(test_db_session, cube_file):
    record = _register(test_db_session, cube_file)
    assert (record.strategy, record.vol_nr) == ("0315", "01")


def test_register_sets_status_available(test_db_session, cube_file):
    assert _register(test_db_session, cube_file).status == COGStatus.AVAILABLE


def test_register_records_file_size_from_stat(test_db_session, cube_file):
    """Size comes from stat(), proving the file itself is never parsed."""
    record = _register(test_db_session, cube_file)
    assert record.file_size_bytes == cube_file.stat().st_size


def test_register_records_file_mtime(test_db_session, cube_file):
    assert _register(test_db_session, cube_file).file_mtime is not None


def test_register_stores_absolute_path(test_db_session, cube_file):
    assert _register(test_db_session, cube_file).file_path == str(cube_file)


def test_register_is_idempotent(test_db_session, cube_file):
    """Restarting the indexer must not duplicate rows."""
    parsed = NCCubeFilenameParser().parse(str(cube_file))
    registrar = NCCubeRegistrar(test_db_session)
    registrar.register(str(cube_file), parsed)
    registrar.register(str(cube_file), parsed)
    count = test_db_session.query(NCCube).filter_by(file_path=str(cube_file)).count()
    assert count == 1


def test_register_skips_unknown_radar(test_db_session, tmp_path):
    """An unknown radar would violate the FK; it should skip, not raise."""
    path = tmp_path / "ZZZ9_0315_01_20260401T205000Z_NCCUBE.nc"
    path.write_bytes(b"x")
    parsed = NCCubeFilenameParser().parse(str(path))
    NCCubeRegistrar(test_db_session).register(str(path), parsed)
    assert test_db_session.query(NCCube).filter_by(file_path=str(path)).first() is None


def test_register_skips_vanished_file(test_db_session, cube_file):
    """A cube pruned between discovery and registration must not be indexed."""
    parsed = NCCubeFilenameParser().parse(str(cube_file))
    cube_file.unlink()
    NCCubeRegistrar(test_db_session).register(str(cube_file), parsed)
    assert test_db_session.query(NCCube).filter_by(file_path=str(cube_file)).first() is None


def test_delete_record_removes_row(test_db_session, cube_file):
    """Cubes are deleted, not marked MISSING — see the registrar docstring."""
    _register(test_db_session, cube_file)
    NCCubeRegistrar(test_db_session).delete_record(str(cube_file))
    assert test_db_session.query(NCCube).filter_by(file_path=str(cube_file)).first() is None


def test_delete_record_reports_true_when_removed(test_db_session, cube_file):
    _register(test_db_session, cube_file)
    assert NCCubeRegistrar(test_db_session).delete_record(str(cube_file)) is True


def test_delete_record_reports_false_when_absent(test_db_session, tmp_path):
    registrar = NCCubeRegistrar(test_db_session)
    assert registrar.delete_record(str(tmp_path / "nope.nc")) is False
