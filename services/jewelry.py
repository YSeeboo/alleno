from typing import Optional

from sqlalchemy.orm import Session

from models.jewelry import Jewelry
from services._helpers import _next_id

_VALID_STATUSES = {"active", "inactive"}


def create_jewelry(db: Session, data: dict) -> Jewelry:
    jewelry = Jewelry(id=_next_id(db, Jewelry, "SP"), **data)
    db.add(jewelry)
    db.flush()
    return jewelry


def get_jewelry(db: Session, jewelry_id: str) -> Optional[Jewelry]:
    return db.query(Jewelry).filter(Jewelry.id == jewelry_id).first()


def list_jewelries(db: Session, category: str = None, status: str = None) -> list:
    q = db.query(Jewelry)
    if category is not None:
        q = q.filter(Jewelry.category == category)
    if status is not None:
        q = q.filter(Jewelry.status == status)
    return q.all()


def update_jewelry(db: Session, jewelry_id: str, data: dict) -> Jewelry:
    jewelry = get_jewelry(db, jewelry_id)
    if jewelry is None:
        raise ValueError(f"Jewelry not found: {jewelry_id}")
    for key, value in data.items():
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
