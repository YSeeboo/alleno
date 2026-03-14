from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.kanban import (
    KanbanResponse,
    VendorDetailResponse,
    VendorReceiptCreate,
    VendorOrderOption,
    OrderItemsForReceiptResponse,
    OrderStatusChangeRequest,
)
from services import kanban as kanban_svc

router = APIRouter()


@router.get("", response_model=KanbanResponse)
def get_kanban(
    type: Annotated[Literal["all", "plating", "handcraft"], Query()] = "all",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    order_type = None if type == "all" else type
    with service_errors():
        return kanban_svc.get_kanban(db, order_type=order_type, page=page, page_size=page_size)


@router.get("/vendors", response_model=list[str])
def get_vendors(
    order_type: Annotated[Optional[Literal["plating", "handcraft"]], Query()] = None,
    q: str | None = Query(default=None, description="模糊搜索厂家名"),
    db: Session = Depends(get_db),
):
    with service_errors():
        return kanban_svc.list_vendors(db, order_type=order_type, q=q)


@router.get("/vendor/{vendor_name}", response_model=VendorDetailResponse)
def get_vendor_detail(
    vendor_name: str,
    order_type: Annotated[Literal["plating", "handcraft"], Query()],
    db: Session = Depends(get_db),
):
    with service_errors():
        return kanban_svc.get_vendor_detail(db, vendor_name=vendor_name, order_type=order_type)


@router.get("/vendor-orders", response_model=list[VendorOrderOption])
def get_vendor_orders(
    vendor_name: str = Query(...),
    order_type: Annotated[Literal["plating", "handcraft"], Query()] = ...,
    db: Session = Depends(get_db),
):
    with service_errors():
        return kanban_svc.get_orders_for_vendor(db, vendor_name=vendor_name, order_type=order_type)


@router.get("/order-items", response_model=OrderItemsForReceiptResponse)
def get_order_items(
    order_id: str = Query(...),
    order_type: Annotated[Literal["plating", "handcraft"], Query()] = ...,
    db: Session = Depends(get_db),
):
    with service_errors():
        return kanban_svc.get_order_items_for_receipt(db, order_id=order_id, order_type=order_type)


@router.post("/order-status")
def change_order_status(
    body: OrderStatusChangeRequest,
    db: Session = Depends(get_db),
):
    with service_errors():
        kanban_svc.change_order_status(
            db,
            order_id=body.order_id,
            order_type=body.order_type,
            new_status=body.new_status,
        )
        db.commit()
    return {"ok": True}


@router.post("/return")
def record_return(
    body: VendorReceiptCreate,
    db: Session = Depends(get_db),
):
    with service_errors():
        _, warnings = kanban_svc.record_vendor_receipt(
            db,
            vendor_name=body.vendor_name,
            order_type=body.order_type,
            order_id=body.order_id,
            items=body.items,
        )
        db.commit()
    return {"ok": True, "warnings": warnings}
