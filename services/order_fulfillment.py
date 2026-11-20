"""Explicit customer shipments and stock reservations, independent of production.

Lock order: customer order -> shipment -> inventory advisory locks (sorted by type/id).
All inventory deductions protect reservations through services.inventory.
"""
from collections import defaultdict
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, text
from models.order import Order, OrderItem
from models.part import Part
from models.jewelry import Jewelry
from models.inventory_log import InventoryLog
from models.order_fulfillment import OrderFulfillment, StockReservation, CustomerShipment, CustomerShipmentItem
from models.production_allocation import ProductionAllocation
from services.production_allocation import lock_order, product_key


ZERO = Decimal(0)


def lock_product(db, kind, product_id):
    model = {"part": Part, "jewelry": Jewelry}.get(kind)
    if model is None:
        raise ValueError("不支持的库存商品类型")
    # Legacy inventory permits item IDs without a catalog row. A transaction
    # advisory lock protects those balances too; never fabricate catalog data.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
               {"key": f"allen-stock:{kind}:{product_id}"})
    return db.get(model, product_id)


def stock_balance(db, kind, product_id):
    stock = db.query(func.sum(InventoryLog.change_qty)).filter_by(item_type=kind, item_id=product_id).scalar() or ZERO
    query = db.query(func.sum(StockReservation.quantity)).join(OrderItem, OrderItem.id == StockReservation.order_item_id)
    query = query.filter(OrderItem.part_id == product_id) if kind == "part" else query.filter(OrderItem.jewelry_id == product_id)
    reserved = query.scalar() or ZERO
    return {"stock": stock, "reserved_total": reserved, "public_available": max(ZERO, stock - reserved)}


def shipped_quantities(db, order_id):
    return dict(db.query(CustomerShipmentItem.order_item_id, func.sum(CustomerShipmentItem.quantity))
                .join(CustomerShipment, CustomerShipment.id == CustomerShipmentItem.shipment_id)
                .filter(CustomerShipment.order_id == order_id, CustomerShipment.status == "confirmed")
                .group_by(CustomerShipmentItem.order_item_id).all())


def _editable(db, order_id):
    order = lock_order(db, order_id)
    if order.status not in {"待生产", "生产中"}:
        raise ValueError("当前订单只读，不允许预留或新建出货")
    if db.get(OrderFulfillment, order_id) is None:
        raise ValueError("请先核对历史出货并启用逐笔履约，不能根据旧状态推算数量")
    return order


def activate(db, order_id, confirmed):
    order = lock_order(db, order_id)
    if db.get(OrderFulfillment, order_id):
        return order_summary(db, order_id)
    if order.status not in {"待生产", "生产中"}:
        raise ValueError("历史完成或取消订单不能直接启用；需单独核对历史")
    if not confirmed:
        raise ValueError("必须核实本单尚无历史实发；已有历史出货的订单须先核对迁移")
    db.add(OrderFulfillment(order_id=order_id))
    db.flush()
    return order_summary(db, order_id)


def order_summary(db, order_id):
    order = db.get(Order, order_id)
    if order is None:
        raise ValueError("订单不存在")
    managed = db.get(OrderFulfillment, order_id) is not None
    shipped = shipped_quantities(db, order_id)
    lines = []
    balances = {}
    for line in db.query(OrderItem).filter_by(order_id=order_id).order_by(OrderItem.id).all():
        key = product_key(line)
        kind, pid = key
        product = db.get(Part if kind == "part" else Jewelry, pid)
        if key not in balances:
            balances[key] = stock_balance(db, *key)
        reservation = db.get(StockReservation, line.id)
        reserved = reservation.quantity if reservation else ZERO
        sent = shipped.get(line.id, ZERO)
        planned = db.query(func.sum(ProductionAllocation.quantity)).filter_by(order_item_id=line.id).scalar() or ZERO
        lines.append({"id": line.id, "product_type": kind, "product_id": pid,
                      "product_name": product.name if product else pid, "image": product.image if product else None,
                      "unit": product.unit if product else None, "customer_code": line.customer_code,
                      "quantity": line.quantity, "planned": planned, "reserved": reserved,
                      "unit_price": line.unit_price, "remarks": line.remarks,
                      "shipped": sent if managed else None,
                      "remaining": max(ZERO, Decimal(line.quantity) - sent) if managed else None,
                      "gap": max(ZERO, Decimal(line.quantity) - sent - reserved) if managed else None,
                      **balances[key]})
    completed = sum(1 for line in lines if managed and line["shipped"] >= line["quantity"])
    percent = (sum(min(Decimal(1), line["shipped"] / line["quantity"]) for line in lines) / len(lines) * 100) if managed and lines else None
    return {"order_id": order.id, "customer_name": order.customer_name, "status": order.status,
            "managed": managed, "editable": managed and order.status in {"待生产", "生产中"},
            "completed_items": completed if managed else None, "total_items": len(lines),
            "percent": round(percent, 1) if percent is not None else None, "lines": lines}


