from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from typing import Optional
from sqlalchemy.orm import Session

from pydantic import BaseModel as _BaseModel, Field as _Field

from database import get_db
from schemas.order import (
    OrderCreate, OrderResponse, OrderItemResponse, StatusUpdate,
    OrderTodoItemResponse, LinkCreateRequest, LinkResponse,
    BatchLinkRequest, BatchLinkResponse, OrderProgressResponse,
    OrderItemUpdate, BatchCustomerCodeRequest, PartsSummaryItemResponse,
    PickingSimulationResponse, PickingMarkRequest, PickingPdfRequest,
    OrderItemCreate, ExtraInfoUpdate,
    TodoBatchCreateRequest, LinkSupplierRequest,
)
from schemas.order_cost_snapshot import OrderCostSnapshotResponse
from services.order import (
    add_order_item,
    create_order,
    delete_order_item,
    enrich_order_items,
    get_order,
    get_order_items,
    get_parts_summary,
    update_extra_info,
    update_order_status,
    update_packaging_cost,
    update_order_item,
    batch_fill_customer_code,
    list_orders,
)
from services.order_cost_snapshot import get_cost_snapshot
from services.order_todo import (
    generate_todo, get_todo, create_link, delete_link,
    batch_link, get_order_progress, batch_get_order_progress, get_jewelry_status,
    get_jewelry_for_batch, create_batch, get_batches, link_supplier, delete_batch,
)
from services.order_todo_pdf import build_order_todo_pdf
from services.cutting_stats import get_order_cutting_stats
from services.cutting_stats_pdf import build_cutting_stats_pdf
from services.picking import (
    get_picking_simulation, mark_picked, unmark_picked, reset_picking,
)
from services.picking_list_pdf import build_picking_list_pdf
from api._errors import service_errors


class PackagingCostUpdate(_BaseModel):
    packaging_cost: float = _Field(ge=0)


router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("/", response_model=list[OrderResponse])
def api_list_orders(
    status: Optional[str] = None,
    customer_name: Optional[str] = None,
    db: Session = Depends(get_db),
):
    with service_errors():
        return list_orders(db, status=status, customer_name=customer_name)


@router.post("/", response_model=OrderResponse, status_code=201)
def api_create_order(body: OrderCreate, db: Session = Depends(get_db)):
    items = [item.model_dump() for item in body.items]
    with service_errors():
        order = create_order(db, body.customer_name, items, created_at=body.created_at)
    return order


@router.get("/batch-progress")
def api_batch_get_progress(order_ids: str, db: Session = Depends(get_db)):
    """批量获取多个订单的备货进度。order_ids 以逗号分隔。"""
    ids = [oid.strip() for oid in order_ids.split(",") if oid.strip()]
    if not ids:
        return []
    return batch_get_order_progress(db, ids)


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
    items = get_order_items(db, order_id)
    return enrich_order_items(db, items)


@router.post("/{order_id}/items", response_model=OrderItemResponse, status_code=201)
def api_add_order_item(order_id: str, body: OrderItemCreate, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        item = add_order_item(db, order_id, body.model_dump())
    return enrich_order_items(db, [item])[0]


@router.post("/{order_id}/items/batch-customer-code")
def api_batch_customer_code(order_id: str, body: BatchCustomerCodeRequest, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        count = batch_fill_customer_code(
            db, order_id, body.item_ids, body.prefix, body.start_number, body.padding,
        )
        return {"updated_count": count}


@router.patch("/{order_id}/items/{item_id}", response_model=OrderItemResponse)
def api_update_order_item(order_id: str, item_id: int, body: OrderItemUpdate, db: Session = Depends(get_db)):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="请提供至少一个要修改的字段")
    with service_errors():
        item = update_order_item(db, order_id, item_id, fields)
    return enrich_order_items(db, [item])[0]


@router.delete("/{order_id}/items/{item_id}", status_code=204)
def api_delete_order_item(order_id: str, item_id: int, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        delete_order_item(db, order_id, item_id)


@router.get("/{order_id}/parts-summary", response_model=list[PartsSummaryItemResponse])
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


@router.get("/{order_id}/cost-snapshot", response_model=OrderCostSnapshotResponse | None)
def api_get_cost_snapshot(order_id: str, db: Session = Depends(get_db)):
    """获取订单的成本快照"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return get_cost_snapshot(db, order_id)


@router.get("/{order_id}/todo-pdf")
def api_download_todo_pdf(order_id: str, batch_id: int | None = None, db: Session = Depends(get_db)):
    """导出配件清单 PDF"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    file_bytes, filename = build_order_todo_pdf(
        db, order_id, order.customer_name, order.created_at,
        batch_id=batch_id,
    )
    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="todo-{order_id}.pdf"; filename*=UTF-8\'\'{quote(filename)}'
            )
        },
    )



@router.get("/{order_id}/cutting-stats")
def api_get_order_cutting_stats(order_id: str, db: Session = Depends(get_db)):
    """获取订单裁剪统计"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        items = get_order_cutting_stats(db, order_id)
    return {"items": items}


@router.post("/{order_id}/cutting-stats/pdf")
def api_download_order_cutting_stats_pdf(order_id: str, db: Session = Depends(get_db)):
    """导出订单裁剪统计 PDF"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        all_items = get_order_cutting_stats(db, order_id)
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


