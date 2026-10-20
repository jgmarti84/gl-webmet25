"""Resolve a radar + time window to an ordered list of NC cube files.

This is what replaces gl-tracker's directory globbing. ``grilla.listar()`` uses
a non-recursive ``glob("*.nc")``, which cannot see radarlib's
``{RADAR}/YYYY/MM/DD/`` layout at all; querying the index instead sidesteps that
and gives a guaranteed chronological order, which ``pipeline.procesar()``
depends on.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from radar_db.models import NCCube, COGStatus
from tracking_api.config import settings

logger = logging.getLogger(__name__)


@dataclass
class Volume:
    """One cube to process."""

    timestamp: datetime
    path: str
    #: True for volumes processed only to warm up velocity history, whose
    #: output is discarded. See `resolve_window`.
    lead_in: bool = False


@dataclass
class Availability:
    """What the index knows about a radar's cubes."""

    radar_code: str
    count: int
    min_time: Optional[datetime]
    max_time: Optional[datetime]


def availability(session: Session, radar_code: Optional[str] = None) -> List[Availability]:
    """Per-radar cube coverage.

    ``min_time`` is the frontend's lower bound: tracking cannot go further back
    than the oldest cube that survived radarlib's retention sweep.
    """
    from sqlalchemy import func

    q = session.query(
        NCCube.radar_code,
        func.count(NCCube.id),
        func.min(NCCube.observation_time),
        func.max(NCCube.observation_time),
    ).filter(NCCube.status == COGStatus.AVAILABLE)

    if radar_code:
        q = q.filter(NCCube.radar_code == radar_code.upper())

    rows = q.group_by(NCCube.radar_code).order_by(NCCube.radar_code).all()
    return [Availability(code, count, lo, hi) for code, count, lo, hi in rows]


def resolve_window(
    session: Session,
    radar_code: str,
    start: datetime,
    end: datetime,
    lead_in: Optional[int] = None,
) -> List[Volume]:
    """Cubes covering [start, end], preceded by lead-in volumes.

    The lead-in exists because tracking has a warm-up. Association needs one
    previous volume and the velocity fit uses up to
    ``Config.velocity_history_len`` (4) of them, so a run that simply starts at
    ``start`` reports every system in its first frame as
    SPONTANEOUS_GENERATION with no velocity and no forecast — which looks like
    a bug and is not. Processing a few earlier volumes and discarding their
    output means the first *returned* frame is already warm.

    Lead-in volumes further back than ``Config.max_gap_tracking_min`` are
    harmless: ``procesar()`` resets tracking on its own when the gap is too
    wide, so no special handling is needed here.

    Returns volumes in ascending time order, lead-in first.
    """
    radar_code = radar_code.upper()
    lead_in = settings.lead_in_volumes if lead_in is None else lead_in

    in_window = (
        session.query(NCCube.observation_time, NCCube.file_path)
        .filter(
            NCCube.radar_code == radar_code,
            NCCube.status == COGStatus.AVAILABLE,
            NCCube.observation_time >= start,
            NCCube.observation_time <= end,
        )
        .order_by(NCCube.observation_time.asc())
        .all()
    )

    if not in_window:
        # Nothing to warm up for. Returning lead-in volumes here would make the
        # caller process them and then discard every one, and the gap reset in
        # procesar() would have thrown the state away regardless.
        logger.info(
            "resolved %s %s..%s -> no volumes in window", radar_code, start, end
        )
        return []

    preceding = []
    if lead_in > 0:
        preceding = (
            session.query(NCCube.observation_time, NCCube.file_path)
            .filter(
                NCCube.radar_code == radar_code,
                NCCube.status == COGStatus.AVAILABLE,
                NCCube.observation_time < start,
            )
            .order_by(NCCube.observation_time.desc())
            .limit(lead_in)
            .all()
        )
        preceding.reverse()  # back to ascending

    volumes = [Volume(ts, path, lead_in=True) for ts, path in preceding]
    volumes += [Volume(ts, path, lead_in=False) for ts, path in in_window]

    logger.info(
        "resolved %s %s..%s -> %d volume(s) (%d lead-in)",
        radar_code, start, end, len(volumes), len(preceding),
    )
    return volumes


def missing_on_disk(volumes: List[Volume]) -> List[Volume]:
    """Volumes whose file the index knows about but disk does not.

    The retention sweep and the indexer's prune pass are not synchronised, so
    there is a window where a row outlives its file. Checking up front turns
    that into a clear error rather than a failure partway through a job.
    """
    return [v for v in volumes if not os.path.isfile(v.path)]
