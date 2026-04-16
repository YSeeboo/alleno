from typing import Optional

from sqlalchemy.orm import Session

from models.order import Order, OrderItem, OrderTodoItem, OrderItemLink, OrderTodoBatch, OrderTodoBatchJewelry
from models.part import Part
from models.plating_order import PlatingOrderItem
from models.handcraft_order import HandcraftPartItem, HandcraftJewelryItem
from models.purchase_order import PurchaseOrderItem
from models.bom import Bom
from models.jewelry import Jewelry
from services.bom import get_bom
from services.inventory import get_stock, batch_get_stock


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
    if not todos:
        return []

    # Batch load parts
    part_ids = list({t.part_id for t in todos})
    parts_db = db.query(Part).filter(Part.id.in_(part_ids)).all()
    part_map = {p.id: p for p in parts_db}

    # Batch load stocks
    stock_map = batch_get_stock(db, "part", part_ids)

    # Batch load linked production
    linked_map = _batch_get_linked_production(db, [t.id for t in todos])

    results = []
    for todo in todos:
        part = part_map.get(todo.part_id)
        stock = stock_map.get(todo.part_id, 0.0)
        required = float(todo.required_qty)
        results.append({
            "id": todo.id,
            "order_id": todo.order_id,
            "part_id": todo.part_id,
            "required_qty": required,
            "part_name": part.name if part else None,
            "part_image": part.image if part else None,
            "part_is_composite": part.is_composite if part else None,
            "stock_qty": stock,
            "gap": max(0.0, required - stock),
            "is_complete": stock >= required,
            "linked_production": linked_map.get(todo.id, []),
        })
    return results


def _batch_get_linked_production(db: Session, todo_item_ids: list[int]) -> dict[int, list[dict]]:
    """Batch-load linked production items for multiple todo items. Returns {todo_item_id: [...]]}."""
    if not todo_item_ids:
        return {}

    links = db.query(OrderItemLink).filter(
        OrderItemLink.order_todo_item_id.in_(todo_item_ids)
    ).all()
    if not links:
        return {}

    # Collect all production item IDs by type
    plating_ids = [l.plating_order_item_id for l in links if l.plating_order_item_id]
    handcraft_ids = [l.handcraft_part_item_id for l in links if l.handcraft_part_item_id]
    purchase_ids = [l.purchase_order_item_id for l in links if l.purchase_order_item_id]

    # Batch load all production items
    poi_map = {}
    if plating_ids:
        for poi in db.query(PlatingOrderItem).filter(PlatingOrderItem.id.in_(plating_ids)).all():
            poi_map[poi.id] = poi
    hpi_map = {}
    if handcraft_ids:
        for hpi in db.query(HandcraftPartItem).filter(HandcraftPartItem.id.in_(handcraft_ids)).all():
            hpi_map[hpi.id] = hpi
    pui_map = {}
    if purchase_ids:
        for pui in db.query(PurchaseOrderItem).filter(PurchaseOrderItem.id.in_(purchase_ids)).all():
            pui_map[pui.id] = pui

    # Build result grouped by todo_item_id
    result: dict[int, list[dict]] = {}
    for link in links:
        tid = link.order_todo_item_id
        entry = None
        if link.plating_order_item_id:
            poi = poi_map.get(link.plating_order_item_id)
            if poi:
                entry = {"link_id": link.id, "type": "plating", "order_id": poi.plating_order_id,
                         "item_id": poi.id, "part_id": poi.part_id, "status": poi.status}
        elif link.handcraft_part_item_id:
            hpi = hpi_map.get(link.handcraft_part_item_id)
            if hpi:
                entry = {"link_id": link.id, "type": "handcraft_part", "order_id": hpi.handcraft_order_id,
                         "item_id": hpi.id, "part_id": hpi.part_id, "status": hpi.status}
        elif link.purchase_order_item_id:
            pui = pui_map.get(link.purchase_order_item_id)
            if pui:
                entry = {"link_id": link.id, "type": "purchase", "order_id": pui.purchase_order_id,
                         "item_id": pui.id, "part_id": pui.part_id, "status": "已采购"}
        if entry:
            result.setdefault(tid, []).append(entry)
    return result


