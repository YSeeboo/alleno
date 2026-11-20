"""Stage 1: direct-output plans. No inventory, receipt, cost or shipment writes.

Lock order: customer Order -> production parent -> output row. Mutations in the
legacy services use the same locks. Historical links are exclusive, unquantified
claims, never inferred allocations. They must be reviewed at their original UI.
"""
import hashlib
import json
from decimal import Decimal, InvalidOperation

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
from models.jewelry import Jewelry
from models.order import Order, OrderItem, OrderItemLink, OrderTodoItem, OrderTodoBatch, OrderTodoBatchJewelry
from models.part import Part
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.production_allocation import ProductionAllocation as Allocation
from models.production_loss import ProductionLoss


SOURCE = {
    "plating": (PlatingOrder, PlatingOrderItem, "plating_order_id", "plating_order_item_id"),
    "handcraft": (HandcraftOrder, HandcraftJewelryItem, "handcraft_order_id", "handcraft_jewelry_item_id"),
}
EDITABLE_ORDERS = {"待生产", "生产中"}


def lock_order(db, order_id):
    order = db.query(Order).filter_by(id=order_id).populate_existing().with_for_update().first()
    if order is None:
        raise ValueError(f"订单 {order_id} 不存在")
    return order


def lock_source(db, source_type, item_id):
    if source_type not in SOURCE:
        raise ValueError("不支持的生产来源")
    parent_model, model, parent_key, _ = SOURCE[source_type]
    item = db.get(model, item_id)
    if item is None:
        raise ValueError("生产产出明细不存在")
    parent = db.query(parent_model).filter_by(id=getattr(item, parent_key)).populate_existing().with_for_update().first()
    if parent is None:
        raise ValueError("生产单已删除，请刷新")
    item = db.query(model).filter_by(id=item_id).populate_existing().with_for_update().first()
    if item is None:
        raise ValueError("生产产出明细已删除，请刷新")
    return parent, item


def source_query(db, source_type, item_id):
    return db.query(Allocation).filter(getattr(Allocation, SOURCE[source_type][3]) == item_id)


def product_key(item, source_type=None):
    if source_type == "plating":
        return "part", item.receive_part_id or item.part_id
    return ("jewelry", item.jewelry_id) if item.jewelry_id else ("part", item.part_id)


def _product(db, key):
    kind, product_id = key
    return db.get(Jewelry if kind == "jewelry" else Part, product_id)


def _unit_mismatch(product, item):
    expected = (product.unit or "").strip() if product else ""
    return bool(expected and expected != (item.unit or "").strip())


def legacy_source_claim(db, source_type, item_id):
    if db.query(OrderItemLink.id).filter(getattr(OrderItemLink, SOURCE[source_type][3]) == item_id).first():
        return True
    if source_type == "handcraft":
        if db.query(OrderTodoBatchJewelry.id).filter_by(handcraft_jewelry_item_id=item_id).first():
            return True
        item = db.get(HandcraftJewelryItem, item_id)
        return item is not None and item.customer_name is not None
    return False


def legacy_demand_claim(db, line):
    """No row-level history exists; protect the matching product, not guessed shares."""
    if line.jewelry_id:
        if (db.query(OrderTodoBatchJewelry.id).join(OrderTodoBatch, OrderTodoBatch.id == OrderTodoBatchJewelry.batch_id)
                .filter(OrderTodoBatch.order_id == line.order_id, OrderTodoBatchJewelry.jewelry_id == line.jewelry_id).first()):
            return True
        return (db.query(OrderItemLink.id).join(HandcraftJewelryItem, HandcraftJewelryItem.id == OrderItemLink.handcraft_jewelry_item_id)
                .filter(OrderItemLink.order_id == line.order_id, HandcraftJewelryItem.jewelry_id == line.jewelry_id).first()) is not None
    return (db.query(OrderItemLink.id).join(OrderTodoItem, OrderTodoItem.id == OrderItemLink.order_todo_item_id)
            .filter(OrderTodoItem.order_id == line.order_id, OrderTodoItem.part_id == line.part_id).first()) is not None


