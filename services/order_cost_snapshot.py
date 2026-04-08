from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from models.bom import Bom
from models.jewelry import Jewelry
from models.order import Order, OrderItem
from models.order_cost_snapshot import OrderCostSnapshot, OrderCostSnapshotItem
from models.part import Part

_Q7 = Decimal("0.0000001")


def generate_cost_snapshot(db: Session, order_id: str) -> OrderCostSnapshot:
    """订单完成时生成成本快照。"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        raise ValueError(f"Order not found: {order_id}")

    items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    if not items:
        raise ValueError(f"订单 {order_id} 没有饰品明细")

    # Batch load all jewelry, BOM rows, and parts
    jewelry_ids = list({item.jewelry_id for item in items})
    jewelries = db.query(Jewelry).filter(Jewelry.id.in_(jewelry_ids)).all()
    jewelry_map = {j.id: j for j in jewelries}

    all_bom = db.query(Bom).filter(Bom.jewelry_id.in_(jewelry_ids)).all()
    bom_by_jewelry: dict[str, list] = {}
    all_part_ids = set()
    for b in all_bom:
        bom_by_jewelry.setdefault(b.jewelry_id, []).append(b)
        all_part_ids.add(b.part_id)

    part_map = {}
    if all_part_ids:
        for p in db.query(Part).filter(Part.id.in_(list(all_part_ids))).all():
            part_map[p.id] = p

    # 前置校验：所有饰品必须有 BOM
    for item in items:
        bom_rows = bom_by_jewelry.get(item.jewelry_id, [])
        if not bom_rows:
            jewelry = jewelry_map.get(item.jewelry_id)
            name = jewelry.name if jewelry else item.jewelry_id
            raise ValueError(f"饰品「{name}」({item.jewelry_id}) 没有 BOM，无法生成成本快照")

    has_incomplete = False
    total_cost = Decimal(0)
    snapshot_items = []

    for item in items:
        jewelry = jewelry_map.get(item.jewelry_id)
        bom_rows = bom_by_jewelry.get(item.jewelry_id, [])

        # 计算 BOM 配件成本
        bom_cost = Decimal(0)
        bom_details = []
        for row in bom_rows:
            part = part_map.get(row.part_id)
            part_unit_cost = Decimal(str(part.unit_cost or 0)) if part else Decimal(0)
            if part and part.unit_cost is None:
                has_incomplete = True
            qty_per_unit = Decimal(str(row.qty_per_unit))
            subtotal = (part_unit_cost * qty_per_unit).quantize(_Q7, rounding=ROUND_HALF_UP)
            bom_cost += subtotal
            bom_details.append({
                "part_id": row.part_id,
                "part_name": part.name if part else None,
                "unit_cost": float(part_unit_cost),
                "qty_per_unit": float(qty_per_unit),
                "subtotal": float(subtotal),
            })

        # 饰品单位成本 = BOM 配件成本 + handcraft_cost
        hc_cost = Decimal(str(jewelry.handcraft_cost or 0)) if jewelry else Decimal(0)
        jewelry_unit_cost = (bom_cost + hc_cost).quantize(_Q7, rounding=ROUND_HALF_UP)
        jewelry_total_cost = (jewelry_unit_cost * item.quantity).quantize(_Q7, rounding=ROUND_HALF_UP)
        total_cost += jewelry_total_cost

        snapshot_items.append({
            "jewelry_id": item.jewelry_id,
            "jewelry_name": jewelry.name if jewelry else None,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price) if item.unit_price is not None else None,
            "handcraft_cost": float(hc_cost),
            "jewelry_unit_cost": float(jewelry_unit_cost),
            "jewelry_total_cost": float(jewelry_total_cost),
            "bom_details": bom_details,
        })

    # 订单总成本 = Σ饰品总成本 + 包装费
    pkg_cost = Decimal(str(order.packaging_cost or 0))
    total_cost = (total_cost + pkg_cost).quantize(_Q7, rounding=ROUND_HALF_UP)

    # 利润
    total_amount = Decimal(str(order.total_amount or 0))
    profit = (total_amount - total_cost).quantize(_Q7, rounding=ROUND_HALF_UP)

    # 创建快照
    snapshot = OrderCostSnapshot(
        order_id=order_id,
        total_cost=total_cost,
        packaging_cost=pkg_cost if order.packaging_cost is not None else None,
        total_amount=order.total_amount,
        profit=profit,
        has_incomplete_cost=1 if has_incomplete else 0,
    )
    db.add(snapshot)
    db.flush()

    for si in snapshot_items:
        bom_details = si.pop("bom_details")
        item_obj = OrderCostSnapshotItem(snapshot_id=snapshot.id, **si)
        item_obj.bom_details = bom_details
        db.add(item_obj)
    db.flush()

    return snapshot


def get_cost_snapshot(db: Session, order_id: str) -> OrderCostSnapshot | None:
    """获取订单的成本快照（最新一条）。"""
    return (
        db.query(OrderCostSnapshot)
        .filter(OrderCostSnapshot.order_id == order_id)
        .order_by(OrderCostSnapshot.id.desc())
        .first()
    )


def update_snapshot_packaging_cost(db: Session, order_id: str, packaging_cost: float) -> None:
    """仅更新已有快照的 packaging_cost / total_cost / profit，不重算 BOM 明细。"""
    snapshot = get_cost_snapshot(db, order_id)
    if snapshot is None:
        return

    new_pkg = Decimal(str(packaging_cost))
    old_pkg = Decimal(str(snapshot.packaging_cost or 0))

    # total_cost = (原 total_cost - 原 packaging) + 新 packaging
    old_total = Decimal(str(snapshot.total_cost))
    items_cost = old_total - old_pkg
    new_total = (items_cost + new_pkg).quantize(_Q7, rounding=ROUND_HALF_UP)

    total_amount = Decimal(str(snapshot.total_amount or 0))
    new_profit = (total_amount - new_total).quantize(_Q7, rounding=ROUND_HALF_UP)

    snapshot.packaging_cost = new_pkg
    snapshot.total_cost = new_total
    snapshot.profit = new_profit
    db.flush()
