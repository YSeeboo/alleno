"""Read-only output overview. Aggregate physical receipts/losses BEFORE joining
sources; clamp each source's remainder BEFORE grouping; paginate whole groups.
No BOM inference, counter-derived receipts, unit conversion or history writes.
"""
from sqlalchemy import Date, and_, case, cast, func, literal, or_

from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
from models.handcraft_receipt import HandcraftReceipt, HandcraftReceiptItem
from models.jewelry import Jewelry
from models.part import Part
from models.production_loss import ProductionLoss
from services.handcraft_summary import _pattern, _physical
from services.production_archive import filter_archive


def _source_query(db, *, supplier_names=(), output_keys=(), date_from=None,
                  date_to=None, progress="all", archive="active"):
    item, order = HandcraftJewelryItem, HandcraftOrder
    receipts = db.query(
        HandcraftReceiptItem.handcraft_jewelry_item_id.label("item_id"),
        func.sum(HandcraftReceiptItem.qty).label("qty"),
        func.count().label("count"),
    ).join(HandcraftReceipt, HandcraftReceipt.id == HandcraftReceiptItem.handcraft_receipt_id).filter(
        _physical()).group_by(HandcraftReceiptItem.handcraft_jewelry_item_id).subquery()
    losses = db.query(
        ProductionLoss.item_id, ProductionLoss.order_id,
        func.sum(ProductionLoss.loss_qty).label("qty"),
    ).filter(ProductionLoss.order_type == "handcraft", ProductionLoss.item_type == "handcraft_jewelry").group_by(
        ProductionLoss.item_id, ProductionLoss.order_id).subquery()
    actual = func.coalesce(receipts.c.qty, 0)
    loss = func.coalesce(losses.c.qty, 0)
    gap = func.greatest(item.qty - actual - loss, 0)
    output_type = case((item.jewelry_id.is_not(None), literal("jewelry")), else_=literal("part"))
    output_id = func.coalesce(item.jewelry_id, item.part_id)
    output_key = output_type + literal(":") + output_id
    dispatch_date = cast(func.coalesce(item.dispatched_at, order.created_at), Date)
    q = db.query(
        item.id.label("handcraft_jewelry_item_id"), order.id.label("handcraft_order_id"),
        order.supplier_name, order.archived_at, item.note, order.note.label("document_note"),
        dispatch_date.label("dispatch_date"),
        case((item.dispatched_at.is_not(None), "actual"), else_="document_reference").label("dispatch_date_basis"),
        case((item.dispatched_at.is_(None), 1), else_=0).label("reference_date_count"),
        func.coalesce(item.unit, "").label("unit"), item.qty.label("expected_qty"),
        actual.label("actual_received_qty"), loss.label("loss_total_qty"), gap.label("unreceived_qty"),
        func.coalesce(receipts.c.count, 0).label("receipt_count"),
        output_key.label("output_key"), output_id.label("output_id"), output_type.label("output_type"),
        case((item.jewelry_id.is_not(None), Jewelry.name), else_=Part.name).label("output_name"),
        case((item.jewelry_id.is_not(None), Jewelry.image), else_=Part.image).label("output_image"),
    ).select_from(item).join(order, order.id == item.handcraft_order_id).outerjoin(
        receipts, receipts.c.item_id == item.id).outerjoin(
        losses, and_(losses.c.item_id == item.id, losses.c.order_id == order.id)).outerjoin(
        Jewelry, Jewelry.id == item.jewelry_id).outerjoin(Part, Part.id == item.part_id).filter(
        order.status.in_(["processing", "completed"]), output_id.is_not(None))
    q = filter_archive(q, order, archive)
    if supplier_names:
        q = q.filter(order.supplier_name.in_(supplier_names))
    if output_keys:
        q = q.filter(output_key.in_(output_keys))
    if date_from:
        q = q.filter(dispatch_date >= date_from)
    if date_to:
        q = q.filter(dispatch_date <= date_to)
    if progress == "unreceived":
        q = q.filter(gap > 0, actual == 0)
    elif progress == "partial":
        q = q.filter(gap > 0, actual > 0)
    elif progress == "settled":
        q = q.filter(gap == 0)
    return q


QUANTITIES = ("expected_qty", "actual_received_qty", "loss_total_qty", "unreceived_qty")


