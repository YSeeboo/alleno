"""Archive real historical work without pretending it was received or paid.

Services flush only; callers own commit/rollback. The maintenance CLI locks
tables and requires a saved preview, backup and explicit confirmation.
"""
from datetime import date, datetime, time
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from models.handcraft_order import (
    HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem,
    HandcraftPickingWeight, HandcraftPickingRecord,
)
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.handcraft_receipt import HandcraftReceipt, HandcraftReceiptItem
from models.plating_receipt import PlatingReceipt, PlatingReceiptItem
from models.vendor_receipt import VendorReceipt
from time_utils import now_beijing


ARCHIVE_FIELDS = {"archived_at", "archive_reason", "archived_by", "archive_batch_id"}
ORDER_MODELS = {"plating": PlatingOrder, "handcraft": HandcraftOrder}


def require_unarchived(order) -> None:
    if order is not None and order.archived_at is not None:
        raise ValueError(f"单据 {order.id} 已历史归档，不可修改；请先由管理员恢复归档")


def filter_archive(query, model, archive: str = "active"):
    if archive == "active":
        return query.filter(model.archived_at.is_(None))
    if archive == "archived":
        return query.filter(model.archived_at.is_not(None))
    if archive == "all":
        return query
    raise ValueError("归档筛选必须是 active、archived 或 all")


def _serialize(row, *, omit_archive=False):
    return {
        col.key: (str(value) if value is not None else None)
        for col in inspect(type(row)).column_attrs
        if not (omit_archive and col.key in ARCHIVE_FIELDS)
        for value in [getattr(row, col.key)]
    }


def _rows(query):
    return [_serialize(row) for row in query.order_by(query.column_descriptions[0]["entity"].id).all()]


def _snapshot(db: Session, orders: dict) -> dict:
    """Capture quantities, actual picking qty, receipts and payment state exactly."""
    plating_ids = [o.id for o in orders["plating"]]
    handcraft_ids = [o.id for o in orders["handcraft"]]
    pi = db.query(PlatingOrderItem).filter(PlatingOrderItem.plating_order_id.in_(plating_ids)).all()
    hp = db.query(HandcraftPartItem).filter(HandcraftPartItem.handcraft_order_id.in_(handcraft_ids)).all()
    hj = db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.handcraft_order_id.in_(handcraft_ids)).all()
    pri = db.query(PlatingReceiptItem).filter(PlatingReceiptItem.plating_order_item_id.in_([i.id for i in pi])).all()
    hri = db.query(HandcraftReceiptItem).filter(
        HandcraftReceiptItem.handcraft_part_item_id.in_([i.id for i in hp])
        | HandcraftReceiptItem.handcraft_jewelry_item_id.in_([i.id for i in hj])
    ).all()
    result = {
        kind: [_serialize(o, omit_archive=True) for o in rows]
        for kind, rows in orders.items()
    }
    for model, rows in (
        (PlatingOrderItem, pi), (HandcraftPartItem, hp), (HandcraftJewelryItem, hj),
        (PlatingReceiptItem, pri), (HandcraftReceiptItem, hri),
    ):
        result[model.__tablename__] = [_serialize(r) for r in sorted(rows, key=lambda r: r.id)]
    result["plating_receipt"] = _rows(db.query(PlatingReceipt).filter(PlatingReceipt.id.in_({r.plating_receipt_id for r in pri})))
    result["handcraft_receipt"] = _rows(db.query(HandcraftReceipt).filter(HandcraftReceipt.id.in_({r.handcraft_receipt_id for r in hri})))
    for model in (HandcraftPickingWeight, HandcraftPickingRecord):
        result[model.__tablename__] = _rows(db.query(model).filter(model.handcraft_order_id.in_(handcraft_ids)))
    result["vendor_receipt"] = _rows(db.query(VendorReceipt).filter(
        ((VendorReceipt.order_type == "plating") & VendorReceipt.order_id.in_(plating_ids))
        | ((VendorReceipt.order_type == "handcraft") & VendorReceipt.order_id.in_(handcraft_ids))
    ))
    return result


def plan_digest(plan: dict) -> str:
    payload = {k: v for k, v in plan.items() if k != "digest"}
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def build_archive_plan(db: Session, before: date) -> dict:
    if before > now_beijing().date():
        raise ValueError("截止日期不能晚于北京时间今天")
    cutoff = datetime.combine(before, time.min)
    orders = {
        kind: db.query(model).filter(
            model.created_at < cutoff,
            model.status.in_(("pending", "processing")),
            model.archived_at.is_(None),
        ).order_by(model.id).all()
        for kind, model in ORDER_MODELS.items()
    }
    plan = {
        "version": 1,
        "before": before.isoformat(),
        "timezone": "Asia/Shanghai",
        "batch_id": uuid4().hex,
        "snapshot": _snapshot(db, orders),
    }
    plan["digest"] = plan_digest(plan)
    return plan


def validate_plan(plan: dict):
    if plan.get("version") != 1 or plan.get("digest") != plan_digest(plan):
        raise ValueError("预览文件格式错误或已被修改，请重新预览")


def apply_archive_plan(db: Session, plan: dict, *, operator: str, reason: str) -> int:
    validate_plan(plan)
    if not operator.strip() or not reason.strip():
        raise ValueError("必须填写操作人和归档原因")
    current = build_archive_plan(db, date.fromisoformat(plan["before"]))
    if current["snapshot"] != plan["snapshot"]:
        raise ValueError("单据、数量或付款信息已变化，请重新预览后再执行")
    archived_at = now_beijing()
    count = 0
    for kind, model in ORDER_MODELS.items():
        for row in plan["snapshot"][kind]:
            order = db.get(model, row["id"])
            order.archived_at = archived_at
            order.archive_reason = reason.strip()
            order.archived_by = operator.strip()
            order.archive_batch_id = plan["batch_id"]
            count += 1
    db.flush()
    return count


def restore_archive_plan(db: Session, plan: dict) -> int:
    """Undo exactly this batch, only while business records remain unchanged."""
    validate_plan(plan)
    orders = {}
    for kind, model in ORDER_MODELS.items():
        ids = [r["id"] for r in plan["snapshot"][kind]]
        orders[kind] = db.query(model).filter(model.id.in_(ids)).order_by(model.id).all()
        if len(orders[kind]) != len(ids) or any(
            o.archive_batch_id != plan["batch_id"] or o.archived_at is None
            for o in orders[kind]
        ):
            raise ValueError("单据不再属于本次归档批次，拒绝恢复")
    if _snapshot(db, orders) != plan["snapshot"]:
        raise ValueError("归档后业务记录已变化，拒绝自动恢复，请先对账")
    count = 0
    for rows in orders.values():
        for order in rows:
            for field in ARCHIVE_FIELDS:
                setattr(order, field, None)
            count += 1
    db.flush()
    return count
