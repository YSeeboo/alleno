from typing import Optional, List
from decimal import Decimal

from sqlalchemy.orm import Session

from models.production_loss import ProductionLoss
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from models.inventory_log import InventoryLog
from services.plating_receipt import _check_plating_order_completion
from services.handcraft_receipt import _check_handcraft_order_completion
from time_utils import now_beijing


def confirm_plating_loss(
    db: Session,
    order_id: str,
    item_id: int,
    loss_qty: float,
    deduct_amount: Optional[float] = None,
    reason: Optional[str] = None,
    note: Optional[str] = None,
) -> ProductionLoss:
    po = db.query(PlatingOrder).filter_by(id=order_id).first()
    if not po:
        raise ValueError(f"电镀单 {order_id} 不存在")

    poi = db.query(PlatingOrderItem).filter_by(id=item_id, plating_order_id=order_id).first()
    if not poi:
        raise ValueError(f"电镀单项 {item_id} 不存在")

    gap = float(poi.qty) - float(poi.received_qty or 0)
    if loss_qty <= 0:
        raise ValueError("损耗数量必须大于 0")
    if loss_qty > gap:
        raise ValueError(f"损耗数量 {loss_qty} 超过差额 {gap}")

    # Create loss record
    loss = ProductionLoss(
        order_type="plating",
        order_id=order_id,
        item_id=item_id,
        item_type="plating_item",
        part_id=poi.part_id,
        loss_qty=loss_qty,
        deduct_amount=Decimal(str(deduct_amount)) if deduct_amount else None,
        reason=reason,
        note=note,
    )
    db.add(loss)

    # Write inventory log (change_qty=0 for audit)
    log = InventoryLog(
        item_type="part",
        item_id=poi.part_id,
        change_qty=0,
        reason="电镀损耗",
        note=f"损耗 {loss_qty}，电镀单 {order_id}" + (f"，原因：{reason}" if reason else ""),
    )
    db.add(log)

    # Increment received_qty to trigger existing status logic
    poi.received_qty = Decimal(str(float(poi.received_qty or 0) + loss_qty))
    if float(poi.received_qty) >= float(poi.qty):
        poi.status = "已收回"
    db.flush()

    # Check order completion
    _check_plating_order_completion(db, order_id)
    db.flush()

    return loss


def confirm_handcraft_loss(
    db: Session,
    order_id: str,
    item_id: int,
    item_type: str,
    loss_qty: float,
    deduct_amount: Optional[float] = None,
    reason: Optional[str] = None,
    note: Optional[str] = None,
) -> ProductionLoss:
    hc = db.query(HandcraftOrder).filter_by(id=order_id).first()
    if not hc:
        raise ValueError(f"手工单 {order_id} 不存在")

    if item_type == "part":
        item = db.query(HandcraftPartItem).filter_by(id=item_id, handcraft_order_id=order_id).first()
        if not item:
            raise ValueError(f"手工单配件项 {item_id} 不存在")
        loss_item_type = "handcraft_part"
        part_id = item.part_id
        jewelry_id = None
        inv_item_type = "part"
        inv_item_id = item.part_id
    elif item_type == "jewelry":
        item = db.query(HandcraftJewelryItem).filter_by(id=item_id, handcraft_order_id=order_id).first()
        if not item:
            raise ValueError(f"手工单产出项 {item_id} 不存在")
        loss_item_type = "handcraft_jewelry"
        if item.part_id and not item.jewelry_id:
            # Part output item
            part_id = item.part_id
            jewelry_id = None
            inv_item_type = "part"
            inv_item_id = item.part_id
        else:
            part_id = None
            jewelry_id = item.jewelry_id
            inv_item_type = "jewelry"
            inv_item_id = item.jewelry_id
    else:
        raise ValueError(f"无效的 item_type: {item_type}")

    gap = float(item.qty) - float(item.received_qty or 0)
    if loss_qty <= 0:
        raise ValueError("损耗数量必须大于 0")
    if item_type == "jewelry" and loss_qty != int(loss_qty):
        raise ValueError("产出项损耗数量必须为整数")
    if loss_qty > gap:
        raise ValueError(f"损耗数量 {loss_qty} 超过差额 {gap}")

    # Create loss record
    loss = ProductionLoss(
        order_type="handcraft",
        order_id=order_id,
        item_id=item_id,
        item_type=loss_item_type,
        part_id=part_id,
        jewelry_id=jewelry_id,
        loss_qty=loss_qty,
        deduct_amount=Decimal(str(deduct_amount)) if deduct_amount else None,
        reason=reason,
        note=note,
    )
    db.add(loss)

    # Write inventory log
    log = InventoryLog(
        item_type=inv_item_type,
        item_id=inv_item_id,
        change_qty=0,
        reason="手工损耗",
        note=f"损耗 {loss_qty}，手工单 {order_id}" + (f"，原因：{reason}" if reason else ""),
    )
    db.add(log)

    # Increment received_qty
    if item_type == "jewelry":
        item.received_qty = int(item.received_qty or 0) + int(loss_qty)
    else:
        item.received_qty = Decimal(str(float(item.received_qty or 0) + loss_qty))

    if float(item.received_qty) >= float(item.qty):
        item.status = "已收回"
    db.flush()

    # Check order completion
    _check_handcraft_order_completion(db, order_id)
    db.flush()

    return loss


def get_losses(
    db: Session,
    order_type: Optional[str] = None,
    order_id: Optional[str] = None,
) -> List[ProductionLoss]:
    q = db.query(ProductionLoss)
    if order_type:
        q = q.filter(ProductionLoss.order_type == order_type)
    if order_id:
        q = q.filter(ProductionLoss.order_id == order_id)
    return q.order_by(ProductionLoss.created_at.desc()).all()


def get_item_loss(db: Session, item_id: int, item_type: str) -> Optional[ProductionLoss]:
    """Get loss record for a specific item, if any."""
    return (
        db.query(ProductionLoss)
        .filter_by(item_id=item_id, item_type=item_type)
        .first()
    )