def _get_linked_production(db: Session, todo_item_id: int) -> list[dict]:
    """获取关联到某 TodoList 行的所有生产项及状态。"""
    return _batch_get_linked_production(db, [todo_item_id]).get(todo_item_id, [])


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

    # Deduplicate input IDs to preserve idempotency (unique constraint on link columns)
    _plating_ids = list(dict.fromkeys(plating_order_item_ids or []))
    _handcraft_ids = list(dict.fromkeys(handcraft_part_item_ids or []))
    _purchase_ids = list(dict.fromkeys(purchase_order_item_ids or []))

    # Batch load all production items
    poi_map = {}
    if _plating_ids:
        for poi in db.query(PlatingOrderItem).filter(PlatingOrderItem.id.in_(_plating_ids)).all():
            poi_map[poi.id] = poi
    hpi_map = {}
    if _handcraft_ids:
        for hpi in db.query(HandcraftPartItem).filter(HandcraftPartItem.id.in_(_handcraft_ids)).all():
            hpi_map[hpi.id] = hpi
    pui_map = {}
    if _purchase_ids:
        for pui in db.query(PurchaseOrderItem).filter(PurchaseOrderItem.id.in_(_purchase_ids)).all():
            pui_map[pui.id] = pui

    # Batch check existing links
    existing_plating = set()
    if _plating_ids:
        existing_plating = {
            r[0] for r in db.query(OrderItemLink.plating_order_item_id)
            .filter(OrderItemLink.plating_order_item_id.in_(_plating_ids)).all()
        }
    existing_handcraft = set()
    if _handcraft_ids:
        existing_handcraft = {
            r[0] for r in db.query(OrderItemLink.handcraft_part_item_id)
            .filter(OrderItemLink.handcraft_part_item_id.in_(_handcraft_ids)).all()
        }
    existing_purchase = set()
    if _purchase_ids:
        existing_purchase = {
            r[0] for r in db.query(OrderItemLink.purchase_order_item_id)
            .filter(OrderItemLink.purchase_order_item_id.in_(_purchase_ids)).all()
        }

    # Batch load part names for skipped items
    all_part_ids = set()
    for poi in poi_map.values():
        all_part_ids.add(poi.part_id)
    for hpi in hpi_map.values():
        all_part_ids.add(hpi.part_id)
    for pui in pui_map.values():
        all_part_ids.add(pui.part_id)
    part_name_map = {}
    if all_part_ids:
        for p in db.query(Part).filter(Part.id.in_(list(all_part_ids))).all():
            part_name_map[p.id] = p.name

    for poi_id in _plating_ids:
        poi = poi_map.get(poi_id)
        if poi is None or poi_id in existing_plating:
            continue
        todo_id = todo_by_part.get(poi.part_id)
        if todo_id is None:
            skipped.append(part_name_map.get(poi.part_id, poi.part_id))
            continue
        db.add(OrderItemLink(order_todo_item_id=todo_id, plating_order_item_id=poi_id))
        linked += 1

    for hpi_id in _handcraft_ids:
        hpi = hpi_map.get(hpi_id)
        if hpi is None or hpi_id in existing_handcraft:
            continue
        todo_id = todo_by_part.get(hpi.part_id)
        if todo_id is None:
            skipped.append(part_name_map.get(hpi.part_id, hpi.part_id))
            continue
        db.add(OrderItemLink(order_todo_item_id=todo_id, handcraft_part_item_id=hpi_id))
        linked += 1

    for poi_id in _purchase_ids:
        pui = pui_map.get(poi_id)
        if pui is None or poi_id in existing_purchase:
            continue
        todo_id = todo_by_part.get(pui.part_id)
        if todo_id is None:
            skipped.append(part_name_map.get(pui.part_id, pui.part_id))
            continue
        db.add(OrderItemLink(order_todo_item_id=todo_id, purchase_order_item_id=poi_id))
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
    if not links:
        return []

    # Batch load todo items to resolve order_ids
    todo_ids = [l.order_todo_item_id for l in links if l.order_todo_item_id]
    todo_map = {}
    if todo_ids:
        for t in db.query(OrderTodoItem).filter(OrderTodoItem.id.in_(todo_ids)).all():
            todo_map[t.id] = t

    # Collect all order_ids
    order_ids = set()
    for link in links:
        oid = link.order_id
        if link.order_todo_item_id:
            todo = todo_map.get(link.order_todo_item_id)
            oid = todo.order_id if todo else None
        if oid:
            order_ids.add(oid)

    # Batch load orders
    order_map = {}
    if order_ids:
        for o in db.query(Order).filter(Order.id.in_(list(order_ids))).all():
            order_map[o.id] = o

    result = []
    for link in links:
        oid = link.order_id
        if link.order_todo_item_id:
            todo = todo_map.get(link.order_todo_item_id)
            oid = todo.order_id if todo else None
        if oid:
            order = order_map.get(oid)
            result.append({
                "order_id": oid,
                "customer_name": order.customer_name if order else None,
                "link_id": link.id,
            })
    return result