def batch_summaries(db, order_ids):
    return [order_summary(db, order_id) for order_id in dict.fromkeys(order_ids) if db.get(Order, order_id)]


def reserve(db, order_id, line_id, quantity, expected_quantity):
    _editable(db, order_id)
    line = db.query(OrderItem).filter_by(id=line_id, order_id=order_id).first()
    if line is None:
        raise ValueError("只能调整当前订单明细")
    lock_product(db, *product_key(line))
    row = db.get(StockReservation, line_id)
    current = row.quantity if row else ZERO
    qty = Decimal(str(quantity))
    if current != Decimal(str(expected_quantity)):
        raise ValueError("预留已变化，请刷新后重试")
    if not qty.is_finite() or qty < 0 or qty != qty.to_integral_value():
        raise ValueError("订单商品预留必须为非负整数")
    remaining = Decimal(line.quantity) - shipped_quantities(db, order_id).get(line_id, ZERO)
    if qty > remaining:
        raise ValueError("预留超过当前明细剩余待发数量")
    balance = stock_balance(db, *product_key(line))
    if qty > current and qty - current > balance["public_available"]:
        raise ValueError("公共可用库存不足，不能挪用其他明细或客户的预留")
    if row:
        row.quantity = qty
    else:
        db.add(StockReservation(order_item_id=line_id, quantity=qty))
    db.flush()
    return order_summary(db, order_id)


def _validated_lines(db, order_id, values):
    if not values:
        raise ValueError("请选择实际出货明细")
    lines = {line.id: line for line in db.query(OrderItem).filter_by(order_id=order_id).all()}
    sent = shipped_quantities(db, order_id)
    checked = []
    seen = set()
    for entry in values:
        line_id, qty = entry["order_item_id"], Decimal(str(entry["quantity"]))
        if line_id in seen or line_id not in lines:
            raise ValueError("出货明细重复或不属于当前订单")
        seen.add(line_id)
        line = lines[line_id]
        if not qty.is_finite() or qty <= 0 or qty != qty.to_integral_value():
            raise ValueError("实际出货必须为正整数")
        if qty + sent.get(line_id, ZERO) > line.quantity:
            raise ValueError("出货数量超过该明细剩余待发数量")
        checked.append((line, qty))
    return checked


def create_shipment(db, data):
    lock_order(db, data["order_id"])
    # Serialize a request key even if competing requests name different orders.
    # An exact retry must also work after the original shipment completed its order.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
               {"key": f"allen-shipment-request:{data['request_key']}"})
    existing = db.query(CustomerShipment).filter_by(request_key=data["request_key"]).first()
    if existing:
        old = shipment_view(db, existing.id)
        incoming = sorted((v["order_item_id"], Decimal(str(v["quantity"]))) for v in data["lines"])
        actual = sorted((v["order_item_id"], v["quantity"]) for v in old["lines"])
        if existing.order_id != data["order_id"] or incoming != actual or (existing.note or "") != data.get("note", "") or (existing.tracking or "") != data.get("tracking", ""):
            raise ValueError("重复提交标识已用于不同的出货内容，请重新核对")
        return old
    _editable(db, data["order_id"])
    checked = _validated_lines(db, data["order_id"], data["lines"])
    shipment = CustomerShipment(id=f"SH-{uuid4().hex[:16].upper()}", order_id=data["order_id"],
                                request_key=data["request_key"], tracking=data.get("tracking"), note=data.get("note"))
    db.add(shipment)
    db.flush()
    for line, qty in checked:
        db.add(CustomerShipmentItem(shipment_id=shipment.id, order_item_id=line.id, quantity=qty))
    db.flush()
    return shipment_view(db, shipment.id)


def shipment_view(db, shipment_id):
    shipment = db.get(CustomerShipment, shipment_id)
    if shipment is None:
        raise ValueError("出货单不存在")
    order = db.get(Order, shipment.order_id)
    entries = []
    for item in db.query(CustomerShipmentItem).filter_by(shipment_id=shipment.id).order_by(CustomerShipmentItem.id).all():
        line = db.get(OrderItem, item.order_item_id)
        kind, pid = product_key(line)
        product = db.get(Part if kind == "part" else Jewelry, pid)
        entries.append({"order_item_id": line.id, "quantity": item.quantity, "product_id": pid,
                        "product_type": kind, "product_name": product.name, "unit": product.unit,
                        "image": product.image, "customer_code": line.customer_code, "inventory_log_id": item.inventory_log_id})
    return {"id": shipment.id, "order_id": shipment.order_id, "customer_name": order.customer_name,
            "status": shipment.status, "tracking": shipment.tracking, "note": shipment.note,
            "created_at": shipment.created_at, "confirmed_at": shipment.confirmed_at, "lines": entries}


def list_shipments(db, order_id=None):
    query = db.query(CustomerShipment)
    if order_id:
        query = query.filter_by(order_id=order_id)
    return [shipment_view(db, row.id) for row in query.order_by(CustomerShipment.created_at.desc()).all()]


