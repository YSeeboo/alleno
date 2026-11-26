"""Product/material output plans. No inventory, receipt, cost or shipment writes.

Lock order: customer Order -> BOM advisory locks -> production parent -> output row. Mutations in the
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
from models.material_production import OrderMaterialDemand, MaterialProductionAllocation
from services.material_production import (
    material_demands, material_source_query, order_material_allocations, guard_material_order_change,
)


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


def source_rows(db, source_type, item_id):
    return source_query(db, source_type, item_id).all() + material_source_query(db, source_type, item_id).all()


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


def legacy_demand_batches(db, line):
    """Keep estimate-only batches visible without claiming any production capacity.

    Either source reference is enough to retain the conservative protection,
    including dangling historical references; never guess a replacement source.
    """
    if not line.jewelry_id:
        return []
    records = (db.query(OrderTodoBatchJewelry, OrderTodoBatch)
               .join(OrderTodoBatch, OrderTodoBatch.id == OrderTodoBatchJewelry.batch_id)
               .filter(OrderTodoBatch.order_id == line.order_id,
                       OrderTodoBatchJewelry.jewelry_id == line.jewelry_id)
               .order_by(OrderTodoBatch.id, OrderTodoBatchJewelry.id).all())
    return [{"batch_id": batch.id, "quantity": item.quantity,
             "production_order_id": batch.handcraft_order_id,
             "source_item_id": item.handcraft_jewelry_item_id,
             "blocks_allocation": batch.handcraft_order_id is not None or item.handcraft_jewelry_item_id is not None}
            for item, batch in records]


def legacy_todo_output_claim(db, order_id, part_id):
    """Only old production OUTPUT links claim demand, not inputs or purchases."""
    return db.query(OrderItemLink.id).join(OrderTodoItem).filter(
        OrderTodoItem.order_id == order_id, OrderTodoItem.part_id == part_id,
        or_(OrderItemLink.plating_order_item_id.isnot(None),
            OrderItemLink.handcraft_jewelry_item_id.isnot(None))).first() is not None


def legacy_demand_claim(db, line):
    """Protect actual old output claims; estimate-only batches are not allocations."""
    if line.jewelry_id:
        if any(batch["blocks_allocation"] for batch in legacy_demand_batches(db, line)):
            return True
        return (db.query(OrderItemLink.id).join(HandcraftJewelryItem, HandcraftJewelryItem.id == OrderItemLink.handcraft_jewelry_item_id)
                .filter(OrderItemLink.order_id == line.order_id, HandcraftJewelryItem.jewelry_id == line.jewelry_id).first()) is not None
    return (
        legacy_todo_output_claim(db, line.order_id, line.part_id)
        or db.query(OrderItemLink.id).join(HandcraftJewelryItem, HandcraftJewelryItem.id == OrderItemLink.handcraft_jewelry_item_id)
        .filter(OrderItemLink.order_id == line.order_id, HandcraftJewelryItem.part_id == line.part_id).first() is not None
    )


def guard_legacy_order_write(db, order_id):
    """Conservative compatibility boundary for legacy whole-order/batch writers."""
    lock_order(db, order_id)
    if (db.query(Allocation.id).join(OrderItem).filter(OrderItem.order_id == order_id).first()
            or order_material_allocations(db, order_id)):
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
    if db.query(MaterialProductionAllocation.id).filter(
            getattr(MaterialProductionAllocation, SOURCE[source_type][3]).in_(item_ids)).first():
        raise ValueError("产出已有配件备料安排，请先在来源订单取消安排")


def guard_source_update(db, source_type, item_id, *, quantity=None, target=None, unit=None, customer_change=False):
    _, item = lock_source(db, source_type, item_id)
    rows = source_rows(db, source_type, item_id)
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
    if source_rows(db, source_type, item_id):
        raise ValueError("此产出已有订单数量安排，不能再使用旧整行关联")


def guard_order_item_change(db, order_id, item_id=None, quantity=None):
    lock_order(db, order_id)
    guard_material_order_change(db, order_id, item_id, quantity)
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
             sorted((r.order_item_id, r.demand.part_id if isinstance(r, MaterialProductionAllocation) else "",
                     quantity_text(r.quantity)) for r in rows)]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def _source_view(db, source_type, item, parent):
    rows = source_rows(db, source_type, item.id)
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
                     "customer_code": line.customer_code, "quantity": row.quantity,
                     "material_part_id": row.demand.part_id if isinstance(row, MaterialProductionAllocation) else None,
                     "purpose": "material" if isinstance(row, MaterialProductionAllocation) else "product"})
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
    materials = material_demands(db, order_id)
    keys.update(("part", row["product_id"]) for row in materials)
    own = db.query(Allocation).join(OrderItem).filter(OrderItem.order_id == order_id).all()
    all_own = own + order_material_allocations(db, order_id)
    own_ids = {("plating", r.plating_order_item_id) if r.plating_order_item_id else ("handcraft", r.handcraft_jewelry_item_id) for r in all_own}
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
                             "legacy_claim": legacy_demand_claim(db, line),
                             "legacy_batches": legacy_demand_batches(db, line)})
    return {"order_id": order.id, "customer_name": order.customer_name, "editable": order.status in EDITABLE_ORDERS,
            "lines": result_lines, "materials": materials, "sources": sources}


def production_uses(db: Session, source_type: str, order_id: str):
    if source_type not in SOURCE:
        raise ValueError("不支持的生产来源")
    parent_model, model, parent_key, _ = SOURCE[source_type]
    parent = db.get(parent_model, order_id)
    if parent is None:
        raise ValueError("生产单不存在")
    return [_source_view(db, source_type, item, parent) for item in
            db.query(model).filter(getattr(model, parent_key) == order_id).order_by(model.id).all()]


def quantity_order_links(db: Session, source_type: str, item_id: int):
    """Reverse order badges for confirmed shares, grouped across both purposes.

    These are not legacy OrderItemLink IDs and must never use legacy unlink APIs.
    """
    orders = {}
    for allocation in source_rows(db, source_type, item_id):
        line = db.get(OrderItem, allocation.order_item_id)
        order = db.get(Order, line.order_id)
        orders[order.id] = {"order_id": order.id, "customer_name": order.customer_name,
                            "link_id": None, "quantity_managed": True}
    return [orders[order_id] for order_id in sorted(orders)]


def replace_order_source(db: Session, order_id: str, source_type: str, item_id: int, revision: str, allocations: list[dict]):
    order = lock_order(db, order_id)
    if order.status not in EDITABLE_ORDERS:
        raise ValueError("仅待生产或生产中的订单可调整生产安排")
    if any(row.get("material_part_id") for row in allocations):
        from services.bom import lock_bom
        for (jewelry_id,) in db.query(OrderItem.jewelry_id).filter_by(order_id=order_id).filter(
                OrderItem.jewelry_id.isnot(None)).distinct().order_by(OrderItem.jewelry_id):
            lock_bom(db, jewelry_id)
    parent, item = lock_source(db, source_type, item_id)
    if parent.archived_at or parent.status not in {"pending", "processing"}:
        raise ValueError("已完成或归档的生产单仅供追溯，不可调整安排")
    rows = source_rows(db, source_type, item_id)
    if revision != _revision(item, parent, rows):
        raise ValueError("生产安排已变化，请刷新后重新核对保存")
    if legacy_source_claim(db, source_type, item_id):
        raise ValueError("此产出存在旧关联、批次或手填客户归属，请先核对并解除旧归属，不能推算历史份额")
    unit_mismatch = _unit_mismatch(_product(db, product_key(item, source_type)), item)
    own_lines = {line.id: line for line in db.query(OrderItem).filter_by(order_id=order_id).populate_existing().all()}
    demands = {(row["order_item_id"], row["material_part_id"]): row for row in material_demands(db, order_id)}
    values = {}
    for data in allocations:
        line_id = data["order_item_id"]
        part_id = data.get("material_part_id")
        key = (line_id, part_id)
        if key in values:
            raise ValueError("同一订单明细不能重复填写")
        line = own_lines.get(line_id)
        if line is None:
            raise ValueError("只能调整当前订单的明细")
        demand = demands.get(key) if part_id else None
        if part_id and (demand is None or product_key(item, source_type) != ("part", part_id)):
            raise ValueError("生产目标产出与订单 BOM 配件需求不匹配")
        if not part_id and product_key(line) != product_key(item, source_type):
            raise ValueError("生产目标产出与订单明细不匹配")
        try:
            qty = Decimal(str(data["quantity"]))
        except (InvalidOperation, ValueError):
            raise ValueError("安排数量无效")
        if not qty.is_finite() or qty < 0 or qty >= Decimal("10000000000") or qty != qty.quantize(Decimal("0.0001")):
            raise ValueError("安排数量必须为最多四位小数的非负数")
        if (not part_id or source_type == "handcraft") and qty != qty.to_integral_value():
            raise ValueError("订单商品数量为整数，生产安排也必须为整数")
        if qty and unit_mismatch:
            raise ValueError("生产产出单位与商品基本单位不一致，请先核对单位；不自动换算")
        if qty and ((demand["legacy_claim"] if part_id else legacy_demand_claim(db, line))):
            raise ValueError("该商品存在无法拆到明细的旧生产安排，请先核对旧关联/批次")
        if part_id:
            if qty and data.get("demand_revision") != demand["demand_revision"]:
                raise ValueError("BOM 或订单需求已变化，请刷新并重新核对配件数量")
            snapshot = db.query(OrderMaterialDemand).filter_by(order_item_id=line_id, part_id=part_id).first()
            demand_rows = db.query(MaterialProductionAllocation).filter_by(demand_id=snapshot.id).all() if snapshot else []
        else:
            demand_rows = db.query(Allocation).filter_by(order_item_id=line_id).all()
        other = sum((r.quantity for r in demand_rows if getattr(r, SOURCE[source_type][3]) != item_id), Decimal(0))
        if qty and other + qty > (demand["quantity"] if part_id else line.quantity):
            raise ValueError("安排数量超过此订单明细需求（含其他生产来源）")
        values[key] = qty
    other_orders = sum((r.quantity for r in rows if r.order_item_id not in own_lines), Decimal(0))
    if other_orders + sum(values.values(), Decimal(0)) > Decimal(item.qty):
        raise ValueError("生产计划容量不足，不能占用其他订单的安排")
    # All checks before mutation. Replace only THIS order's share; omit/zero clears
    # its rows, never touches the other customers, actual receipts or inventory.
    for row in rows:
        if row.order_item_id in own_lines:
            db.delete(row)
    db.flush()
    for (line_id, part_id), qty in values.items():
        if qty:
            if part_id:
                demand = demands[(line_id, part_id)]
                snapshot = db.query(OrderMaterialDemand).filter_by(order_item_id=line_id, part_id=part_id).first()
                if snapshot is None:
                    snapshot = OrderMaterialDemand(order_item_id=line_id, part_id=part_id)
                    db.add(snapshot)
                snapshot.qty_per_unit = demand["qty_per_unit"]
                snapshot.order_quantity = own_lines[line_id].quantity
                snapshot.unit = demand["unit"]
                db.flush()
                db.add(MaterialProductionAllocation(demand_id=snapshot.id, quantity=qty,
                                                    **{SOURCE[source_type][3]: item_id}))
            else:
                db.add(Allocation(order_item_id=line_id, quantity=qty, **{SOURCE[source_type][3]: item_id}))
    if any(values.values()):
        mark_production_started(order)
    db.flush()
    return _source_view(db, source_type, item, parent)


def replace_order_sources(db, order_id, sources):
    """One atomic confirmation, with stable lock order across multiple outputs."""
    keys = [(row["source_type"], row["source_item_id"]) for row in sources]
    if len(set(keys)) != len(keys):
        raise ValueError("同一产出不能重复提交")
    with db.begin_nested():
        lock_order(db, order_id)
        if any(entry.get("material_part_id") for row in sources for entry in row["allocations"]):
            from services.bom import lock_bom
            for (jewelry_id,) in db.query(OrderItem.jewelry_id).filter_by(order_id=order_id).filter(
                    OrderItem.jewelry_id.isnot(None)).distinct().order_by(OrderItem.jewelry_id):
                lock_bom(db, jewelry_id)
        # Resolve parent identities before locking: different outputs in one parent
        # must not cause parent locks to be taken in inconsistent order.
        def lock_key(row):
            kind, item_id = row["source_type"], row["source_item_id"]
            if kind not in SOURCE:
                raise ValueError("不支持的生产来源")
            item = db.get(SOURCE[kind][1], item_id)
            return kind, getattr(item, SOURCE[kind][2], ""), item_id
        ordered = sorted(sources, key=lock_key)
        locked = []
        for row in ordered:
            kind, item_id = row["source_type"], row["source_item_id"]
            parent, item = lock_source(db, kind, item_id)
            rows = source_rows(db, kind, item_id)
            if row["revision"] != _revision(item, parent, rows):
                raise ValueError("生产安排已变化，请刷新后重新核对保存")
            locked.append((row, parent, item, rows))
        # Release this order's submitted shares together before validating the
        # replacement totals. Otherwise moving demand from a later source to an
        # earlier one would incorrectly exceed the demand limit mid-batch.
        own_ids = {line.id for line in db.query(OrderItem).filter_by(order_id=order_id)}
        for _, _, _, rows in locked:
            for allocation in rows:
                if allocation.order_item_id in own_ids:
                    db.delete(allocation)
        db.flush()
        return [replace_order_source(db, order_id, row["source_type"], item.id,
                                     _revision(item, parent, source_rows(db, row["source_type"], item.id)),
                                     row["allocations"]) for row, parent, item, _ in locked]