def get_jewelry_status(db: Session, order_id: str) -> list[dict]:
    """Compute status for each jewelry item in the order.

    Priority (highest first):
    1. 完成备货  — jewelry stock >= order quantity
    2. 等待手工返回 — linked to HandcraftJewelryItem (via OrderItemLink or batch)
    3. 等待发往手工 — all BOM parts have sufficient stock
    4. 等待配件备齐 — default
    """
    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise ValueError(f"订单 {order_id} 不存在")

    items = db.query(OrderItem).filter_by(order_id=order_id).all()
    if not items:
        return []

    # Aggregate by jewelry_id (same jewelry may appear multiple times)
    agg_qty: dict[str, int] = {}
    for it in items:
        agg_qty[it.jewelry_id] = agg_qty.get(it.jewelry_id, 0) + it.quantity
    jewelry_ids = list(agg_qty.keys())

    # Batch fetch jewelry stock
    jewelry_stocks = batch_get_stock(db, "jewelry", jewelry_ids)

    # Batch fetch part stock for BOM check
    all_bom = db.query(Bom).filter(Bom.jewelry_id.in_(jewelry_ids)).all()
    all_part_ids = list({b.part_id for b in all_bom})
    part_stocks = batch_get_stock(db, "part", all_part_ids) if all_part_ids else {}

    # Check handcraft links: via OrderItemLink
    linked_jewelry_ids_via_link = set()
    links = (
        db.query(OrderItemLink.handcraft_jewelry_item_id)
        .filter(
            OrderItemLink.order_id == order_id,
            OrderItemLink.handcraft_jewelry_item_id.isnot(None),
        )
        .all()
    )
    if links:
        hc_item_ids = [l[0] for l in links]
        hc_items = db.query(HandcraftJewelryItem).filter(
            HandcraftJewelryItem.id.in_(hc_item_ids)
        ).all()
        linked_jewelry_ids_via_link = {hci.jewelry_id for hci in hc_items}

    # Check handcraft links: via batch
    linked_jewelry_ids_via_batch = set()
    batches = (
        db.query(OrderTodoBatch)
        .filter(
            OrderTodoBatch.order_id == order_id,
            OrderTodoBatch.handcraft_order_id.isnot(None),
        )
        .all()
    )
    for batch in batches:
        hc_j_items = (
            db.query(HandcraftJewelryItem)
            .filter_by(handcraft_order_id=batch.handcraft_order_id)
            .all()
        )
        for hci in hc_j_items:
            linked_jewelry_ids_via_batch.add(hci.jewelry_id)

    linked_jewelry_ids = linked_jewelry_ids_via_link | linked_jewelry_ids_via_batch

    # Build BOM lookup: jewelry_id -> [(part_id, qty_per_unit)]
    bom_map: dict[str, list[tuple[str, float]]] = {}
    for b in all_bom:
        bom_map.setdefault(b.jewelry_id, []).append((b.part_id, float(b.qty_per_unit)))

    # Fetch jewelry info
    jewelries = db.query(Jewelry).filter(Jewelry.id.in_(jewelry_ids)).all()
    jewelry_info = {j.id: j for j in jewelries}

    result = []
    for jid, qty in agg_qty.items():
        j = jewelry_info.get(jid)

        # Priority 1: 完成备货
        if jewelry_stocks.get(jid, 0) >= qty:
            status = "完成备货"
        # Priority 2: 等待手工返回
        elif jid in linked_jewelry_ids:
            status = "等待手工返回"
        # Priority 3: 等待发往手工
        elif _all_parts_sufficient(bom_map.get(jid, []), qty, part_stocks):
            status = "等待发往手工"
        # Priority 4: default
        else:
            status = "等待配件备齐"

        result.append({
            "jewelry_id": jid,
            "jewelry_name": j.name if j else "",
            "jewelry_image": j.image if j else None,
            "quantity": qty,
            "status": status,
        })

    return result


def _all_parts_sufficient(bom_parts: list[tuple[str, float]], order_qty: int, part_stocks: dict[str, float]) -> bool:
    """Check if all BOM parts have sufficient stock for the given order quantity."""
    if not bom_parts:
        return True
    for part_id, qty_per_unit in bom_parts:
        needed = qty_per_unit * order_qty
        if part_stocks.get(part_id, 0) < needed:
            return False
    return True


