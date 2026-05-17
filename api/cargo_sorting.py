"""Cargo sorting endpoints for sorting workers (分拣员).
Mounted separately from handcraft_router so the 'sorting' permission can grant
access to these endpoints without granting access to handcraft management."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas.handcraft import CargoSortingListResponse, CargoSortingOrderView, CargoSortingSuppliersResponse
from services.handcraft import (
    get_handcraft_jewelry_breakdown,
    get_handcraft_order_by_receipt_code,
    list_handcraft_orders_with_sorting,
    list_suppliers_with_sorting,
)

# Same URL prefix as handcraft_router so URLs are unchanged:
# GET /api/handcraft/suppliers-with-sorting
router = APIRouter(prefix="/api/handcraft", tags=["cargo-sorting"])


@router.get("/suppliers-with-sorting", response_model=CargoSortingSuppliersResponse)
def api_list_suppliers_with_sorting(db: Session = Depends(get_db)):
    return {"suppliers": list_suppliers_with_sorting(db)}


@router.get("/sorting", response_model=CargoSortingListResponse)
def api_list_handcraft_orders_with_sorting(
    supplier_name: str = Query(..., min_length=1),
    limit: int = Query(15, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return list_handcraft_orders_with_sorting(
        db, supplier_name=supplier_name, limit=limit, offset=offset
    )


@router.get("/sorting/by-receipt-code/{code}", response_model=CargoSortingOrderView)
def api_get_sorting_by_receipt_code(code: str, db: Session = Depends(get_db)):
    order = get_handcraft_order_by_receipt_code(db, code)
    if order is None:
        raise HTTPException(status_code=404, detail=f"无此回执编号：{code.upper()}")
    return {
        "id": order.id,
        "supplier_name": order.supplier_name,
        "receipt_code": order.receipt_code,
        "status": order.status,
        "created_at": order.created_at,
        "breakdown": get_handcraft_jewelry_breakdown(db, order.id, only_with_customer=True),
    }
