"""Read-only, source-detail handcraft summary. No stock/counter mutations.

Material/output membership is inferred from the CURRENT positive BOM, never a
historical allocation. Pagination/counting operate on source IDs, not joins to
receipts or BOM rows. All page enrichment is batched.
"""
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import Date, and_, case, cast, exists, func, or_, select, union
from sqlalchemy.orm import aliased

from models.bom import Bom
from models.part_bom import PartBom
from models.part import Part
from models.jewelry import Jewelry
from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem, HandcraftPickingWeight
from models.handcraft_receipt import HandcraftReceipt, HandcraftReceiptItem
from models.order import OrderItemLink, OrderTodoItem
from models.production_loss import ProductionLoss
from services.handcraft import handcraft_atomic_picking_join_clause, handcraft_effective_qty_expr
from services.production_archive import filter_archive
from time_utils import now_beijing


def _membership():
    # UNION (not UNION ALL) deduplicates paths and terminates even legacy cycles.
    descendants = select(
        PartBom.parent_part_id.label("root"), PartBom.child_part_id.label("child")
    ).where(PartBom.qty_per_unit > 0).cte("summary_descendants", recursive=True)
    descendants = descendants.union(select(descendants.c.root, PartBom.child_part_id).join(
        PartBom, PartBom.parent_part_id == descendants.c.child
    ).where(PartBom.qty_per_unit > 0))
    jewelry_parts = union(
        select(Bom.jewelry_id.label("output"), Bom.part_id.label("material")).where(Bom.qty_per_unit > 0),
        select(Bom.jewelry_id, descendants.c.child).join(
            descendants, descendants.c.root == Bom.part_id
        ).where(Bom.qty_per_unit > 0),
    ).subquery()
    material, output = HandcraftPartItem, HandcraftJewelryItem
    jewelry_match = exists(select(1).select_from(jewelry_parts).where(
        jewelry_parts.c.output == output.jewelry_id, jewelry_parts.c.material == material.part_id
    ).correlate(material, output))
    part_match = exists(select(1).select_from(descendants).where(
        descendants.c.root == output.part_id, descendants.c.child == material.part_id,
        output.part_id != material.part_id,
    ).correlate(material, output))
    return and_(material.handcraft_order_id == output.handcraft_order_id,
                or_(and_(output.jewelry_id.is_not(None), jewelry_match),
                    and_(output.jewelry_id.is_(None), part_match)))


def _order_match(source, keyword):
    source_key = (OrderItemLink.handcraft_part_item_id if source is HandcraftPartItem
                  else OrderItemLink.handcraft_jewelry_item_id)
    return exists(select(1).select_from(OrderItemLink).outerjoin(
        OrderTodoItem, OrderTodoItem.id == OrderItemLink.order_todo_item_id
    ).where(source_key == source.id,
            func.coalesce(OrderItemLink.order_id, OrderTodoItem.order_id).ilike(_pattern(keyword), escape="\\")))


def _pattern(value):
    return "%" + value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _output_match(keyword):
    return or_(HandcraftJewelryItem.jewelry_id.ilike(_pattern(keyword), escape="\\"),
               HandcraftJewelryItem.part_id.ilike(_pattern(keyword), escape="\\"),
               exists(select(1).where(Jewelry.id == HandcraftJewelryItem.jewelry_id,
                                      Jewelry.name.ilike(_pattern(keyword), escape="\\")).correlate(HandcraftJewelryItem)),
               exists(select(1).where(Part.id == HandcraftJewelryItem.part_id,
                                      Part.name.ilike(_pattern(keyword), escape="\\")).correlate(HandcraftJewelryItem)))


def _physical():
    return and_(HandcraftReceiptItem.handcraft_jewelry_item_id.is_not(None),
                HandcraftReceiptItem.handcraft_part_item_id.is_(None), HandcraftReceiptItem.qty > 0)


def _base(db, source, *, supplier_name=None, archive="active", order_id=None):
    q = db.query(source, HandcraftOrder).join(HandcraftOrder, source.handcraft_order_id == HandcraftOrder.id)
    q = filter_archive(q, HandcraftOrder, archive)
    q = q.filter(HandcraftOrder.status.in_(["processing", "completed"]))
    if supplier_name:
        q = q.filter(HandcraftOrder.supplier_name == supplier_name)
    if order_id and order_id.strip():
        q = q.filter(_order_match(source, order_id))
    return q


def _common(item, order):
    return dict(handcraft_order_id=order.id, supplier_name=order.supplier_name,
                dispatch_date=order.created_at.date(), archived_at=order.archived_at,
                note=item.note, document_note=order.note, unit=item.unit)


