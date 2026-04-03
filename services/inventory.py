from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.inventory_log import InventoryLog
from models.jewelry import Jewelry
from models.part import Part


def get_stock(db: Session, item_type: str, item_id: str) -> float:
    result = db.query(func.sum(InventoryLog.change_qty)).filter(
        InventoryLog.item_type == item_type,
        InventoryLog.item_id == item_id,
    ).scalar()
    return float(result) if result is not None else 0.0


def batch_get_stock(db: Session, item_type: str, item_ids: list[str]) -> dict[str, float]:
    if not item_ids:
        return {}
    rows = (
        db.query(InventoryLog.item_id, func.sum(InventoryLog.change_qty))
        .filter(InventoryLog.item_type == item_type, InventoryLog.item_id.in_(item_ids))
        .group_by(InventoryLog.item_id)
        .all()
    )
    result = {item_id: 0.0 for item_id in item_ids}
    for item_id, total in rows:
        result[item_id] = float(total) if total is not None else 0.0
    return result


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


def list_stock_logs(
    db: Session,
    item_type: str | None = None,
    item_id: str | None = None,
    reason: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    q = db.query(InventoryLog)
    if item_type:
        q = q.filter(InventoryLog.item_type == item_type)
    if item_id:
        q = q.filter(InventoryLog.item_id.ilike(f"%{item_id}%"))
    if reason:
        q = q.filter(InventoryLog.reason.ilike(f"%{reason}%"))
    total = q.count()
    rows = q.order_by(InventoryLog.created_at.desc(), InventoryLog.id.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": rows}


def get_inventory_overview(
    db: Session,
    item_type: str | None = None,
    name: str | None = None,
    in_stock_only: bool = False,
) -> list[dict]:
    stock_sq = (
        db.query(
            InventoryLog.item_type,
            InventoryLog.item_id,
            func.sum(InventoryLog.change_qty).label("current"),
            func.max(InventoryLog.created_at).label("updated_at"),
        )
        .group_by(InventoryLog.item_type, InventoryLog.item_id)
        .subquery()
    )

    results = []

    if item_type in (None, "part"):
        q = db.query(Part, stock_sq.c.current, stock_sq.c.updated_at).outerjoin(
            stock_sq,
            (stock_sq.c.item_type == "part") & (stock_sq.c.item_id == Part.id),
        )
        if name:
            q = q.filter(Part.name.ilike(f"%{name}%") | Part.id.ilike(f"%{name}%"))
        for part, current, updated_at in q.all():
            current = float(current) if current is not None else 0.0
            if in_stock_only and current <= 0:
                continue
            results.append({
                "item_type": "part",
                "item_id": part.id,
                "name": part.name,
                "image": part.image,
                "category": part.category,
                "current": current,
                "updated_at": updated_at,
            })

    if item_type in (None, "jewelry"):
        q = db.query(Jewelry, stock_sq.c.current, stock_sq.c.updated_at).outerjoin(
            stock_sq,
            (stock_sq.c.item_type == "jewelry") & (stock_sq.c.item_id == Jewelry.id),
        )
        if name:
            q = q.filter(Jewelry.name.ilike(f"%{name}%") | Jewelry.id.ilike(f"%{name}%"))
        for jewelry, current, updated_at in q.all():
            current = float(current) if current is not None else 0.0
            if in_stock_only and current <= 0:
                continue
            results.append({
                "item_type": "jewelry",
                "item_id": jewelry.id,
                "name": jewelry.name,
                "image": jewelry.image,
                "category": jewelry.category,
                "current": current,
                "updated_at": updated_at,
            })

    results.sort(key=lambda x: x["item_id"])
    return results
