from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.plating import (
    PlatingCreate,
    PlatingDeliveryImagesUpdate,
    PlatingItemCreate,
    PlatingItemResponse,
    PlatingResponse,
    ReceiptRequest,
)
from services.plating_excel import build_plating_order_excel
from services.plating_pdf import build_plating_order_pdf
from services.plating import (
    add_plating_item,
    create_plating_order,
    delete_plating_order,
    delete_plating_item,
    get_plating_order,
    get_plating_items,
    list_plating_orders,
    receive_plating_items,
    send_plating_order,
    update_plating_delivery_images,
    update_plating_item,
    update_plating_order_status,
)


class PlatingItemUpdate(BaseModel):
    qty: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = None
    plating_method: Optional[str] = None
    note: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str

router = APIRouter(prefix="/api/plating", tags=["plating"])


@router.post("/", response_model=PlatingResponse, status_code=201)
def api_create_plating_order(body: PlatingCreate, db: Session = Depends(get_db)):
    with service_errors():
        order = create_plating_order(
            db,
            supplier_name=body.supplier_name,
            items=[item.model_dump() for item in body.items],
            note=body.note,
        )
    return order


@router.get("/", response_model=list[PlatingResponse])
def api_list_plating_orders(status: Optional[str] = None, db: Session = Depends(get_db)):
    with service_errors():
        return list_plating_orders(db, status=status)


@router.get("/{order_id}", response_model=PlatingResponse)
def api_get_plating_order(order_id: str, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    return order


@router.delete("/{order_id}", status_code=204)
def api_delete_plating_order(order_id: str, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    with service_errors():
        delete_plating_order(db, order_id)


@router.get("/{order_id}/items", response_model=list[PlatingItemResponse])
def api_get_plating_items(order_id: str, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    return get_plating_items(db, order_id)


@router.get("/{order_id}/excel")
def api_download_plating_excel(order_id: str, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    file_bytes, filename = build_plating_order_excel(db, order_id)
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="plating-export.xlsx"; filename*=UTF-8\'\'{quote(filename)}'
            )
        },
    )


@router.get("/{order_id}/pdf")
def api_download_plating_pdf(order_id: str, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    file_bytes, filename = build_plating_order_pdf(db, order_id)
    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="plating-export.pdf"; filename*=UTF-8\'\'{quote(filename)}'
            )
        },
    )


@router.post("/{order_id}/send", response_model=PlatingResponse)
def api_send_plating_order(order_id: str, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    with service_errors():
        order = send_plating_order(db, order_id)
    return order


@router.post("/{order_id}/receive", response_model=list[PlatingItemResponse])
def api_receive_plating_items(order_id: str, body: ReceiptRequest, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    with service_errors():
        updated = receive_plating_items(
            db,
            order_id,
            [r.model_dump() for r in body.receipts],
        )
    return updated


@router.post("/{order_id}/items", response_model=PlatingItemResponse, status_code=201)
def api_add_plating_item(order_id: str, body: PlatingItemCreate, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    with service_errors():
        item = add_plating_item(db, order_id, body.model_dump())
    return item


@router.put("/{order_id}/items/{item_id}", response_model=PlatingItemResponse)
def api_update_plating_item(order_id: str, item_id: int, body: PlatingItemUpdate, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    with service_errors():
        item = update_plating_item(db, order_id, item_id, body.model_dump(exclude_unset=True))
    return item


@router.delete("/{order_id}/items/{item_id}", status_code=204)
def api_delete_plating_item(order_id: str, item_id: int, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    with service_errors():
        delete_plating_item(db, order_id, item_id)


@router.patch("/{order_id}/status", response_model=PlatingResponse)
def api_update_plating_status(order_id: str, body: StatusUpdate, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    with service_errors():
        order = update_plating_order_status(db, order_id, body.status)
    return order


@router.patch("/{order_id}/delivery-images", response_model=PlatingResponse)
def api_update_plating_delivery_images(order_id: str, body: PlatingDeliveryImagesUpdate, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    with service_errors():
        order = update_plating_delivery_images(db, order_id, body.delivery_images)
    return order
