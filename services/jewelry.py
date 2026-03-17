from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.jewelry import Jewelry
from services._helpers import _next_id_by_category

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
    if name is not None:
        q = q.filter(or_(Jewelry.name.ilike(f"%{name}%"), Jewelry.id.ilike(f"%{name}%")))
    return q.order_by(Jewelry.id.desc()).all()


def update_jewelry(db: Session, jewelry_id: str, data: dict) -> Jewelry:
    jewelry = get_jewelry(db, jewelry_id)
    if jewelry is None:
        raise ValueError(f"Jewelry not found: {jewelry_id}")
    if "category" in data and data["category"] is not None:
        if data["category"] not in JEWELRY_CATEGORIES:
            raise ValueError(
                f"Invalid category '{data['category']}'. Must be one of: {list(JEWELRY_CATEGORIES.keys())}"
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