def guard_legacy_order_write(db, order_id):
    """Conservative compatibility boundary for legacy whole-order/batch writers."""
    lock_order(db, order_id)
    if db.query(Allocation.id).join(OrderItem).filter(OrderItem.order_id == order_id).first():
        raise ValueError("本单已有按明细的生产数量安排，请在「本单生产需求」调整；不能混用旧整行关联/批次分配")


def mark_production_started(order):
    """Call after a confirmed HC/plating link, with the customer order locked.

    Starting is a milestone: unlinking does not rewind it, and closed historical
    orders must never be reopened. This does not receive, reserve or ship stock.
    """
    if order.status == "待生产":
        order.status = "生产中"


def guard_source_delete(db, source_type, item_ids):
    for item_id in sorted(item_ids):
        lock_source(db, source_type, item_id)
    field = getattr(Allocation, SOURCE[source_type][3])
    if db.query(Allocation.id).filter(field.in_(item_ids)).first():
        raise ValueError("产出已有订单数量安排，请先在来源订单的「本单生产需求」取消安排")


def guard_source_update(db, source_type, item_id, *, quantity=None, target=None, unit=None, customer_change=False):
    _, item = lock_source(db, source_type, item_id)
    rows = source_query(db, source_type, item_id).all()
    if not rows:
        return
    if quantity is not None and Decimal(str(quantity)) < sum((r.quantity for r in rows), Decimal(0)):
        raise ValueError("计划数量不能小于已安排的客户需求数量，请先调整来源订单")
    if target is not None and target != product_key(item, source_type):
        raise ValueError("已有客户数量安排，不能更换目标产出，请先取消安排")
    if unit is not None and unit != item.unit:
        raise ValueError("已有客户数量安排，不能更换计量单位")
    if customer_change:
        raise ValueError("此产出按订单数量分配客户，不能同时使用手填客户归属")


def guard_legacy_source_write(db, source_type, item_id):
    lock_source(db, source_type, item_id)
    if source_query(db, source_type, item_id).first():
        raise ValueError("此产出已有订单数量安排，不能再使用旧整行关联")


def guard_order_item_change(db, order_id, item_id=None, quantity=None):
    lock_order(db, order_id)
    query = db.query(Allocation).join(OrderItem).filter(OrderItem.order_id == order_id)
    if item_id is not None:
        query = query.filter(Allocation.order_item_id == item_id)
    rows = query.all()
    if rows and (quantity is None or Decimal(str(quantity)) < sum((r.quantity for r in rows), Decimal(0))):
        raise ValueError("订单存在生产数量安排，请先在「本单生产需求」调整或取消安排")


def _revision(item, parent, rows):
    def quantity_text(qty):
        return format(Decimal(qty).quantize(Decimal("0.0001")), "f")
    value = [quantity_text(item.qty), item.unit, product_key(item, "plating" if isinstance(item, PlatingOrderItem) else "handcraft"),
             parent.status, str(parent.archived_at),
             sorted((r.order_item_id, quantity_text(r.quantity)) for r in rows)]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def _source_view(db, source_type, item, parent):
    rows = source_query(db, source_type, item.id).order_by(Allocation.id).all()
    used = sum((r.quantity for r in rows), Decimal(0))
    legacy = legacy_source_claim(db, source_type, item.id)
    kind, pid = product_key(item, source_type)
    losses = db.query(ProductionLoss).filter_by(order_type=source_type, order_id=parent.id, item_id=item.id,
                                               item_type="plating_item" if source_type == "plating" else "handcraft_jewelry").all()
    loss_qty = sum((Decimal(str(row.loss_qty)) for row in losses), Decimal(0))
    product = _product(db, (kind, pid))
    uses = []
    for row in rows:
        line = db.get(OrderItem, row.order_item_id)
        order = db.get(Order, line.order_id)
        uses.append({"order_id": order.id, "customer_name": order.customer_name, "order_item_id": line.id,
                     "customer_code": line.customer_code, "quantity": row.quantity})
    linked_order_ids = {value for (value,) in db.query(OrderItemLink.order_id).filter(
        getattr(OrderItemLink, SOURCE[source_type][3]) == item.id).all() if value}
    if source_type == "handcraft":
        linked_order_ids.update(value for (value,) in
            db.query(OrderTodoBatch.order_id).join(OrderTodoBatchJewelry, OrderTodoBatchJewelry.batch_id == OrderTodoBatch.id)
            .filter(OrderTodoBatchJewelry.handcraft_jewelry_item_id == item.id).all())
    return {
        "source_type": source_type, "source_item_id": item.id, "production_order_id": parent.id,
        "supplier_name": parent.supplier_name, "status": parent.status, "archived": bool(parent.archived_at),
        "product_type": kind, "product_id": pid, "product_name": product.name if product else pid,
        "image": product.image if product else None,
        "input_part_id": item.part_id if source_type == "plating" else None,
        "unit": item.unit, "planned": item.qty,
        "product_unit": product.unit if product else None, "unit_mismatch": _unit_mismatch(product, item),
        "received": max(Decimal(0), Decimal(item.received_qty or 0) - loss_qty), "loss": loss_qty,
        "risk": bool(loss_qty),
        "allocated": used, "public_unallocated": max(Decimal(0), Decimal(item.qty) - used) if not legacy else None,
        "legacy_claim": legacy, "linked_order_ids": sorted(linked_order_ids),
        "allocations": uses, "revision": _revision(item, parent, rows),
    }


