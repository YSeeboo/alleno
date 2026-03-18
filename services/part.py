from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.part import Part
from services._helpers import _next_id_by_category

PART_CATEGORIES = {
    "吊坠": "PJ-DZ",
    "链条": "PJ-LT",
    "小配件": "PJ-X",
}


def create_part(db: Session, data: dict) -> Part:
    category = data.get("category")
    if category not in PART_CATEGORIES:
        raise ValueError(
            f"Invalid category '{category}'. Must be one of: {list(PART_CATEGORIES.keys())}"
        )
    prefix = PART_CATEGORIES[category]
    part = Part(id=_next_id_by_category(db, Part, prefix), **data)
    db.add(part)
    db.flush()
    return part


def get_part(db: Session, part_id: str) -> Optional[Part]:
    return db.query(Part).filter(Part.id == part_id).first()


def list_parts(db: Session, category: str = None, name: str = None) -> List[Part]:
    q = db.query(Part)
    if category is not None:
        q = q.filter(Part.category == category)
    if name is not None:
        q = q.filter(or_(Part.name.ilike(f"%{name}%"), Part.id.ilike(f"%{name}%")))
    return q.order_by(Part.id.desc()).all()


def update_part(db: Session, part_id: str, data: dict) -> Part:
    part = get_part(db, part_id)
    if part is None:
        raise ValueError(f"Part not found: {part_id}")
    # Category changes are disallowed because the part ID encodes the category
    # (e.g. PJ-DZ-00001 means 吊坠). Allowing a category change would make the
    # ID misleading and break the ID-format contract.
    if "category" in data:
        raise ValueError(
            "Category cannot be changed after creation — the part ID encodes the category."
        )
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
