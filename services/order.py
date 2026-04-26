import math
from datetime import datetime, date as date_type
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from sqlalchemy import func as sa_func
from models.order import Order, OrderItem, OrderTodoBatch, OrderTodoBatchJewelry, OrderItemLink
from models.handcraft_order import HandcraftJewelryItem
from models.part import Part
from services._helpers import _next_id
from services.bom import get_bom

_VALID_STATUSES = {"待生产", "生产中", "已完成", "已取消"}
_Q7 = Decimal("0.0000001")


def _writeback_part_wholesale_price(db: Session, part_id: str, new_price: Decimal) -> None:
    """Overwrite part.wholesale_price with the latest sale price.
    Raises ValueError if the part does not exist."""
    part = db.query(Part).filter(Part.id == part_id).first()
    if part is None:
        raise ValueError(f"配件 {part_id} 不存在")
    if part.wholesale_price != new_price:
        part.wholesale_price = new_price
        db.flush()


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
            jewelry_id=item.get("jewelry_id"),
            part_id=item.get("part_id"),
            quantity=item["quantity"],
            unit_price=unit_price,
            remarks=item.get("remarks"),
        ))
        if item.get("part_id"):
            _writeback_part_wholesale_price(db, item["part_id"], unit_price)
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

    jewelry_ids = list({oi.jewelry_id for oi in active_items if oi.jewelry_id is not None})
    all_bom = db.query(Bom).filter(
        Bom.jewelry_id.in_(jewelry_ids),
        Bom.part_id.in_(part_ids),
    ).all() if jewelry_ids else []
    bom_cache: dict[str, list] = {}
    for b in all_bom:
        bom_cache.setdefault(b.jewelry_id, []).append(b)

    # Aggregate order qty per jewelry across all active orders
    agg_qty: dict[str, int] = {}
    for oi in active_items:
        if oi.jewelry_id is None:
            continue
        agg_qty[oi.jewelry_id] = agg_qty.get(oi.jewelry_id, 0) + oi.quantity

    # Deduct finished jewelry stock (parts already consumed)
    jewelry_stocks = batch_get_stock(db, "jewelry", jewelry_ids) if jewelry_ids else {}

    global_map: dict[str, float] = {}
    for jid, total in agg_qty.items():
        unfulfilled = max(0, total - jewelry_stocks.get(jid, 0))
        if unfulfilled > 0:
            for bom in bom_cache.get(jid, []):
                pid = bom.part_id
                global_map[pid] = global_map.get(pid, 0) + float(bom.qty_per_unit) * unfulfilled

    # Add direct part purchases from active orders
    direct_rows = (
        db.query(OrderItem.part_id, sa_func.sum(OrderItem.quantity))
        .join(Order, OrderItem.order_id == Order.id)
        .filter(
            Order.status.notin_(["已完成", "已取消"]),
            OrderItem.part_id.in_(part_ids),
        )
        .group_by(OrderItem.part_id)
        .all()
    )
    for pid, qty in direct_rows:
        global_map[pid] = global_map.get(pid, 0) + float(qty)

    return global_map


