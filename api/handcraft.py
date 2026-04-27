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
    HandcraftPickingMarkRequest,
    HandcraftPickingResponse,
    HandcraftResponse,
    HandcraftSuggestPartItem,
    HandcraftSuggestRequest,
    HandcraftUpdate,
)
from schemas.production_loss import ConfirmLossHandcraftRequest, ProductionLossResponse
from services.production_loss import confirm_handcraft_loss
from services.order_todo import get_links_for_production_item, delete_link
from services.handcraft_excel import build_handcraft_order_excel
from services.handcraft_pdf import build_handcraft_order_pdf
from services.cutting_stats import get_handcraft_cutting_stats
from services.cutting_stats_pdf import build_cutting_stats_pdf
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
    suggest_handcraft_parts,
    update_handcraft_delivery_images,
    update_handcraft_jewelry,
    update_handcraft_order,
    update_handcraft_order_status,
    update_handcraft_part,
)
from services.handcraft_picking import (
    get_handcraft_picking_simulation,
    mark_picked,
    unmark_picked,
    reset_picking,
)
from services.handcraft_picking_list_pdf import build_handcraft_picking_list_pdf


class HandcraftPartUpdate(BaseModel):
    qty: Optional[float] = Field(None, gt=0)
    weight: Optional[float] = Field(None, ge=0)
    weight_unit: Optional[str] = None
    unit: Optional[str] = None
    note: Optional[str] = None
    bom_qty: Optional[float] = None


class HandcraftJewelryUpdate(BaseModel):
    qty: Optional[int] = Field(None, gt=0)
    weight: Optional[float] = Field(None, ge=0)
    weight_unit: Optional[str] = None
    unit: Optional[str] = None
    note: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str

router = APIRouter(prefix="/api/handcraft", tags=["handcraft"])


@router.post("/", response_model=HandcraftResponse, status_code=201, responses={200: {"model": HandcraftResponse, "description": "Merged into existing pending order"}})
def api_create_handcraft_order(body: HandcraftCreate, db: Session = Depends(get_db)):
    with service_errors():
        order = create_handcraft_order(
            db,
            supplier_name=body.supplier_name,
            parts=[p.model_dump() for p in body.parts],
            jewelries=[j.model_dump() for j in body.jewelries],
            note=body.note,
            created_at=body.created_at,
        )
    from fastapi.responses import JSONResponse
    status_code = 200 if getattr(order, "merged", False) else 201
    return JSONResponse(content=HandcraftResponse.model_validate(order).model_dump(mode="json"), status_code=status_code)


@router.get("/", response_model=list[HandcraftResponse])
def api_list_handcraft_orders(status: Optional[str] = None, supplier_name: Optional[str] = None, db: Session = Depends(get_db)):
    with service_errors():
        return list_handcraft_orders(db, status=status, supplier_name=supplier_name)


@router.get("/suppliers", response_model=list[str])
def api_get_handcraft_supplier_names(db: Session = Depends(get_db)):
    return get_handcraft_supplier_names(db)


@router.post("/suggest-parts", response_model=list[HandcraftSuggestPartItem])
def api_suggest_handcraft_parts(body: HandcraftSuggestRequest, db: Session = Depends(get_db)):
    with service_errors():
        return suggest_handcraft_parts(
            db,
            jewelry_items=[item.model_dump() for item in body.jewelry_items],
        )


