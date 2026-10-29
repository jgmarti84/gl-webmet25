"""Tests for the job store and cache keying.

The cache key is the part worth pinning: too loose and a client gets another
run's results, too tight and the cache never hits.
"""

from datetime import datetime, timedelta, timezone

import pytest

from tracking_api.jobs import Job, JobStatus, JobStore, cache_key

T0 = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(hours=1)
CFG = {"cappi_height_m": 2500.0, "dbz_threshold": 35.0, "min_area_km2": 50.0}


class TestCacheKey:
    def test_is_deterministic(self):
        assert cache_key("RMA1", T0, T1, CFG) == cache_key("RMA1", T0, T1, CFG)

    def test_ignores_dict_ordering(self):
        """Same config written in another order is the same run."""
        reordered = {k: CFG[k] for k in reversed(list(CFG))}
        assert cache_key("RMA1", T0, T1, CFG) == cache_key("RMA1", T0, T1, reordered)

    def test_radar_case_does_not_split_the_cache(self):
        assert cache_key("rma1", T0, T1, CFG) == cache_key("RMA1", T0, T1, CFG)

    def test_differs_by_radar(self):
        assert cache_key("RMA1", T0, T1, CFG) != cache_key("RMA7", T0, T1, CFG)

    def test_differs_by_start(self):
        assert cache_key("RMA1", T0, T1, CFG) != cache_key("RMA1", T0 + timedelta(minutes=1), T1, CFG)

    def test_differs_by_end(self):
        assert cache_key("RMA1", T0, T1, CFG) != cache_key("RMA1", T0, T1 + timedelta(minutes=1), CFG)

    @pytest.mark.parametrize("field", ["cappi_height_m", "dbz_threshold", "min_area_km2"])
    def test_differs_by_every_config_knob(self, field):
        """Any knob changes the output, so any knob must change the key."""
        other = dict(CFG, **{field: CFG[field] + 1})
        assert cache_key("RMA1", T0, T1, CFG) != cache_key("RMA1", T0, T1, other)

    def test_differs_by_forecast_growth_switch(self):
        """Growth on and off give different forecasts: two cache entries."""
        on, off = dict(CFG, apply_scale=True), dict(CFG, apply_scale=False)
        assert cache_key("RMA1", T0, T1, on) != cache_key("RMA1", T0, T1, off)


class TestJobStore:
    def test_create_assigns_an_id(self):
        assert JobStore().create("RMA1", T0, T1, CFG).job_id

    def test_create_normalises_radar_case(self):
        assert JobStore().create("rma1", T0, T1, CFG).radar == "RMA1"

    def test_new_job_is_pending(self):
        assert JobStore().create("RMA1", T0, T1, CFG).status is JobStatus.PENDING

    def test_get_returns_the_job(self):
        store = JobStore()
        job = store.create("RMA1", T0, T1, CFG)
        assert store.get(job.job_id) is job

    def test_get_unknown_returns_none(self):
        assert JobStore().get("nope") is None

    def test_evicts_oldest_beyond_the_cap(self):
        store = JobStore(max_jobs=3)
        made = []
        for _ in range(5):
            job = store.create("RMA1", T0, T1, CFG)
            job.status = JobStatus.DONE      # only finished jobs are evictable
            made.append(job)
        assert store.get(made[0].job_id) is None

    def test_does_not_evict_a_running_job(self):
        """Evicting it would mean its completion writes into a dropped record."""
        store = JobStore(max_jobs=2)
        running = store.create("RMA1", T0, T1, CFG)
        running.status = JobStatus.RUNNING
        for _ in range(4):
            store.create("RMA1", T0, T1, CFG).status = JobStatus.DONE
        assert store.get(running.job_id) is running


class TestResultCache:
    def test_round_trips(self):
        store = JobStore()
        job = store.create("RMA1", T0, T1, CFG)
        store.put_cached("k", job)
        assert store.find_cached("k") is job

    def test_miss_returns_none(self):
        assert JobStore().find_cached("absent") is None

    def test_evicts_least_recently_used(self):
        store = JobStore(max_cached=2)
        for key in ("a", "b", "c"):
            store.put_cached(key, store.create("RMA1", T0, T1, CFG))
        assert store.find_cached("a") is None

    def test_lookup_refreshes_recency(self):
        store = JobStore(max_cached=2)
        for key in ("a", "b"):
            store.put_cached(key, store.create("RMA1", T0, T1, CFG))
        store.find_cached("a")                       # a is now most recent
        store.put_cached("c", store.create("RMA1", T0, T1, CFG))
        assert store.find_cached("a") is not None and store.find_cached("b") is None


class TestProgress:
    def test_zero_volumes_is_not_a_division_error(self):
        assert Job("i", "RMA1", T0, T1, CFG).progress == 0.0

    def test_reports_fraction(self):
        job = Job("i", "RMA1", T0, T1, CFG)
        job.volumes_total, job.volumes_done = 8, 2
        assert job.progress == 0.25


class TestExecution:
    def test_runs_the_callable_and_marks_done(self):
        store = JobStore()
        job = store.create("RMA1", T0, T1, CFG)
        store.submit(job, lambda j: setattr(j, "frames", []))
        store._pool.shutdown(wait=True)
        assert job.status is JobStatus.DONE

    def test_failure_is_captured_not_raised(self):
        """One bad job must not take the worker thread down."""
        store = JobStore()
        job = store.create("RMA1", T0, T1, CFG)

        def boom(j):
            raise ValueError("nope")

        store.submit(job, boom)
        store._pool.shutdown(wait=True)
        assert job.status is JobStatus.ERROR and "nope" in job.error

    def test_finished_at_is_set_on_failure_too(self):
        store = JobStore()
        job = store.create("RMA1", T0, T1, CFG)
        store.submit(job, lambda j: 1 / 0)
        store._pool.shutdown(wait=True)
        assert job.finished_at is not None