def _enrich(db, material_ids, output_ids, membership):
    """Bounded query count irrespective of page size, outputs or receipt batches."""
    pairs = []
    if material_ids or output_ids:
        pairs = db.query(HandcraftPartItem.id, HandcraftJewelryItem.id).filter(membership).filter(
            HandcraftPartItem.id.in_(material_ids) if material_ids else HandcraftJewelryItem.id.in_(output_ids)
        ).all()
    all_outputs = set(output_ids) | {o for _, o in pairs}
    output_map = {}
    output_part = aliased(Part)
    if all_outputs:
        for item, jewelry, part in db.query(HandcraftJewelryItem, Jewelry, output_part).outerjoin(
            Jewelry, Jewelry.id == HandcraftJewelryItem.jewelry_id
        ).outerjoin(output_part, output_part.id == HandcraftJewelryItem.part_id).filter(HandcraftJewelryItem.id.in_(all_outputs)):
            product = jewelry if item.jewelry_id else part
            output_map[item.id] = dict(handcraft_jewelry_item_id=item.id,
                output_id=item.jewelry_id or item.part_id, output_type="jewelry" if item.jewelry_id else "part",
                output_name=product.name if product else None, output_image=product.image if product else None)
    batches = defaultdict(list)
    if all_outputs:
        for item, receipt in db.query(HandcraftReceiptItem, HandcraftReceipt).join(
            HandcraftReceipt, HandcraftReceipt.id == HandcraftReceiptItem.handcraft_receipt_id
        ).filter(_physical(), HandcraftReceiptItem.handcraft_jewelry_item_id.in_(all_outputs)).order_by(
            HandcraftReceipt.created_at, HandcraftReceiptItem.id
        ):
            batches[item.handcraft_jewelry_item_id].append(dict(receipt_id=receipt.id,
                receipt_item_id=item.id, receipt_date=receipt.created_at.date(), qty=float(item.qty),
                unit=item.unit, note=item.note, document_note=receipt.note))
    orders = defaultdict(list)
    if material_ids or output_ids:
        for material, output, order_id in db.query(OrderItemLink.handcraft_part_item_id,
                OrderItemLink.handcraft_jewelry_item_id, func.coalesce(OrderItemLink.order_id, OrderTodoItem.order_id)
        ).outerjoin(OrderTodoItem, OrderTodoItem.id == OrderItemLink.order_todo_item_id).filter(or_(
            OrderItemLink.handcraft_part_item_id.in_(material_ids), OrderItemLink.handcraft_jewelry_item_id.in_(output_ids)
        )):
            if order_id:
                orders[("material", material) if material is not None else ("output", output)].append(order_id)
    return pairs, output_map, batches, orders


def list_dispatched(db, *, supplier_name=None, date_from=None, date_to=None,
                    part_id=None, output_id=None, order_id=None, archive="active",
                    sort="dispatch_date_desc", skip=0, limit=30):
    membership = _membership()
    q = _base(db, HandcraftPartItem, supplier_name=supplier_name, archive=archive, order_id=order_id)
    if date_from:
        q = q.filter(cast(HandcraftOrder.created_at, Date) >= date_from)
    if date_to:
        q = q.filter(cast(HandcraftOrder.created_at, Date) <= date_to)
    if part_id and part_id.strip():
        q = q.filter(or_(HandcraftPartItem.part_id.ilike(_pattern(part_id), escape="\\"), exists(select(1).where(
            Part.id == HandcraftPartItem.part_id, Part.name.ilike(_pattern(part_id), escape="\\")).correlate(HandcraftPartItem))))
    if output_id and output_id.strip():
        q = q.filter(exists(select(1).select_from(HandcraftJewelryItem).where(membership, _output_match(output_id))))
    total = q.count()
    q = q.outerjoin(Part, Part.id == HandcraftPartItem.part_id).outerjoin(
        HandcraftPickingWeight, handcraft_atomic_picking_join_clause()
    ).add_columns(Part, handcraft_effective_qty_expr())
    if sort == "days_out_desc":
        q = q.order_by(case((or_(HandcraftOrder.archived_at.is_not(None),
            func.coalesce(HandcraftPartItem.received_qty, 0) >= handcraft_effective_qty_expr()), 1), else_=0),
            HandcraftOrder.created_at.asc(), HandcraftPartItem.id.desc())
    else:
        q = q.order_by(HandcraftOrder.created_at.desc(), HandcraftPartItem.id.desc())
    page = q.offset(skip).limit(limit).all()
    ids = [item.id for item, *_ in page]
    pairs, output_map, batches, orders = _enrich(db, ids, [], membership)
    relationships = defaultdict(list)
    for material, output in pairs:
        relationships[material].append(output)
    weights = defaultdict(list)
    if ids:
        for weight in db.query(HandcraftPickingWeight).filter(HandcraftPickingWeight.part_item_id.in_(ids)):
            weights[weight.part_item_id].append(weight)
    today = now_beijing().date()
    result = []
    for item, order, part, qty in page:
        completed = Decimal(item.received_qty or 0) >= Decimal(qty or 0)
        weight, weight_unit = None, None
        if part and part.is_composite:
            values = [w for w in weights[item.id] if w.weight is not None]
            if values:
                weight = sum(float(w.weight) / (1000 if w.weight_unit == "g" else 1) for w in values)
                weight_unit = "kg"
        else:
            picked_weight = next((w for w in weights[item.id] if w.atom_part_id == item.part_id), None)
            if picked_weight:
                weight, weight_unit = picked_weight.weight, picked_weight.weight_unit or "kg"
        related = sorted(relationships[item.id])
        receipts = {b["receipt_item_id"]: b for output in related for b in batches[output]}
        result.append(dict(**_common(item, order), handcraft_part_item_id=item.id, part_id=item.part_id,
            part_name=part.name if part else None, part_image=part.image if part else None, qty=float(qty or 0),
            weight=weight, weight_unit=weight_unit, outputs=[output_map[o] for o in related],
            relationship_basis="current_bom" if related else "unmatched",
            receipts=sorted(receipts.values(), key=lambda b: (b["receipt_date"], b["receipt_item_id"])),
            order_ids=sorted(set(orders[("material", item.id)])), is_completed=completed,
            days_out=None if completed or order.archived_at else max(0, (today - order.created_at.date()).days - 1)))
    return result, total


