from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from models.order import Order, OrderItem
from services._helpers import _next_id
from services.bom import get_bom

_VALID_STATUSES = {"待生产", "生产中", "已完成", "已取消"}
_Q7 = Decimal("0.0000001")


def create_order(db: Session, customer_name: str, items: list) -> Order:
    order_id = _next_id(db, Order, "OR")
    total = Decimal(0)
    order = Order(id=order_id, customer_name=customer_name)
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
    return q.order_by(Order.created_at.desc()).all()


def get_order_items(db: Session, order_id: str) -> list:
    return db.query(OrderItem).filter(OrderItem.order_id == order_id).all()


def get_parts_summary(db: Session, order_id: str) -> list[dict]:
    """Get aggregated parts summary with total and remaining quantities."""
    from models.part import Part

    items = get_order_items(db, order_id)
    if not items:
        return []

    # Calculate total BOM requirements
    total_map: dict[str, float] = {}
    for oi in items:
        bom_rows = get_bom(db, oi.jewelry_id)
        for bom in bom_rows:
            pid = bom.part_id
            total_map[pid] = total_map.get(pid, 0) + float(bom.qty_per_unit) * oi.quantity

    # Calculate deduction based on concrete handled quantities, not status.
    # "Handled" = allocated to handcraft OR covered by jewelry stock.
    # This avoids the problem where a binary status (e.g. 等待发往手工)
    # deducts the full order qty even when nothing has been allocated.
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
    jewelry_ids = list(agg_qty.keys())
    jewelry_stocks = batch_get_stock(db, "jewelry", jewelry_ids)

    deduct_map: dict[str, float] = {}
    for jid, total in agg_qty.items():
        # If jewelry stock covers the order → fully handled
        if jewelry_stocks.get(jid, 0) >= total:
            deduct_qty = total
        else:
            # Otherwise, only the allocated portion is handled
            deduct_qty = min(total, allocated_map.get(jid, 0))

        if deduct_qty > 0:
            bom_rows = get_bom(db, jid)
            for bom in bom_rows:
                pid = bom.part_id
                deduct_map[pid] = deduct_map.get(pid, 0) + float(bom.qty_per_unit) * deduct_qty

    # Enrich with part info
    part_ids = list(total_map.keys())
    parts = db.query(Part).filter(Part.id.in_(part_ids)).all() if part_ids else []
    part_info = {p.id: p for p in parts}

    result = []
    for pid, total_qty in total_map.items():
        p = part_info.get(pid)
        remaining = total_qty - deduct_map.get(pid, 0)
        result.append({
            "part_id": pid,
            "part_name": p.name if p else "",
            "part_image": p.image if p else None,
            "total_qty": total_qty,
            "remaining_qty": max(0.0, remaining),
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
        if hasattr(order, key):
            setattr(order, key, value)
    db.flush()
    return order


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