def get_parts_summary(db: Session, order_id: str) -> list[dict]:
    """Get aggregated parts summary with total and remaining quantities."""
    from models.bom import Bom
    from models.part import Part

    items = get_order_items(db, order_id)
    if not items:
        return []

    jewelry_items = [oi for oi in items if oi.jewelry_id is not None]
    part_items = [oi for oi in items if oi.part_id is not None]

    # Batch load BOM for all jewelry_ids once
    jewelry_ids = list({oi.jewelry_id for oi in jewelry_items})
    all_bom = db.query(Bom).filter(Bom.jewelry_id.in_(jewelry_ids)).all() if jewelry_ids else []
    bom_cache: dict[str, list] = {}
    for b in all_bom:
        bom_cache.setdefault(b.jewelry_id, []).append(b)

    # Calculate total BOM requirements
    total_map: dict[str, float] = {}
    for oi in jewelry_items:
        for bom in bom_cache.get(oi.jewelry_id, []):
            pid = bom.part_id
            total_map[pid] = total_map.get(pid, 0) + float(bom.qty_per_unit) * oi.quantity

    from services.inventory import batch_get_stock

    # Aggregate order quantities by jewelry_id
    agg_qty: dict[str, int] = {}
    for oi in jewelry_items:
        agg_qty[oi.jewelry_id] = agg_qty.get(oi.jewelry_id, 0) + oi.quantity

    # Get jewelry stock — finished jewelry already in inventory means parts are consumed
    jewelry_stocks = batch_get_stock(db, "jewelry", jewelry_ids) if jewelry_ids else {}

    # Only deduct for finished jewelry in stock (parts already consumed).
    # Do NOT deduct for handcraft allocation — those parts are either:
    #   - already sent (stock reduced), or
    #   - not yet sent (still in part stock, will be subtracted below)
    deduct_map: dict[str, float] = {}
    for jid, total in agg_qty.items():
        deduct_qty = min(total, jewelry_stocks.get(jid, 0))
        if deduct_qty > 0:
            for bom in bom_cache.get(jid, []):
                pid = bom.part_id
                deduct_map[pid] = deduct_map.get(pid, 0) + float(bom.qty_per_unit) * deduct_qty

    # Build source jewelries breakdown: part_id → [{jewelry_id, qty_per_unit, order_qty, subtotal}]
    from models.jewelry import Jewelry
    source_map: dict[str, list[dict]] = {}
    for jid, order_qty in agg_qty.items():
        for bom in bom_cache.get(jid, []):
            pid = bom.part_id
            source_map.setdefault(pid, []).append({
                "jewelry_id": jid,
                "qty_per_unit": float(bom.qty_per_unit),
                "order_qty": order_qty,
                "subtotal": float(bom.qty_per_unit) * order_qty,
            })
    # Enrich with jewelry names
    jewelry_db = db.query(Jewelry).filter(Jewelry.id.in_(jewelry_ids)).all() if jewelry_ids else []
    jewelry_info = {j.id: j for j in jewelry_db}
    for entries in source_map.values():
        for entry in entries:
            j = jewelry_info.get(entry["jewelry_id"])
            entry["jewelry_name"] = j.name if j else ""

    # Add direct part contributions (customer-purchased parts)
    direct_part_qty: dict[str, int] = {}
    for pi in part_items:
        direct_part_qty[pi.part_id] = direct_part_qty.get(pi.part_id, 0) + pi.quantity
    for pid, dq in direct_part_qty.items():
        total_map[pid] = total_map.get(pid, 0) + dq
        source_map.setdefault(pid, []).append({
            "source_type": "direct",
            "jewelry_id": None,
            "jewelry_name": "",
            "qty_per_unit": None,
            "order_qty": dq,
            "subtotal": float(dq),
        })
    # Tag existing BOM-derived sources with source_type="jewelry"
    for entries in source_map.values():
        for entry in entries:
            entry.setdefault("source_type", "jewelry")

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
        global_demand_raw = global_demand_map.get(pid, 0)
        # Global-sufficiency flag is computed on RAW floats before ceiling. This
        # is the single source of truth for the "orange" bucket in the UI sort /
        # filter / row color. If callers reconstruct it from the ceiled
        # current_stock / reserved_qty / global_demand, rounding error can flip
        # the classification (e.g. stock=100.1, reserved=50.6, demand=49.8:
        # raw says orange, ceiled independently says green).
        globally_sufficient = global_demand_raw <= available
        # Round UP all display quantities. Meter-based parts (chains) accumulate
        # float noise like 982.8000000000002 from repeated BOM multiplication;
        # piece-based parts are already whole numbers so ceil is a no-op.
        # Rounding up (not round-to-nearest) is the safer direction for ordering:
        # if a BOM needs 982.1 meters, the user should purchase 983 to be safe.
        raw_remaining = max(0.0, needed - own_processing - available)
        result.append({
            "part_id": pid,
            "part_name": p.name if p else "",
            "part_image": p.image if p else None,
            "part_is_composite": p.is_composite if p else False,
            "total_qty": math.ceil(total_qty),
            "raw_total_qty": total_qty,
            "current_stock": math.ceil(stock),
            "reserved_qty": math.ceil(reserved_by_others),
            "global_demand": math.ceil(global_demand_raw),
            "remaining_qty": math.ceil(raw_remaining),
            "_raw_remaining_qty": raw_remaining,
            "globally_sufficient": globally_sufficient,
            "source_jewelries": source_map.get(pid, []),
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
    if (data.get("jewelry_id") is None) == (data.get("part_id") is None):
        raise ValueError("jewelry_id 和 part_id 必须且只能填一个")
    unit_price = Decimal(str(data["unit_price"])).quantize(_Q7, rounding=ROUND_HALF_UP)
    item = OrderItem(
        order_id=order_id,
        jewelry_id=data.get("jewelry_id"),
        part_id=data.get("part_id"),
        quantity=data["quantity"],
        unit_price=unit_price,
        remarks=data.get("remarks"),
    )
    db.add(item)
    db.flush()
    if data.get("part_id"):
        _writeback_part_wholesale_price(db, data["part_id"], unit_price)
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

    items = get_order_items(db, order_id)
    part_qty_map: dict[str, int] = {}
    for it in items:
        if it.part_id is not None:
            part_qty_map[it.part_id] = part_qty_map.get(it.part_id, 0) + it.quantity

    # Transition INTO "已完成" — pre-check then deduct part stock
    if status == "已完成" and order.status != "已完成":
        if part_qty_map:
            from services.inventory import batch_get_stock, deduct_stock
            stocks = batch_get_stock(db, "part", list(part_qty_map.keys()))
            insufficient = [
                f"{pid} 需要 {qty}，仅有 {stocks.get(pid, 0):.2f}"
                for pid, qty in part_qty_map.items()
                if stocks.get(pid, 0) < qty
            ]
            if insufficient:
                raise ValueError("配件库存不足：" + "；".join(insufficient))
            for pid, qty in part_qty_map.items():
                deduct_stock(db, "part", pid, qty, "订单出货")
        from services.order_cost_snapshot import generate_cost_snapshot
        generate_cost_snapshot(db, order_id)

    # Transition OUT of "已完成" — restore part stock
    elif order.status == "已完成" and status != "已完成":
        if part_qty_map:
            from services.inventory import add_stock
            for pid, qty in part_qty_map.items():
                add_stock(db, "part", pid, qty, "订单出货撤回")

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


def update_order_item(db: Session, order_id: str, item_id: int, fields: dict) -> OrderItem:
    """Update order item fields (quantity, unit_price, customer_code)."""
    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"订单 {order_id} 不存在")
    if order.status == "已取消":
        raise ValueError("已取消的订单不允许修改")
    item = db.query(OrderItem).filter_by(id=item_id, order_id=order_id).first()
    if not item:
        raise ValueError(f"订单项 {item_id} 不存在")
    if "customer_code" in fields and item.part_id is not None:
        raise ValueError("配件项不允许设置客户货号")
    price_fields = {"quantity", "unit_price"}
    if price_fields & fields.keys() and order.status not in ("待生产", "生产中"):
        raise ValueError("仅待生产或生产中状态可修改数量和单价")
    if "quantity" in fields:
        new_qty = fields["quantity"]
        if item.jewelry_id is not None:
            jewelry_id = item.jewelry_id
            # Sum allocated from batch flow
            batch_allocated = (
                db.query(sa_func.coalesce(sa_func.sum(OrderTodoBatchJewelry.quantity), 0))
                .join(OrderTodoBatch, OrderTodoBatchJewelry.batch_id == OrderTodoBatch.id)
                .filter(OrderTodoBatch.order_id == order_id, OrderTodoBatchJewelry.jewelry_id == jewelry_id)
                .scalar()
            )
            # Sum allocated from legacy direct HC jewelry links (not already in batch)
            legacy_allocated = 0
            batch_hc_ids = {
                b.handcraft_order_id
                for b in db.query(OrderTodoBatch).filter_by(order_id=order_id).all()
                if b.handcraft_order_id
            }
            links = (
                db.query(OrderItemLink)
                .filter(OrderItemLink.order_id == order_id, OrderItemLink.handcraft_jewelry_item_id.isnot(None))
                .all()
            )
            if links:
                hc_item_ids = [l.handcraft_jewelry_item_id for l in links]
                hc_items = db.query(HandcraftJewelryItem).filter(
                    HandcraftJewelryItem.id.in_(hc_item_ids),
                    HandcraftJewelryItem.jewelry_id == jewelry_id,
                ).all()
                for hci in hc_items:
                    if hci.handcraft_order_id not in batch_hc_ids:
                        legacy_allocated += hci.qty
            total_allocated = batch_allocated + legacy_allocated
            # Compare against whole-order total for this jewelry after the edit
            other_qty = (
                db.query(sa_func.coalesce(sa_func.sum(OrderItem.quantity), 0))
                .filter(OrderItem.order_id == order_id, OrderItem.jewelry_id == jewelry_id, OrderItem.id != item_id)
                .scalar()
            )
            new_total = other_qty + new_qty
            if new_total < total_allocated:
                raise ValueError(f"该饰品整单已分配 {total_allocated}，修改后总数量 {new_total} 不足")
    for key, value in fields.items():
        if hasattr(item, key):
            setattr(item, key, value)
    db.flush()
    if "unit_price" in fields and item.part_id is not None:
        new_price = Decimal(str(fields["unit_price"])).quantize(_Q7, rounding=ROUND_HALF_UP)
        _writeback_part_wholesale_price(db, item.part_id, new_price)
    if price_fields & fields.keys():
        _recalc_total(db, order)
    return item


def update_order_item_customer_code(db: Session, order_id: str, item_id: int, customer_code: str | None) -> OrderItem:
    return update_order_item(db, order_id, item_id, {"customer_code": customer_code})


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
    if any(it.part_id is not None for it in items):
        raise ValueError("配件项不允许设置客户货号")
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


def enrich_order_items(db: Session, items: list) -> list:
    """Attach part_name / part_image / part_unit for part-typed items."""
    part_ids = [i.part_id for i in items if i.part_id is not None]
    if not part_ids:
        return items
    parts = {p.id: p for p in db.query(Part).filter(Part.id.in_(part_ids)).all()}
    enriched = []
    for it in items:
        if it.part_id is None:
            enriched.append(it)
            continue
        p = parts.get(it.part_id)
        d = {
            "id": it.id, "order_id": it.order_id,
            "jewelry_id": it.jewelry_id, "part_id": it.part_id,
            "quantity": it.quantity, "unit_price": float(it.unit_price),
            "remarks": it.remarks, "customer_code": it.customer_code,
            "part_name": p.name if p else None,
            "part_image": p.image if p else None,
            "part_unit": p.unit if p else None,
        }
        enriched.append(d)
    return enriched
