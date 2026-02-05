# api/app/routers/products.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from radar_db import get_db, RadarProduct, Reference
from ..schemas import ProductResponse, ProductListResponse, ReferenceResponse, ColormapResponse, ColormapEntry

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=ProductListResponse)
def list_products(
    enabled_only: bool = True,
    db: Session = Depends(get_db)
):
    """
    List all radar products.
    
    - **enabled_only**: If true, only return enabled products (default: true)
    """
    query = db.query(RadarProduct).options(joinedload(RadarProduct.references))
    
    if enabled_only:
        query = query.filter(RadarProduct.enabled == True)
    
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


@router.get("/{product_key}/colormap", response_model=ColormapResponse)
def get_product_colormap(
    product_key: str,
    db: Session = Depends(get_db)
):
    """
    Get the colormap for a product.
    
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