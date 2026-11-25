from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.bom import Bom
from models.jewelry import Jewelry
from schemas.bom import BomCopyRequest
from services._helpers import _next_id, keyword_filter


class BomCopyNotFound(Exception):
    pass


class BomCopyConflict(Exception):
    pass


def lock_bom(db, jewelry_id):
    from sqlalchemy import text
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
               {"key": f"allen-bom:{jewelry_id}"})


def set_bom(db: Session, jewelry_id: str, part_id: str, qty_per_unit: float) -> Bom:
    lock_bom(db, jewelry_id)
    existing = (
        db.query(Bom)
        .filter(Bom.jewelry_id == jewelry_id, Bom.part_id == part_id)
        .populate_existing()
        .first()
    )
    if existing:
        existing.qty_per_unit = qty_per_unit
        db.flush()
        return existing
    bom = _add_bom(db, jewelry_id, part_id, qty_per_unit)
    db.flush()
    return bom


def _add_bom(db, jewelry_id, part_id, qty_per_unit):
    bom = Bom(
        id=_next_id(db, Bom, "BM"),
        jewelry_id=jewelry_id,
        part_id=part_id,
        qty_per_unit=qty_per_unit,
    )
    db.add(bom)
    return bom


def get_bom(db: Session, jewelry_id: str) -> list:
    return db.query(Bom).filter(Bom.jewelry_id == jewelry_id).all()


def list_bom_copy_sources(db: Session, target_id: str, keyword: str, offset: int, limit: int) -> dict:
    if db.get(Jewelry, target_id) is None:
        raise BomCopyNotFound("目标饰品不存在")
    query = select(Jewelry.id, Jewelry.name, Jewelry.unit, Jewelry.status).where(Jewelry.id != target_id)
    clause = keyword_filter(keyword, Jewelry.name, Jewelry.id)
    if clause is not None:
        query = query.where(clause)
    results = db.execute(query.order_by(Jewelry.id.desc()).offset(offset).limit(limit + 1)).mappings().all()
    page = results[:limit]
    counts = dict(db.execute(
        select(Bom.jewelry_id, func.count(func.distinct(Bom.part_id)))
        .where(Bom.jewelry_id.in_([item.id for item in page]))
        .group_by(Bom.jewelry_id)
    ).all()) if page else {}
    return {"items": [{**item, "part_count": counts.get(item.id, 0)} for item in page], "has_more": len(results) > limit}


def _copy_jewelries(db, target_id, source_id, *, lock=False):
    if target_id == source_id:
        raise ValueError("不能从当前饰品复制用料")
    query = select(Jewelry).where(Jewelry.id.in_([target_id, source_id])).order_by(Jewelry.id)
    if lock:
        # Keep both units stable until the insert commits. Advisory locks
        # serialize with set_bom/delete_bom_item and reverse-direction copies.
        for jewelry_id in sorted((target_id, source_id)):
            lock_bom(db, jewelry_id)
        query = query.with_for_update(read=True).execution_options(populate_existing=True)
    items = {item.id: item for item in db.scalars(query)}
    if target_id not in items:
        raise BomCopyNotFound("目标饰品不存在")
    if source_id not in items:
        raise BomCopyNotFound("来源饰品不存在，请重新选择")
    return items[target_id], items[source_id]


def preview_bom_copy(db: Session, target_id: str, source_id: str) -> dict:
    target, source = _copy_jewelries(db, target_id, source_id)
    # Collapse any historical duplicate source rows by part ID, keeping the first.
    rows = {}
    for row in db.scalars(select(Bom).where(Bom.jewelry_id == source_id).order_by(Bom.id)):
        rows.setdefault(row.part_id, row)
    return {"source": source, "target_unit": target.unit, "rows": list(rows.values())}


def copy_bom_items(db: Session, target_id: str, body: BomCopyRequest) -> dict:
    target, source = _copy_jewelries(db, target_id, body.source_id, lock=True)
    if (target.unit, source.unit) != (body.target_unit, body.source_unit):
        raise BomCopyConflict("饰品计量单位已变更，请重新加载来源用料后核对")
    if (not (target.unit or "").strip() or not (source.unit or "").strip() or target.unit != source.unit) and not body.unit_confirmed:
        raise ValueError("请先核对来源和目标的计量单位")

    requested = {item.part_id: item.qty_per_unit for item in body.items}
    pairs = db.execute(select(Bom.jewelry_id, Bom.part_id).where(
        Bom.jewelry_id.in_([target_id, source.id]), Bom.part_id.in_(requested),
    )).all()
    source_parts = {part_id for jewelry_id, part_id in pairs if jewelry_id == source.id}
    if requested.keys() - source_parts:
        raise BomCopyConflict("来源用料已变更，请重新加载来源用料后核对")
    existing = {part_id for jewelry_id, part_id in pairs if jewelry_id == target_id}
    added, skipped = [], []
    for part_id, qty_per_unit in requested.items():
        if part_id in existing:
            skipped.append(part_id)
        else:
            _add_bom(db, target_id, part_id, qty_per_unit)
            added.append(part_id)
    db.flush()
    return {"added_part_ids": added, "skipped_part_ids": skipped}


def delete_bom_item(db: Session, bom_id: str) -> None:
    bom = db.query(Bom).filter(Bom.id == bom_id).first()
    if bom is None:
        raise ValueError(f"BOM item not found: {bom_id}")
    lock_bom(db, bom.jewelry_id)
    db.delete(bom)
    db.flush()


def calculate_parts_needed(db: Session, jewelry_id: str, qty: int) -> dict:
    rows = get_bom(db, jewelry_id)
    return {row.part_id: float(row.qty_per_unit) * qty for row in rows}