def order_production(db: Session, order_id: str):
    order = db.get(Order, order_id)
    if order is None:
        raise ValueError("订单不存在")
    lines = db.query(OrderItem).filter_by(order_id=order_id).order_by(OrderItem.id).all()
    keys = {product_key(line) for line in lines}
    own = db.query(Allocation).join(OrderItem).filter(OrderItem.order_id == order_id).all()
    own_ids = {("plating", r.plating_order_item_id) if r.plating_order_item_id else ("handcraft", r.handcraft_jewelry_item_id) for r in own}
    sources = []
    for source_type, (parent_model, model, parent_key, _) in SOURCE.items():
        # Match exact output identity, never the plating input. Retain associated
        # completed/archived sources for traceability even though they are read-only.
        if source_type == "plating":
            ids = [pid for kind, pid in keys if kind == "part"]
            match = or_(model.receive_part_id.in_(ids), (model.receive_part_id.is_(None) & model.part_id.in_(ids)))
        else:
            match = or_(model.jewelry_id.in_([pid for kind, pid in keys if kind == "jewelry"]),
                        model.part_id.in_([pid for kind, pid in keys if kind == "part"]))
        associated = [item_id for kind, item_id in own_ids if kind == source_type]
        # Exact old links remain visible as confirmed associations, including
        # completed history. A matching customer name alone is never a link.
        associated.extend(item_id for (item_id,) in db.query(getattr(OrderItemLink, SOURCE[source_type][3]))
                          .filter(OrderItemLink.order_id == order_id,
                                  getattr(OrderItemLink, SOURCE[source_type][3]).isnot(None)).all())
        if source_type == "handcraft":
            associated.extend(item_id for (item_id,) in
                db.query(OrderTodoBatchJewelry.handcraft_jewelry_item_id)
                .join(OrderTodoBatch, OrderTodoBatch.id == OrderTodoBatchJewelry.batch_id)
                .filter(OrderTodoBatch.order_id == order_id,
                        OrderTodoBatchJewelry.handcraft_jewelry_item_id.isnot(None)).all())
        query = (db.query(model, parent_model).join(parent_model, parent_model.id == getattr(model, parent_key))
                 .filter(or_(match & parent_model.archived_at.is_(None) & parent_model.status.in_(["pending", "processing"]),
                             model.id.in_(associated)))
                 .order_by(parent_model.id, model.id))
        for item, parent in query.all():
            sources.append(_source_view(db, source_type, item, parent))
    result_lines = []
    for line in lines:
        kind, pid = product_key(line)
        product = _product(db, (kind, pid))
        result_lines.append({"id": line.id, "product_type": kind, "product_id": pid,
                             "product_name": product.name if product else pid,
                             "image": product.image if product else None,
                             "quantity": line.quantity, "customer_code": line.customer_code,
                             "unit": product.unit if product else None,
                             "allocated": sum((row.quantity for row in own if row.order_item_id == line.id), Decimal(0)),
                             "legacy_claim": legacy_demand_claim(db, line)})
    return {"order_id": order.id, "customer_name": order.customer_name, "editable": order.status in EDITABLE_ORDERS,
            "lines": result_lines, "sources": sources}


