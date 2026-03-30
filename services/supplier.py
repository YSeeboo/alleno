from typing import Optional

from sqlalchemy.orm import Session

from models.supplier import Supplier


def create_supplier(db: Session, name: str, type: str) -> Supplier:
    existing = db.query(Supplier).filter(
        Supplier.name == name, Supplier.type == type
    ).first()
    if existing:
        raise ValueError(f"同类型商家 '{name}' 已存在")
    supplier = Supplier(name=name, type=type)
    db.add(supplier)
    db.flush()
    return supplier


def list_suppliers(db: Session, type: Optional[str] = None) -> list[Supplier]:
    q = db.query(Supplier)
    if type is not None:
        q = q.filter(Supplier.type == type)
    return q.order_by(Supplier.name.asc()).all()


def update_supplier(db: Session, supplier_id: int, name: str) -> Supplier:
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if supplier is None:
        raise ValueError(f"Supplier not found: {supplier_id}")
    duplicate = db.query(Supplier).filter(
        Supplier.name == name, Supplier.type == supplier.type, Supplier.id != supplier_id
    ).first()
    if duplicate:
        raise ValueError(f"同类型商家 '{name}' 已存在")
    supplier.name = name
    db.flush()
    return supplier


def delete_supplier(db: Session, supplier_id: int) -> None:
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if supplier is None:
        raise ValueError(f"Supplier not found: {supplier_id}")
    db.delete(supplier)
    db.flush()