@router.patch("/{order_id}/extra-info", response_model=OrderResponse)
def api_update_extra_info(order_id: str, body: ExtraInfoUpdate, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        order = update_extra_info(db, order_id, body.model_dump(exclude_unset=True))
    return order


@router.patch("/{order_id}/packaging-cost", response_model=OrderResponse)
def api_update_packaging_cost(order_id: str, body: PackagingCostUpdate, db: Session = Depends(get_db)):
    """更新订单包装费"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        order = update_packaging_cost(db, order_id, body.packaging_cost)
    return order


# --- TodoList ---

@router.post("/{order_id}/todo", response_model=list[OrderTodoItemResponse])
def api_generate_todo(order_id: str, db: Session = Depends(get_db)):
    """手动生成/重新生成配件 TodoList"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        return generate_todo(db, order_id)


@router.get("/{order_id}/todo", response_model=list[OrderTodoItemResponse])
def api_get_todo(order_id: str, db: Session = Depends(get_db)):
    """获取配件 TodoList"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return get_todo(db, order_id)


# --- Link ---

@router.post("/{order_id}/links", response_model=LinkResponse, status_code=201)
def api_create_link(order_id: str, body: LinkCreateRequest, db: Session = Depends(get_db)):
    """单选关联"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    data = body.model_dump()
    # 确保饰品项关联的 order_id 与路径一致
    if body.order_id and body.order_id != order_id:
        raise HTTPException(status_code=400, detail="body order_id 与路径 order_id 不一致")
    if body.handcraft_jewelry_item_id:
        data["order_id"] = order_id
    # 校验 todo_item 属于该订单
    if body.order_todo_item_id:
        from models.order import OrderTodoItem
        todo = db.get(OrderTodoItem, body.order_todo_item_id)
        if todo and todo.order_id != order_id:
            raise HTTPException(status_code=400, detail="TodoItem 不属于该订单")
    with service_errors():
        link = create_link(db, data)
    return link


@router.post("/{order_id}/links/batch", response_model=BatchLinkResponse)
def api_batch_link(order_id: str, body: BatchLinkRequest, db: Session = Depends(get_db)):
    """批量关联：按 part_id 自动匹配 TodoList 行"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        result = batch_link(
            db,
            order_id=order_id,
            plating_order_item_ids=body.plating_order_item_ids,
            handcraft_part_item_ids=body.handcraft_part_item_ids,
            purchase_order_item_ids=body.purchase_order_item_ids,
        )
    return result


@router.delete("/links/{link_id}", status_code=204)
def api_delete_link(link_id: int, db: Session = Depends(get_db)):
    """解除关联（从订单侧）"""
    with service_errors():
        delete_link(db, link_id)


# --- Progress ---

@router.get("/{order_id}/jewelry-status")
def api_jewelry_status(order_id: str, db: Session = Depends(get_db)):
    with service_errors():
        return get_jewelry_status(db, order_id)


@router.get("/{order_id}/jewelry-for-batch")
def api_jewelry_for_batch(order_id: str, db: Session = Depends(get_db)):
    with service_errors():
        return get_jewelry_for_batch(db, order_id)


@router.post("/{order_id}/todo-batch")
def api_create_todo_batch(order_id: str, req: TodoBatchCreateRequest, db: Session = Depends(get_db)):
    items = [(item.jewelry_id, item.quantity) for item in req.items]
    with service_errors():
        return create_batch(db, order_id, items)


@router.get("/{order_id}/todo-batches")
def api_get_todo_batches(order_id: str, db: Session = Depends(get_db)):
    with service_errors():
        return {"batches": get_batches(db, order_id)}


@router.post("/{order_id}/todo-batch/{batch_id}/link-supplier")
def api_link_batch_supplier(
    order_id: str,
    batch_id: int,
    req: LinkSupplierRequest,
    db: Session = Depends(get_db),
):
    with service_errors():
        return link_supplier(db, order_id, batch_id, req.supplier_name)


@router.delete("/{order_id}/todo-batch/{batch_id}", status_code=204)
def api_delete_batch(order_id: str, batch_id: int, db: Session = Depends(get_db)):
    with service_errors():
        delete_batch(db, order_id, batch_id)


@router.get("/{order_id}/progress", response_model=OrderProgressResponse)
def api_get_order_progress(order_id: str, db: Session = Depends(get_db)):
    """获取订单备料进度概要"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return get_order_progress(db, order_id)


# --- Picking simulation (配货模拟) ---


@router.get("/{order_id}/picking", response_model=PickingSimulationResponse)
def api_get_picking(order_id: str, db: Session = Depends(get_db)):
    """Aggregate order parts into a picking-oriented structure, join picked state."""
    with service_errors():
        return get_picking_simulation(db, order_id)


@router.post("/{order_id}/picking/mark")
def api_picking_mark(
    order_id: str,
    body: PickingMarkRequest,
    db: Session = Depends(get_db),
):
    """Mark a variant as picked. Idempotent."""
    with service_errors():
        result = mark_picked(db, order_id, body.part_id, body.qty_per_unit)
    return {"picked": result.picked, "picked_at": result.picked_at}


@router.post("/{order_id}/picking/unmark")
def api_picking_unmark(
    order_id: str,
    body: PickingMarkRequest,
    db: Session = Depends(get_db),
):
    """Unmark a variant. Idempotent."""
    with service_errors():
        result = unmark_picked(db, order_id, body.part_id, body.qty_per_unit)
    return {"picked": result.picked}


@router.delete("/{order_id}/picking/reset")
def api_picking_reset(order_id: str, db: Session = Depends(get_db)):
    """Clear all picking records for this order."""
    with service_errors():
        deleted = reset_picking(db, order_id)
    return {"deleted": deleted}


@router.post("/{order_id}/picking/pdf")
def api_picking_pdf(
    order_id: str,
    body: PickingPdfRequest,
    db: Session = Depends(get_db),
):
    """Export the picking list PDF. By default, only unpicked rows appear."""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        file_bytes, filename = build_picking_list_pdf(
            db, order_id, order.customer_name, include_picked=body.include_picked,
        )
    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="picking-list-{order_id}.pdf"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )
