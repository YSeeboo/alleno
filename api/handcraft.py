from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.handcraft import (
    HandcraftCreate,
    HandcraftJewelryIn,
    HandcraftJewelryItemResponse,
    HandcraftPartIn,
    HandcraftPartItemResponse,
    HandcraftResponse,
    ReceiptRequest,
)
from services.handcraft import (
    add_handcraft_jewelry,
    add_handcraft_part,
    create_handcraft_order,
    delete_handcraft_jewelry,
    delete_handcraft_part,
    get_handcraft_jewelries,
    get_handcraft_order,
    get_handcraft_parts,
    list_handcraft_orders,
    receive_handcraft_jewelries,
    send_handcraft_order,
    update_handcraft_jewelry,
    update_handcraft_order_status,
    update_handcraft_part,
)


class HandcraftPartUpdate(BaseModel):
    qty: Optional[float] = None
    unit: Optional[str] = None
    note: Optional[str] = None
    bom_qty: Optional[float] = None


class HandcraftJewelryUpdate(BaseModel):
    qty: Optional[int] = None
    unit: Optional[str] = None
    note: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str

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


@router.get("/{order_id}/parts", response_model=list[HandcraftPartItemResponse])
def api_get_handcraft_parts(order_id: str, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    return get_handcraft_parts(db, order_id)


@router.get("/{order_id}/jewelries", response_model=list[HandcraftJewelryItemResponse])
def api_get_handcraft_jewelries(order_id: str, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    return get_handcraft_jewelries(db, order_id)


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


@router.post("/{order_id}/parts", response_model=HandcraftPartItemResponse, status_code=201)
def api_add_handcraft_part(order_id: str, body: HandcraftPartIn, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        item = add_handcraft_part(db, order_id, body.model_dump())
    return item


@router.put("/{order_id}/parts/{item_id}", response_model=HandcraftPartItemResponse)
def api_update_handcraft_part(order_id: str, item_id: int, body: HandcraftPartUpdate, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        item = update_handcraft_part(db, order_id, item_id, body.model_dump(exclude_unset=True))
    return item


@router.delete("/{order_id}/parts/{item_id}", status_code=204)
def api_delete_handcraft_part(order_id: str, item_id: int, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        delete_handcraft_part(db, order_id, item_id)


@router.post("/{order_id}/jewelries", response_model=HandcraftJewelryItemResponse, status_code=201)
def api_add_handcraft_jewelry(order_id: str, body: HandcraftJewelryIn, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        item = add_handcraft_jewelry(db, order_id, body.model_dump())
    return item


@router.put("/{order_id}/jewelries/{item_id}", response_model=HandcraftJewelryItemResponse)
def api_update_handcraft_jewelry(order_id: str, item_id: int, body: HandcraftJewelryUpdate, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        item = update_handcraft_jewelry(db, order_id, item_id, body.model_dump(exclude_unset=True))
    return item


@router.delete("/{order_id}/jewelries/{item_id}", status_code=204)
def api_delete_handcraft_jewelry(order_id: str, item_id: int, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        delete_handcraft_jewelry(db, order_id, item_id)


@router.patch("/{order_id}/status", response_model=HandcraftResponse)
def api_update_handcraft_status(order_id: str, body: StatusUpdate, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        order = update_handcraft_order_status(db, order_id, body.status)
    return order
