"""Create explicit output(s) and their exact-line plans in one transaction.

Materials are explicit planned inputs, not an issue/receipt or a BOM snapshot.
Lock order follows production_allocation: customer order -> production parent.
"""
import hashlib
import json
from decimal import Decimal

from sqlalchemy import text

from models.handcraft_order import HandcraftJewelryItem
from models.order import OrderItem
from models.part import Part
from models.production_allocation import ProductionAllocation
from models.production_creation import ProductionCreation
from services.handcraft import create_handcraft_order
from services.supplier import ensure_supplier
from services.production_allocation import (
    EDITABLE_ORDERS, _product, legacy_demand_claim, lock_order,
    product_key, replace_order_source, _revision,
)


def create_order_handcraft(db, order_id, data):
    return _create_order_handcraft(db, order_id, data, batch=False)


def create_order_handcraft_batch(db, order_id, data):
    return _create_order_handcraft(db, order_id, data, batch=True)


def _validate_output(db, order_id, entry, output):
    line = db.query(OrderItem).filter_by(order_id=order_id, id=entry["order_item_id"]).first()
    if line is None:
        raise ValueError("只能为当前订单的具体明细安排制作")
    if legacy_demand_claim(db, line):
        raise ValueError("该商品存在旧关联/批次，请先核对旧归属")
    if product_key(line) != (("jewelry", output["jewelry_id"]) if output.get("jewelry_id") else ("part", output.get("part_id"))):
        raise ValueError("目标产出与所选订单明细不匹配")
    product = _product(db, product_key(line))
    if product is None or not product.unit or (product.unit or "").strip() != (output.get("unit") or "").strip():
        raise ValueError("目标产出单位与商品不一致，请核对；不自动换算")
    if output.get("customer_name") is not None:
        raise ValueError("按明细安排不能同时手填客户归属")
    qty, planned = Decimal(str(entry["allocated_quantity"])), Decimal(str(output["qty"]))
    used = sum((row.quantity for row in db.query(ProductionAllocation).filter_by(order_item_id=line.id)), Decimal(0))
    if (not qty.is_finite() or not planned.is_finite() or qty <= 0 or qty >= 1000000000
            or qty != qty.to_integral_value() or planned != planned.to_integral_value()
            or planned >= 1000000000 or qty > planned or used + qty > line.quantity):
        raise ValueError("本单安排数量超过目标产出或该明细剩余生产需求，请刷新核对")
    return line, qty, planned


def _create_order_handcraft(db, order_id, data, *, batch):
    order = lock_order(db, order_id)
    key = data["request_key"]
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
               {"key": f"allen-production-create:{key}"})
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    old = db.get(ProductionCreation, key)
    if old is not None:
        if old.order_id != order_id or old.payload_hash != digest:
            raise ValueError("此制作请求已用于不同内容，请重新核对，不能重复创建")
        return old.result
    if order.status not in EDITABLE_ORDERS:
        raise ValueError("仅待生产或生产中的订单可安排制作")
    outputs = data["jewelries"]
    entries = data["allocations"] if batch else [data]
    if not batch and len(outputs) != 1:
        raise ValueError("按明细安排制作必须且只能有一条目标产出")
    if not entries or len(entries) > 100 or len(entries) != len(outputs) or len({r["order_item_id"] for r in entries}) != len(entries):
        raise ValueError("每条订单明细必须对应一条独立产出，不能重复选择明细")
    validated = [_validate_output(db, order_id, entry, output) for entry, output in zip(entries, outputs)]
    if not data["parts"]:
        raise ValueError("请至少填写一条计划投入材料")
    for material in data["parts"]:
        part = db.get(Part, material["part_id"])
        amount = Decimal(str(material["qty"]))
        if not amount.is_finite() or amount <= 0 or amount >= 1000000 or amount != amount.quantize(Decimal("0.0001")):
            raise ValueError("材料数量必须为小于一百万、最多四位小数的正数")
        if part is None or not part.unit or part.unit != material.get("unit"):
            raise ValueError("计划材料不存在或单位不一致，请核对；不自动换算")
    # A failed request must not leave a half-created output, even for service callers.
    with db.begin_nested():
        parent = create_handcraft_order(db, data["supplier_name"], data["parts"], outputs,
                                        note=data.get("note"), created_at=data.get("created_at"),
                                        append_to_order_id=data.get("append_to_order_id"))
        # New output rows are always appended; existing row quantities/identities
        # are never folded together, including identical products on the same task.
        # The parent is locked by create_handcraft_order. Inserts preserve input
        # order; no concurrent append can interleave these newly appended rows.
        output_rows = list(reversed(db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=parent.id)
                                    .order_by(HandcraftJewelryItem.id.desc()).limit(len(outputs)).all()))
        results = []
        for output_row, (line, qty, planned) in zip(output_rows, validated):
            replace_order_source(db, order_id, "handcraft", output_row.id,
                                 _revision(output_row, parent, []),
                                 [{"order_item_id": line.id, "quantity": qty}])
            results.append({"source_item_id": output_row.id, "order_item_id": line.id,
                            "allocated_quantity": int(qty), "public_quantity": int(planned - qty)})
        ensure_supplier(db, parent.supplier_name, "handcraft")
        result = {"production_order_id": parent.id, "appended": bool(data.get("append_to_order_id")),
                  **({"rows": results} if batch else results[0])}
        db.add(ProductionCreation(request_key=key, order_id=order_id, payload_hash=digest, result=result))
        db.flush()
    return result
