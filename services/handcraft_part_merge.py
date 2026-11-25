"""Non-destructive eligibility and preview-checked merge for issued-part rows."""

import hashlib
import json
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from models.handcraft_order import (
    HandcraftOrder, HandcraftPartItem, HandcraftPickingRecord, HandcraftPickingWeight,
)
from models.handcraft_receipt import HandcraftReceiptItem
from models.order import OrderItemLink
from models.part import Part
from models.production_loss import ProductionLoss


class HandcraftPartMergeConflict(Exception):
    pass


# Both qty and bom_qty are NUMERIC(10, 4).
_MAX_QTY = Decimal("999999.9999")


def _protected_rows(db: Session, order_id: str, row_ids: list[int]) -> dict[int, str]:
    loss = ProductionLoss.item_id
    receipt = HandcraftReceiptItem.handcraft_part_item_id
    linked = OrderItemLink.handcraft_part_item_id
    picked = HandcraftPickingRecord.handcraft_part_item_id
    measured = HandcraftPickingWeight.part_item_id
    checks = [
        (db.query(loss).filter_by(order_type="handcraft", order_id=order_id, item_type="handcraft_part"), loss, "已有损耗记录"),
        (db.query(receipt), receipt, "已有回收记录"),
        (db.query(linked), linked, "已关联订单"),
        (db.query(picked), picked, "已有配货记录"),
        (db.query(measured), measured, "已有称重或实配数量记录"),
    ]
    protected = {}
    for query, column, reason in checks:
        for (row_id,) in query.filter(column.in_(row_ids)):
            protected.setdefault(row_id, reason)
    return protected


def _block_reason(rows, part, protected):
    if part.is_composite:
        return "组合配件暂不支持合并"
    if not rows[0].unit or not rows[0].unit.strip():
        return "明细缺少单位"
    for row in rows:
        if row.id in protected:
            return protected[row.id]
        if row.weight is not None:
            return "已有称重记录"
        if row.status != "未送出" or any((row.received_qty, row.returned_qty, row.consumed_qty)):
            return "已有发出或回收记录"
        if not row.qty.is_finite() or row.qty <= 0:
            return "有无效的发出数量"
        if row.bom_qty is not None and (not row.bom_qty.is_finite() or row.bom_qty < 0):
            return "有无效的 BOM 理论用量"
    if any(row.bom_qty is None for row in rows) and any(row.bom_qty is not None for row in rows):
        return "部分明细缺少 BOM 理论用量"
    if sum(row.qty for row in rows) > _MAX_QTY or sum(row.bom_qty or 0 for row in rows) > _MAX_QTY:
        return "合计数量超出系统上限"
    return None


def _plans(db: Session, order_id: str, *, lock: bool = False):
    orders = db.query(HandcraftOrder).filter_by(id=order_id).populate_existing()
    order = (orders.with_for_update() if lock else orders).one_or_none()
    if order is None:
        raise ValueError(f"手工单 {order_id} 不存在")
    if order.archived_at is not None or order.status != "pending":
        if lock:
            raise HandcraftPartMergeConflict("仅待发出且未归档的手工单可以合并配件")
        return []

    query = (db.query(HandcraftPartItem, Part)
             .join(Part, Part.id == HandcraftPartItem.part_id)
             .filter(HandcraftPartItem.handcraft_order_id == order_id)
             .order_by(HandcraftPartItem.id).populate_existing())
    # Same order lock as dispatch; row locks also serialize edits and FK references
    # to the originals. Look up protections AFTER acquiring these locks.
    if lock:
        query = query.with_for_update(of=HandcraftPartItem)
    by_key = defaultdict(list)
    parts = {}
    for row, part in query:
        by_key[(row.part_id, row.unit)].append(row)
        parts[row.part_id] = part
    duplicates = [rows for rows in by_key.values() if len(rows) > 1]
    if not duplicates:
        return []
    protected = _protected_rows(db, order_id, [row.id for rows in duplicates for row in rows])

    plans = []
    for rows in duplicates:
        first = rows[0]
        part = parts[first.part_id]
        reason = _block_reason(rows, part, protected)
        group = {
            "part_id": first.part_id,
            "part_name": part.name,
            "unit": first.unit,
            "retain_item_id": first.id,
            "rows": [{"id": row.id, "qty": row.qty, "note": row.note} for row in rows],
            "blocked_reason": reason,
        }
        if not reason:
            snapshot = [order_id, first.part_id, first.unit, [
                (row.id, str(row.qty), str(row.bom_qty), row.note) for row in rows
            ]]
            revision = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False).encode()).hexdigest()
            notes = dict.fromkeys(row.note for row in rows if row.note and row.note.strip())
            group.update(
                revision=revision,
                merged_qty=sum(row.qty for row in rows),
                merged_bom_qty=sum(row.bom_qty for row in rows) if first.bom_qty is not None else None,
                merged_note="\n".join(notes) if notes else first.note,
            )
        plans.append((group, rows))
    return plans


def preview_handcraft_part_merge(db: Session, order_id: str):
    return [group for group, _ in _plans(db, order_id)]


def apply_handcraft_part_merge(db: Session, order_id: str, selections: dict[int, str]):
    plans = {group["retain_item_id"]: (group, rows) for group, rows in _plans(db, order_id, lock=True)}
    chosen = []
    for row_id, revision in selections.items():
        group, rows = plans.get(row_id, (None, None))
        if group and group["blocked_reason"]:
            raise HandcraftPartMergeConflict(f'{group["part_id"]} 不可合并：{group["blocked_reason"]}。请重新预览。')
        if not group or group["revision"] != revision:
            raise HandcraftPartMergeConflict("发出配件明细已变更，本次未合并，请重新预览")
        chosen.append((group, rows))

    removed = 0
    for group, (first, *others) in chosen:
        first.qty = group["merged_qty"]
        first.bom_qty = group["merged_bom_qty"]
        first.note = group["merged_note"]
        for row in others:
            db.delete(row)
        removed += len(others)
    db.flush()
    return {"merged_groups": len(chosen), "removed_rows": removed}
