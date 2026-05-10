from typing import Optional

from sqlalchemy.orm import Session

from models.jewelry import Jewelry
from services._helpers import _next_id_by_category, keyword_filter

_VALID_STATUSES = {"active", "inactive"}

JEWELRY_CATEGORIES = {
    "套装": "SP-SET",
    "单件": "SP-PCS",
    "单对": "SP-PAIR",
}


_JEWELRY_MODEL_FIELDS = {c.key for c in Jewelry.__table__.columns}


def create_jewelry(db: Session, data: dict) -> Jewelry:
    category = data.get("category")
    if category not in JEWELRY_CATEGORIES:
        raise ValueError(
            f"Invalid category '{category}'. Must be one of: {list(JEWELRY_CATEGORIES.keys())}"
        )
    prefix = JEWELRY_CATEGORIES[category]
    model_data = {k: v for k, v in data.items() if k in _JEWELRY_MODEL_FIELDS}
    jewelry = Jewelry(id=_next_id_by_category(db, Jewelry, prefix), **model_data)
    db.add(jewelry)
    db.flush()
    return jewelry


def get_jewelry(db: Session, jewelry_id: str) -> Optional[Jewelry]:
    return db.query(Jewelry).filter(Jewelry.id == jewelry_id).first()


def list_jewelries(db: Session, category: str = None, status: str = None, name: str = None) -> list:
    q = db.query(Jewelry)
    if category is not None:
        q = q.filter(Jewelry.category == category)
    if status is not None:
        q = q.filter(Jewelry.status == status)
    clause = keyword_filter(name, Jewelry.name, Jewelry.id)
    if clause is not None:
        q = q.filter(clause)
    return q.order_by(Jewelry.id.desc()).all()


def update_jewelry(db: Session, jewelry_id: str, data: dict) -> Jewelry:
    jewelry = get_jewelry(db, jewelry_id)
    if jewelry is None:
        raise ValueError(f"Jewelry not found: {jewelry_id}")
    # Category changes are disallowed because the jewelry ID encodes the category
    # (e.g. SP-SET-00001 means 套装). Allowing a category change would make the
    # ID misleading and break the ID-format contract.
    if "category" in data:
        raise ValueError(
            "Category cannot be changed after creation — the jewelry ID encodes the category."
        )
    for key, value in data.items():
        if key in _JEWELRY_MODEL_FIELDS:
            setattr(jewelry, key, value)
    db.flush()
    return jewelry


def set_status(db: Session, jewelry_id: str, status: str) -> Jewelry:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {_VALID_STATUSES}")
    return update_jewelry(db, jewelry_id, {"status": status})


def delete_jewelry(db: Session, jewelry_id: str) -> None:
    jewelry = get_jewelry(db, jewelry_id)
    if jewelry is None:
        raise ValueError(f"Jewelry not found: {jewelry_id}")
    db.delete(jewelry)
    db.flush()


def copy_jewelry(db: Session, source_id: str, override_data: dict) -> Jewelry:
    """Clone a jewelry's basic info + BOM rows into a new jewelry record.

    - Raises ValueError if source_id does not exist.
    - Category is always inherited from source (any 'category' key in
      override_data is ignored).
    - Inventory log is NOT cloned; the new jewelry starts at stock 0.
    - status defaults to 'active'.
    """
    from models.bom import Bom
    from services._helpers import _next_id

    source = get_jewelry(db, source_id)
    if source is None:
        raise ValueError(f"Jewelry not found: {source_id}")

    base_data = {
        "name": source.name,
        "image": source.image,
        "structure_image": source.structure_image,
        "category": source.category,
        "color": source.color,
        "unit": source.unit,
        "retail_price": float(source.retail_price) if source.retail_price is not None else None,
        "wholesale_price": float(source.wholesale_price) if source.wholesale_price is not None else None,
        "handcraft_cost": float(source.handcraft_cost) if source.handcraft_cost is not None else None,
    }
    merged = {**base_data, **(override_data or {})}
    merged["category"] = source.category  # force, ignore any override

    new_jewelry = create_jewelry(db, merged)

    src_boms = db.query(Bom).filter(Bom.jewelry_id == source_id).all()
    for src_bom in src_boms:
        new_bom = Bom(
            id=_next_id(db, Bom, "BM"),
            jewelry_id=new_jewelry.id,
            part_id=src_bom.part_id,
            qty_per_unit=src_bom.qty_per_unit,
        )
        db.add(new_bom)
    db.flush()
    return new_jewelry
