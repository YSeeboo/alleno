"""Receipt-scoped reconciliation, without changing source prices or part costs."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from models.part import Part
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.plating_receipt import PlatingReceipt, PlatingReceiptItem
from models.plating_reconciliation import PlatingReconciliation
from services.production_archive import require_unarchived

Q7 = Decimal("0.0000001")
MAX_AMOUNT = Decimal("99999999999.9999999")
DETAIL_HEADERS = ["回收时间", "配件", "电镀方式", "回收数量", "单位", "重量", "单价", "改价", "金额", "备注"]


def current_amount(item, reconciliation):
    override = reconciliation.override_price if reconciliation is not None else None
    if override is None:
        return item.amount
    amount = (Decimal(str(item.qty)) * Decimal(str(override))).quantize(Q7, rounding=ROUND_HALF_UP)
    if amount > MAX_AMOUNT:
        raise ValueError("对账金额超出允许范围，请检查数量和改价")
    return amount


def snapshot_receipt(db: Session, receipt, *, paid: bool):
    """Caller holds the receipt lock; snapshot and source status commit together."""
    items = db.query(PlatingReceiptItem).filter_by(plating_receipt_id=receipt.id).populate_existing().all()
    for item in items:
        record = db.get(PlatingReconciliation, item.id, populate_existing=True)
        if paid:
            if record is None:
                record = PlatingReconciliation(receipt_item_id=item.id)
                db.add(record)
            record.settled_amount = current_amount(item, record)
            record.settled_at = receipt.paid_at
        elif record is not None:
            record.settled_amount = None
            record.settled_at = None
    db.flush()


def update_price(db: Session, item_id: int, override: Decimal | None):
    # Same parent lock used by source status/item writes. Serialize even first-time
    # overrides, when there is no independent row to lock yet.
    receipt_id = db.query(PlatingReceiptItem.plating_receipt_id).filter_by(id=item_id).scalar()
    if receipt_id is None:
        raise ValueError("回收明细不存在")
    receipt = db.query(PlatingReceipt).filter_by(id=receipt_id).populate_existing().with_for_update().first()
    if receipt is None:
        raise ValueError("回收单不存在")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能改价")
    item = db.get(PlatingReceiptItem, item_id, populate_existing=True)
    if item is None:
        raise ValueError("回收明细不存在")
    order = db.query(PlatingOrder).join(PlatingOrderItem).filter(
        PlatingOrderItem.id == item.plating_order_item_id,
    ).first()
    require_unarchived(order)
    if override is not None:
        if not override.is_finite() or override < 0 or override > MAX_AMOUNT or override != override.quantize(Q7):
            raise ValueError("改价必须大于等于 0，最多 7 位小数")
    record = db.get(PlatingReconciliation, item_id, populate_existing=True)
    if record is None:
        record = PlatingReconciliation(receipt_item_id=item_id)
        db.add(record)
    record.override_price = override
    current_amount(item, record)  # Validate before a Numeric overflow reaches the DB.
    db.flush()


def _query(db, *, vendor_name=None, date_from=None, date_to=None, status=None):
    if date_from and date_to and date_from > date_to:
        raise ValueError("开始日期不能晚于结束日期")
    item, receipt, record = PlatingReceiptItem, PlatingReceipt, PlatingReconciliation
    live_amount = case(
        (record.override_price.is_not(None), func.round(item.qty * record.override_price, 7)),
        else_=item.amount,
    )
    amount = case(
        (receipt.status == "已付款", case(
            (record.settled_at.is_not(None), record.settled_amount), else_=item.amount,
        )), else_=live_amount,
    ).label("reconciliation_amount")
    query = db.query(item, receipt, record, PlatingOrderItem, PlatingOrder, Part, amount).join(
        receipt, item.plating_receipt_id == receipt.id,
    ).outerjoin(record, record.receipt_item_id == item.id).join(
        PlatingOrderItem, item.plating_order_item_id == PlatingOrderItem.id,
    ).join(PlatingOrder, PlatingOrderItem.plating_order_id == PlatingOrder.id).join(
        Part, item.part_id == Part.id,
    )
    if vendor_name:
        query = query.filter(receipt.vendor_name == vendor_name)
    if date_from:
        query = query.filter(receipt.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        # Inclusive end day, without converting indexed created_at to DATE.
        if date_to < date.max:
            query = query.filter(receipt.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
    if status:
        query = query.filter(receipt.status == status)
    return query, amount


def _row(row):
    item, receipt, record, poi, order, part, amount = row
    return dict(
        receipt_item_id=item.id, receipt_id=receipt.id, created_at=receipt.created_at,
        vendor_name=receipt.vendor_name, status=receipt.status, part_id=item.part_id,
        part_name=part.name, plating_order_id=poi.plating_order_id, plating_order_item_id=poi.id,
        plating_method=poi.plating_method, archived=order.archived_at is not None,
        qty=item.qty, unit=item.unit, weight=item.weight, weight_unit=item.weight_unit,
        price=item.price, override_price=record.override_price if record else None,
        amount=amount, note=item.note,
    )


def list_reconciliation(db: Session, *, skip=0, limit=30, **filters):
    query, amount = _query(db, **filters)
    due = func.coalesce(func.sum(amount), 0)
    paid = func.coalesce(func.sum(case((PlatingReceipt.status == "已付款", amount), else_=0)), 0)
    groups = query.with_entities(
        PlatingReceipt.vendor_name, due, paid,
        func.count(case((amount.is_(None), 1))),
        func.count(func.distinct(PlatingReceipt.id)), func.count(PlatingReceiptItem.id),
    ).group_by(PlatingReceipt.vendor_name).order_by(PlatingReceipt.vendor_name).all()
    merchants = [dict(vendor_name=g[0], due=g[1], paid=g[2], pending=g[1]-g[2],
                      unpriced_count=g[3], receipt_count=g[4], item_count=g[5]) for g in groups]
    totals = {key: sum((m[key] for m in merchants), Decimal(0) if key != "unpriced_count" else 0)
              for key in ("due", "paid", "pending", "unpriced_count")}
    rows = query.order_by(PlatingReceipt.created_at.desc(), PlatingReceipt.id.desc(), PlatingReceiptItem.id)
    if limit is not None:
        rows = rows.offset(skip).limit(limit)
    return dict(totals=totals, merchants=merchants, items=[_row(r) for r in rows.all()],
                total=sum(m["item_count"] for m in merchants))


def build_reconciliation_excel(db: Session, **filters):
    data = list_reconciliation(db, limit=None, **filters)
    wb = Workbook()
    detail = wb.active
    detail.title = "回收明细"
    detail.append(DETAIL_HEADERS)
    for row in data["items"]:
        weight = ""
        if row["weight"] is not None:
            weight_value = format(row["weight"], "f")
            if "." in weight_value:
                weight_value = weight_value.rstrip("0").rstrip(".")
            weight = f'{weight_value} {row["weight_unit"] or "g"}'
        detail.append([
            row["created_at"], row["part_name"], row["plating_method"], row["qty"], row["unit"],
            weight, row["price"], row["override_price"],
            row["amount"] if row["amount"] is not None else "待定价", row["note"],
        ])
    summary = wb.create_sheet("商家汇总")
    summary.append(["商家名称", "应付款", "已付款", "待付款", "待定价明细数"])
    for merchant in data["merchants"]:
        summary.append([merchant[k] for k in ("vendor_name", "due", "paid", "pending", "unpriced_count")])
    summary.append(["合计", *[data["totals"][k] for k in ("due", "paid", "pending", "unpriced_count")]])
    for ws in wb:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.font = Font(color="FFFFFF", bold=True)
            cell.fill = PatternFill("solid", fgColor="1E7A5A")
        for column in ws.columns:
            ws.column_dimensions[column[0].column_letter].width = 20
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                # User text is never interpreted as an Excel formula.
                if isinstance(cell.value, str):
                    cell.data_type = "s"
                if isinstance(cell.value, Decimal):
                    # Excel keeps the decimal separator in "0.#######" even
                    # when all optional digits are absent. Format each value
                    # with only its significant fractional digits instead.
                    fraction = format(cell.value, "f").partition(".")[2].rstrip("0")
                    cell.number_format = "0." + "0" * len(fraction) if fraction else "0"
        if ws == detail:
            for cell in ws["A"][1:]:
                cell.number_format = "yyyy-mm-dd hh:mm:ss"
            for cell in ws["H"][1:]:
                cell.font = Font(color="FFFF0000")
    wb.active = 0
    output = BytesIO()
    wb.save(output)
    return output.getvalue()
