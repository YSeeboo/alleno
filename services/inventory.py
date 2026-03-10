from sqlalchemy import func
from sqlalchemy.orm import Session

from models.inventory_log import InventoryLog


def get_stock(db: Session, item_type: str, item_id: str) -> float:
    result = db.query(func.sum(InventoryLog.change_qty)).filter(
        InventoryLog.item_type == item_type,
        InventoryLog.item_id == item_id,
    ).scalar()
    return float(result) if result is not None else 0.0


def add_stock(db: Session, item_type: str, item_id: str, qty: float, reason: str, note: str = None) -> InventoryLog:
    if qty <= 0:
        raise ValueError(f"qty must be positive, got {qty}")
    log = InventoryLog(item_type=item_type, item_id=item_id, change_qty=qty, reason=reason, note=note)
    db.add(log)
    db.flush()
    return log


def deduct_stock(db: Session, item_type: str, item_id: str, qty: float, reason: str, note: str = None) -> InventoryLog:
    if qty <= 0:
        raise ValueError(f"qty must be positive, got {qty}")
    current = get_stock(db, item_type, item_id)
    if current < qty:
        raise ValueError(f"库存不足：{item_type} {item_id} 当前库存 {current}，需要 {qty}")
    log = InventoryLog(item_type=item_type, item_id=item_id, change_qty=-qty, reason=reason, note=note)
    db.add(log)
    db.flush()
    return log


def get_stock_log(db: Session, item_type: str, item_id: str) -> list:
    return (
        db.query(InventoryLog)
        .filter(InventoryLog.item_type == item_type, InventoryLog.item_id == item_id)
        .order_by(InventoryLog.created_at.desc(), InventoryLog.id.desc())
        .all()
    )
