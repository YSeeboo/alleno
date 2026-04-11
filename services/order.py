from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from models.order import Order, OrderItem
from services._helpers import _next_id
from services.bom import get_bom

_VALID_STATUSES = {"待生产", "生产中", "已完成", "已取消"}
_Q7 = Decimal("0.0000001")


def _user_date_to_datetime(d: Optional[date_type]) -> Optional[datetime]:
    """Store a user-supplied date as midnight. Do not inject a fake time-of-day —
    the user only told us the date, so we must not fabricate audit data.
    Same-day ordering is handled by an `id DESC` tie-breaker in list queries.
    """
    if d is None:
        return None
    return datetime.combine(d, datetime.min.time())


def _replace_date(existing: Optional[datetime], new_date: date_type) -> datetime:
    """Combine new_date with the time-of-day from existing; fall back to midnight."""
    time_of_day = existing.time() if existing else datetime.min.time()
    return datetime.combine(new_date, time_of_day)


def create_order(db: Session, customer_name: str, items: list, created_at: Optional[date_type] = None) -> Order:
    order_id = _next_id(db, Order, "OR")
    total = Decimal(0)
    order = Order(id=order_id, customer_name=customer_name)
    if created_at is not None:
        order.created_at = _user_date_to_datetime(created_at)
    db.add(order)
    db.flush()
    for item in items:
        unit_price = Decimal(str(item["unit_price"])).quantize(_Q7, rounding=ROUND_HALF_UP)
        subtotal = (Decimal(str(item["quantity"])) * unit_price).quantize(_Q7, rounding=ROUND_HALF_UP)
        total += subtotal
        db.add(OrderItem(
            order_id=order_id,
            jewelry_id=item["jewelry_id"],
            quantity=item["quantity"],
            unit_price=unit_price,
            remarks=item.get("remarks"),
        ))
    order.total_amount = total
    db.flush()
    return order


def get_order(db: Session, order_id: str) -> Optional[Order]:
    return db.query(Order).filter(Order.id == order_id).first()


def list_orders(db: Session, status: Optional[str] = None, customer_name: Optional[str] = None) -> list:
    q = db.query(Order)
    if status is not None:
        q = q.filter(Order.status == status)
    if customer_name is not None:
        q = q.filter(Order.customer_name.contains(customer_name))
    return q.order_by(Order.created_at.desc(), Order.id.desc()).all()


def get_order_items(db: Session, order_id: str) -> list:
    return db.query(OrderItem).filter(OrderItem.order_id == order_id).all()


def _calc_global_part_demand(db: Session, part_ids: list[str]) -> dict[str, float]:
    """Sum BOM-driven part demand across all active orders, minus finished jewelry stock."""
    if not part_ids:
        return {}
    from models.bom import Bom
    from services.inventory import batch_get_stock

    # All order items from active orders
    active_items = (
        db.query(OrderItem)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.status.notin_(["已完成", "已取消"]))
        .all()
    )
    if not active_items:
        return {}

    jewelry_ids = list({oi.jewelry_id for oi in active_items})
    all_bom = db.query(Bom).filter(
        Bom.jewelry_id.in_(jewelry_ids),
        Bom.part_id.in_(part_ids),
    ).all()
    bom_cache: dict[str, list] = {}
    for b in all_bom:
        bom_cache.setdefault(b.jewelry_id, []).append(b)

    # Aggregate order qty per jewelry across all active orders
    agg_qty: dict[str, int] = {}
    for oi in active_items:
        agg_qty[oi.jewelry_id] = agg_qty.get(oi.jewelry_id, 0) + oi.quantity

    # Deduct finished jewelry stock (parts already consumed)
    jewelry_stocks = batch_get_stock(db, "jewelry", jewelry_ids)

    global_map: dict[str, float] = {}
    for jid, total in agg_qty.items():
        unfulfilled = max(0, total - jewelry_stocks.get(jid, 0))
        if unfulfilled > 0:
            for bom in bom_cache.get(jid, []):
                pid = bom.part_id
                global_map[pid] = global_map.get(pid, 0) + float(bom.qty_per_unit) * unfulfilled

    return global_map


