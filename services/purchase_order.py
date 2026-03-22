from typing import Optional

from sqlalchemy.orm import Session

from models.part import Part
from models.purchase_order import PurchaseOrder, PurchaseOrderItem
from services._helpers import _next_id
from services.inventory import add_stock, deduct_stock
from time_utils import now_beijing


_VALID_STATUSES = {"未付款", "已付款"}


def _require_part(db: Session, part_id: str) -> None:
    if db.get(Part, part_id) is None:
        raise ValueError(f"Part not found: {part_id}")


def _normalize_delivery_images(delivery_images: Optional[list]) -> list[str]:
    cleaned = [str(item).strip() for item in (delivery_images or []) if str(item).strip()]
    if len(cleaned) > 4:
        raise ValueError("图片最多上传 4 张")
    return cleaned


def _recalc_total(db: Session, order: PurchaseOrder) -> None:
    items = get_purchase_items(db, order.id)
    total = sum(float(item.amount or 0) for item in items)
    order.total_amount = total


def create_purchase_order(
    db: Session,
    vendor_name: str,
    items: list,
    status: str = "未付款",
    note: str = None,
) -> PurchaseOrder:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Valid values: {', '.join(sorted(_VALID_STATUSES))}")

    for item in items:
        _require_part(db, item["part_id"])

    order_id = _next_id(db, PurchaseOrder, "CG")
    order = PurchaseOrder(
        id=order_id,
        vendor_name=vendor_name,
        status=status,
        note=note,
    )
    if status == "已付款":
        order.paid_at = now_beijing()
    db.add(order)
    db.flush()

    total = 0.0
    for item in items:
        price = round(item["price"], 3) if item.get("price") is not None else None
        qty = item["qty"]
        amount = round(qty * price, 3) if price is not None else None
        if amount is not None:
            total += amount

        db.add(PurchaseOrderItem(
            purchase_order_id=order_id,
            part_id=item["part_id"],
            qty=qty,
            unit=item.get("unit", "个"),
            price=price,
            amount=amount,
            note=item.get("note"),
        ))
        add_stock(db, "part", item["part_id"], qty, "采购入库")

    order.total_amount = total
    db.flush()
    return order


def list_purchase_orders(db: Session, vendor_name: str = None) -> list:
    q = db.query(PurchaseOrder)
    if vendor_name is not None:
        q = q.filter(PurchaseOrder.vendor_name == vendor_name)
    return q.order_by(PurchaseOrder.created_at.desc()).all()


def get_purchase_order(db: Session, order_id: str) -> Optional[PurchaseOrder]:
    return db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()


def get_purchase_items(db: Session, order_id: str) -> list:
    return (
        db.query(PurchaseOrderItem)
        .filter(PurchaseOrderItem.purchase_order_id == order_id)
        .order_by(PurchaseOrderItem.id.asc())
        .all()
    )


def delete_purchase_order(db: Session, order_id: str) -> None:
    order = get_purchase_order(db, order_id)
    if order is None:
        raise ValueError(f"PurchaseOrder not found: {order_id}")
    if order.status == "已付款":
        raise ValueError("已付款的采购单不能删除")

    items = get_purchase_items(db, order_id)
    for item in items:
        deduct_stock(db, "part", item.part_id, float(item.qty), "采购单删除")

    db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.purchase_order_id == order_id
    ).delete(synchronize_session=False)
    db.flush()
    db.delete(order)
    db.flush()


def update_purchase_order_status(db: Session, order_id: str, status: str) -> PurchaseOrder:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Valid values: {', '.join(sorted(_VALID_STATUSES))}")
    order = get_purchase_order(db, order_id)
    if order is None:
        raise ValueError(f"PurchaseOrder not found: {order_id}")
    if order.status == status:
        raise ValueError(f"采购单已经是「{status}」状态")
    if status == "已付款":
        order.paid_at = now_beijing()
    else:
        order.paid_at = None
    order.status = status
    db.flush()
    return order


def update_purchase_order_images(db: Session, order_id: str, delivery_images: Optional[list]) -> PurchaseOrder:
    order = get_purchase_order(db, order_id)
    if order is None:
        raise ValueError(f"PurchaseOrder not found: {order_id}")
    order.delivery_images = _normalize_delivery_images(delivery_images)
    db.flush()
    return order


def update_purchase_item(db: Session, order_id: str, item_id: int, data: dict) -> PurchaseOrderItem:
    order = get_purchase_order(db, order_id)
    if order is None:
        raise ValueError(f"PurchaseOrder not found: {order_id}")
    if order.status == "已付款":
        raise ValueError("已付款的采购单不能修改明细")

    item = db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.id == item_id,
        PurchaseOrderItem.purchase_order_id == order_id,
    ).first()
    if item is None:
        raise ValueError(f"PurchaseOrderItem {item_id} not found in order {order_id}")

    old_qty = float(item.qty)

    for field in ("unit", "note"):
        if field in data:
            setattr(item, field, data[field])
    if "price" in data:
        item.price = round(data["price"], 3) if data["price"] is not None else None
    if "qty" in data and data["qty"] is not None:
        item.qty = data["qty"]

    new_qty = float(item.qty)
    if new_qty != old_qty:
        diff = new_qty - old_qty
        if diff > 0:
            add_stock(db, "part", item.part_id, diff, "采购明细修改")
        else:
            deduct_stock(db, "part", item.part_id, -diff, "采购明细修改")

    # Recalc amount
    if item.price is not None:
        item.amount = round(float(item.qty) * float(item.price), 3)
    else:
        item.amount = None

    _recalc_total(db, order)
    db.flush()
    return item


def delete_purchase_item(db: Session, order_id: str, item_id: int) -> None:
    order = get_purchase_order(db, order_id)
    if order is None:
        raise ValueError(f"PurchaseOrder not found: {order_id}")
    if order.status == "已付款":
        raise ValueError("已付款的采购单不能删除明细")

    item = db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.id == item_id,
        PurchaseOrderItem.purchase_order_id == order_id,
    ).first()
    if item is None:
        raise ValueError(f"PurchaseOrderItem {item_id} not found in order {order_id}")

    remaining = db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.purchase_order_id == order_id,
        PurchaseOrderItem.id != item_id,
    ).count()
    if remaining == 0:
        raise ValueError("不能删除最后一条明细，请直接删除整个采购单")

    deduct_stock(db, "part", item.part_id, float(item.qty), "采购明细删除")
    db.delete(item)
    db.flush()
    _recalc_total(db, order)
    db.flush()


def get_vendor_names(db: Session) -> list[str]:
    rows = db.query(PurchaseOrder.vendor_name).distinct().all()
    return [row[0] for row in rows]
