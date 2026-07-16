# api/app/routers/products.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from radar_db import get_db, RadarProduct, Reference, RadarCOG, COGStatus
from ..schemas import ProductResponse, ProductListResponse, ReferenceResponse, ColormapResponse, ColormapEntry

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=ProductListResponse)
def list_products(
    enabled_only: bool = True,
    vol_nr: Optional[List[str]] = Query(
        default=None,
        description="Filter to products that have COGs in these volume number(s). Repeatable: ?vol_nr=01&vol_nr=02",
    ),
    strategy: Optional[List[str]] = Query(
        default=None,
        description="When vol_nr is set, also filter by strategy code(s), e.g. '0315'. Repeatable: ?strategy=0315&strategy=1000",
    ),
    db: Session = Depends(get_db)
):
    """
    List all radar products.
    
    - **enabled_only**: If true, only return enabled products (default: true)
    """
    query = db.query(RadarProduct).options(joinedload(RadarProduct.references))
    
    if enabled_only:
        query = query.filter(RadarProduct.enabled == True)

    if vol_nr:
        # Only return products that actually have COGs in the requested volumes.
        # Match via polarimetric_var (new-format COGs) which mirrors product_key.
        subq = db.query(RadarCOG.polarimetric_var).filter(
            RadarCOG.vol_nr.in_(vol_nr),
            RadarCOG.status == COGStatus.AVAILABLE,
            RadarCOG.polarimetric_var.isnot(None),
            RadarCOG.polarimetric_var != "",
        )
        if strategy:
            subq = subq.filter(RadarCOG.estrategia_code.in_(strategy))
        available_keys = {row[0] for row in subq.distinct().all()}
        query = query.filter(RadarProduct.product_key.in_(available_keys))

    products = query.order_by(RadarProduct.product_key).all()
    
    product_responses = []
    for product in products:
        # Sort references by value descending (like in Django model)
        sorted_refs = sorted(product.references, key=lambda r: r.value, reverse=True)
        
        product_responses.append(ProductResponse(
            id=product.id,
            product_key=product.product_key,
            product_title=product.product_title,
            product_description=product.product_description,
            enabled=product.enabled,
            see_in_open=product.see_in_open,
            min_value=product.min_value,
            max_value=product.max_value,
            unit=product.unit,
            references=[ReferenceResponse.model_validate(r) for r in sorted_refs]
        ))
    
    return ProductListResponse(
        products=product_responses,
        count=len(product_responses)
    )


@router.get("/{product_key}", response_model=ProductResponse)
def get_product(
    product_key: str,
    db: Session = Depends(get_db)
):
    """Get a specific product by key."""
    product = db.query(RadarProduct)\
        .options(joinedload(RadarProduct.references))\
        .filter(RadarProduct.product_key == product_key)\
        .first()
    
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_key}' not found")
    
    sorted_refs = sorted(product.references, key=lambda r: r.value, reverse=True)
    
    return ProductResponse(
        id=product.id,
        product_key=product.product_key,
        product_title=product.product_title,
        product_description=product.product_description,
        enabled=product.enabled,
        see_in_open=product.see_in_open,
        min_value=product.min_value,
        max_value=product.max_value,
        unit=product.unit,
        references=[ReferenceResponse.model_validate(r) for r in sorted_refs]
    )


@router.get("/{product_key}/colormap", response_model=ColormapResponse, deprecated=True)
def get_product_colormap(
    product_key: str,
    db: Session = Depends(get_db)
):
    """
    DEPRECATED: Get the colormap for a product from database references.
    
    This endpoint is deprecated. Use /api/v1/colormap/info/{product_key} instead
    to get predefined colormaps based on product type.
    
    Returns color mapping for use in tile rendering and legend display.
    """
    product = db.query(RadarProduct)\
        .options(joinedload(RadarProduct.references))\
        .filter(RadarProduct.product_key == product_key)\
        .first()
    
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_key}' not found")
    
    # Sort by value ascending for colormap
    sorted_refs = sorted(product.references, key=lambda r: r.value)
    
    entries = [
        ColormapEntry(
            value=ref.value,
            color=ref.color,
            label=ref.title
        )
        for ref in sorted_refs
    ]
    
    min_val = min(r.value for r in sorted_refs) if sorted_refs else 0
    max_val = max(r.value for r in sorted_refs) if sorted_refs else 100
    
    return ColormapResponse(
        product_key=product_key,
        entries=entries,
        min_value=min_val,
        max_value=max_val,
        unit=product.unit
    )