def production_uses(db: Session, source_type: str, order_id: str):
    if source_type not in SOURCE:
        raise ValueError("不支持的生产来源")
    parent_model, model, parent_key, _ = SOURCE[source_type]
    parent = db.get(parent_model, order_id)
    if parent is None:
        raise ValueError("生产单不存在")
    return [_source_view(db, source_type, item, parent) for item in
            db.query(model).filter(getattr(model, parent_key) == order_id).order_by(model.id).all()]


def replace_order_source(db: Session, order_id: str, source_type: str, item_id: int, revision: str, allocations: list[dict]):
    order = lock_order(db, order_id)
    if order.status not in EDITABLE_ORDERS:
        raise ValueError("仅待生产或生产中的订单可调整生产安排")
    parent, item = lock_source(db, source_type, item_id)
    if parent.archived_at or parent.status not in {"pending", "processing"}:
        raise ValueError("已完成或归档的生产单仅供追溯，不可调整安排")
    rows = source_query(db, source_type, item_id).all()
    if revision != _revision(item, parent, rows):
        raise ValueError("生产安排已变化，请刷新后重新核对保存")
    if legacy_source_claim(db, source_type, item_id):
        raise ValueError("此产出存在旧关联、批次或手填客户归属，请先核对并解除旧归属，不能推算历史份额")
    unit_mismatch = _unit_mismatch(_product(db, product_key(item, source_type)), item)
    own_lines = {line.id: line for line in db.query(OrderItem).filter_by(order_id=order_id).all()}
    values = {}
    for data in allocations:
        line_id = data["order_item_id"]
        if line_id in values:
            raise ValueError("同一订单明细不能重复填写")
        line = own_lines.get(line_id)
        if line is None:
            raise ValueError("只能调整当前订单的明细")
        if product_key(line) != product_key(item, source_type):
            raise ValueError("生产目标产出与订单明细不匹配")
        try:
            qty = Decimal(str(data["quantity"]))
        except (InvalidOperation, ValueError):
            raise ValueError("安排数量无效")
        if not qty.is_finite() or qty < 0 or qty >= Decimal("10000000000") or qty != qty.quantize(Decimal("0.0001")):
            raise ValueError("安排数量必须为最多四位小数的非负数")
        if qty != qty.to_integral_value():
            raise ValueError("订单商品数量为整数，生产安排也必须为整数")
        if qty and unit_mismatch:
            raise ValueError("生产产出单位与商品基本单位不一致，请先核对单位；不自动换算")
        if qty and legacy_demand_claim(db, line):
            raise ValueError("该商品存在无法拆到明细的旧生产安排，请先核对旧关联/批次")
        other = sum((r.quantity for r in db.query(Allocation).filter_by(order_item_id=line_id).all()
                     if getattr(r, SOURCE[source_type][3]) != item_id), Decimal(0))
        if other + qty > line.quantity:
            raise ValueError("安排数量超过此订单明细需求（含其他生产来源）")
        values[line_id] = qty
    other_orders = sum((r.quantity for r in rows if r.order_item_id not in own_lines), Decimal(0))
    if other_orders + sum(values.values(), Decimal(0)) > Decimal(item.qty):
        raise ValueError("生产计划容量不足，不能占用其他订单的安排")
    # All checks before mutation. Replace only THIS order's share; omit/zero clears
    # its rows, never touches the other customers, actual receipts or inventory.
    for row in rows:
        if row.order_item_id in own_lines:
            db.delete(row)
    db.flush()
    for line_id, qty in values.items():
        if qty:
            db.add(Allocation(order_item_id=line_id, quantity=qty, **{SOURCE[source_type][3]: item_id}))
    if any(values.values()):
        mark_production_started(order)
    db.flush()
    return _source_view(db, source_type, item, parent)
