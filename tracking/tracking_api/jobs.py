"""Job store and runner.

Tracking a window is seconds of CPU, not milliseconds, so it is submitted
rather than awaited. The shape matters beyond timeouts: a synchronous call has
nowhere to report progress and no way to return partial results, and it
forecloses resuming from cached state later.

Deliberately in-memory and single-worker for v1:

* **In-memory** — jobs do not survive a restart. Acceptable while this is a
  single container and results are cheap to recompute; a client should treat a
  404 on poll as "resubmit", not as an error.
* **Single worker** — concurrency is explicitly out of scope. One worker makes
  the resource ceiling obvious instead of letting N simultaneous requests
  quietly exhaust the box. Raising it later is a one-line change here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class Job:
    job_id: str
    radar: str
    start: datetime
    end: datetime
    config: Dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    volumes_total: int = 0
    volumes_done: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    frames: Optional[List[Dict]] = None
    config_in_force: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    #: Set when the result was served from cache rather than recomputed.
    cached: bool = False

    @property
    def progress(self) -> float:
        if not self.volumes_total:
            return 0.0
        return round(self.volumes_done / self.volumes_total, 3)


def cache_key(radar: str, start: datetime, end: datetime, config: Dict[str, Any]) -> str:
    """Identity of a tracking run.

    The config participates because changing any knob changes the output — and
    `sort_keys` because two dicts with the same contents in a different order
    describe the same run and must not miss each other in the cache.
    """
    blob = json.dumps(
        {
            "radar": radar.upper(),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "config": config,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


class JobStore:
    """Thread-safe job registry with a bounded result cache."""

    def __init__(self, max_jobs: int = 50, max_cached: int = 20) -> None:
        self._jobs: "OrderedDict[str, Job]" = OrderedDict()
        self._cache: "OrderedDict[str, Job]" = OrderedDict()
        self._lock = threading.Lock()
        self._max_jobs = max_jobs
        self._max_cached = max_cached
        # One worker: see the module docstring. Jobs queue rather than compete.
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tracking")

    # -- registry ---------------------------------------------------------

    def create(self, radar: str, start: datetime, end: datetime,
               config: Dict[str, Any]) -> Job:
        job = Job(
            job_id=uuid.uuid4().hex[:16],
            radar=radar.upper(),
            start=start,
            end=end,
            config=config,
        )
        with self._lock:
            self._jobs[job.job_id] = job
            while len(self._jobs) > self._max_jobs:
                # Oldest first. A job still running is never evicted, or its
                # own completion would write into a dropped record.
                oldest, candidate = next(iter(self._jobs.items()))
                if candidate.status in (JobStatus.PENDING, JobStatus.RUNNING):
                    break
                self._jobs.pop(oldest)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def find_cached(self, key: str) -> Optional[Job]:
        with self._lock:
            job = self._cache.get(key)
            if job is not None:
                self._cache.move_to_end(key)
            return job

    def put_cached(self, key: str, job: Job) -> None:
        with self._lock:
            self._cache[key] = job
            while len(self._cache) > self._max_cached:
                self._cache.popitem(last=False)

    # -- execution --------------------------------------------------------

    def submit(self, job: Job, fn, *args, **kwargs) -> None:
        """Queue `fn` to populate `job`. Returns immediately."""
        self._pool.submit(self._run, job, fn, *args, **kwargs)

    def _run(self, job: Job, fn, *args, **kwargs) -> None:
        job.status = JobStatus.RUNNING
        try:
            fn(job, *args, **kwargs)
            job.status = JobStatus.DONE
        except Exception as exc:
            logger.error("job %s failed: %s", job.job_id, exc, exc_info=True)
            job.error = f"{type(exc).__name__}: {exc}"
            job.status = JobStatus.ERROR
        finally:
            job.finished_at = datetime.now(timezone.utc)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)


store = JobStore()
