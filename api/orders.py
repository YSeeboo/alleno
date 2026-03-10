from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas.order import OrderCreate, OrderResponse, OrderItemResponse, StatusUpdate
from services.order import (
    create_order,
    get_order,
    get_order_items,
    get_parts_summary,
    update_order_status,
)
from api._errors import service_errors

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("/", response_model=OrderResponse, status_code=201)
def api_create_order(body: OrderCreate, db: Session = Depends(get_db)):
    items = [item.model_dump() for item in body.items]
    with service_errors():
        order = create_order(db, body.customer_name, items)
    return order


@router.get("/{order_id}", response_model=OrderResponse)
def api_get_order(order_id: str, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return order


@router.get("/{order_id}/items", response_model=list[OrderItemResponse])
def api_get_order_items(order_id: str, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return get_order_items(db, order_id)


@router.get("/{order_id}/parts-summary")
def api_get_parts_summary(order_id: str, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        summary = get_parts_summary(db, order_id)
    return summary


@router.patch("/{order_id}/status", response_model=OrderResponse)
def api_update_order_status(order_id: str, body: StatusUpdate, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        order = update_order_status(db, order_id, body.status)
    return order
