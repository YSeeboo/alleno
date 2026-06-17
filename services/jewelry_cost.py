from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from models.bom import Bom
from models.part import Part

_Q7 = Decimal("0.0000001")


def compute_jewelry_cost(jewelry, bom_rows, part_map) -> dict:
    """单饰品成本（物料 + 手工费）的纯计算，被订单成本快照与饰品实时成本共用。

    - jewelry: 任意带 `.handcraft_cost` 的对象（ORM 或测试桩）
    - bom_rows: 该饰品的 Bom 行（带 `.part_id` / `.qty_per_unit`）
    - part_map: {part_id: Part}，Part 带 `.unit_cost` / `.name`

    返回的 material_cost / handcraft_cost / total_cost 均为 Decimal（保留快照层的
    精确累加能力，API 层再转 float）。has_incomplete_cost 在以下任一情况为 True：
    没有 BOM 行、引用的配件不在 part_map、或配件 unit_cost 为 None。
    """
    bom_cost = Decimal(0)
    has_incomplete = False
    bom_details: list[dict] = []
    for row in bom_rows:
        part = part_map.get(row.part_id)
        if part is None or part.unit_cost is None:
            has_incomplete = True
        part_unit_cost = (
            Decimal(str(part.unit_cost))
            if (part is not None and part.unit_cost is not None)
            else Decimal(0)
        )
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

    if not bom_rows:
        has_incomplete = True

    material_cost = bom_cost.quantize(_Q7, rounding=ROUND_HALF_UP) if bom_rows else Decimal(0)
    handcraft_cost = Decimal(str(jewelry.handcraft_cost or 0))
    total_cost = (material_cost + handcraft_cost).quantize(_Q7, rounding=ROUND_HALF_UP)
    return {
        "material_cost": material_cost,
        "handcraft_cost": handcraft_cost,
        "total_cost": total_cost,
        "has_incomplete_cost": has_incomplete,
        "bom_details": bom_details,
    }


def attach_jewelry_costs(db: Session, jewelries: list) -> list:
    """批量给饰品 ORM 实例挂上 material_cost / total_cost / has_incomplete_cost
    三个非持久化属性（不写库）。一次性聚合查 BOM 与配件，避免逐饰品 N+1。"""
    if not jewelries:
        return jewelries

    jewelry_ids = [j.id for j in jewelries]
    boms = db.query(Bom).filter(Bom.jewelry_id.in_(jewelry_ids)).all()
    bom_by_jewelry: dict[str, list] = {}
    part_ids = set()
    for b in boms:
        bom_by_jewelry.setdefault(b.jewelry_id, []).append(b)
        part_ids.add(b.part_id)

    part_map = {}
    if part_ids:
        part_map = {
            p.id: p
            for p in db.query(Part).filter(Part.id.in_(list(part_ids))).all()
        }

    for j in jewelries:
        cost = compute_jewelry_cost(j, bom_by_jewelry.get(j.id, []), part_map)
        j.material_cost = float(cost["material_cost"])
        j.total_cost = float(cost["total_cost"])
        j.has_incomplete_cost = cost["has_incomplete_cost"]
    return jewelries
