from datetime import date as date_type
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.handcraft import (
    HandcraftCreate,
    HandcraftDeliveryImagesUpdate,
    HandcraftJewelryIn,
    HandcraftJewelryItemResponse,
    HandcraftPartIn,
    HandcraftPartItemResponse,
    HandcraftResponse,
)
from services.handcraft_excel import build_handcraft_order_excel
from services.handcraft_pdf import build_handcraft_order_pdf
from services.handcraft import (
    add_handcraft_jewelry,
    add_handcraft_part,
    create_handcraft_order,
    get_handcraft_supplier_names,
    delete_handcraft_order,
    delete_handcraft_jewelry,
    delete_handcraft_part,
    get_handcraft_jewelries,
    get_handcraft_order,
    get_handcraft_parts,
    list_handcraft_orders,
    list_handcraft_pending_receive_items,
    send_handcraft_order,
    update_handcraft_delivery_images,
    update_handcraft_jewelry,
    update_handcraft_order_status,
    update_handcraft_part,
)


class HandcraftPartUpdate(BaseModel):
    qty: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = None
    note: Optional[str] = None
    bom_qty: Optional[float] = None


class HandcraftJewelryUpdate(BaseModel):
    qty: Optional[int] = Field(None, gt=0)
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
def api_list_handcraft_orders(status: Optional[str] = None, supplier_name: Optional[str] = None, db: Session = Depends(get_db)):
    with service_errors():
        return list_handcraft_orders(db, status=status, supplier_name=supplier_name)


@router.get("/suppliers", response_model=list[str])
def api_get_handcraft_supplier_names(db: Session = Depends(get_db)):
    return get_handcraft_supplier_names(db)


@router.get("/items/pending-receive")
def api_list_handcraft_pending_receive_items(
    keyword: str = None,
    supplier_name: str = None,
    date_on: date_type = None,
    exclude_item_ids: list[int] = Query(None),
    db: Session = Depends(get_db),
):
    with service_errors():
        return list_handcraft_pending_receive_items(
            db, keyword, supplier_name=supplier_name,
            date_on=date_on, exclude_item_ids=exclude_item_ids or None,
        )


@router.get("/{order_id}", response_model=HandcraftResponse)
def api_get_handcraft_order(order_id: str, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    return order


@router.delete("/{order_id}", status_code=204)
def api_delete_handcraft_order(order_id: str, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        delete_handcraft_order(db, order_id)


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


@router.get("/{order_id}/excel")
def api_download_handcraft_excel(order_id: str, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    file_bytes, filename = build_handcraft_order_excel(db, order_id)
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="handcraft-export.xlsx"; filename*=UTF-8\'\'{quote(filename)}'
            )
        },
    )


@router.get("/{order_id}/pdf")
def api_download_handcraft_pdf(order_id: str, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    file_bytes, filename = build_handcraft_order_pdf(db, order_id)
    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="handcraft-export.pdf"; filename*=UTF-8\'\'{quote(filename)}'
            )
        },
    )


@router.post("/{order_id}/send", response_model=HandcraftResponse)
def api_send_handcraft_order(order_id: str, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        order = send_handcraft_order(db, order_id)
    return order



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


@router.patch("/{order_id}/delivery-images", response_model=HandcraftResponse)
def api_update_handcraft_delivery_images(order_id: str, body: HandcraftDeliveryImagesUpdate, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        order = update_handcraft_delivery_images(db, order_id, body.delivery_images)
    return order
