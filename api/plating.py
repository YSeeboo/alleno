from datetime import date as date_type
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.plating import (
    PendingReceiveItemResponse,
    PlatingCreate,
    PlatingDeliveryImagesUpdate,
    PlatingItemCreate,
    PlatingItemResponse,
    PlatingResponse,
    PlatingUpdate,
)
from schemas.production_loss import ConfirmLossRequest, ProductionLossResponse
from services.production_loss import confirm_plating_loss
from services.order_todo import get_links_for_production_item, get_links_for_plating_order, delete_link
from services.plating_excel import build_plating_order_excel
from services.plating_pdf import build_plating_order_pdf
from services.plating import (
    add_plating_item,
    create_plating_order,
    delete_plating_order,
    delete_plating_item,
    get_plating_order,
    get_plating_items,
    get_plating_supplier_names,
    list_pending_receive_items,
    list_plating_orders,
    send_plating_order,
    update_plating_delivery_images,
    update_plating_item,
    update_plating_order,
    update_plating_order_status,
)


class PlatingItemUpdate(BaseModel):
    part_id: Optional[str] = None
    qty: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = None
    plating_method: Optional[str] = None
    note: Optional[str] = None
    receive_part_id: Optional[str] = None


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
def api_list_plating_orders(status: Optional[str] = None, supplier_name: Optional[str] = None, db: Session = Depends(get_db)):
    with service_errors():
        return list_plating_orders(db, status=status, supplier_name=supplier_name)


@router.get("/suppliers", response_model=list[str])
def api_get_plating_supplier_names(db: Session = Depends(get_db)):
    return get_plating_supplier_names(db)


@router.get("/items/pending-receive", response_model=list[PendingReceiveItemResponse])
def api_list_pending_receive_items(
    part_keyword: str = None,
    supplier_name: str = None,
    date_on: date_type = None,
    exclude_item_ids: list[int] = Query(None),
    db: Session = Depends(get_db),
):
    with service_errors():
        return list_pending_receive_items(
            db, part_keyword, supplier_name=supplier_name,
            date_on=date_on, exclude_item_ids=exclude_item_ids or None,
        )


@router.get("/{order_id}", response_model=PlatingResponse)
def api_get_plating_order(order_id: str, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    return order


@router.patch("/{order_id}", response_model=PlatingResponse)
def api_update_plating_order(order_id: str, body: PlatingUpdate, db: Session = Depends(get_db)):
    with service_errors():
        return update_plating_order(db, order_id, body.model_dump())


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


@router.post("/{order_id}/items/{item_id}/confirm-loss", response_model=ProductionLossResponse)
def api_confirm_plating_loss(order_id: str, item_id: int, body: ConfirmLossRequest, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    with service_errors():
        return confirm_plating_loss(
            db, order_id, item_id,
            loss_qty=body.loss_qty,
            deduct_amount=body.deduct_amount,
            reason=body.reason,
            note=body.note,
        )


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


@router.get("/{order_id}/items/order-links")
def api_get_plating_all_item_orders(order_id: str, db: Session = Depends(get_db)):
    """批量获取电镀单所有配件项的关联订单"""
    from services.plating import get_plating_order
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    return get_links_for_plating_order(db, order_id)


@router.get("/{order_id}/items/{item_id}/orders")
def api_get_plating_item_orders(order_id: str, item_id: int, db: Session = Depends(get_db)):
    """获取电镀配件项关联的订单列表"""
    from models.plating_order import PlatingOrderItem
    poi = db.get(PlatingOrderItem, item_id)
    if poi is None or poi.plating_order_id != order_id:
        raise HTTPException(status_code=404, detail="配件项不存在或不属于该电镀单")
    return get_links_for_production_item(db, plating_order_item_id=item_id)


@router.delete("/{order_id}/items/{item_id}/orders/{link_id}", status_code=204)
def api_delete_plating_item_order_link(order_id: str, item_id: int, link_id: int, db: Session = Depends(get_db)):
    """从电镀单侧解除关联"""
    from models.plating_order import PlatingOrderItem
    from models.order import OrderItemLink
    poi = db.get(PlatingOrderItem, item_id)
    if poi is None or poi.plating_order_id != order_id:
        raise HTTPException(status_code=404, detail="配件项不存在或不属于该电镀单")
    link = db.get(OrderItemLink, link_id)
    if link is None or link.plating_order_item_id != item_id:
        raise HTTPException(status_code=404, detail="Link not found for this item")
    with service_errors():
        delete_link(db, link_id)
