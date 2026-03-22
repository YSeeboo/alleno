from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.part import Part
from services._helpers import _next_id_by_category

COLOR_VARIANTS = [
    {"code": "G", "label": "金色"},
    {"code": "S", "label": "白K"},
    {"code": "RG", "label": "玫瑰金"},
]
COLOR_SUFFIXES = [v["label"] for v in COLOR_VARIANTS]


def _is_color_variant(name: str) -> bool:
    return any(name.endswith(f"_{suffix}") for suffix in COLOR_SUFFIXES)


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
    parent_part_id = data.get("parent_part_id")
    if parent_part_id is not None:
        parent = db.get(Part, parent_part_id)
        if parent is None:
            raise ValueError(f"Parent part not found: {parent_part_id}")
        if parent.parent_part_id is not None:
            raise ValueError("不支持多层嵌套：目标配件已有父配件")
    prefix = PART_CATEGORIES[category]
    part = Part(id=_next_id_by_category(db, Part, prefix), **data)
    db.add(part)
    db.flush()
    return part


def get_part(db: Session, part_id: str) -> Optional[Part]:
    return db.query(Part).filter(Part.id == part_id).first()


def list_parts(db: Session, category: str = None, name: str = None, parent_part_id: str = None) -> List[Part]:
    q = db.query(Part)
    if category is not None:
        q = q.filter(Part.category == category)
    if name is not None:
        q = q.filter(or_(Part.name.ilike(f"%{name}%"), Part.id.ilike(f"%{name}%")))
    if parent_part_id is not None:
        q = q.filter(Part.parent_part_id == parent_part_id)
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
    if (_is_color_variant(part.name) or part.parent_part_id is not None) and "color" in data:
        raise ValueError("变体配件不可修改颜色")
    if part.parent_part_id is not None and "parent_part_id" in data:
        raise ValueError("变体配件不可修改父配件关系")
    if "parent_part_id" in data and data["parent_part_id"] is not None:
        if data["parent_part_id"] == part_id:
            raise ValueError("配件不能指向自身作为父配件")
        parent = db.get(Part, data["parent_part_id"])
        if parent is None:
            raise ValueError(f"Parent part not found: {data['parent_part_id']}")
        if parent.parent_part_id is not None:
            raise ValueError("不支持多层嵌套：目标配件已有父配件")
        has_children = db.query(Part).filter(Part.parent_part_id == part_id).first() is not None
        if has_children:
            raise ValueError("不支持多层嵌套：当前配件已有子配件，不能再挂到其他配件下")
    for key, value in data.items():
        setattr(part, key, value)
    db.flush()
    return part


COLOR_CODES = {v["code"]: v["label"] for v in COLOR_VARIANTS}


def _validate_variant_request(db: Session, part_id: str, color_code: str):
    """Validate part exists, is not a variant, and color_code is valid. Returns (parent, color_label)."""
    color = COLOR_CODES.get(color_code)
    if color is None:
        raise ValueError(
            f"Invalid color_code '{color_code}'. Must be one of: {list(COLOR_CODES.keys())}"
        )
    parent = get_part(db, part_id)
    if parent is None:
        raise ValueError(f"Part not found: {part_id}")
    if _is_color_variant(parent.name) or parent.parent_part_id is not None:
        raise ValueError("当前非原色配件，不可创建变体")
    return parent, color


def _find_existing_variant(db: Session, part_id: str, variant_name: str, color: str):
    """Find existing variant by name or color under the same parent, with fallback to global name match."""
    # First: look among children of this parent
    by_parent = (
        db.query(Part)
        .filter(
            Part.parent_part_id == part_id,
            or_(Part.name == variant_name, Part.color == color),
        )
        .first()
    )
    if by_parent is not None:
        return by_parent
    # Fallback: match by exact name among orphan parts in the same category
    parent = db.get(Part, part_id)
    if parent is None:
        return None
    by_name = (
        db.query(Part)
        .filter(
            Part.name == variant_name,
            Part.id != part_id,
            Part.category == parent.category,
            Part.parent_part_id.is_(None),
        )
        .first()
    )
    if by_name is not None:
        # Adopt: set parent_part_id so future lookups find it directly
        by_name.parent_part_id = part_id
        if not by_name.color:
            by_name.color = color
        db.flush()
        return by_name
    return None


def create_part_variant(db: Session, part_id: str, color_code: str) -> Part:
    parent, color = _validate_variant_request(db, part_id, color_code)
    variant_name = f"{parent.name}_{color}"
    existing = _find_existing_variant(db, part_id, variant_name, color)
    if existing is not None:
        return existing
    prefix = PART_CATEGORIES[parent.category]
    variant = Part(
        id=_next_id_by_category(db, Part, prefix),
        name=variant_name,
        category=parent.category,
        unit=parent.unit,
        unit_cost=parent.unit_cost,
        plating_process=parent.plating_process,
        image=parent.image,
        color=color,
        parent_part_id=part_id,
    )
    db.add(variant)
    db.flush()
    return variant


def find_or_create_variant(db: Session, part_id: str, color_code: str) -> dict:
    parent, color = _validate_variant_request(db, part_id, color_code)
    variant_name = f"{parent.name}_{color}"
    existing = _find_existing_variant(db, part_id, variant_name, color)
    if existing is not None:
        return {"part": existing, "suggested_name": None}
    return {"part": None, "suggested_name": variant_name}


def list_part_variants(db: Session, part_id: str) -> List[Part]:
    part = get_part(db, part_id)
    if part is None:
        raise ValueError(f"Part not found: {part_id}")
    root_id = part.parent_part_id if part.parent_part_id is not None else part_id
    variants = (
        db.query(Part)
        .filter(Part.parent_part_id == root_id)
        .order_by(Part.id.desc())
        .all()
    )
    if part.parent_part_id is not None:
        # Include the root part when querying from a variant
        root = db.get(Part, root_id)
        return [root] + variants if root else variants
    return variants


def delete_part(db: Session, part_id: str) -> None:
    part = get_part(db, part_id)
    if part is None:
        raise ValueError(f"Part not found: {part_id}")
    has_children = db.query(Part).filter(Part.parent_part_id == part_id).first() is not None
    if has_children:
        raise ValueError("该配件存在颜色变体，请先删除所有变体后再删除根配件")
    db.delete(part)
    db.flush()