def output_overview(db, *, view="merchant", skip=0, limit=10, **filters):
    sources = _source_query(db, **filters).cte("output_sources")
    c = sources.c
    group_key = c.supplier_name if view == "merchant" else c.output_key
    counts = db.query(func.count().label("source_count"),
        func.count(func.distinct(c.supplier_name)).label("supplier_count"),
        func.count(func.distinct(c.output_key)).label("output_count"),
        func.coalesce(func.sum(c.reference_date_count), 0).label("reference_date_count"),
        func.count(func.distinct(group_key)).label("total")).one()._asdict()
    totals = [row._asdict() for row in db.query(c.unit, *[
        func.sum(c[key]).label(key) for key in QUANTITIES]).group_by(c.unit).order_by(c.unit)]
    page = db.query(group_key.label("key"), func.count().label("source_count"),
        func.sum(case((c.unreceived_qty > 0, 1), else_=0)).label("pending_source_count")
    ).group_by(group_key).order_by(group_key).offset(skip).limit(limit).all()
    groups = [dict(row._asdict(), items=[]) for row in page]
    if groups:
        by_key = {group["key"]: group for group in groups}
        identity = [c.supplier_name, c.output_key, c.output_id, c.output_type, c.output_name, c.output_image, c.unit]
        for row in db.query(*identity, func.count().label("source_count"),
            func.sum(c.reference_date_count).label("reference_date_count"), *[
                func.sum(c[key]).label(key) for key in QUANTITIES]
        ).filter(group_key.in_(by_key)).group_by(*identity).order_by(c.supplier_name, c.output_key, c.unit):
            values = row._asdict()
            by_key[values["supplier_name"] if view == "merchant" else values["output_key"]]["items"].append(values)
    return dict(**counts, totals=totals, groups=groups)


def output_sources(db, *, supplier_name, output_key, unit, skip=0, limit=20, **filters):
    sources = _source_query(db, **filters).subquery()
    q = db.query(sources).filter(sources.c.supplier_name == supplier_name,
        sources.c.output_key == output_key, sources.c.unit == unit)
    total = q.count()
    rows = q.order_by(sources.c.dispatch_date.desc().nullslast(), sources.c.handcraft_jewelry_item_id.desc()
    ).offset(skip).limit(limit).all()
    return dict(items=[row._asdict() for row in rows], total=total)


def output_receipts(db, source_id, *, skip=0, limit=20):
    eligible = db.query(HandcraftJewelryItem.id).join(HandcraftOrder,
        HandcraftOrder.id == HandcraftJewelryItem.handcraft_order_id).filter(
        HandcraftJewelryItem.id == source_id, HandcraftOrder.status.in_(["processing", "completed"])).first()
    if not eligible:
        return None
    q = db.query(HandcraftReceiptItem, HandcraftReceipt).join(HandcraftReceipt,
        HandcraftReceipt.id == HandcraftReceiptItem.handcraft_receipt_id).filter(
        _physical(), HandcraftReceiptItem.handcraft_jewelry_item_id == source_id)
    total = q.count()
    rows = q.order_by(HandcraftReceipt.created_at, HandcraftReceiptItem.id).offset(skip).limit(limit).all()
    return dict(total=total, items=[dict(receipt_id=receipt.id, receipt_item_id=item.id,
        receipt_date=receipt.created_at.date(), qty=item.qty, unit=item.unit,
        note=item.note, document_note=receipt.note) for item, receipt in rows])


def output_options(db, *, q="", selected_keys=(), limit=50):
    # Options come from dispatched output history, independent of current filters.
    # Typed keys prevent colliding jewelry/part IDs; selected values remain visible
    # even when searching for another product or after a product has been disabled.
    sources = _source_query(db, archive="all").subquery()
    c = sources.c
    identity = [c.output_key, c.output_id, c.output_type, c.output_name, c.output_image]
    products = db.query(*identity).distinct()
    matching = products
    if q.strip():
        matching = matching.filter(or_(c.output_id.ilike(_pattern(q), escape="\\"),
                                      c.output_name.ilike(_pattern(q), escape="\\")))
    matches = matching.order_by(c.output_key).limit(limit + 1).all()
    outputs = {row.output_key: row._asdict() for row in matches[:limit]}
    if selected_keys:
        outputs.update({row.output_key: row._asdict() for row in products.filter(c.output_key.in_(selected_keys))})
    suppliers = db.query(HandcraftOrder.supplier_name).filter(
        HandcraftOrder.status.in_(["processing", "completed"])).distinct().order_by(HandcraftOrder.supplier_name).all()
    return dict(suppliers=[row[0] for row in suppliers], outputs=list(outputs.values()), has_more=len(matches) > limit)
