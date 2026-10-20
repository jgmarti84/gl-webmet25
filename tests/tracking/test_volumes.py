"""Tests for volume resolution.

The lead-in behaviour is the subtle part and the reason this file exists:
tracking has a warm-up, so a window resolved naively reports its first frame as
all-new with no velocity. These tests pin that the resolver compensates.
"""

from datetime import datetime, timedelta, timezone

import pytest

from radar_db.models import NCCube, COGStatus
from tracking_api.volumes import availability, missing_on_disk, resolve_window

T0 = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
CADENCE = timedelta(minutes=9)


@pytest.fixture()
def cubes(test_db_session, tmp_path):
    """Twelve RMA1 cubes at a 9-minute cadence, with files on disk."""
    made = []
    for i in range(12):
        ts = T0 + i * CADENCE
        path = tmp_path / f"RMA1_0315_01_{ts:%Y%m%dT%H%M%S}Z_NCCUBE.nc"
        path.write_bytes(b"x")
        row = NCCube(
            radar_code="RMA1",
            observation_time=ts,
            file_path=str(path),
            file_name=path.name,
            file_size_bytes=1,
            status=COGStatus.AVAILABLE,
            strategy="0315",
            vol_nr="01",
        )
        test_db_session.add(row)
        made.append((ts, path))
    test_db_session.flush()
    return made


class TestAvailability:
    def test_reports_the_radar(self, test_db_session, cubes):
        rows = availability(test_db_session, "RMA1")
        assert rows[0].radar_code == "RMA1"

    def test_counts_cubes(self, test_db_session, cubes):
        assert availability(test_db_session, "RMA1")[0].count == 12

    def test_min_time_is_the_frontend_lower_bound(self, test_db_session, cubes):
        assert availability(test_db_session, "RMA1")[0].min_time == T0

    def test_max_time(self, test_db_session, cubes):
        assert availability(test_db_session, "RMA1")[0].max_time == T0 + 11 * CADENCE

    def test_unknown_radar_returns_empty(self, test_db_session, cubes):
        """Never 404 — an unknown radar is simply no coverage."""
        assert availability(test_db_session, "ZZZ9") == []

    def test_radar_code_is_case_insensitive(self, test_db_session, cubes):
        assert availability(test_db_session, "rma1")[0].count == 12


class TestResolveWindow:
    def test_returns_volumes_in_the_window(self, test_db_session, cubes):
        vols = resolve_window(
            test_db_session, "RMA1", T0 + 5 * CADENCE, T0 + 7 * CADENCE, lead_in=0
        )
        assert [v.timestamp for v in vols] == [
            T0 + 5 * CADENCE, T0 + 6 * CADENCE, T0 + 7 * CADENCE
        ]

    def test_is_chronological(self, test_db_session, cubes):
        """procesar() mutates tracking state in order; reversal corrupts it."""
        vols = resolve_window(test_db_session, "RMA1", T0, T0 + 11 * CADENCE)
        stamps = [v.timestamp for v in vols]
        assert stamps == sorted(stamps)

    def test_prepends_lead_in_volumes(self, test_db_session, cubes):
        vols = resolve_window(
            test_db_session, "RMA1", T0 + 5 * CADENCE, T0 + 7 * CADENCE, lead_in=4
        )
        assert [v.timestamp for v in vols][0] == T0 + 1 * CADENCE

    def test_lead_in_volumes_are_flagged(self, test_db_session, cubes):
        """Their output is discarded, so the driver must be able to tell."""
        vols = resolve_window(
            test_db_session, "RMA1", T0 + 5 * CADENCE, T0 + 7 * CADENCE, lead_in=4
        )
        assert [v.lead_in for v in vols] == [True] * 4 + [False] * 3

    def test_lead_in_is_capped(self, test_db_session, cubes):
        vols = resolve_window(
            test_db_session, "RMA1", T0 + 5 * CADENCE, T0 + 5 * CADENCE, lead_in=2
        )
        assert sum(v.lead_in for v in vols) == 2

    def test_lead_in_at_start_of_record_is_not_an_error(self, test_db_session, cubes):
        """Nothing precedes the first cube; the window must still resolve."""
        vols = resolve_window(test_db_session, "RMA1", T0, T0 + CADENCE, lead_in=4)
        assert sum(v.lead_in for v in vols) == 0

    def test_zero_lead_in_returns_only_the_window(self, test_db_session, cubes):
        vols = resolve_window(
            test_db_session, "RMA1", T0 + 5 * CADENCE, T0 + 6 * CADENCE, lead_in=0
        )
        assert all(v.lead_in is False for v in vols)

    def test_empty_window_returns_nothing(self, test_db_session, cubes):
        far = T0 + timedelta(days=30)
        assert resolve_window(test_db_session, "RMA1", far, far + CADENCE) == []

    def test_window_bounds_are_inclusive(self, test_db_session, cubes):
        vols = resolve_window(test_db_session, "RMA1", T0, T0, lead_in=0)
        assert len(vols) == 1

    def test_other_radars_are_excluded(self, test_db_session, cubes, tmp_path):
        p = tmp_path / "RMA7_0315_01_20261020T120000Z_NCCUBE.nc"
        p.write_bytes(b"x")
        test_db_session.add(NCCube(
            radar_code="RMA7", observation_time=T0, file_path=str(p),
            file_name=p.name, status=COGStatus.AVAILABLE,
        ))
        test_db_session.flush()
        vols = resolve_window(test_db_session, "RMA1", T0, T0, lead_in=0)
        assert len(vols) == 1

    def test_non_available_cubes_are_excluded(self, test_db_session, cubes, tmp_path):
        p = tmp_path / "RMA1_0315_01_20261019T120000Z_NCCUBE.nc"
        p.write_bytes(b"x")
        test_db_session.add(NCCube(
            radar_code="RMA1", observation_time=T0 - CADENCE, file_path=str(p),
            file_name=p.name, status=COGStatus.ERROR,
        ))
        test_db_session.flush()
        vols = resolve_window(test_db_session, "RMA1", T0, T0, lead_in=4)
        assert sum(v.lead_in for v in vols) == 0


class TestMissingOnDisk:
    """Retention and the indexer prune are not synchronised, so a row can
    briefly outlive its file."""

    def test_detects_a_vanished_file(self, test_db_session, cubes):
        vols = resolve_window(test_db_session, "RMA1", T0, T0, lead_in=0)
        cubes[0][1].unlink()
        assert len(missing_on_disk(vols)) == 1

    def test_reports_nothing_when_all_present(self, test_db_session, cubes):
        vols = resolve_window(test_db_session, "RMA1", T0, T0 + CADENCE, lead_in=0)
        assert missing_on_disk(vols) == []