def create_batch(db: Session, order_id: str, items: list[tuple[str, int]]) -> dict:
    """Create a new todo batch for selected jewelry items with quantities.

    items: list of (jewelry_id, quantity) tuples
    """
    if not items:
        raise ValueError("items 不能为空")
    jewelry_ids = [jid for jid, _ in items]
    if len(jewelry_ids) != len(set(jewelry_ids)):
        raise ValueError("jewelry_ids 中存在重复项")

    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise ValueError(f"订单 {order_id} 不存在")

    order_items_db = db.query(OrderItem).filter_by(order_id=order_id).all()
    order_jewelry_ids = {oi.jewelry_id for oi in order_items_db}
    for jid in jewelry_ids:
        if jid not in order_jewelry_ids:
            raise ValueError(f"饰品 {jid} 不在订单 {order_id} 中")

    # Get allocation info and validate selectability
    for_batch = get_jewelry_for_batch(db, order_id)
    allocation_map = {fb["jewelry_id"]: fb for fb in for_batch}
    for jid, qty in items:
        if type(qty) is not int or qty <= 0:
            raise ValueError(f"饰品 {jid} 数量必须为正整数")
        alloc = allocation_map.get(jid)
        if alloc and not alloc["selectable"]:
            reason = alloc.get("disabled_reason") or "不可选"
            raise ValueError(f"饰品 {jid} 不可选择：{reason}")
        remaining = alloc["remaining_quantity"] if alloc else 0
        if remaining <= 0:
            raise ValueError(f"饰品 {jid} 无剩余可分配数量")
        if qty > remaining:
            raise ValueError(f"饰品 {jid} 数量 {qty} 超过剩余可分配数量 {remaining}")

    batch = OrderTodoBatch(order_id=order_id)
    db.add(batch)
    db.flush()

    batch_jewelries = []
    for jid, qty in items:
        bj = OrderTodoBatchJewelry(
            batch_id=batch.id,
            jewelry_id=jid,
            quantity=qty,
        )
        db.add(bj)
        batch_jewelries.append(bj)
    db.flush()

    # Generate BOM-based todo items for this batch
    part_qty_map: dict[str, float] = {}
    for bj in batch_jewelries:
        bom_rows = get_bom(db, bj.jewelry_id)
        for bom in bom_rows:
            pid = bom.part_id
            part_qty_map[pid] = part_qty_map.get(pid, 0) + float(bom.qty_per_unit) * bj.quantity

    todo_items = []
    for part_id, required_qty in part_qty_map.items():
        todo = OrderTodoItem(
            order_id=order_id,
            part_id=part_id,
            required_qty=required_qty,
            batch_id=batch.id,
        )
        db.add(todo)
        todo_items.append(todo)
    db.flush()

    return _build_batch_response(db, batch, batch_jewelries, todo_items)


def get_batches(db: Session, order_id: str) -> list[dict]:
    """Get all batches for an order with enriched details."""
    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise ValueError(f"订单 {order_id} 不存在")

    batches = (
        db.query(OrderTodoBatch)
        .filter_by(order_id=order_id)
        .order_by(OrderTodoBatch.created_at)
        .all()
    )

    result = []
    for batch in batches:
        batch_jewelries = (
            db.query(OrderTodoBatchJewelry)
            .filter_by(batch_id=batch.id)
            .all()
        )
        todo_items = (
            db.query(OrderTodoItem)
            .filter_by(batch_id=batch.id)
            .all()
        )
        result.append(_build_batch_response(db, batch, batch_jewelries, todo_items))

    return result