@router.get("/items/pending-receive")
def api_list_handcraft_pending_receive_items(
    keyword: str = None,
    supplier_name: str = None,
    date_on: date_type = None,
    exclude_part_item_ids: list[int] = Query(None),
    exclude_jewelry_item_ids: list[int] = Query(None),
    db: Session = Depends(get_db),
):
    with service_errors():
        return list_handcraft_pending_receive_items(
            db, keyword, supplier_name=supplier_name,
            date_on=date_on,
            exclude_part_item_ids=exclude_part_item_ids or None,
            exclude_jewelry_item_ids=exclude_jewelry_item_ids or None,
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


@router.get("/{order_id}/cutting-stats")
def api_get_handcraft_cutting_stats(order_id: str, db: Session = Depends(get_db)):
    """获取手工单裁剪统计"""
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        items = get_handcraft_cutting_stats(db, order_id)
    return {"items": items}


@router.post("/{order_id}/cutting-stats/pdf")
def api_download_handcraft_cutting_stats_pdf(order_id: str, db: Session = Depends(get_db)):
    """导出手工单裁剪统计 PDF"""
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        all_items = get_handcraft_cutting_stats(db, order_id)
        items = [i for i in all_items if i["qty"] > 0]
        file_bytes, filename = build_cutting_stats_pdf(items, order_id)
    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="cutting-stats-{order_id}.pdf"; '
                f"filename*=UTF-8''{quote(filename)}"
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


@router.post("/{order_id}/items/{item_id}/confirm-loss", response_model=ProductionLossResponse)
def api_confirm_handcraft_loss(order_id: str, item_id: int, body: ConfirmLossHandcraftRequest, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        return confirm_handcraft_loss(
            db, order_id, item_id,
            item_type=body.item_type,
            loss_qty=body.loss_qty,
            deduct_amount=body.deduct_amount,
            reason=body.reason,
            note=body.note,
        )


@router.patch("/{order_id}", response_model=HandcraftResponse)
def api_update_handcraft_order(order_id: str, body: HandcraftUpdate, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        return update_handcraft_order(db, order_id, body.model_dump(exclude_unset=True))


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


@router.get("/{order_id}/parts/{item_id}/orders")
def api_get_handcraft_part_orders(order_id: str, item_id: int, db: Session = Depends(get_db)):
    """获取手工配件项关联的订单列表"""
    from models.handcraft_order import HandcraftPartItem
    hpi = db.get(HandcraftPartItem, item_id)
    if hpi is None or hpi.handcraft_order_id != order_id:
        raise HTTPException(status_code=404, detail="配件项不存在或不属于该手工单")
    return get_links_for_production_item(db, handcraft_part_item_id=item_id)


@router.delete("/{order_id}/parts/{item_id}/orders/{link_id}", status_code=204)
def api_delete_handcraft_part_order_link(order_id: str, item_id: int, link_id: int, db: Session = Depends(get_db)):
    """从手工单侧解除配件项关联"""
    from models.handcraft_order import HandcraftPartItem
    from models.order import OrderItemLink
    hpi = db.get(HandcraftPartItem, item_id)
    if hpi is None or hpi.handcraft_order_id != order_id:
        raise HTTPException(status_code=404, detail="配件项不存在或不属于该手工单")
    link = db.get(OrderItemLink, link_id)
    if link is None or link.handcraft_part_item_id != item_id:
        raise HTTPException(status_code=404, detail="Link not found for this item")
    with service_errors():
        delete_link(db, link_id)


@router.get("/{order_id}/jewelries/{item_id}/orders")
def api_get_handcraft_jewelry_orders(order_id: str, item_id: int, db: Session = Depends(get_db)):
    """获取手工饰品项关联的订单列表"""
    from models.handcraft_order import HandcraftJewelryItem
    hji = db.get(HandcraftJewelryItem, item_id)
    if hji is None or hji.handcraft_order_id != order_id:
        raise HTTPException(status_code=404, detail="饰品项不存在或不属于该手工单")
    return get_links_for_production_item(db, handcraft_jewelry_item_id=item_id)


@router.delete("/{order_id}/jewelries/{item_id}/orders/{link_id}", status_code=204)
def api_delete_handcraft_jewelry_order_link(order_id: str, item_id: int, link_id: int, db: Session = Depends(get_db)):
    """从手工单侧解除饰品项关联"""
    from models.handcraft_order import HandcraftJewelryItem
    from models.order import OrderItemLink
    hji = db.get(HandcraftJewelryItem, item_id)
    if hji is None or hji.handcraft_order_id != order_id:
        raise HTTPException(status_code=404, detail="饰品项不存在或不属于该手工单")
    link = db.get(OrderItemLink, link_id)
    if link is None or link.handcraft_jewelry_item_id != item_id:
        raise HTTPException(status_code=404, detail="Link not found for this item")
    with service_errors():
        delete_link(db, link_id)


# --- Picking simulation (配货模拟) ---

@router.get("/{order_id}/picking", response_model=HandcraftPickingResponse)
def api_get_handcraft_picking(order_id: str, db: Session = Depends(get_db)):
    """Aggregate handcraft order parts into a picking-oriented grouped structure."""
    with service_errors():
        return get_handcraft_picking_simulation(db, order_id)


@router.post("/{order_id}/picking/mark")
def api_handcraft_picking_mark(
    order_id: str,
    body: HandcraftPickingMarkRequest,
    db: Session = Depends(get_db),
):
    """Mark a (part_item, atom) pair as picked. Idempotent. Pending only."""
    with service_errors():
        result = mark_picked(db, order_id, body.part_item_id, body.part_id)
    return {"picked": result.picked, "picked_at": result.picked_at}


@router.post("/{order_id}/picking/unmark")
def api_handcraft_picking_unmark(
    order_id: str,
    body: HandcraftPickingMarkRequest,
    db: Session = Depends(get_db),
):
    """Unmark a (part_item, atom) pair. Idempotent. Pending only."""
    with service_errors():
        result = unmark_picked(db, order_id, body.part_item_id, body.part_id)
    return {"picked": result.picked}


@router.delete("/{order_id}/picking/reset")
def api_handcraft_picking_reset(order_id: str, db: Session = Depends(get_db)):
    """Clear all picking records for this handcraft order. Pending only."""
    with service_errors():
        deleted = reset_picking(db, order_id)
    return {"deleted": deleted}


@router.post("/{order_id}/picking/pdf")
def api_handcraft_picking_pdf(order_id: str, db: Session = Depends(get_db)):
    """Export the handcraft picking list PDF (unpicked rows only by default)."""
    with service_errors():
        file_bytes, filename = build_handcraft_picking_list_pdf(
            db, order_id, include_picked=False,
        )
    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="handcraft-picking-{order_id}.pdf"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )
