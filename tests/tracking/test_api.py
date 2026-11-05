"""Tests for the radar-scoped routes and the last_n limit.

The worker is replaced by a no-op, so these check routing, validation and
caching without running gl-tracker (which is not in this image).
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from radar_db.models import COGStatus, NCCube
from tracking_api import main as tracking_main
from tracking_api.config import settings
from tracking_api.db import get_db
from tracking_api.jobs import JobStatus, JobStore

T0 = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
WINDOW = {"start": T0.isoformat(), "end": (T0 + timedelta(hours=2)).isoformat()}


@pytest.fixture()
def client(test_db_session, monkeypatch):
    store = JobStore()
    monkeypatch.setattr(store, "submit", lambda job, fn: None)  # never run gl-tracker
    monkeypatch.setattr(tracking_main, "store", store)
    tracking_main.app.dependency_overrides[get_db] = lambda: test_db_session
    yield TestClient(tracking_main.app)
    tracking_main.app.dependency_overrides.clear()


@pytest.fixture()
def cube(test_db_session):
    row = NCCube(
        radar_code="RMA1", observation_time=T0, file_path="/nccube/x.nc",
        file_name="x.nc", status=COGStatus.AVAILABLE,
    )
    test_db_session.add(row)
    test_db_session.flush()
    return row


class TestRadarAvailability:
    def test_reports_the_radar_and_the_limit(self, client, cube):
        body = client.get("/api/tracking/radars/RMA1/availability").json()
        assert body["radar_code"] == "RMA1"
        assert body["count"] == 1
        assert body["max_last_n"] == settings.max_last_n

    def test_radar_without_cubes_is_200_with_zero(self, client):
        res = client.get("/api/tracking/radars/RMA9/availability")
        assert res.status_code == 200
        assert res.json()["count"] == 0

    def test_code_is_case_insensitive(self, client, cube):
        assert client.get("/api/tracking/radars/rma1/availability").json()["count"] == 1

    def test_rejects_a_malformed_code(self, client):
        assert client.get("/api/tracking/radars/RMA-1/availability").status_code == 422


class TestRadarJobs:
    def test_queues_a_job_with_last_n(self, client):
        res = client.post("/api/tracking/radars/RMA1/jobs", json={**WINDOW, "last_n": 3})
        assert res.status_code == 202
        body = res.json()
        assert body["radar"] == "RMA1"
        assert body["last_n"] == 3
        assert body["cached"] is False

    def test_poll_reports_last_n(self, client):
        job_id = client.post("/api/tracking/radars/RMA1/jobs",
                             json={**WINDOW, "last_n": 5}).json()["job_id"]
        assert client.get(f"/api/tracking/jobs/{job_id}").json()["last_n"] == 5

    def test_last_n_is_optional(self, client):
        res = client.post("/api/tracking/radars/RMA1/jobs", json=WINDOW)
        assert res.status_code == 202
        assert res.json()["last_n"] is None

    def test_last_n_above_the_cap_is_rejected(self, client):
        res = client.post("/api/tracking/radars/RMA1/jobs",
                          json={**WINDOW, "last_n": settings.max_last_n + 1})
        assert res.status_code == 422

    @pytest.mark.parametrize("bad", [0, -1])
    def test_last_n_must_be_positive(self, client, bad):
        res = client.post("/api/tracking/radars/RMA1/jobs", json={**WINDOW, "last_n": bad})
        assert res.status_code == 422

    def test_original_route_accepts_last_n(self, client):
        res = client.post("/api/tracking/jobs", json={**WINDOW, "radar": "RMA1", "last_n": 3})
        assert res.status_code == 202
        assert res.json()["last_n"] == 3

    def test_both_routes_share_the_cache(self, client, cube):
        """The same run through either route is one job."""
        first = client.post("/api/tracking/radars/RMA1/jobs", json={**WINDOW, "last_n": 3}).json()
        again = client.post("/api/tracking/jobs", json={**WINDOW, "radar": "rma1", "last_n": 3}).json()
        assert again["cached"] is True
        assert again["job_id"] == first["job_id"]

    def test_a_run_in_progress_is_shared(self, client, cube):
        """Identical requests arriving together do not queue the work twice."""
        first = client.post("/api/tracking/radars/RMA1/jobs", json={**WINDOW, "last_n": 3}).json()
        assert tracking_main.store.get(first["job_id"]).status.value == "pending"
        again = client.post("/api/tracking/radars/RMA1/jobs", json={**WINDOW, "last_n": 3}).json()
        assert again["job_id"] == first["job_id"]

    def test_a_different_window_with_the_same_volumes_hits_the_cache(self, client, cube):
        """Keyed on the volumes, not on the window that selected them."""
        first = client.post("/api/tracking/radars/RMA1/jobs", json={**WINDOW, "last_n": 3}).json()
        wider = {"start": (T0 - timedelta(hours=1)).isoformat(), "end": WINDOW["end"]}
        again = client.post("/api/tracking/radars/RMA1/jobs", json={**wider, "last_n": 3}).json()
        assert again["job_id"] == first["job_id"]

    def test_a_new_cube_in_the_same_window_starts_a_new_run(self, client, cube, test_db_session):
        """A live window can gain a cube after the first request; the result must include it."""
        first = client.post("/api/tracking/radars/RMA1/jobs", json={**WINDOW, "last_n": 3}).json()
        test_db_session.add(NCCube(
            radar_code="RMA1", observation_time=T0 + timedelta(minutes=9),
            file_path="/nccube/y.nc", file_name="y.nc", status=COGStatus.AVAILABLE,
        ))
        test_db_session.flush()
        again = client.post("/api/tracking/radars/RMA1/jobs", json={**WINDOW, "last_n": 3}).json()
        assert again["job_id"] != first["job_id"]
        assert again["cached"] is False

    def test_a_failed_run_is_not_reused(self, client, cube):
        first = client.post("/api/tracking/radars/RMA1/jobs", json={**WINDOW, "last_n": 3}).json()
        tracking_main.store.get(first["job_id"]).status = JobStatus.ERROR
        again = client.post("/api/tracking/radars/RMA1/jobs", json={**WINDOW, "last_n": 3}).json()
        assert again["job_id"] != first["job_id"]

    def test_the_job_keeps_the_resolved_volumes(self, client, cube):
        """The run processes exactly the volumes the cache key was built from."""
        first = client.post("/api/tracking/radars/RMA1/jobs", json={**WINDOW, "last_n": 3}).json()
        job = tracking_main.store.get(first["job_id"])
        assert [v.timestamp for v in job.volumes] == [T0]