def _build_batch_response(db: Session, batch, batch_jewelries, todo_items) -> dict:
    """Build enriched batch response dict."""
    from models.handcraft_order import HandcraftOrder as HCOrder

    supplier_name = None
    if batch.handcraft_order_id:
        hc = db.query(HCOrder).filter_by(id=batch.handcraft_order_id).first()
        if hc:
            supplier_name = hc.supplier_name
        else:
            batch.handcraft_order_id = None
            db.flush()

    # Enrich jewelry info
    jewelry_ids = [bj.jewelry_id for bj in batch_jewelries]
    jewelries = db.query(Jewelry).filter(Jewelry.id.in_(jewelry_ids)).all() if jewelry_ids else []
    j_info = {j.id: j for j in jewelries}

    jewelry_list = []
    for bj in batch_jewelries:
        j = j_info.get(bj.jewelry_id)
        jewelry_list.append({
            "jewelry_id": bj.jewelry_id,
            "jewelry_name": j.name if j else "",
            "jewelry_image": j.image if j else None,
            "quantity": bj.quantity,
        })

    # Enrich todo items
    part_ids = [t.part_id for t in todo_items]
    parts_db = db.query(Part).filter(Part.id.in_(part_ids)).all() if part_ids else []
    part_info = {p.id: p for p in parts_db}
    part_stocks = batch_get_stock(db, "part", part_ids) if part_ids else {}

    allocated = batch.handcraft_order_id is not None

    # Batch load linked production for all todo items
    linked_map = _batch_get_linked_production(db, [t.id for t in todo_items])

    items_list = []
    for t in todo_items:
        p = part_info.get(t.part_id)
        req = float(t.required_qty)
        if allocated:
            stock_val = None
            gap_val = None
        else:
            stock = part_stocks.get(t.part_id, 0.0)
            stock_val = stock
            gap_val = max(0.0, req - stock)
        items_list.append({
            "id": t.id,
            "order_id": t.order_id,
            "part_id": t.part_id,
            "required_qty": req,
            "batch_id": t.batch_id,
            "part_name": p.name if p else "",
            "part_image": p.image if p else None,
            "part_is_composite": p.is_composite if p else False,
            "stock_qty": stock_val,
            "gap": gap_val,
            "is_allocated": allocated,
            "linked_production": linked_map.get(t.id, []),
        })

    return {
        "id": batch.id,
        "order_id": batch.order_id,
        "handcraft_order_id": batch.handcraft_order_id,
        "supplier_name": supplier_name,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "jewelries": jewelry_list,
        "items": items_list,
    }


def link_supplier(db: Session, order_id: str, batch_id: int, supplier_name: str) -> dict:
    """Link a handcraft supplier to a batch, creating a HandcraftOrder."""
    supplier_name = supplier_name.strip()
    if not supplier_name:
        raise ValueError("供应商名称不能为空")
    from models.supplier import Supplier
    from models.handcraft_order import HandcraftOrder as HCOrder
    from services._helpers import _next_id

    batch = db.query(OrderTodoBatch).filter_by(id=batch_id, order_id=order_id).first()
    if not batch:
        raise ValueError(f"批次 {batch_id} 不存在")
    if batch.handcraft_order_id:
        hc_exists = db.query(HCOrder).filter_by(id=batch.handcraft_order_id).first()
        if hc_exists:
            raise ValueError("该批次已关联手工商家")
        batch.handcraft_order_id = None
        db.flush()

    # Check stock sufficiency (accounting for pending handcraft reservations)
    # Lock pending HandcraftPartItem rows (FOR UPDATE) to serialize concurrent allocations
    todo_items_check = db.query(OrderTodoItem).filter_by(batch_id=batch_id).all()
    if todo_items_check:
        check_part_ids = [t.part_id for t in todo_items_check]
        check_stocks = batch_get_stock(db, "part", check_part_ids)

        # Sum quantities reserved by pending (unsent) handcraft orders
        from sqlalchemy import func as sqla_func
        reserved_rows = (
            db.query(HandcraftPartItem.part_id, sqla_func.sum(HandcraftPartItem.qty))
            .join(HCOrder, HandcraftPartItem.handcraft_order_id == HCOrder.id)
            .filter(
                HCOrder.status == "pending",
                HandcraftPartItem.part_id.in_(check_part_ids),
            )
            .group_by(HandcraftPartItem.part_id)
            .all()
        )
        reserved: dict[str, float] = {}
        for pid, total in reserved_rows:
            reserved[pid] = float(total)

        insufficient = []
        for t in todo_items_check:
            stock = check_stocks.get(t.part_id, 0.0)
            available = stock - reserved.get(t.part_id, 0.0)
            req = float(t.required_qty)
            if available < req:
                insufficient.append(f"{t.part_id} 可用 {available}（库存 {stock}，已预留 {reserved.get(t.part_id, 0.0)}），需要 {req}")
        if insufficient:
            raise ValueError("库存数量不足：" + "；".join(insufficient))

    # Find or create supplier
    supplier = db.query(Supplier).filter_by(name=supplier_name, type="handcraft").first()
    if not supplier:
        supplier = Supplier(name=supplier_name, type="handcraft")
        db.add(supplier)
        db.flush()

    # Auto-merge: reuse existing pending order for same supplier on same day
    from sqlalchemy import Date, func as sa_func
    from time_utils import now_beijing
    today_beijing = now_beijing().date()
    existing_hc = (
        db.query(HCOrder)
        .filter(
            HCOrder.supplier_name == supplier_name,
            HCOrder.status == "pending",
            sa_func.cast(HCOrder.created_at, Date) == today_beijing,
        )
        .order_by(HCOrder.created_at.asc())
        .first()
    )
    if existing_hc:
        hc = existing_hc
        hc_id = hc.id
    else:
        hc_id = _next_id(db, HCOrder, "HC")
        hc = HCOrder(id=hc_id, supplier_name=supplier_name, status="pending")
        db.add(hc)
        db.flush()

    # Migrate parts: batch todo items → HandcraftPartItem
    todo_items = db.query(OrderTodoItem).filter_by(batch_id=batch_id).all()
    for todo in todo_items:
        hc_part = HandcraftPartItem(
            handcraft_order_id=hc_id,
            part_id=todo.part_id,
            qty=float(todo.required_qty),
        )
        db.add(hc_part)
        db.flush()
        link = OrderItemLink(
            order_todo_item_id=todo.id,
            handcraft_part_item_id=hc_part.id,
        )
        db.add(link)

    # Migrate jewelry: batch jewelry → HandcraftJewelryItem
    batch_jewelries = db.query(OrderTodoBatchJewelry).filter_by(batch_id=batch_id).all()
    for bj in batch_jewelries:
        hc_jewelry = HandcraftJewelryItem(
            handcraft_order_id=hc_id,
            jewelry_id=bj.jewelry_id,
            qty=bj.quantity,
        )
        db.add(hc_jewelry)
        db.flush()
        # Record the exact HC jewelry item this batch entry created
        bj.handcraft_jewelry_item_id = hc_jewelry.id
        link = OrderItemLink(
            order_id=order_id,
            handcraft_jewelry_item_id=hc_jewelry.id,
        )
        db.add(link)

    batch.handcraft_order_id = hc_id
    db.flush()

    return {"handcraft_order_id": hc_id}


