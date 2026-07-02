"""Admin CRUD endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import func

from radar_db import (
    COGStatus,
    Radar,
    RadarCOG,
    RadarProduct,
    Reference,
    TopsAndCores,
    get_db,
)
from radar_db.models import Estrategia, Volumen, ColormapStop, ProductColormapOption
from ..schemas.admin import (
    AdminBulkDeleteResponse,
    AdminCOGListResponse,
    AdminCOGPatchStatus,
    AdminCOGResponse,
    AdminColormapStopCreate,
    AdminColormapStopResponse,
    AdminColormapSummary,
    AdminColormapCreateFromHex,
    AdminEstrategiaCreate,
    AdminEstrategiaResponse,
    AdminEstrategiaUpdate,
    AdminProductColormapOptionCreate,
    AdminProductColormapOptionResponse,
    AdminRadarCreate,
    AdminRadarPatch,
    AdminRadarProductCreate,
    AdminRadarProductPatch,
    AdminRadarProductResponse,
    AdminRadarProductUpdate,
    AdminRadarResponse,
    AdminRadarUpdate,
    AdminReferenceCreate,
    AdminReferenceResponse,
    AdminReferenceUpdate,
    AdminTopsAndCoresListResponse,
    AdminTopsAndCoresPatchStatus,
    AdminTopsAndCoresResponse,
    AdminVolumenCreate,
    AdminVolumenResponse,
    AdminVolumenUpdate,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


# TODO: These endpoints currently rely on Nginx-level Basic Auth and need FastAPI auth dependencies before production deployment.


def _coerce_float(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _ensure_cog_status(status_value: str) -> COGStatus:
    try:
        return COGStatus(status_value.lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid status '{status_value}'"
        ) from exc


def _apply_changes(instance, values: dict) -> None:
    for key, value in values.items():
        setattr(instance, key, value)


def _commit_or_conflict(db: Session, conflict_detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=conflict_detail) from exc


def _radar_response(radar: Radar) -> AdminRadarResponse:
    return AdminRadarResponse(
        code=radar.code,
        title=radar.title,
        description=radar.description,
        center_lat=_coerce_float(radar.center_lat),
        center_long=_coerce_float(radar.center_long),
        img_radio=radar.img_radio,
        is_active=radar.is_active,
        detail_view_enabled=radar.detail_view_enabled,
        point1_lat=_coerce_float(radar.point1_lat),
        point1_long=_coerce_float(radar.point1_long),
        point2_lat=_coerce_float(radar.point2_lat),
        point2_long=_coerce_float(radar.point2_long),
        created_at=radar.created_at,
        updated_at=radar.updated_at,
    )


def _cog_response(cog: RadarCOG) -> AdminCOGResponse:
    return AdminCOGResponse(
        id=cog.id,
        radar_code=cog.radar_code,
        product_id=cog.product_id,
        product_key=cog.polarimetric_var
        or (cog.product.product_key if cog.product else None),
        observation_time=cog.observation_time,
        file_path=cog.file_path,
        file_name=cog.file_name,
        file_size_bytes=cog.file_size_bytes,
        file_checksum=cog.file_checksum,
        status=cog.status.value if hasattr(cog.status, "value") else str(cog.status),
        vol_nr=cog.vol_nr,
        polarimetric_var=cog.polarimetric_var,
        indexed_at=cog.indexed_at,
        error_message=cog.error_message,
        created_at=cog.created_at,
        updated_at=cog.updated_at,
    )


def _tops_cores_response(record: TopsAndCores) -> AdminTopsAndCoresResponse:
    return AdminTopsAndCoresResponse(
        id=record.id,
        radar_code=record.radar_code,
        observation_time=record.observation_time,
        file_path=record.file_path,
        file_name=record.file_name,
        feature_count=record.feature_count,
        core_count=record.core_count,
        top_count=record.top_count,
        status=(
            record.status.value
            if hasattr(record.status, "value")
            else str(record.status)
        ),
        strategy=record.strategy,
        vol_nr=record.vol_nr,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _apply_cog_filters(
    query,
    radar_code: Optional[str],
    product_key: Optional[str],
    status_value: Optional[str],
    vol_nr: Optional[str],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
):
    if radar_code:
        query = query.filter(RadarCOG.radar_code == radar_code)
    if product_key:
        query = query.filter(
            (RadarCOG.polarimetric_var == product_key)
            | (RadarCOG.product.has(RadarProduct.product_key == product_key))
        )
    if status_value:
        query = query.filter(RadarCOG.status == _ensure_cog_status(status_value))
    if vol_nr:
        query = query.filter(RadarCOG.vol_nr == vol_nr)
    if start_time:
        query = query.filter(RadarCOG.observation_time >= start_time)
    if end_time:
        query = query.filter(RadarCOG.observation_time <= end_time)
    return query


def _apply_tops_cores_filters(
    query,
    radar_code: Optional[str],
    strategy: Optional[str],
    vol_nr: Optional[str],
    status_value: Optional[str],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
):
    if radar_code:
        query = query.filter(TopsAndCores.radar_code == radar_code)
    if strategy:
        query = query.filter(TopsAndCores.strategy == strategy)
    if vol_nr:
        query = query.filter(TopsAndCores.vol_nr == vol_nr)
    if status_value:
        query = query.filter(TopsAndCores.status == _ensure_cog_status(status_value))
    if start_time:
        query = query.filter(TopsAndCores.observation_time >= start_time)
    if end_time:
        query = query.filter(TopsAndCores.observation_time <= end_time)
    return query


def _load_volumenes_or_422(db: Session, volumen_ids):
    volumenes = (
        db.query(Volumen).filter(Volumen.id.in_(volumen_ids)).all()
        if volumen_ids
        else []
    )
    if len(volumenes) != len(set(volumen_ids)):
        raise HTTPException(
            status_code=422, detail="One or more volumen IDs do not exist"
        )
    return volumenes


@router.get("/radars", response_model=list[AdminRadarResponse])
def admin_list_radars(db: Session = Depends(get_db)):
    """List all radars, including inactive records."""
    radars = db.query(Radar).order_by(Radar.code).all()
    return [_radar_response(radar) for radar in radars]


@router.get("/radars/{code}", response_model=AdminRadarResponse)
def admin_get_radar(code: str, db: Session = Depends(get_db)):
    """Get a single radar by code."""
    radar = db.query(Radar).filter(Radar.code == code).first()
    if radar is None:
        raise HTTPException(status_code=404, detail=f"Radar '{code}' not found")
    return _radar_response(radar)


@router.post(
    "/radars", response_model=AdminRadarResponse, status_code=status.HTTP_201_CREATED
)
def admin_create_radar(payload: AdminRadarCreate, db: Session = Depends(get_db)):
    """Create a new radar record."""
    radar = Radar(**payload.model_dump())
    db.add(radar)
    _commit_or_conflict(db, f"Radar with code '{payload.code}' already exists")
    db.refresh(radar)
    return _radar_response(radar)


@router.put("/radars/{code}", response_model=AdminRadarResponse)
def admin_update_radar(
    code: str, payload: AdminRadarUpdate, db: Session = Depends(get_db)
):
    """Update all editable fields for a radar."""
    radar = db.query(Radar).filter(Radar.code == code).first()
    if radar is None:
        raise HTTPException(status_code=404, detail=f"Radar '{code}' not found")
    _apply_changes(radar, payload.model_dump())
    _commit_or_conflict(db, f"Radar with code '{code}' could not be updated")
    db.refresh(radar)
    return _radar_response(radar)


@router.patch("/radars/{code}", response_model=AdminRadarResponse)
def admin_patch_radar(
    code: str, payload: AdminRadarPatch, db: Session = Depends(get_db)
):
    """Partially update radar fields."""
    radar = db.query(Radar).filter(Radar.code == code).first()
    if radar is None:
        raise HTTPException(status_code=404, detail=f"Radar '{code}' not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _radar_response(radar)
    _apply_changes(radar, changes)
    _commit_or_conflict(db, f"Radar with code '{code}' could not be updated")
    db.refresh(radar)
    return _radar_response(radar)


@router.delete("/radars/{code}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_radar(code: str, db: Session = Depends(get_db)):
    """Delete a radar by code."""
    radar = db.query(Radar).filter(Radar.code == code).first()
    if radar is None:
        raise HTTPException(status_code=404, detail=f"Radar '{code}' not found")
    db.delete(radar)
    _commit_or_conflict(db, f"Radar '{code}' could not be deleted")


@router.get("/products", response_model=list[AdminRadarProductResponse])
def admin_list_products(db: Session = Depends(get_db)):
    """List all radar products."""
    products = db.query(RadarProduct).order_by(RadarProduct.id).all()
    return [AdminRadarProductResponse.model_validate(product) for product in products]


@router.get("/products/{product_id}", response_model=AdminRadarProductResponse)
def admin_get_product(product_id: int, db: Session = Depends(get_db)):
    """Get a single product by ID."""
    product = db.query(RadarProduct).filter(RadarProduct.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")
    return AdminRadarProductResponse.model_validate(product)


@router.post(
    "/products",
    response_model=AdminRadarProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_product(
    payload: AdminRadarProductCreate, db: Session = Depends(get_db)
):
    """Create a product."""
    product = RadarProduct(**payload.model_dump())
    db.add(product)
    _commit_or_conflict(db, f"Product key '{payload.product_key}' already exists")
    db.refresh(product)
    return AdminRadarProductResponse.model_validate(product)


@router.put("/products/{product_id}", response_model=AdminRadarProductResponse)
def admin_update_product(
    product_id: int, payload: AdminRadarProductUpdate, db: Session = Depends(get_db)
):
    """Update all editable fields for a product."""
    product = db.query(RadarProduct).filter(RadarProduct.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")
    _apply_changes(product, payload.model_dump())
    _commit_or_conflict(db, "Product update conflicts with existing data")
    db.refresh(product)
    return AdminRadarProductResponse.model_validate(product)


@router.patch("/products/{product_id}", response_model=AdminRadarProductResponse)
def admin_patch_product(
    product_id: int, payload: AdminRadarProductPatch, db: Session = Depends(get_db)
):
    """Partially update a product."""
    product = db.query(RadarProduct).filter(RadarProduct.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return AdminRadarProductResponse.model_validate(product)
    _apply_changes(product, changes)
    _commit_or_conflict(db, "Product update conflicts with existing data")
    db.refresh(product)
    return AdminRadarProductResponse.model_validate(product)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_product(product_id: int, db: Session = Depends(get_db)):
    """Delete a product by ID."""
    product = db.query(RadarProduct).filter(RadarProduct.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")
    db.delete(product)
    _commit_or_conflict(db, f"Product '{product_id}' could not be deleted")


@router.get("/references", response_model=list[AdminReferenceResponse])
def admin_list_references(
    product_id: Optional[int] = Query(default=None), db: Session = Depends(get_db)
):
    """List references, optionally filtered by product ID."""
    query = db.query(Reference)
    if product_id is not None:
        query = query.filter(Reference.product_id == product_id)
    return [
        AdminReferenceResponse.model_validate(reference)
        for reference in query.order_by(Reference.id).all()
    ]


@router.get("/references/{reference_id}", response_model=AdminReferenceResponse)
def admin_get_reference(reference_id: int, db: Session = Depends(get_db)):
    """Get a reference by ID."""
    reference = db.query(Reference).filter(Reference.id == reference_id).first()
    if reference is None:
        raise HTTPException(
            status_code=404, detail=f"Reference '{reference_id}' not found"
        )
    return AdminReferenceResponse.model_validate(reference)


@router.post(
    "/references",
    response_model=AdminReferenceResponse,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_reference(
    payload: AdminReferenceCreate, db: Session = Depends(get_db)
):
    """Create a color scale reference entry."""
    product = (
        db.query(RadarProduct).filter(RadarProduct.id == payload.product_id).first()
    )
    if product is None:
        raise HTTPException(
            status_code=422, detail=f"Product '{payload.product_id}' not found"
        )
    reference = Reference(**payload.model_dump())
    db.add(reference)
    _commit_or_conflict(db, "Reference could not be created")
    db.refresh(reference)
    return AdminReferenceResponse.model_validate(reference)


@router.put("/references/{reference_id}", response_model=AdminReferenceResponse)
def admin_update_reference(
    reference_id: int, payload: AdminReferenceUpdate, db: Session = Depends(get_db)
):
    """Update a reference entry."""
    reference = db.query(Reference).filter(Reference.id == reference_id).first()
    if reference is None:
        raise HTTPException(
            status_code=404, detail=f"Reference '{reference_id}' not found"
        )
    product = (
        db.query(RadarProduct).filter(RadarProduct.id == payload.product_id).first()
    )
    if product is None:
        raise HTTPException(
            status_code=422, detail=f"Product '{payload.product_id}' not found"
        )
    _apply_changes(reference, payload.model_dump())
    _commit_or_conflict(db, "Reference could not be updated")
    db.refresh(reference)
    return AdminReferenceResponse.model_validate(reference)


@router.delete("/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_reference(reference_id: int, db: Session = Depends(get_db)):
    """Delete a reference entry by ID."""
    reference = db.query(Reference).filter(Reference.id == reference_id).first()
    if reference is None:
        raise HTTPException(
            status_code=404, detail=f"Reference '{reference_id}' not found"
        )
    db.delete(reference)
    _commit_or_conflict(db, f"Reference '{reference_id}' could not be deleted")


@router.delete("/references", response_model=AdminBulkDeleteResponse)
def admin_bulk_delete_references(
    product_id: int = Query(...), db: Session = Depends(get_db)
):
    """Bulk delete references by product ID."""
    deleted_count = (
        db.query(Reference)
        .filter(Reference.product_id == product_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return AdminBulkDeleteResponse(deleted_count=deleted_count)


@router.get("/cogs", response_model=AdminCOGListResponse)
def admin_list_cogs(
    radar_code: Optional[str] = None,
    product_key: Optional[str] = None,
    status_value: Optional[str] = Query(default=None, alias="status"),
    vol_nr: Optional[str] = None,
    start_time: Optional[datetime] = Query(default=None),
    end_time: Optional[datetime] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List COG records with admin filters and pagination."""
    query = db.query(RadarCOG)
    query = _apply_cog_filters(
        query, radar_code, product_key, status_value, vol_nr, start_time, end_time
    )
    total = query.count()
    items = (
        query.order_by(RadarCOG.observation_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return AdminCOGListResponse(
        page=page,
        page_size=page_size,
        total=total,
        items=[_cog_response(item) for item in items],
    )


@router.get("/cogs/{cog_id}", response_model=AdminCOGResponse)
def admin_get_cog(cog_id: int, db: Session = Depends(get_db)):
    """Get full COG detail by ID."""
    cog = db.query(RadarCOG).filter(RadarCOG.id == cog_id).first()
    if cog is None:
        raise HTTPException(status_code=404, detail=f"COG '{cog_id}' not found")
    return _cog_response(cog)


@router.patch("/cogs/{cog_id}", response_model=AdminCOGResponse)
def admin_patch_cog_status(
    cog_id: int, payload: AdminCOGPatchStatus, db: Session = Depends(get_db)
):
    """Update COG status only."""
    cog = db.query(RadarCOG).filter(RadarCOG.id == cog_id).first()
    if cog is None:
        raise HTTPException(status_code=404, detail=f"COG '{cog_id}' not found")
    cog.status = _ensure_cog_status(payload.status)
    _commit_or_conflict(db, f"COG '{cog_id}' could not be updated")
    db.refresh(cog)
    return _cog_response(cog)


@router.delete("/cogs/{cog_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_cog(cog_id: int, db: Session = Depends(get_db)):
    """Delete a COG record by ID."""
    cog = db.query(RadarCOG).filter(RadarCOG.id == cog_id).first()
    if cog is None:
        raise HTTPException(status_code=404, detail=f"COG '{cog_id}' not found")
    db.delete(cog)
    _commit_or_conflict(db, f"COG '{cog_id}' could not be deleted")


@router.delete("/cogs", response_model=AdminBulkDeleteResponse)
def admin_bulk_delete_cogs(
    radar_code: Optional[str] = None,
    product_key: Optional[str] = None,
    status_value: Optional[str] = Query(default=None, alias="status"),
    vol_nr: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    """Bulk delete COG records by filters."""
    if not any([radar_code, product_key, status_value, vol_nr, start_time, end_time]):
        raise HTTPException(
            status_code=422, detail="At least one filter is required for bulk delete"
        )
    query = _apply_cog_filters(
        db.query(RadarCOG),
        radar_code,
        product_key,
        status_value,
        vol_nr,
        start_time,
        end_time,
    )
    deleted_count = query.delete(synchronize_session=False)
    db.commit()
    return AdminBulkDeleteResponse(deleted_count=deleted_count)


@router.get("/estrategias", response_model=list[AdminEstrategiaResponse])
def admin_list_estrategias(db: Session = Depends(get_db)):
    """List all estrategias."""
    estrategias = db.query(Estrategia).order_by(Estrategia.code).all()
    return [
        AdminEstrategiaResponse(
            code=item.code,
            description=item.description,
            volumen_ids=[vol.id for vol in item.volumenes],
            volumen_values=[vol.value for vol in item.volumenes],
        )
        for item in estrategias
    ]


@router.get("/estrategias/{code}", response_model=AdminEstrategiaResponse)
def admin_get_estrategia(code: str, db: Session = Depends(get_db)):
    """Get a strategy by code."""
    estrategia = db.query(Estrategia).filter(Estrategia.code == code).first()
    if estrategia is None:
        raise HTTPException(status_code=404, detail=f"Estrategia '{code}' not found")
    return AdminEstrategiaResponse(
        code=estrategia.code,
        description=estrategia.description,
        volumen_ids=[vol.id for vol in estrategia.volumenes],
        volumen_values=[vol.value for vol in estrategia.volumenes],
    )


@router.post(
    "/estrategias",
    response_model=AdminEstrategiaResponse,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_estrategia(
    payload: AdminEstrategiaCreate, db: Session = Depends(get_db)
):
    """Create an estrategia and attach volumen relations."""
    estrategia = Estrategia(code=payload.code, description=payload.description)
    estrategia.volumenes = _load_volumenes_or_422(db, payload.volumen_ids)
    db.add(estrategia)
    _commit_or_conflict(db, f"Estrategia '{payload.code}' already exists")
    db.refresh(estrategia)
    return AdminEstrategiaResponse(
        code=estrategia.code,
        description=estrategia.description,
        volumen_ids=[vol.id for vol in estrategia.volumenes],
        volumen_values=[vol.value for vol in estrategia.volumenes],
    )


@router.put("/estrategias/{code}", response_model=AdminEstrategiaResponse)
def admin_update_estrategia(
    code: str, payload: AdminEstrategiaUpdate, db: Session = Depends(get_db)
):
    """Update strategy description and associated volumenes."""
    estrategia = db.query(Estrategia).filter(Estrategia.code == code).first()
    if estrategia is None:
        raise HTTPException(status_code=404, detail=f"Estrategia '{code}' not found")
    estrategia.description = payload.description
    estrategia.volumenes = _load_volumenes_or_422(db, payload.volumen_ids)
    _commit_or_conflict(db, f"Estrategia '{code}' could not be updated")
    db.refresh(estrategia)
    return AdminEstrategiaResponse(
        code=estrategia.code,
        description=estrategia.description,
        volumen_ids=[vol.id for vol in estrategia.volumenes],
        volumen_values=[vol.value for vol in estrategia.volumenes],
    )


@router.delete("/estrategias/{code}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_estrategia(code: str, db: Session = Depends(get_db)):
    """Delete an estrategia by code."""
    estrategia = db.query(Estrategia).filter(Estrategia.code == code).first()
    if estrategia is None:
        raise HTTPException(status_code=404, detail=f"Estrategia '{code}' not found")
    db.delete(estrategia)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Estrategia is in use and cannot be deleted due to foreign key constraints",
        ) from exc


@router.get("/volumenes", response_model=list[AdminVolumenResponse])
def admin_list_volumenes(db: Session = Depends(get_db)):
    """List all volumenes."""
    return [
        AdminVolumenResponse.model_validate(item)
        for item in db.query(Volumen).order_by(Volumen.id).all()
    ]


@router.get("/volumenes/{volumen_id}", response_model=AdminVolumenResponse)
def admin_get_volumen(volumen_id: int, db: Session = Depends(get_db)):
    """Get a volumen by ID."""
    volumen = db.query(Volumen).filter(Volumen.id == volumen_id).first()
    if volumen is None:
        raise HTTPException(status_code=404, detail=f"Volumen '{volumen_id}' not found")
    return AdminVolumenResponse.model_validate(volumen)


@router.post(
    "/volumenes",
    response_model=AdminVolumenResponse,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_volumen(payload: AdminVolumenCreate, db: Session = Depends(get_db)):
    """Create a volumen."""
    volumen = Volumen(value=payload.value)
    db.add(volumen)
    _commit_or_conflict(db, "Volumen could not be created")
    db.refresh(volumen)
    return AdminVolumenResponse.model_validate(volumen)


@router.put("/volumenes/{volumen_id}", response_model=AdminVolumenResponse)
def admin_update_volumen(
    volumen_id: int, payload: AdminVolumenUpdate, db: Session = Depends(get_db)
):
    """Update a volumen."""
    volumen = db.query(Volumen).filter(Volumen.id == volumen_id).first()
    if volumen is None:
        raise HTTPException(status_code=404, detail=f"Volumen '{volumen_id}' not found")
    volumen.value = payload.value
    _commit_or_conflict(db, "Volumen could not be updated")
    db.refresh(volumen)
    return AdminVolumenResponse.model_validate(volumen)


@router.delete("/volumenes/{volumen_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_volumen(volumen_id: int, db: Session = Depends(get_db)):
    """Delete a volumen."""
    volumen = db.query(Volumen).filter(Volumen.id == volumen_id).first()
    if volumen is None:
        raise HTTPException(status_code=404, detail=f"Volumen '{volumen_id}' not found")
    db.delete(volumen)
    _commit_or_conflict(db, f"Volumen '{volumen_id}' could not be deleted")


@router.get("/tops-cores", response_model=AdminTopsAndCoresListResponse)
def admin_list_tops_cores(
    radar_code: Optional[str] = None,
    strategy: Optional[str] = None,
    vol_nr: Optional[str] = None,
    status_value: Optional[str] = Query(default=None, alias="status"),
    start_time: Optional[datetime] = Query(default=None),
    end_time: Optional[datetime] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List tops-and-cores records with filters and pagination."""
    query = db.query(TopsAndCores)
    query = _apply_tops_cores_filters(
        query, radar_code, strategy, vol_nr, status_value, start_time, end_time
    )
    total = query.count()
    items = (
        query.order_by(TopsAndCores.observation_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return AdminTopsAndCoresListResponse(
        page=page,
        page_size=page_size,
        total=total,
        items=[_tops_cores_response(item) for item in items],
    )


@router.get("/tops-cores/{record_id}", response_model=AdminTopsAndCoresResponse)
def admin_get_tops_cores(record_id: int, db: Session = Depends(get_db)):
    """Get a single tops-and-cores record."""
    record = db.query(TopsAndCores).filter(TopsAndCores.id == record_id).first()
    if record is None:
        raise HTTPException(
            status_code=404, detail=f"TopsAndCores '{record_id}' not found"
        )
    return _tops_cores_response(record)


@router.patch("/tops-cores/{record_id}", response_model=AdminTopsAndCoresResponse)
def admin_patch_tops_cores_status(
    record_id: int, payload: AdminTopsAndCoresPatchStatus, db: Session = Depends(get_db)
):
    """Update tops-and-cores status only."""
    record = db.query(TopsAndCores).filter(TopsAndCores.id == record_id).first()
    if record is None:
        raise HTTPException(
            status_code=404, detail=f"TopsAndCores '{record_id}' not found"
        )
    record.status = _ensure_cog_status(payload.status)
    _commit_or_conflict(db, f"TopsAndCores '{record_id}' could not be updated")
    db.refresh(record)
    return _tops_cores_response(record)


@router.delete("/tops-cores/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_tops_cores(record_id: int, db: Session = Depends(get_db)):
    """Delete one tops-and-cores record."""
    record = db.query(TopsAndCores).filter(TopsAndCores.id == record_id).first()
    if record is None:
        raise HTTPException(
            status_code=404, detail=f"TopsAndCores '{record_id}' not found"
        )
    db.delete(record)
    _commit_or_conflict(db, f"TopsAndCores '{record_id}' could not be deleted")


@router.delete("/tops-cores", response_model=AdminBulkDeleteResponse)
def admin_bulk_delete_tops_cores(
    radar_code: Optional[str] = None,
    strategy: Optional[str] = None,
    vol_nr: Optional[str] = None,
    status_value: Optional[str] = Query(default=None, alias="status"),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    """Bulk delete tops-and-cores records by filters."""
    if not any([radar_code, strategy, vol_nr, status_value, start_time, end_time]):
        raise HTTPException(
            status_code=422, detail="At least one filter is required for bulk delete"
        )
    query = _apply_tops_cores_filters(
        db.query(TopsAndCores),
        radar_code,
        strategy,
        vol_nr,
        status_value,
        start_time,
        end_time,
    )
    deleted_count = query.delete(synchronize_session=False)
    db.commit()
    return AdminBulkDeleteResponse(deleted_count=deleted_count)


# ── Colormap stops ────────────────────────────────────────────────────────────


@router.get("/colormap-stops", response_model=List[AdminColormapSummary])
def admin_list_colormap_summaries(db: Session = Depends(get_db)):
    """List all colormaps with stop count and system flag."""
    rows = (
        db.query(
            ColormapStop.cmap_name,
            func.count(ColormapStop.id).label("stop_count"),
            func.bool_and(ColormapStop.is_system).label("is_system"),
        )
        .group_by(ColormapStop.cmap_name)
        .order_by(ColormapStop.cmap_name)
        .all()
    )
    return [
        AdminColormapSummary(cmap_name=r.cmap_name, stop_count=r.stop_count, is_system=r.is_system)
        for r in rows
    ]


@router.get("/colormap-stops/{cmap_name}", response_model=List[AdminColormapStopResponse])
def admin_get_colormap_stops(
    cmap_name: str,
    db: Session = Depends(get_db),
):
    """Get all stops for a specific colormap."""
    stops = (
        db.query(ColormapStop)
        .filter(ColormapStop.cmap_name == cmap_name)
        .order_by(ColormapStop.channel, ColormapStop.sort_order)
        .all()
    )
    if not stops:
        raise HTTPException(status_code=404, detail=f"Colormap '{cmap_name}' not found")
    return stops


@router.post("/colormap-stops", response_model=AdminColormapStopResponse, status_code=201)
def admin_create_colormap_stop(
    payload: AdminColormapStopCreate,
    db: Session = Depends(get_db),
):
    """Append a single stop row to a colormap."""
    stop = ColormapStop(**payload.model_dump())
    db.add(stop)
    _commit_or_conflict(db, "Failed to create colormap stop")
    db.refresh(stop)
    return stop


@router.delete("/colormap-stops/{cmap_name}", response_model=AdminBulkDeleteResponse)
def admin_delete_colormap(
    cmap_name: str,
    db: Session = Depends(get_db),
):
    """Delete all stops for a non-system colormap."""
    system_row = (
        db.query(ColormapStop)
        .filter(ColormapStop.cmap_name == cmap_name, ColormapStop.is_system.is_(True))
        .first()
    )
    if system_row:
        raise HTTPException(
            status_code=403,
            detail=f"Colormap '{cmap_name}' is a system colormap and cannot be deleted",
        )
    deleted = (
        db.query(ColormapStop)
        .filter(ColormapStop.cmap_name == cmap_name)
        .delete(synchronize_session=False)
    )
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"Colormap '{cmap_name}' not found")
    db.commit()
    return AdminBulkDeleteResponse(deleted_count=deleted)


# ── Product colormap options ──────────────────────────────────────────────────


@router.get("/colormap-options", response_model=List[AdminProductColormapOptionResponse])
def admin_list_colormap_options(
    product_key: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all product colormap options, optionally filtered by product_key."""
    query = db.query(ProductColormapOption).order_by(
        ProductColormapOption.product_key, ProductColormapOption.cmap_name
    )
    if product_key:
        query = query.filter(ProductColormapOption.product_key == product_key)
    return query.all()


@router.post("/colormap-options", response_model=AdminProductColormapOptionResponse, status_code=201)
def admin_create_colormap_option(
    payload: AdminProductColormapOptionCreate,
    db: Session = Depends(get_db),
):
    """Add a colormap option to a product."""
    option = ProductColormapOption(
        product_key=payload.product_key,
        cmap_name=payload.cmap_name,
    )
    db.add(option)
    _commit_or_conflict(db, f"Option '{payload.cmap_name}' already exists for '{payload.product_key}'")
    db.refresh(option)
    return option


@router.delete("/colormap-options/{option_id}", status_code=204)
def admin_delete_colormap_option(
    option_id: int,
    db: Session = Depends(get_db),
):
    """Delete a product colormap option by ID."""
    option = db.query(ProductColormapOption).get(option_id)
    if option is None:
        raise HTTPException(status_code=404, detail=f"Colormap option '{option_id}' not found")
    db.delete(option)
    db.commit()


# ── Colormap creator (hex stops → channels) ──────────────────────────────────


def _hex_to_rgb(hex_color: str):
    """Convert #RRGGBB to (r_float, g_float, b_float) in [0, 1]."""
    h = hex_color.lstrip('#')
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: {hex_color!r}")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)


@router.post("/colormap-from-hex", response_model=AdminColormapSummary, status_code=201)
def admin_create_colormap_from_hex(
    payload: AdminColormapCreateFromHex,
    db: Session = Depends(get_db),
):
    """
    Create a new colormap from a list of (position, hex_color) stops.

    Each hex stop is expanded into three ColormapStop rows (r, g, b).
    Optionally add the new colormap as an option for the supplied product_keys.
    """
    # Reject if already exists.
    existing = db.query(ColormapStop).filter(ColormapStop.cmap_name == payload.cmap_name).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Colormap '{payload.cmap_name}' already exists. Delete it first to recreate.",
        )

    # Validate + convert hex stops.
    try:
        rgb_stops = [(s.position, _hex_to_rgb(s.color)) for s in payload.stops]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    rgb_stops.sort(key=lambda x: x[0])

    # Insert channel rows.
    channel_names = ('r', 'g', 'b')
    rows_to_add = []
    for ch_idx, ch_name in enumerate(channel_names):
        for sort_order, (position, rgb) in enumerate(rgb_stops):
            rows_to_add.append(
                ColormapStop(
                    cmap_name=payload.cmap_name,
                    channel=ch_name,
                    position=position,
                    val_left=rgb[ch_idx],
                    val_right=rgb[ch_idx],
                    sort_order=sort_order,
                    is_system=False,
                )
            )
    db.add_all(rows_to_add)

    # Link to products if requested.
    for key in payload.product_keys:
        # Skip if already linked.
        already = (
            db.query(ProductColormapOption)
            .filter(
                ProductColormapOption.product_key == key,
                ProductColormapOption.cmap_name == payload.cmap_name,
            )
            .first()
        )
        if not already:
            db.add(ProductColormapOption(product_key=key, cmap_name=payload.cmap_name))

    db.commit()

    stop_count = len(rows_to_add)
    return AdminColormapSummary(cmap_name=payload.cmap_name, stop_count=stop_count, is_system=False)