def confirm_shipment(db, shipment_id, checked):
    source = db.get(CustomerShipment, shipment_id)
    if source is None:
        raise ValueError("出货单不存在")
    order = lock_order(db, source.order_id)
    shipment = db.query(CustomerShipment).filter_by(id=shipment_id).populate_existing().with_for_update().one()
    if shipment.status == "confirmed":
        return shipment_view(db, shipment_id)
    if shipment.status != "draft":
        raise ValueError("已作废草稿不可确认")
    if not checked:
        raise ValueError("请先核对实际货物与数量")
    _editable(db, order.id)
    rows = db.query(CustomerShipmentItem).filter_by(shipment_id=shipment_id).order_by(CustomerShipmentItem.id).all()
    validated = _validated_lines(db, order.id, [{"order_item_id": row.order_item_id, "quantity": row.quantity} for row in rows])
    for key in sorted({product_key(line) for line, _ in validated}):
        lock_product(db, *key)
    public_needs = defaultdict(lambda: ZERO)
    release = []
    for line, qty in validated:
        row = db.get(StockReservation, line.id)
        own = min(qty, row.quantity if row else ZERO)
        public_needs[product_key(line)] += qty - own
        release.append((row, own))
    # Whole-request validation before touching ANY reservation, stock or status.
    for key, qty in public_needs.items():
        if qty > stock_balance(db, *key)["public_available"]:
            raise ValueError(f"{key[1]} 公共可用库存不足，其他明细预留不可挪用；请先登记真实入库")
    for row, qty in release:
        if row:
            row.quantity -= qty
    db.flush()
    from services.inventory import deduct_stock
    for (line, qty), row in zip(validated, rows):
        log = deduct_stock(db, *product_key(line), qty, "客户逐笔出货", f"{shipment.id} / {order.id} / 明细 #{line.id}")
        row.inventory_log_id = log.id
    from time_utils import now_beijing
    shipment.status = "confirmed"
    shipment.confirmed_at = now_beijing()
    db.flush()
    summary = order_summary(db, order.id)
    if summary["total_items"] and summary["completed_items"] == summary["total_items"]:
        # Do NOT call legacy update_order_status: it deducts stock a second time.
        order.status = "已完成"
        from services.order_cost_snapshot import generate_cost_snapshot
        generate_cost_snapshot(db, order.id, allow_missing_bom=True)
    db.flush()
    return shipment_view(db, shipment_id)


def void_shipment(db, shipment_id):
    source = db.get(CustomerShipment, shipment_id)
    if source is None:
        raise ValueError("出货单不存在")
    lock_order(db, source.order_id)
    shipment = db.query(CustomerShipment).filter_by(id=shipment_id).populate_existing().with_for_update().one()
    if shipment.status == "confirmed":
        raise ValueError("已确认出货不能直接作废回库，实际退货需独立凭据")
    shipment.status = "void"
    db.flush()
    return shipment_view(db, shipment_id)


def guard_fulfillment_change(db, order_id, *, line_id=None, quantity=None, deleting=False, status=None):
    """Keep legacy editors, but never let them rewrite verified shipment history."""
    if db.get(OrderFulfillment, order_id) is None:
        return
    if status is not None:
        order = db.get(Order, order_id)
        if status == order.status:
            return
        if status == "已完成" or order.status == "已完成":
            raise ValueError("逐笔履约订单仅在全部明细足量出货后完成，不能通过改状态扣库或回库")
        if status == "已取消":
            if db.query(CustomerShipment.id).filter_by(order_id=order_id, status="confirmed").first():
                raise ValueError("已有真实出货，请先处理退货，不能直接取消订单")
            reserved = db.query(StockReservation).join(OrderItem).filter(OrderItem.order_id == order_id, StockReservation.quantity > 0).first()
            if reserved:
                raise ValueError("请先取消本单库存预留")
    query = db.query(OrderItem).filter_by(order_id=order_id)
    if line_id is not None:
        query = query.filter_by(id=line_id)
    for line in query.all():
        row = db.get(StockReservation, line.id)
        sent = shipped_quantities(db, order_id).get(line.id, ZERO)
        reserved = row.quantity if row else ZERO
        referenced = db.query(CustomerShipmentItem.id).filter_by(order_item_id=line.id).first()
        if deleting and (row is not None or referenced):
            raise ValueError("存在库存预留记录或出货凭据，不能删除订单明细")
        if quantity is not None and Decimal(str(quantity)) < sent + reserved:
            raise ValueError("订购数量不能小于已出货与待发预留之和")
        if quantity is not None:
            drafts = db.query(CustomerShipmentItem.quantity).join(CustomerShipment).filter(
                CustomerShipmentItem.order_item_id == line.id, CustomerShipment.status == "draft").all()
            if any(Decimal(str(quantity)) < sent + qty for (qty,) in drafts):
                raise ValueError("订购数量不能小于已出货与现存出货草稿数量之和，请先核对草稿")
    if deleting and line_id is None:
        raise ValueError("已启用逐笔履约的订单请保留记录，不允许硬删除")