def delete_batch(db: Session, order_id: str, batch_id: int) -> None:
    """Delete a batch and all associated data.

    - Unlinked batch: delete batch, batch_jewelries, todo_items
    - Pending HC: also delete HC order, HC items, and links
    - Processing/completed HC: reject
    """
    from models.handcraft_order import HandcraftOrder as HCOrder

    batch = db.query(OrderTodoBatch).filter_by(id=batch_id, order_id=order_id).first()
    if not batch:
        raise ValueError(f"批次 {batch_id} 不存在")

    # If linked to a handcraft order, check status
    if batch.handcraft_order_id:
        hc = db.query(HCOrder).filter_by(id=batch.handcraft_order_id).first()
        if hc and hc.status != "pending":
            raise ValueError(f"手工单 {hc.id} 已发出，无法删除该批次")

        if hc:
            # Only delete HC items that were created by this batch (via OrderItemLink),
            # not manually-added items. Keep HC order alive if it still has other items.

            # Collect IDs of HC items to delete (linked from this batch)
            hc_part_ids_to_delete = set()
            hc_jewelry_ids_to_delete = set()

            batch_todo_ids = [
                t.id for t in db.query(OrderTodoItem).filter_by(batch_id=batch_id).all()
            ]
            if batch_todo_ids:
                part_links = (
                    db.query(OrderItemLink)
                    .filter(
                        OrderItemLink.order_todo_item_id.in_(batch_todo_ids),
                        OrderItemLink.handcraft_part_item_id.isnot(None),
                    )
                    .all()
                )
                for link in part_links:
                    hc_part_ids_to_delete.add(link.handcraft_part_item_id)

            # Precisely identify HC jewelry items created by this batch
            # via the recorded handcraft_jewelry_item_id on OrderTodoBatchJewelry
            batch_jewelry_entries = db.query(OrderTodoBatchJewelry).filter_by(
                batch_id=batch_id
            ).all()
            for bj in batch_jewelry_entries:
                if bj.handcraft_jewelry_item_id:
                    hc_jewelry_ids_to_delete.add(bj.handcraft_jewelry_item_id)

            # Step 1: Delete all links and clear batch jewelry FKs
            if batch_todo_ids:
                db.query(OrderItemLink).filter(
                    OrderItemLink.order_todo_item_id.in_(batch_todo_ids),
                    OrderItemLink.handcraft_part_item_id.isnot(None),
                ).delete(synchronize_session=False)
            for jid in hc_jewelry_ids_to_delete:
                db.query(OrderItemLink).filter_by(
                    handcraft_jewelry_item_id=jid
                ).delete()
            # Clear batch jewelry FK references before deleting HC items
            for bj in batch_jewelry_entries:
                bj.handcraft_jewelry_item_id = None
            db.flush()

            # Step 2: Delete the HC items
            if hc_part_ids_to_delete:
                db.query(HandcraftPartItem).filter(
                    HandcraftPartItem.id.in_(hc_part_ids_to_delete)
                ).delete(synchronize_session=False)
            if hc_jewelry_ids_to_delete:
                db.query(HandcraftJewelryItem).filter(
                    HandcraftJewelryItem.id.in_(hc_jewelry_ids_to_delete)
                ).delete(synchronize_session=False)

            # Step 3: Clear batch FK
            batch.handcraft_order_id = None
            db.flush()

            # Step 4: Delete HC order only if it has no remaining items
            remaining_parts = db.query(HandcraftPartItem).filter_by(
                handcraft_order_id=hc.id
            ).count()
            remaining_jewelry = db.query(HandcraftJewelryItem).filter_by(
                handcraft_order_id=hc.id
            ).count()
            if remaining_parts == 0 and remaining_jewelry == 0:
                db.delete(hc)
                db.flush()

    # Delete links referencing todo items in this batch
    todo_item_ids = [
        t.id for t in db.query(OrderTodoItem).filter_by(batch_id=batch_id).all()
    ]
    if todo_item_ids:
        db.query(OrderItemLink).filter(
            OrderItemLink.order_todo_item_id.in_(todo_item_ids)
        ).delete(synchronize_session=False)
    # Delete todo items for this batch
    db.query(OrderTodoItem).filter_by(batch_id=batch_id).delete()
    # Delete batch jewelries
    db.query(OrderTodoBatchJewelry).filter_by(batch_id=batch_id).delete()
    # Delete the batch itself
    db.delete(batch)
    db.flush()


