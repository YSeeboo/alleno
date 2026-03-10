from typing import List, Optional

from sqlalchemy.orm import Session

from models.part import Part
from services._helpers import _next_id


def create_part(db: Session, data: dict) -> Part:
    part = Part(id=_next_id(db, Part, "PJ"), **data)
    db.add(part)
    db.flush()
    return part


def get_part(db: Session, part_id: str) -> Optional[Part]:
    return db.query(Part).filter(Part.id == part_id).first()


def list_parts(db: Session, category: str = None) -> List[Part]:
    q = db.query(Part)
    if category is not None:
        q = q.filter(Part.category == category)
    return q.all()


def update_part(db: Session, part_id: str, data: dict) -> Part:
    part = get_part(db, part_id)
    if part is None:
        raise ValueError(f"Part not found: {part_id}")
    for key, value in data.items():
        setattr(part, key, value)
    db.flush()
    return part


def delete_part(db: Session, part_id: str) -> None:
    part = get_part(db, part_id)
    if part is None:
        raise ValueError(f"Part not found: {part_id}")
    db.delete(part)
    db.flush()
