from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.handcraft import (
    HandcraftCreate,
    HandcraftResponse,
    ReceiptRequest,
    HandcraftJewelryItemResponse,
)
from services.handcraft import (
    create_handcraft_order,
    get_handcraft_order,
    list_handcraft_orders,
    receive_handcraft_jewelries,
    send_handcraft_order,
)

router = APIRouter(prefix="/api/handcraft", tags=["handcraft"])


@router.post("/", response_model=HandcraftResponse, status_code=201)
def api_create_handcraft_order(body: HandcraftCreate, db: Session = Depends(get_db)):
    with service_errors():
        order = create_handcraft_order(
            db,
            supplier_name=body.supplier_name,
            parts=[p.model_dump() for p in body.parts],
            jewelries=[j.model_dump() for j in body.jewelries],
            note=body.note,
        )
    return order


@router.get("/", response_model=list[HandcraftResponse])
def api_list_handcraft_orders(status: Optional[str] = None, db: Session = Depends(get_db)):
    with service_errors():
        return list_handcraft_orders(db, status=status)


@router.get("/{order_id}", response_model=HandcraftResponse)
def api_get_handcraft_order(order_id: str, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    return order


@router.post("/{order_id}/send", response_model=HandcraftResponse)
def api_send_handcraft_order(order_id: str, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        order = send_handcraft_order(db, order_id)
    return order


@router.post("/{order_id}/receive", response_model=list[HandcraftJewelryItemResponse])
def api_receive_handcraft_jewelries(order_id: str, body: ReceiptRequest, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        updated = receive_handcraft_jewelries(
            db,
            order_id,
            [r.model_dump() for r in body.receipts],
        )
    return updated