def get_jewelry_for_batch(db: Session, order_id: str) -> list[dict]:
    """Get jewelry list for batch selection modal."""
    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise ValueError(f"订单 {order_id} 不存在")

    items = db.query(OrderItem).filter_by(order_id=order_id).all()
    if not items:
        return []

    # Aggregate by jewelry_id
    agg_qty: dict[str, int] = {}
    for it in items:
        agg_qty[it.jewelry_id] = agg_qty.get(it.jewelry_id, 0) + it.quantity
    jewelry_ids = list(agg_qty.keys())

    # Get jewelry status for disable check
    statuses = get_jewelry_status(db, order_id)
    status_map = {s["jewelry_id"]: s["status"] for s in statuses}

    # Calculate allocated quantities per jewelry_id
    allocated_map: dict[str, int] = {}

    # 1. Count from all batches (including those not yet linked to a supplier)
    batch_jewelries = (
        db.query(OrderTodoBatchJewelry)
        .join(OrderTodoBatch, OrderTodoBatchJewelry.batch_id == OrderTodoBatch.id)
        .filter(OrderTodoBatch.order_id == order_id)
        .all()
    )
    for bj in batch_jewelries:
        allocated_map[bj.jewelry_id] = allocated_map.get(bj.jewelry_id, 0) + bj.quantity

    # 2. Count from direct HC jewelry links (legacy, not via batch flow)
    batch_hc_ids = {
        b.handcraft_order_id
        for b in db.query(OrderTodoBatch).filter_by(order_id=order_id).all()
        if b.handcraft_order_id
    }
    links = (
        db.query(OrderItemLink)
        .filter(
            OrderItemLink.order_id == order_id,
            OrderItemLink.handcraft_jewelry_item_id.isnot(None),
        )
        .all()
    )
    if links:
        hc_item_ids = [l.handcraft_jewelry_item_id for l in links]
        hc_items = db.query(HandcraftJewelryItem).filter(
            HandcraftJewelryItem.id.in_(hc_item_ids)
        ).all()
        for hci in hc_items:
            # Skip items already counted via batch flow
            if hci.handcraft_order_id in batch_hc_ids:
                continue
            allocated_map[hci.jewelry_id] = allocated_map.get(hci.jewelry_id, 0) + hci.qty

    jewelries = db.query(Jewelry).filter(Jewelry.id.in_(jewelry_ids)).all()
    jewelry_info = {j.id: j for j in jewelries}

    result = []
    for jid, total_qty in agg_qty.items():
        j = jewelry_info.get(jid)
        allocated = allocated_map.get(jid, 0)
        remaining = total_qty - allocated
        status = status_map.get(jid, "等待配件备齐")

        selectable = True
        disabled_reason = None
        if status == "完成备货":
            selectable = False
            disabled_reason = status
        elif remaining <= 0:
            selectable = False
            disabled_reason = "已全部分配"

        result.append({
            "jewelry_id": jid,
            "jewelry_name": j.name if j else "",
            "jewelry_image": j.image if j else None,
            "order_quantity": total_qty,
            "allocated_quantity": allocated,
            "remaining_quantity": max(0, remaining),
            "selectable": selectable,
            "disabled_reason": disabled_reason,
        })

    result.sort(key=lambda x: (not x["selectable"], x["jewelry_id"]))
    return result