def get_parts_summary(db: Session, order_id: str) -> list[dict]:
    """Get aggregated parts summary with total and remaining quantities."""
    from models.bom import Bom
    from models.part import Part

    items = get_order_items(db, order_id)
    if not items:
        return []

    # Batch load BOM for all jewelry_ids once
    jewelry_ids = list({oi.jewelry_id for oi in items})
    all_bom = db.query(Bom).filter(Bom.jewelry_id.in_(jewelry_ids)).all()
    bom_cache: dict[str, list] = {}
    for b in all_bom:
        bom_cache.setdefault(b.jewelry_id, []).append(b)

    # Calculate total BOM requirements
    total_map: dict[str, float] = {}
    for oi in items:
        for bom in bom_cache.get(oi.jewelry_id, []):
            pid = bom.part_id
            total_map[pid] = total_map.get(pid, 0) + float(bom.qty_per_unit) * oi.quantity

    from services.inventory import batch_get_stock
    from services.order_todo import get_jewelry_for_batch

    # Aggregate order quantities by jewelry_id
    agg_qty: dict[str, int] = {}
    for oi in items:
        agg_qty[oi.jewelry_id] = agg_qty.get(oi.jewelry_id, 0) + oi.quantity

    # Get allocated quantities from handcraft orders
    for_batch = get_jewelry_for_batch(db, order_id)
    allocated_map = {fb["jewelry_id"]: fb["allocated_quantity"] for fb in for_batch}

    # Get jewelry stock to check 完成备货
    jewelry_stocks = batch_get_stock(db, "jewelry", jewelry_ids)

    deduct_map: dict[str, float] = {}
    for jid, total in agg_qty.items():
        if jewelry_stocks.get(jid, 0) >= total:
            deduct_qty = total
        else:
            deduct_qty = min(total, allocated_map.get(jid, 0))

        if deduct_qty > 0:
            for bom in bom_cache.get(jid, []):
                pid = bom.part_id
                deduct_map[pid] = deduct_map.get(pid, 0) + float(bom.qty_per_unit) * deduct_qty

    # Enrich with part info
    part_ids = list(total_map.keys())
    parts = db.query(Part).filter(Part.id.in_(part_ids)).all() if part_ids else []
    part_info = {p.id: p for p in parts}

    # Get current part stock and reserved qty (pending handcraft orders hold stock)
    part_stocks = batch_get_stock(db, "part", part_ids) if part_ids else {}

    from models.handcraft_order import HandcraftOrder, HandcraftPartItem
    from models.order import OrderItemLink, OrderTodoItem
    from sqlalchemy import func as sqla_func

    # Find this order's own HandcraftPartItem IDs (batch path only).
    # The batch flow creates precise row-level links: each OrderItemLink points
    # to the exact HandcraftPartItem created for this order, safe even when
    # multiple orders merge into one HandcraftOrder.
    #
    # Legacy direct-link path (order_id + handcraft_jewelry_item_id) is NOT
    # included here because it only tracks jewelry items, not part items.
    # For merged HC orders, we can't distinguish which part rows belong to
    # which order. Omitting legacy means those parts are conservatively counted
    # as "others' reserved" — remaining_qty may be slightly pessimistic, but
    # never dangerously optimistic.
    from sqlalchemy import text as sa_text
    batch_hcpi_rows = db.execute(sa_text(
        "SELECT oil.handcraft_part_item_id "
        "FROM order_item_link oil "
        "JOIN order_todo_item oti ON oil.order_todo_item_id = oti.id "
        "WHERE oti.order_id = :oid AND oil.handcraft_part_item_id IS NOT NULL"
    ), {"oid": order_id}).fetchall()
    own_hcpi_ids = {row[0] for row in batch_hcpi_rows}

    # Sum own part items by handcraft status
    def _sum_own_parts(statuses: list[str]) -> dict[str, float]:
        if not own_hcpi_ids or not part_ids:
            return {}
        rows = (
            db.query(HandcraftPartItem.part_id, sqla_func.sum(HandcraftPartItem.qty))
            .join(HandcraftOrder, HandcraftPartItem.handcraft_order_id == HandcraftOrder.id)
            .filter(
                HandcraftPartItem.id.in_(own_hcpi_ids),
                HandcraftOrder.status.in_(statuses),
                HandcraftPartItem.part_id.in_(part_ids),
            )
            .group_by(HandcraftPartItem.part_id)
            .all()
        )
        return {pid: float(total) for pid, total in rows}

    # Own processing parts: sent out, no longer in stock, working toward this order
    own_processing_map = _sum_own_parts(["processing"])
    # Own pending parts: still in stock AND in global reserved, but earmarked for us
    own_pending_map = _sum_own_parts(["pending"])

    # Total reserved by ALL pending handcraft orders
    reserved_map: dict[str, float] = {}
    if part_ids:
        reserved_rows = (
            db.query(HandcraftPartItem.part_id, sqla_func.sum(HandcraftPartItem.qty))
            .join(HandcraftOrder, HandcraftPartItem.handcraft_order_id == HandcraftOrder.id)
            .filter(
                HandcraftOrder.status == "pending",
                HandcraftPartItem.part_id.in_(part_ids),
            )
            .group_by(HandcraftPartItem.part_id)
            .all()
        )
        for pid, total in reserved_rows:
            reserved_map[pid] = float(total)

    # Calculate global demand: total BOM needs across all active orders
    global_demand_map = _calc_global_part_demand(db, part_ids)

    result = []
    for pid, total_qty in total_map.items():
        p = part_info.get(pid)
        needed = total_qty - deduct_map.get(pid, 0)
        stock = part_stocks.get(pid, 0)
        total_reserved = reserved_map.get(pid, 0)
        own_pending = own_pending_map.get(pid, 0)
        own_processing = own_processing_map.get(pid, 0)
        # Exclude own pending from "reserved by others" since those parts are for us
        reserved_by_others = max(0.0, total_reserved - own_pending)
        # Available stock for this order (own pending parts are still in stock, available to us)
        available = max(0.0, stock - reserved_by_others)
        result.append({
            "part_id": pid,
            "part_name": p.name if p else "",
            "part_image": p.image if p else None,
            "total_qty": total_qty,
            "current_stock": stock,
            "reserved_qty": reserved_by_others,
            "global_demand": global_demand_map.get(pid, 0),
            "remaining_qty": max(0.0, needed - own_processing - available),
        })

    return result


