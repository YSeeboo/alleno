from typing import Optional

from sqlalchemy.orm import Session

from models.order import Order, OrderItem, OrderTodoItem, OrderItemLink
from models.part import Part
from models.plating_order import PlatingOrderItem
from models.handcraft_order import HandcraftPartItem, HandcraftJewelryItem
from models.purchase_order import PurchaseOrderItem
from services.bom import get_bom
from services.inventory import get_stock


def generate_todo(db: Session, order_id: str) -> list[dict]:
    """基于订单饰品的 BOM 生成配件 TodoList，持久化存储。

    如果已有 TodoList，重新生成时保留能匹配的关联关系（按 part_id 匹配）。
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        raise ValueError(f"Order not found: {order_id}")

    # 计算 BOM 需求
    items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    summary: dict[str, float] = {}
    for item in items:
        bom_rows = get_bom(db, item.jewelry_id)
        for row in bom_rows:
            summary[row.part_id] = summary.get(row.part_id, 0.0) + float(row.qty_per_unit) * item.quantity

    # 获取现有 todo items 及其关联
    old_todos = db.query(OrderTodoItem).filter(OrderTodoItem.order_id == order_id).all()
    # 按 part_id 索引旧的 todo item id，用于保留关联
    old_by_part: dict[str, int] = {t.part_id: t.id for t in old_todos}

    # 删除不再需要的 todo items（part_id 不在新 summary 中）
    for todo in old_todos:
        if todo.part_id not in summary:
            # 删除关联
            db.query(OrderItemLink).filter(
                OrderItemLink.order_todo_item_id == todo.id
            ).delete(synchronize_session=False)
            db.delete(todo)
        else:
            # 更新数量
            todo.required_qty = summary[todo.part_id]
    db.flush()

    # 添加新的 todo items（part_id 不在旧列表中）
    existing_parts = {t.part_id for t in old_todos if t.part_id in summary}
    for part_id, qty in summary.items():
        if part_id not in existing_parts:
            db.add(OrderTodoItem(
                order_id=order_id,
                part_id=part_id,
                required_qty=qty,
            ))
    db.flush()

    return get_todo(db, order_id)


def get_todo(db: Session, order_id: str) -> list[dict]:
    """获取订单的 TodoList，返回 enriched 字典列表。"""
    todos = (
        db.query(OrderTodoItem)
        .filter(OrderTodoItem.order_id == order_id)
        .order_by(OrderTodoItem.id.asc())
        .all()
    )
    results = []
    for todo in todos:
        part = db.get(Part, todo.part_id)
        stock = get_stock(db, "part", todo.part_id)
        required = float(todo.required_qty)
        results.append({
            "id": todo.id,
            "order_id": todo.order_id,
            "part_id": todo.part_id,
            "required_qty": required,
            "part_name": part.name if part else None,
            "part_image": part.image if part else None,
            "stock_qty": stock,
            "gap": max(0.0, required - stock),
            "is_complete": stock >= required,
            "linked_production": _get_linked_production(db, todo.id),
        })
    return results


def _get_linked_production(db: Session, todo_item_id: int) -> list[dict]:
    """获取关联到某 TodoList 行的所有生产项及状态。"""
    links = db.query(OrderItemLink).filter(
        OrderItemLink.order_todo_item_id == todo_item_id
    ).all()
    result = []
    for link in links:
        if link.plating_order_item_id:
            poi = db.get(PlatingOrderItem, link.plating_order_item_id)
            if poi:
                result.append({
                    "link_id": link.id,
                    "type": "plating",
                    "order_id": poi.plating_order_id,
                    "item_id": poi.id,
                    "part_id": poi.part_id,
                    "status": poi.status,
                })
        elif link.handcraft_part_item_id:
            hpi = db.get(HandcraftPartItem, link.handcraft_part_item_id)
            if hpi:
                result.append({
                    "link_id": link.id,
                    "type": "handcraft_part",
                    "order_id": hpi.handcraft_order_id,
                    "item_id": hpi.id,
                    "part_id": hpi.part_id,
                    "status": hpi.status,
                })
        elif link.purchase_order_item_id:
            poi = db.get(PurchaseOrderItem, link.purchase_order_item_id)
            if poi:
                result.append({
                    "link_id": link.id,
                    "type": "purchase",
                    "order_id": poi.purchase_order_id,
                    "item_id": poi.id,
                    "part_id": poi.part_id,
                    "status": "已采购",
                })
    return result


def create_link(db: Session, data: dict) -> OrderItemLink:
    """创建单个关联。"""
    # 校验四选一
    production_keys = ["plating_order_item_id", "handcraft_part_item_id", "handcraft_jewelry_item_id", "purchase_order_item_id"]
    set_keys = [k for k in production_keys if data.get(k) is not None]
    if len(set_keys) != 1:
        raise ValueError("必须指定且仅指定一个生产项（plating_order_item_id / handcraft_part_item_id / handcraft_jewelry_item_id / purchase_order_item_id）")

    # 校验关联目标（todo_item 或 order_id 二选一）
    has_todo = data.get("order_todo_item_id") is not None
    has_order = data.get("order_id") is not None
    if not has_todo and not has_order:
        raise ValueError("必须指定 order_todo_item_id 或 order_id")
    if has_todo and has_order:
        raise ValueError("order_todo_item_id 和 order_id 不能同时指定")

    # 饰品项只能用 order_id
    if data.get("handcraft_jewelry_item_id") and has_todo:
        raise ValueError("手工饰品项只能关联 order_id，不能关联 TodoList 行")

    # 配件项只能用 order_todo_item_id
    if (data.get("plating_order_item_id") or data.get("handcraft_part_item_id") or data.get("purchase_order_item_id")) and has_order:
        raise ValueError("配件项只能关联 TodoList 行，不能直接关联 order_id")

    # 校验 todo_item 存在
    todo = None
    if has_todo:
        todo = db.get(OrderTodoItem, data["order_todo_item_id"])
        if todo is None:
            raise ValueError(f"OrderTodoItem not found: {data['order_todo_item_id']}")

    # 校验 order 存在
    if has_order:
        order = db.query(Order).filter(Order.id == data["order_id"]).first()
        if order is None:
            raise ValueError(f"Order not found: {data['order_id']}")

        # 校验饰品项的 jewelry_id 在订单中存在
        if data.get("handcraft_jewelry_item_id"):
            hji = db.get(HandcraftJewelryItem, data["handcraft_jewelry_item_id"])
            if hji is None:
                raise ValueError(f"HandcraftJewelryItem not found: {data['handcraft_jewelry_item_id']}")
            order_jewelry_ids = {
                oi.jewelry_id
                for oi in db.query(OrderItem).filter(OrderItem.order_id == data["order_id"]).all()
            }
            if hji.jewelry_id not in order_jewelry_ids:
                raise ValueError(f"该订单不包含饰品 {hji.jewelry_id}，无法关联")

    # 校验配件项的 part_id 与 todo 行的 part_id 一致
    if todo is not None:
        prod_part_id = None
        if data.get("plating_order_item_id"):
            poi = db.get(PlatingOrderItem, data["plating_order_item_id"])
            if poi is None:
                raise ValueError(f"PlatingOrderItem not found: {data['plating_order_item_id']}")
            prod_part_id = poi.part_id
        elif data.get("handcraft_part_item_id"):
            hpi = db.get(HandcraftPartItem, data["handcraft_part_item_id"])
            if hpi is None:
                raise ValueError(f"HandcraftPartItem not found: {data['handcraft_part_item_id']}")
            prod_part_id = hpi.part_id
        elif data.get("purchase_order_item_id"):
            poi = db.get(PurchaseOrderItem, data["purchase_order_item_id"])
            if poi is None:
                raise ValueError(f"PurchaseOrderItem not found: {data['purchase_order_item_id']}")
            prod_part_id = poi.part_id
        if prod_part_id and prod_part_id != todo.part_id:
            raise ValueError(f"生产项配件 {prod_part_id} 与 TodoList 行配件 {todo.part_id} 不匹配")

    # 校验唯一性：同一个生产项只能关联一个订单
    prod_key = set_keys[0]
    prod_id = data[prod_key]
    existing = db.query(OrderItemLink).filter(
        getattr(OrderItemLink, prod_key) == prod_id
    ).first()
    if existing:
        raise ValueError(f"该生产项已关联订单，请先解除关联")

    link = OrderItemLink(
        order_todo_item_id=data.get("order_todo_item_id"),
        order_id=data.get("order_id"),
        plating_order_item_id=data.get("plating_order_item_id"),
        handcraft_part_item_id=data.get("handcraft_part_item_id"),
        handcraft_jewelry_item_id=data.get("handcraft_jewelry_item_id"),
        purchase_order_item_id=data.get("purchase_order_item_id"),
    )
    db.add(link)
    db.flush()
    return link


def delete_link(db: Session, link_id: int) -> None:
    """解除关联。"""
    link = db.get(OrderItemLink, link_id)
    if link is None:
        raise ValueError(f"OrderItemLink not found: {link_id}")
    db.delete(link)
    db.flush()


def batch_link(
    db: Session,
    order_id: str,
    plating_order_item_ids: list[int] = None,
    handcraft_part_item_ids: list[int] = None,
    purchase_order_item_ids: list[int] = None,
) -> dict:
    """批量关联：按 part_id 自动匹配 TodoList 行。

    返回 {"linked": 成功数, "skipped": [未匹配的配件名]}
    """
    # 获取订单的 TodoList，按 part_id 索引
    todos = db.query(OrderTodoItem).filter(OrderTodoItem.order_id == order_id).all()
    if not todos:
        raise ValueError(f"订单 {order_id} 尚未生成配件清单，请先生成")
    todo_by_part: dict[str, int] = {t.part_id: t.id for t in todos}

    linked = 0
    skipped = []

    for poi_id in (plating_order_item_ids or []):
        poi = db.get(PlatingOrderItem, poi_id)
        if poi is None:
            continue
        # 检查是否已关联
        existing = db.query(OrderItemLink).filter(
            OrderItemLink.plating_order_item_id == poi_id
        ).first()
        if existing:
            continue
        todo_id = todo_by_part.get(poi.part_id)
        if todo_id is None:
            part = db.get(Part, poi.part_id)
            skipped.append(part.name if part else poi.part_id)
            continue
        db.add(OrderItemLink(
            order_todo_item_id=todo_id,
            plating_order_item_id=poi_id,
        ))
        linked += 1

    for hpi_id in (handcraft_part_item_ids or []):
        hpi = db.get(HandcraftPartItem, hpi_id)
        if hpi is None:
            continue
        existing = db.query(OrderItemLink).filter(
            OrderItemLink.handcraft_part_item_id == hpi_id
        ).first()
        if existing:
            continue
        todo_id = todo_by_part.get(hpi.part_id)
        if todo_id is None:
            part = db.get(Part, hpi.part_id)
            skipped.append(part.name if part else hpi.part_id)
            continue
        db.add(OrderItemLink(
            order_todo_item_id=todo_id,
            handcraft_part_item_id=hpi_id,
        ))
        linked += 1

    for poi_id in (purchase_order_item_ids or []):
        poi = db.get(PurchaseOrderItem, poi_id)
        if poi is None:
            continue
        existing = db.query(OrderItemLink).filter(
            OrderItemLink.purchase_order_item_id == poi_id
        ).first()
        if existing:
            continue
        todo_id = todo_by_part.get(poi.part_id)
        if todo_id is None:
            part = db.get(Part, poi.part_id)
            skipped.append(part.name if part else poi.part_id)
            continue
        db.add(OrderItemLink(
            order_todo_item_id=todo_id,
            purchase_order_item_id=poi_id,
        ))
        linked += 1

    db.flush()
    return {"linked": linked, "skipped": skipped}


def get_links_for_production_item(
    db: Session,
    plating_order_item_id: int = None,
    handcraft_part_item_id: int = None,
    handcraft_jewelry_item_id: int = None,
    purchase_order_item_id: int = None,
) -> list[dict]:
    """获取某个生产项关联的订单信息（反向查询，用于电镀/手工/采购单详情页）。"""
    q = db.query(OrderItemLink)
    if plating_order_item_id:
        q = q.filter(OrderItemLink.plating_order_item_id == plating_order_item_id)
    elif handcraft_part_item_id:
        q = q.filter(OrderItemLink.handcraft_part_item_id == handcraft_part_item_id)
    elif handcraft_jewelry_item_id:
        q = q.filter(OrderItemLink.handcraft_jewelry_item_id == handcraft_jewelry_item_id)
    elif purchase_order_item_id:
        q = q.filter(OrderItemLink.purchase_order_item_id == purchase_order_item_id)
    else:
        return []

    links = q.all()
    result = []
    for link in links:
        order_id = link.order_id
        if link.order_todo_item_id:
            todo = db.get(OrderTodoItem, link.order_todo_item_id)
            order_id = todo.order_id if todo else None
        if order_id:
            order = db.query(Order).filter(Order.id == order_id).first()
            result.append({
                "order_id": order_id,
                "customer_name": order.customer_name if order else None,
                "link_id": link.id,
            })
    return result


def get_order_progress(db: Session, order_id: str) -> dict:
    """获取订单的生产进度概要。"""
    # 通过 TodoList 关联的配件项
    todo_ids = [t.id for t in db.query(OrderTodoItem).filter(OrderTodoItem.order_id == order_id).all()]

    links = []
    if todo_ids:
        links.extend(
            db.query(OrderItemLink)
            .filter(OrderItemLink.order_todo_item_id.in_(todo_ids))
            .all()
        )
    # 直接关联 order_id 的饰品项
    links.extend(
        db.query(OrderItemLink)
        .filter(OrderItemLink.order_id == order_id)
        .all()
    )

    total = len(links)
    completed = 0
    for link in links:
        if link.plating_order_item_id:
            poi = db.get(PlatingOrderItem, link.plating_order_item_id)
            if poi and poi.status == "已收回":
                completed += 1
        elif link.handcraft_part_item_id:
            hpi = db.get(HandcraftPartItem, link.handcraft_part_item_id)
            if hpi and hpi.status == "已收回":
                completed += 1
        elif link.handcraft_jewelry_item_id:
            hji = db.get(HandcraftJewelryItem, link.handcraft_jewelry_item_id)
            if hji and hji.status == "已收回":
                completed += 1
        elif link.purchase_order_item_id:
            # 采购单配件项存在即视为已完成
            poi = db.get(PurchaseOrderItem, link.purchase_order_item_id)
            if poi:
                completed += 1

    return {"order_id": order_id, "total": total, "completed": completed}