def get_order_progress(db: Session, order_id: str) -> dict:
    """获取订单的备货进度。

    x = jewelry items with status '完成备货'
    y = distinct jewelry types in the order
    """
    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise ValueError(f"订单 {order_id} 不存在")

    statuses = get_jewelry_status(db, order_id)
    total = len(statuses)
    completed = sum(1 for s in statuses if s["status"] == "完成备货")

    return {"order_id": order_id, "total": total, "completed": completed}


def get_links_for_plating_order(db: Session, plating_order_id: str) -> dict[int, list[dict]]:
    """Batch get order links for all items in a plating order. Returns {item_id: [...]}."""
    plating_items = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == plating_order_id
    ).all()
    if not plating_items:
        return {}

    item_ids = [pi.id for pi in plating_items]
    links = db.query(OrderItemLink).filter(
        OrderItemLink.plating_order_item_id.in_(item_ids)
    ).all()
    if not links:
        return {}

    # Batch load todo items → order_ids
    todo_ids = [l.order_todo_item_id for l in links if l.order_todo_item_id]
    todo_map = {}
    if todo_ids:
        for t in db.query(OrderTodoItem).filter(OrderTodoItem.id.in_(todo_ids)).all():
            todo_map[t.id] = t

    # Collect and batch load orders
    order_ids = set()
    for link in links:
        oid = link.order_id
        if link.order_todo_item_id:
            todo = todo_map.get(link.order_todo_item_id)
            oid = todo.order_id if todo else None
        if oid:
            order_ids.add(oid)
    order_map = {}
    if order_ids:
        for o in db.query(Order).filter(Order.id.in_(list(order_ids))).all():
            order_map[o.id] = o

    # Build result grouped by plating_order_item_id
    result: dict[int, list[dict]] = {}
    for link in links:
        oid = link.order_id
        if link.order_todo_item_id:
            todo = todo_map.get(link.order_todo_item_id)
            oid = todo.order_id if todo else None
        if oid:
            order = order_map.get(oid)
            result.setdefault(link.plating_order_item_id, []).append({
                "order_id": oid,
                "customer_name": order.customer_name if order else None,
                "link_id": link.id,
            })
    return result


def batch_get_order_progress(db: Session, order_ids: list[str]) -> list[dict]:
    """Batch get progress for multiple orders."""
    if not order_ids:
        return []

    orders = db.query(Order).filter(Order.id.in_(order_ids)).all()
    order_map = {o.id: o for o in orders}

    # Batch load order items
    all_items = db.query(OrderItem).filter(OrderItem.order_id.in_(order_ids)).all()
    items_by_order: dict[str, list] = {}
    for it in all_items:
        items_by_order.setdefault(it.order_id, []).append(it)

    # Collect all jewelry_ids across all orders
    all_jewelry_ids = set()
    agg_qty_by_order: dict[str, dict[str, int]] = {}
    for oid in order_ids:
        if oid not in order_map:
            continue
        agg: dict[str, int] = {}
        for it in items_by_order.get(oid, []):
            agg[it.jewelry_id] = agg.get(it.jewelry_id, 0) + it.quantity
        agg_qty_by_order[oid] = agg
        all_jewelry_ids.update(agg.keys())

    if not all_jewelry_ids:
        return [{"order_id": oid, "total": 0, "completed": 0} for oid in order_ids if oid in order_map]

    # Batch load jewelry stocks
    jewelry_stocks = batch_get_stock(db, "jewelry", list(all_jewelry_ids))

    result = []
    for oid in order_ids:
        if oid not in order_map:
            continue
        agg = agg_qty_by_order.get(oid, {})
        total = len(agg)
        completed = sum(1 for jid, qty in agg.items() if jewelry_stocks.get(jid, 0) >= qty)
        result.append({"order_id": oid, "total": total, "completed": completed})

    return result
