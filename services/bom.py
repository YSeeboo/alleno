from sqlalchemy.orm import Session

from models.bom import Bom
from services._helpers import _next_id


def set_bom(db: Session, jewelry_id: str, part_id: str, qty_per_unit: float) -> Bom:
    existing = (
        db.query(Bom)
        .filter(Bom.jewelry_id == jewelry_id, Bom.part_id == part_id)
        .first()
    )
    if existing:
        existing.qty_per_unit = qty_per_unit
        db.flush()
        return existing
    bom = Bom(
        id=_next_id(db, Bom, "BM"),
        jewelry_id=jewelry_id,
        part_id=part_id,
        qty_per_unit=qty_per_unit,
    )
    db.add(bom)
    db.flush()
    return bom


def get_bom(db: Session, jewelry_id: str) -> list:
    return db.query(Bom).filter(Bom.jewelry_id == jewelry_id).all()


def delete_bom_item(db: Session, bom_id: str) -> None:
    bom = db.query(Bom).filter(Bom.id == bom_id).first()
    if bom is None:
        raise ValueError(f"BOM item not found: {bom_id}")
    db.delete(bom)
    db.flush()


def calculate_parts_needed(db: Session, jewelry_id: str, qty: int) -> dict:
    rows = get_bom(db, jewelry_id)
    return {row.part_id: float(row.qty_per_unit) * qty for row in rows}