def _recalc_total(db: Session, order: Order) -> None:
    items = get_order_items(db, order.id)
    total = sum(
        (Decimal(str(i.quantity)) * Decimal(str(i.unit_price))).quantize(_Q7, rounding=ROUND_HALF_UP)
        for i in items
    )
    order.total_amount = total
    db.flush()


def add_order_item(db: Session, order_id: str, data: dict) -> OrderItem:
    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"Order not found: {order_id}")
    if order.status != "待生产":
        raise ValueError(f"订单状态为「{order.status}」，只有「待生产」状态可以修改饰品明细")
    unit_price = Decimal(str(data["unit_price"])).quantize(_Q7, rounding=ROUND_HALF_UP)
    item = OrderItem(
        order_id=order_id,
        jewelry_id=data["jewelry_id"],
        quantity=data["quantity"],
        unit_price=unit_price,
        remarks=data.get("remarks"),
    )
    db.add(item)
    db.flush()
    _recalc_total(db, order)
    return item


def delete_order_item(db: Session, order_id: str, item_id: int) -> None:
    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"Order not found: {order_id}")
    if order.status != "待生产":
        raise ValueError(f"订单状态为「{order.status}」，只有「待生产」状态可以修改饰品明细")
    item = db.query(OrderItem).filter(
        OrderItem.id == item_id, OrderItem.order_id == order_id
    ).first()
    if item is None:
        raise ValueError(f"OrderItem not found: {item_id}")
    db.delete(item)
    db.flush()
    order = get_order(db, order_id)
    _recalc_total(db, order)


def update_order_status(db: Session, order_id: str, status: str) -> Order:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {_VALID_STATUSES}")
    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"Order not found: {order_id}")
    if order.status == status:
        return order  # no-op，避免重复生成快照
    if status == "已完成":
        from services.order_cost_snapshot import generate_cost_snapshot
        generate_cost_snapshot(db, order_id)
    order.status = status
    db.flush()
    return order


def update_extra_info(db: Session, order_id: str, data: dict) -> Order:
    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise ValueError(f"订单 {order_id} 不存在")
    for key, value in data.items():
        if key == "created_at" and isinstance(value, date_type) and not isinstance(value, datetime):
            value = _replace_date(order.created_at, value)
        if hasattr(order, key):
            setattr(order, key, value)
    db.flush()
    return order


def _check_order_not_cancelled(db: Session, order_id: str) -> None:
    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"订单 {order_id} 不存在")
    if order.status == "已取消":
        raise ValueError("已取消的订单不允许修改客户货号")


def update_order_item_customer_code(db: Session, order_id: str, item_id: int, customer_code: str | None) -> OrderItem:
    _check_order_not_cancelled(db, order_id)
    item = db.query(OrderItem).filter_by(id=item_id, order_id=order_id).first()
    if not item:
        raise ValueError(f"订单项 {item_id} 不存在")
    item.customer_code = customer_code
    db.flush()
    return item


def batch_fill_customer_code(
    db: Session,
    order_id: str,
    item_ids: list[int],
    prefix: str,
    start_number: int,
    padding: int = 2,
) -> int:
    _check_order_not_cancelled(db, order_id)
    if not item_ids:
        raise ValueError("item_ids 不能为空")
    if not prefix:
        raise ValueError("前缀不能为空")
    if start_number < 0:
        raise ValueError("起始号不能为负数")
    if padding < 1 or padding > 6:
        raise ValueError("位数必须在 1 到 6 之间")
    items = (
        db.query(OrderItem)
        .filter(OrderItem.id.in_(item_ids), OrderItem.order_id == order_id)
        .order_by(OrderItem.id)
        .all()
    )
    if len(items) != len(item_ids):
        raise ValueError("部分订单项不存在或不属于该订单")
    for i, item in enumerate(items):
        code = f"{prefix}{start_number + i:0{padding}d}"
        item.customer_code = code
    db.flush()
    return len(items)


def update_packaging_cost(db: Session, order_id: str, packaging_cost: float) -> Order:
    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"Order not found: {order_id}")
    order.packaging_cost = packaging_cost
    db.flush()
    # 如果订单已完成，仅更新快照中的包装费相关字段（不重算 BOM 明细）
    if order.status == "已完成":
        from services.order_cost_snapshot import update_snapshot_packaging_cost
        update_snapshot_packaging_cost(db, order_id, packaging_cost)
    return order
