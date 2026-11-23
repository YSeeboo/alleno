"""One-level BOM demand preview, persisted only on explicit confirmation."""
import hashlib
import json
from decimal import Decimal

from models.bom import Bom
from models.order import OrderItem, OrderTodoItem, OrderItemLink
from models.part import Part
from models.jewelry import Jewelry
from models.material_production import OrderMaterialDemand as Demand, MaterialProductionAllocation as Allocation


def demand_revision(line, part_id, coefficient, unit):
    value = [line.id, line.jewelry_id, line.quantity, part_id, str(Decimal(str(coefficient)).normalize()), unit or ""]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def material_demands(db, order_id):
    """GET must not generate legacy todos or mutate snapshots after BOM edits."""
    result = []
    for line in db.query(OrderItem).filter_by(order_id=order_id).populate_existing().order_by(OrderItem.id):
        if not line.jewelry_id:
            continue
        current = {row.part_id: row.qty_per_unit for row in db.query(Bom).filter_by(jewelry_id=line.jewelry_id).populate_existing()}
        saved = {row.part_id: row for row in db.query(Demand).filter_by(order_item_id=line.id)}
        product = db.get(Jewelry, line.jewelry_id)
        for part_id in sorted(current.keys() | saved.keys()):
            part, snapshot = db.get(Part, part_id), saved.get(part_id)
            coefficient, unit = current.get(part_id, Decimal(0)), part.unit if part else None
            rows = db.query(Allocation).filter_by(demand_id=snapshot.id).all() if snapshot else []
            allocated = sum((row.quantity for row in rows), Decimal(0))
            revision = demand_revision(line, part_id, coefficient, unit)
            changed = snapshot is not None and revision != demand_revision(
                line, part_id, snapshot.qty_per_unit, snapshot.unit)
            changed = changed or bool(snapshot and snapshot.order_quantity != line.quantity)
            from services.production_allocation import legacy_demand_claim
            legacy = legacy_demand_claim(db, line) or db.query(OrderItemLink.id).join(OrderTodoItem).filter(
                OrderTodoItem.order_id == order_id, OrderTodoItem.part_id == part_id).first() is not None
            result.append({
                "id": f"material:{line.id}:{part_id}", "order_item_id": line.id, "material_part_id": part_id,
                "product_type": "part", "product_id": part_id, "product_name": part.name if part else part_id,
                "image": part.image if part else None, "unit": unit,
                "parent_product_name": product.name if product else line.jewelry_id,
                "customer_code": line.customer_code, "qty_per_unit": coefficient,
                "quantity": Decimal(str(coefficient)) * line.quantity, "allocated": allocated,
                "snapshot_quantity": snapshot.qty_per_unit * snapshot.order_quantity if snapshot else None,
                "demand_changed": changed, "demand_revision": revision, "legacy_claim": legacy,
            })
    return result


def material_source_query(db, source_type, item_id):
    field = "plating_order_item_id" if source_type == "plating" else "handcraft_jewelry_item_id"
    return db.query(Allocation).filter(getattr(Allocation, field) == item_id)


def order_material_allocations(db, order_id):
    return db.query(Allocation).join(Demand).join(OrderItem).filter(OrderItem.order_id == order_id).all()


def guard_material_order_change(db, order_id, item_id=None, quantity=None):
    rows = order_material_allocations(db, order_id)
    totals = {}
    for row in rows:
        if item_id is None or row.order_item_id == item_id:
            totals[row.demand_id] = totals.get(row.demand_id, Decimal(0)) + row.quantity
    for demand_id, assigned in totals.items():
        snapshot = db.get(Demand, demand_id)
        line = db.get(OrderItem, snapshot.order_item_id)
        current = db.query(Bom).filter_by(jewelry_id=line.jewelry_id, part_id=snapshot.part_id).first()
        coefficient = min(snapshot.qty_per_unit, current.qty_per_unit if current else Decimal(0))
        if quantity is None or assigned > coefficient * Decimal(str(quantity)):
            raise ValueError("订单存在配件备料安排，请先调整或取消对应配件份额")
