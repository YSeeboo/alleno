from decimal import Decimal

from sqlalchemy.orm import Session

from models.part_bom import PartBom
from models.part import Part
from services._helpers import _next_id


def set_part_bom(db: Session, parent_part_id: str, child_part_id: str, qty_per_unit: float) -> PartBom:
    if parent_part_id == child_part_id:
        raise ValueError("配件不能引用自身作为子配件")

    parent = db.query(Part).filter_by(id=parent_part_id).first()
    if not parent:
        raise ValueError(f"配件 {parent_part_id} 不存在")
    child = db.query(Part).filter_by(id=child_part_id).first()
    if not child:
        raise ValueError(f"配件 {child_part_id} 不存在")

    existing = (
        db.query(PartBom)
        .filter_by(parent_part_id=parent_part_id, child_part_id=child_part_id)
        .first()
    )
    if existing:
        existing.qty_per_unit = qty_per_unit
        db.flush()
        recalc_part_unit_cost(db, parent_part_id)
        return existing

    bom = PartBom(
        id=_next_id(db, PartBom, "PB"),
        parent_part_id=parent_part_id,
        child_part_id=child_part_id,
        qty_per_unit=qty_per_unit,
    )
    db.add(bom)
    db.flush()
    recalc_part_unit_cost(db, parent_part_id)
    return bom


def get_part_bom(db: Session, parent_part_id: str) -> list[dict]:
    rows = db.query(PartBom).filter_by(parent_part_id=parent_part_id).all()
    result = []
    for row in rows:
        child = db.query(Part).filter_by(id=row.child_part_id).first()
        result.append({
            "id": row.id,
            "parent_part_id": row.parent_part_id,
            "child_part_id": row.child_part_id,
            "qty_per_unit": float(row.qty_per_unit),
            "child_part_name": child.name if child else "",
            "child_part_image": child.image if child else None,
        })
    return result


def delete_part_bom_item(db: Session, bom_id: str) -> None:
    row = db.query(PartBom).filter_by(id=bom_id).first()
    if not row:
        raise ValueError(f"配件 BOM {bom_id} 不存在")
    parent_id = row.parent_part_id
    db.delete(row)
    db.flush()
    recalc_part_unit_cost(db, parent_id)


def calculate_child_parts_needed(db: Session, parent_part_id: str, qty: float) -> dict:
    rows = db.query(PartBom).filter_by(parent_part_id=parent_part_id).all()
    return {row.child_part_id: float(row.qty_per_unit) * qty for row in rows}


def recalc_part_unit_cost(db: Session, part_id: str) -> None:
    """Recalculate unit_cost for a composite part based on its part_bom.

    unit_cost = Σ(child.unit_cost × qty_per_unit) + assembly_cost
    Only applies if the part has part_bom rows.
    """
    rows = db.query(PartBom).filter_by(parent_part_id=part_id).all()
    if not rows:
        return  # Not a composite part, don't touch unit_cost

    part = db.query(Part).filter_by(id=part_id).first()
    if not part:
        return

    total = Decimal("0")
    for row in rows:
        child = db.query(Part).filter_by(id=row.child_part_id).first()
        child_cost = Decimal(str(child.unit_cost or 0)) if child else Decimal("0")
        total += child_cost * Decimal(str(row.qty_per_unit))

    assembly = Decimal(str(part.assembly_cost or 0))
    part.unit_cost = total + assembly
    db.flush()


def recalc_parents_of_child(db: Session, child_part_id: str) -> None:
    """Find all parent parts that use this child and recalculate their unit_cost."""
    parent_boms = db.query(PartBom).filter_by(child_part_id=child_part_id).all()
    for bom in parent_boms:
        recalc_part_unit_cost(db, bom.parent_part_id)
