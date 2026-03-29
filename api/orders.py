from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from sqlalchemy.orm import Session

from database import get_db
from schemas.order import (
    OrderCreate, OrderResponse, OrderItemResponse, StatusUpdate,
    OrderTodoItemResponse, LinkCreateRequest, LinkResponse,
    BatchLinkRequest, BatchLinkResponse, OrderProgressResponse,
)
from schemas.order import OrderItemCreate
from services.order import (
    add_order_item,
    create_order,
    delete_order_item,
    get_order,
    get_order_items,
    get_parts_summary,
    update_order_status,
    list_orders,
)
from services.order_todo import (
    generate_todo, get_todo, create_link, delete_link,
    batch_link, get_order_progress,
)
from api._errors import service_errors

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


@router.post("/{order_id}/items", response_model=OrderItemResponse, status_code=201)
def api_add_order_item(order_id: str, body: OrderItemCreate, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        return add_order_item(db, order_id, body.model_dump())


@router.delete("/{order_id}/items/{item_id}", status_code=204)
def api_delete_order_item(order_id: str, item_id: int, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        delete_order_item(db, order_id, item_id)


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
        )
    return result


@router.delete("/links/{link_id}", status_code=204)
def api_delete_link(link_id: int, db: Session = Depends(get_db)):
    """解除关联（从订单侧）"""
    with service_errors():
        delete_link(db, link_id)


# --- Progress ---

@router.get("/{order_id}/progress", response_model=OrderProgressResponse)
def api_get_order_progress(order_id: str, db: Session = Depends(get_db)):
    """获取订单生产进度概要"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return get_order_progress(db, order_id)
