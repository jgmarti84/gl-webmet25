"""Tests for the NC cube watcher.

Covers the two things the parser and registrar tests cannot: recursive
discovery over radarlib's ``{RADAR}/YYYY/MM/DD/`` layout, and the prune pass
that keeps rows from outliving their files.
"""

import pytest

from indexer.watcher import NCCubeWatcher
from radar_db.models import NCCube, COGStatus


def _cube(root, day, name):
    d = root / "RMA1" / day
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_bytes(b"\x89HDF\r\n\x1a\n" + b"0" * 512)
    return p


@pytest.fixture()
def cube_root(tmp_path):
    """Two cubes in different day directories, plus files that must be ignored."""
    root = tmp_path / "nccube"
    _cube(root, "2026/04/01", "RMA1_0315_01_20260401T205000Z_NCCUBE.nc")
    _cube(root, "2026/04/02", "RMA1_0315_01_20260402T205000Z_NCCUBE.nc")
    _cube(root, "2026/04/02", "RMA1_0315_01_20260402T205000Z_DBZH.tif")
    _cube(root, "2026/04/02", "garbage_NCCUBE.nc")
    return root


class TestDiscovery:
    def test_finds_cubes_across_day_directories(self, cube_root):
        """Backfill writes into older day dirs, so the walk must be recursive."""
        found = NCCubeWatcher(str(cube_root)).discover_files()
        assert len(found) == 3  # two valid + one unparseable, all *_NCCUBE.nc

    def test_ignores_other_products(self, cube_root):
        names = [p.name for p in NCCubeWatcher(str(cube_root)).discover_files()]
        assert not any(n.endswith(".tif") for n in names)

    def test_missing_directory_returns_zero(self, test_db_session, tmp_path):
        """The cube dir only exists once a radar has ADD_NCCUBE enabled."""
        watcher = NCCubeWatcher(str(tmp_path / "absent"))
        assert watcher.run_scan(test_db_session) == 0


class TestScan:
    def test_registers_valid_cubes(self, test_db_session, cube_root):
        """The return value counts files registered, so the unparseable one
        is excluded even though discovery picked it up."""
        watcher = NCCubeWatcher(str(cube_root))
        assert watcher.run_scan(test_db_session) == 2

    def test_creates_rows_only_for_parseable_names(self, test_db_session, cube_root):
        NCCubeWatcher(str(cube_root)).run_scan(test_db_session)
        assert test_db_session.query(NCCube).count() == 2

    def test_rescan_registers_nothing_new(self, test_db_session, cube_root):
        watcher = NCCubeWatcher(str(cube_root))
        watcher.run_scan(test_db_session)
        assert watcher.run_scan(test_db_session) == 0

    def test_rescan_does_not_duplicate_rows(self, test_db_session, cube_root):
        watcher = NCCubeWatcher(str(cube_root))
        watcher.run_scan(test_db_session)
        watcher.run_scan(test_db_session)
        assert test_db_session.query(NCCube).count() == 2


class TestPrune:
    """Rows must not outlive their files — cubes are deleted, not marked."""

    def _scan_then_prune(self, session, root, doomed):
        watcher = NCCubeWatcher(str(root))
        watcher.run_scan(session)
        doomed.unlink()
        watcher._prune_cycles = watcher._prune_interval - 1  # force the pass
        watcher.run_scan(session)
        return watcher

    def test_removes_row_for_deleted_file(self, test_db_session, cube_root):
        doomed = cube_root / "RMA1/2026/04/01/RMA1_0315_01_20260401T205000Z_NCCUBE.nc"
        self._scan_then_prune(test_db_session, cube_root, doomed)
        remaining = test_db_session.query(NCCube).filter_by(file_path=str(doomed)).first()
        assert remaining is None

    def test_keeps_rows_for_surviving_files(self, test_db_session, cube_root):
        doomed = cube_root / "RMA1/2026/04/01/RMA1_0315_01_20260401T205000Z_NCCUBE.nc"
        self._scan_then_prune(test_db_session, cube_root, doomed)
        assert test_db_session.query(NCCube).count() == 1

    def test_does_not_mark_missing(self, test_db_session, cube_root):
        """Explicitly not the COG/TopsAndCores behaviour."""
        doomed = cube_root / "RMA1/2026/04/01/RMA1_0315_01_20260401T205000Z_NCCUBE.nc"
        self._scan_then_prune(test_db_session, cube_root, doomed)
        missing = test_db_session.query(NCCube).filter_by(status=COGStatus.MISSING).count()
        assert missing == 0

    def test_reappearing_file_is_reindexed(self, test_db_session, cube_root):
        """Pruning must clear the in-process set, or a restored cube stays invisible."""
        doomed = cube_root / "RMA1/2026/04/01/RMA1_0315_01_20260401T205000Z_NCCUBE.nc"
        watcher = self._scan_then_prune(test_db_session, cube_root, doomed)
        _cube(cube_root, "2026/04/01", doomed.name)
        assert watcher.run_scan(test_db_session) == 1
