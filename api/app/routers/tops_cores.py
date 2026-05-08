# api/app/routers/tops_cores.py
"""
Tops and Cores endpoints.

Serves metadata records (query by radar + time range) and raw GeoJSON
feature content (by record ID) for convective cores and storm tops indexed
from the TopsAndCores GeoJSON files produced by radarlib.
"""
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from radar_db import get_db, TopsAndCores, COGStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tops-cores", tags=["Tops & Cores"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class TopsAndCoresRecord(BaseModel):
    """Metadata record for a single TopsAndCores GeoJSON file."""

    id: int
    radar_code: str
    observation_time: datetime
    file_name: str
    feature_count: int
    core_count: int
    top_count: int
    status: str
    strategy: Optional[str] = None
    vol_nr: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record_to_response(record: TopsAndCores) -> TopsAndCoresRecord:
    """Convert a TopsAndCores ORM object to its response schema."""
    return TopsAndCoresRecord(
        id=record.id,
        radar_code=record.radar_code,
        observation_time=record.observation_time,
        file_name=record.file_name,
        feature_count=record.feature_count,
        core_count=record.core_count,
        top_count=record.top_count,
        status=record.status.value if hasattr(record.status, "value") else str(record.status),
        strategy=record.strategy,
        vol_nr=record.vol_nr,
    )


# ---------------------------------------------------------------------------
# Endpoint 1 — Query records by radar + time range
# ---------------------------------------------------------------------------

@router.get("", response_model=List[TopsAndCoresRecord])
def list_tops_and_cores(
    response: Response,
    radar_codes: List[str] = Query(..., description="Radar codes to filter by"),
    time_from: datetime = Query(..., description="Start of time range (ISO 8601)"),
    time_to: datetime = Query(..., description="End of time range (ISO 8601)"),
    status: Optional[str] = Query(default="available", description="Status filter"),
    db: Session = Depends(get_db),
) -> List[TopsAndCoresRecord]:
    """
    Query TopsAndCores metadata records.

    Returns records whose ``radar_code`` is in ``radar_codes``, whose
    ``observation_time`` falls between ``time_from`` and ``time_to``
    (inclusive), and whose ``status`` matches the optional filter.

    Returns an empty list when no records match — never 404.
    """
    try:
        cog_status = COGStatus(status.lower()) if status else COGStatus.AVAILABLE
    except ValueError:
        cog_status = COGStatus.AVAILABLE

    records = (
        db.query(TopsAndCores)
        .filter(
            TopsAndCores.radar_code.in_(radar_codes),
            TopsAndCores.observation_time >= time_from,
            TopsAndCores.observation_time <= time_to,
            TopsAndCores.status == cog_status,
        )
        .order_by(TopsAndCores.observation_time.asc())
        .all()
    )

    response.headers["Cache-Control"] = "no-cache"
    return [_record_to_response(r) for r in records]


# ---------------------------------------------------------------------------
# Endpoint 2 — Fetch GeoJSON content by ID
# ---------------------------------------------------------------------------

@router.get("/{record_id}/features")
def get_tops_and_cores_features(
    record_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """
    Return the raw GeoJSON FeatureCollection for a TopsAndCores record.

    - 404 if the record does not exist or its file is missing on disk.
    - 500 if the GeoJSON cannot be parsed.
    - Supports conditional GET via ``ETag`` / ``If-None-Match`` (SHA-256 of
      file bytes) for efficient browser caching.
    - Immutable cache: ``Cache-Control: public, max-age=86400, immutable``.
    """
    record = db.query(TopsAndCores).filter(TopsAndCores.id == record_id).first()

    if record is None:
        raise HTTPException(status_code=404, detail="TopsAndCores record not found")

    if record.status == COGStatus.MISSING:
        raise HTTPException(status_code=404, detail="File not found on disk")

    file_path = Path(record.file_path)

    if not file_path.exists():
        # Update status to MISSING before returning 404
        try:
            record.status = COGStatus.MISSING
            db.commit()
        except Exception as exc:
            logger.warning(
                f"Failed to mark TopsAndCores id={record_id} as MISSING: {exc}"
            )
            db.rollback()
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Read raw bytes for ETag and content
    try:
        raw_bytes = file_path.read_bytes()
    except OSError as exc:
        logger.error(f"Cannot read TopsAndCores file {file_path}: {exc}")
        raise HTTPException(status_code=404, detail="File not found on disk")

    # ETag is SHA-256 of the raw file bytes (first 32 hex characters = 128 bits)
    etag = f'"{hashlib.sha256(raw_bytes).hexdigest()[:32]}"'

    cache_headers = {
        "Cache-Control": "public, max-age=86400, immutable",
        "ETag": etag,
    }

    # Conditional GET: return 304 if client's ETag matches
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers=cache_headers)

    # Parse GeoJSON to validate (raises 500 on malformed content)
    try:
        geojson = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        logger.error(
            f"Failed to parse GeoJSON for TopsAndCores id={record_id}: {exc}"
        )
        raise HTTPException(status_code=500, detail="GeoJSON parse error")

    return Response(
        content=json.dumps(geojson),
        media_type="application/geo+json",
        headers=cache_headers,
    )