def list_received(db, *, supplier_name=None, date_from=None, date_to=None,
                  part_id=None, output_id=None, order_id=None, archive="active", skip=0, limit=30):
    membership = _membership()
    q = _base(db, HandcraftJewelryItem, supplier_name=supplier_name, archive=archive, order_id=order_id)
    if output_id and output_id.strip():
        q = q.filter(_output_match(output_id))
    if part_id and part_id.strip():
        q = q.filter(exists(select(1).select_from(HandcraftPartItem).where(membership, or_(
            HandcraftPartItem.part_id.ilike(_pattern(part_id), escape="\\"), exists(select(1).where(
                Part.id == HandcraftPartItem.part_id, Part.name.ilike(_pattern(part_id), escape="\\")))))))
    if date_from or date_to:
        receipt_match = select(1).select_from(HandcraftReceiptItem).join(
            HandcraftReceipt, HandcraftReceipt.id == HandcraftReceiptItem.handcraft_receipt_id
        ).where(_physical(), HandcraftReceiptItem.handcraft_jewelry_item_id == HandcraftJewelryItem.id)
        if date_from:
            receipt_match = receipt_match.where(cast(HandcraftReceipt.created_at, Date) >= date_from)
        if date_to:
            receipt_match = receipt_match.where(cast(HandcraftReceipt.created_at, Date) <= date_to)
        q = q.filter(exists(receipt_match))
    total = q.count()
    # Existing counters are appropriate for ordering settlement, NOT actual receipts.
    page = q.order_by(case((func.coalesce(HandcraftJewelryItem.received_qty, 0) >= HandcraftJewelryItem.qty, 1), else_=0),
                      HandcraftOrder.created_at.desc(), HandcraftJewelryItem.id.desc()).offset(skip).limit(limit).all()
    ids = [item.id for item, _ in page]
    _, output_map, batches, orders = _enrich(db, [], ids, membership)
    losses = dict(db.query(ProductionLoss.item_id, func.sum(ProductionLoss.loss_qty)).join(
        HandcraftJewelryItem, and_(HandcraftJewelryItem.id == ProductionLoss.item_id,
                                  HandcraftJewelryItem.handcraft_order_id == ProductionLoss.order_id)
    ).filter(ProductionLoss.order_type == "handcraft", ProductionLoss.item_type == "handcraft_jewelry",
             ProductionLoss.item_id.in_(ids)).group_by(ProductionLoss.item_id).all()) if ids else {}
    result = []
    for item, order in page:
        receipts = batches[item.id]
        actual = sum((Decimal(str(batch["qty"])) for batch in receipts), Decimal(0))
        loss = Decimal(losses.get(item.id) or 0)
        gap = max(Decimal(0), Decimal(item.qty) - actual - loss)
        # Legacy counters may disagree: never offer more than the existing loss endpoint accepts.
        confirmable = min(gap, max(Decimal(0), Decimal(item.qty) - Decimal(item.received_qty or 0)))
        result.append(dict(**_common(item, order), **output_map[item.id], expected_qty=item.qty,
            actual_received_qty=float(actual), loss_total_qty=float(loss), unreceived_qty=float(gap),
            max_loss_qty=0 if order.archived_at else float(confirmable), is_completed=gap == 0,
            receipts=receipts, order_ids=sorted(set(orders[("output", item.id)]))))
    return result, total
