import math
import secrets
from datetime import datetime, date as date_type
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, and_, exists, func, or_
from sqlalchemy.orm import Session

from models.bom import Bom
from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem, HandcraftPickingRecord, HandcraftPickingWeight
from models.jewelry import Jewelry
from models.part import Part
from services._helpers import _next_id, keyword_filter
from services.inventory import add_stock, batch_get_stock, deduct_stock, supplement_shortfall
from time_utils import now_beijing


# Per-tier buffer rule for suggesting handcraft part allocation:
#   suggested = ceil(theoretical) + ceil(max(floor, theoretical * ratio))
# ratio kept as Decimal so qty_per_unit (Numeric) × ratio stays exact —
# float would corrupt theoretical_qty for fractional BOM (e.g. 0.3m chain × 1000).
HANDCRAFT_BUFFER_RULES = {
    "small":  {"ratio": Decimal("0.02"), "floor": 50},
    "medium": {"ratio": Decimal("0.01"), "floor": 15},
}


_RECEIPT_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 31 chars, excludes 0/O/1/I/L


def _gen_receipt_code(db: Session, max_tries: int = 10) -> str:
    """Generate a unique 5-char opaque receipt code for a HandcraftOrder.

    Uses cryptographic randomness and probes the unique index for collisions.
    31^5 ≈ 28.6M combinations — collisions are negligible at realistic volumes.

    The SELECT-then-INSERT is intentionally not atomic. Concurrent callers can
    pass the check with the same code and rely on the partial unique index
    (ix_handcraft_order_receipt_code) to reject the loser at INSERT time —
    callers must surface that IntegrityError up. Acceptable for the single-
    store usage pattern; if multi-writer becomes a thing, switch to
    `INSERT ... ON CONFLICT DO NOTHING RETURNING id` and retry on empty.
    """
    for _ in range(max_tries):
        code = "".join(secrets.choice(_RECEIPT_CODE_ALPHABET) for _ in range(5))
        if not db.query(HandcraftOrder.id).filter_by(receipt_code=code).first():
            return code
    raise RuntimeError("无法生成唯一回执码（碰撞次数超限）")


def compute_suggested_qty(part: Part, theoretical: Decimal) -> int:
    """Apply the per-tier buffer rule (with per-part override) to theoretical
    demand. Returns ceil(theoretical) + buffer.

    Direct dict lookup (not .get()): size_tier is constrained by Pydantic
    Literal + DB NOT NULL. An unknown value is data corruption and should
    fail loud rather than silently apply a default rule.

    Caller must ensure theoretical is a positive Decimal.
    """
    tier_rule = HANDCRAFT_BUFFER_RULES[part.size_tier]
    ratio = part.buffer_ratio_override if part.buffer_ratio_override is not None else tier_rule["ratio"]
    floor = part.buffer_floor_override if part.buffer_floor_override is not None else tier_rule["floor"]
    buffer = math.ceil(max(Decimal(floor), theoretical * Decimal(ratio)))
    return math.ceil(theoretical) + buffer


def _user_date_to_datetime(d: Optional[date_type]) -> Optional[datetime]:
    """Store a user-supplied date as midnight. Same-day ordering is handled by
    an `id DESC` tie-breaker in list queries, not by fabricating a time-of-day."""
    if d is None:
        return None
    return datetime.combine(d, datetime.min.time())


def _replace_date(existing: Optional[datetime], new_date: date_type) -> datetime:
    """Combine new_date with the time-of-day from existing; fall back to midnight."""
    time_of_day = existing.time() if existing else datetime.min.time()
    return datetime.combine(new_date, time_of_day)


def _require_part(db: Session, part_id: str) -> None:
    if db.get(Part, part_id) is None:
        raise ValueError(f"Part not found: {part_id}")


def _category_prefix(part_id: str) -> str:
    parts = part_id.split("-")
    return "-".join(parts[:2]) if len(parts) >= 2 else part_id


def suggest_handcraft_parts(db: Session, jewelry_items: list[dict]) -> list[dict]:
    """Compute suggested handcraft allocation for a set of jewelry orders.

    For each part used by any of the requested jewelries, aggregate the
    theoretical demand across jewelries (BOM qty_per_unit × jewelry qty),
    then apply the buffer rule for that part's size_tier.

    jewelry_items: [{"jewelry_id": str, "qty": int}, ...]
    """
    seen_ids = set()
    for item in jewelry_items:
        jid = item["jewelry_id"]
        if jid in seen_ids:
            raise ValueError(f"重复的饰品 ID: {jid}")
        seen_ids.add(jid)

    if not seen_ids:
        return []

    jewelries = {
        j.id: j
        for j in db.query(Jewelry).filter(Jewelry.id.in_(seen_ids)).all()
    }
    missing = seen_ids - jewelries.keys()
    if missing:
        raise ValueError(f"饰品不存在: {sorted(missing)}")

    boms = (
        db.query(Bom)
        .filter(Bom.jewelry_id.in_(seen_ids))
        .all()
    )
    qty_by_jewelry = {item["jewelry_id"]: item["qty"] for item in jewelry_items}
    totals: dict[str, Decimal] = {}
    for bom in boms:
        # qty_per_unit is Numeric → Decimal; staying in Decimal avoids
        # float drift like 0.3 * 1000 == 300.00000000000006.
        contribution = bom.qty_per_unit * qty_by_jewelry[bom.jewelry_id]
        totals[bom.part_id] = totals.get(bom.part_id, Decimal(0)) + contribution

    if not totals:
        return []

    parts_by_id = {
        p.id: p
        for p in db.query(Part).filter(Part.id.in_(totals.keys())).all()
    }

    results = []
    for part_id, theo in totals.items():
        if theo <= 0:
            continue
        part = parts_by_id.get(part_id)
        if part is None:
            continue
        suggested = compute_suggested_qty(part, theo)
        buffer = suggested - math.ceil(theo)
        results.append({
            "part_id": part_id,
            "part_name": part.name,
            "size_tier": part.size_tier,
            "theoretical_qty": float(theo),
            "buffer": buffer,
            "suggested_qty": suggested,
        })

    results.sort(key=lambda r: (_category_prefix(r["part_id"]), r["part_id"]))
    return results


def _require_jewelry(db: Session, jewelry_id: str) -> None:
    if db.get(Jewelry, jewelry_id) is None:
        raise ValueError(f"Jewelry not found: {jewelry_id}")


def _normalize_delivery_images(delivery_images: Optional[list]) -> list[str]:
    cleaned = [str(item).strip() for item in (delivery_images or []) if str(item).strip()]
    if len(cleaned) > 10:
        raise ValueError("发货图片最多上传 10 张")
    return cleaned



def _attach_part_colors(db: Session, items: list[HandcraftPartItem]) -> list[HandcraftPartItem]:
    if not items:
        return items
    part_ids = {item.part_id for item in items}
    parts = {
        part.id: part
        for part in db.query(Part).filter(Part.id.in_(part_ids)).all()
    }
    for item in items:
        part = parts.get(item.part_id)
        item.color = part.color if part else None
    return items


def create_handcraft_order(
    db: Session,
    supplier_name: str,
    parts: list,
    jewelries: Optional[list] = None,
    note: str = None,
    created_at: Optional[date_type] = None,
) -> HandcraftOrder:
    for p in parts:
        _require_part(db, p["part_id"])
    for j in jewelries or []:
        jewelry_id = j.get("jewelry_id")
        part_id = j.get("part_id")
        if jewelry_id and part_id:
            raise ValueError("产出项不能同时指定 jewelry_id 和 part_id")
        if jewelry_id:
            _require_jewelry(db, jewelry_id)
        elif part_id:
            _require_part(db, part_id)
        else:
            raise ValueError("产出项必须指定 jewelry_id 或 part_id")

    # Auto-merge: reuse existing pending order for same supplier on same day.
    # Skip merge when user explicitly provides created_at (补录历史单据的场景).
    merged = False
    existing = None
    if created_at is None:
        today_beijing = now_beijing().date()
        existing = (
            db.query(HandcraftOrder)
            .filter(
                HandcraftOrder.supplier_name == supplier_name,
                HandcraftOrder.status == "pending",
                func.cast(HandcraftOrder.created_at, Date) == today_beijing,
            )
            .order_by(HandcraftOrder.created_at.asc(), HandcraftOrder.id.asc())
            .first()
        )

    if existing:
        order = existing
        merged = True
        if note:
            order.note = f"{order.note}; {note}" if order.note else note
            db.flush()
    else:
        order_id = _next_id(db, HandcraftOrder, "HC")
        order = HandcraftOrder(
            id=order_id,
            supplier_name=supplier_name,
            status="pending",
            note=note,
            receipt_code=_gen_receipt_code(db),
        )
        if created_at is not None:
            order.created_at = _user_date_to_datetime(created_at)
        db.add(order)
        db.flush()

    pending_weights: list[tuple[HandcraftPartItem, float, str]] = []
    for p in parts:
        # Mirror add_handcraft_part: weight goes to handcraft_picking_weight,
        # not the legacy part_item columns. Atomic only — composite weights
        # are per-atom after expansion, so silently drop here.
        new_item = HandcraftPartItem(
            handcraft_order_id=order.id,
            part_id=p["part_id"],
            qty=p["qty"],
            weight=None,
            weight_unit=None,
            bom_qty=p.get("bom_qty"),
            unit=p.get("unit", "个"),
            note=p.get("note"),
        )
        db.add(new_item)
        incoming_weight = p.get("weight")
        if incoming_weight is not None:
            unit_val = p.get("weight_unit") or "kg"
            pending_weights.append((new_item, float(incoming_weight), unit_val))
    for j in jewelries or []:
        jewelry_id = j.get("jewelry_id")
        part_id = j.get("part_id")
        default_unit = "套" if jewelry_id else "个"
        db.add(HandcraftJewelryItem(
            handcraft_order_id=order.id,
            jewelry_id=jewelry_id,
            part_id=part_id,
            qty=j["qty"],
            weight=j.get("weight"),
            weight_unit=j.get("weight_unit"),
            received_qty=0,
            status="未送出",
            unit=j.get("unit") or default_unit,
            note=j.get("note"),
            customer_name=j.get("customer_name"),
        ))
    db.flush()

    if pending_weights:
        from services.handcraft_picking_weight import upsert_weight
        composite_ids = {
            p.id for p in db.query(Part).filter(
                Part.id.in_({pi.part_id for pi, _, _ in pending_weights})
            ).all()
            if p.is_composite
        }
        for pi, weight, unit_val in pending_weights:
            if pi.part_id in composite_ids:
                continue  # composite weights not supported on the part_item level
            upsert_weight(db, order.id, pi.id, pi.part_id, weight, unit_val)

    order.merged = merged
    return order


def _compute_effective_part_totals(
    db: Session, handcraft_order_id: str, part_items: list
) -> dict[str, float]:
    """Sum picking-effective qty per part_id for a handcraft order. Atomic
    items use the 勾选'd actual_qty override; composites and unpicked atoms
    fall back to pi.qty. Single source of truth for both
    `send_handcraft_order` and `supplement_and_send_handcraft_order` — they
    must agree, otherwise supplement under-tops and send fails 库存不足.
    """
    actual_by_key = load_actual_qty_map(db, handcraft_order_id)
    totals: dict[str, float] = {}
    for item in part_items:
        effective = actual_by_key.get((item.id, item.part_id), float(item.qty))
        totals[item.part_id] = totals.get(item.part_id, 0.0) + effective
    return totals


def send_handcraft_order(db: Session, handcraft_order_id: str) -> HandcraftOrder:
    order = get_handcraft_order(db, handcraft_order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {handcraft_order_id}")
    if order.status != "pending":
        raise ValueError(f"HandcraftOrder {handcraft_order_id} cannot be sent: current status is '{order.status}'")
    part_items = (
        db.query(HandcraftPartItem)
        .filter(HandcraftPartItem.handcraft_order_id == handcraft_order_id)
        .all()
    )
    if not part_items:
        raise ValueError(f"HandcraftOrder {handcraft_order_id} has no part items and cannot be sent")
    jewelry_items = (
        db.query(HandcraftJewelryItem)
        .filter(HandcraftJewelryItem.handcraft_order_id == handcraft_order_id)
        .all()
    )
    part_totals = _compute_effective_part_totals(db, handcraft_order_id, part_items)
    # Batch check all parts before deducting
    stocks = batch_get_stock(db, "part", list(part_totals.keys()))
    insufficient = []
    for part_id, total_qty in part_totals.items():
        current = stocks.get(part_id, 0.0)
        if current < total_qty:
            insufficient.append(f"{part_id} 当前库存 {current}，需要 {total_qty}")
    if insufficient:
        raise ValueError("库存不足：" + "；".join(insufficient))
    deducted = []
    try:
        for part_id, total_qty in part_totals.items():
            deduct_stock(db, "part", part_id, total_qty, "手工发出")
            deducted.append((part_id, total_qty))
    except Exception:
        for part_id, qty in deducted:
            add_stock(db, "part", part_id, qty, "手工发出回滚")
        raise
    for pi in part_items:
        pi.status = "制作中"
    for ji in jewelry_items:
        ji.status = "制作中"
    order.status = "processing"
    db.flush()
    return order



def supplement_and_send_handcraft_order(
    db: Session, handcraft_order_id: str
) -> tuple[HandcraftOrder, dict[str, float]]:
    """Supplement any part-stock shortfall for this order, then immediately
    call send_handcraft_order. Returns (order, supplemented) where
    supplemented is {part_id: qty} for parts that needed补进 (may be empty).
    All validation lives in send_handcraft_order; failures roll back.
    """
    order = get_handcraft_order(db, handcraft_order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {handcraft_order_id}")
    if order.status != "pending":
        raise ValueError(
            f"HandcraftOrder {handcraft_order_id} cannot be sent: "
            f"current status is '{order.status}'"
        )
    part_items = (
        db.query(HandcraftPartItem)
        .filter(HandcraftPartItem.handcraft_order_id == handcraft_order_id)
        .all()
    )
    if not part_items:
        raise ValueError(
            f"HandcraftOrder {handcraft_order_id} has no part items "
            f"and cannot be sent"
        )
    part_totals = _compute_effective_part_totals(db, handcraft_order_id, part_items)
    supplemented = supplement_shortfall(
        db, "part", part_totals,
        reason="手工单缺货补进",
        note=handcraft_order_id,
    )
    order = send_handcraft_order(db, handcraft_order_id)
    return order, supplemented


def get_handcraft_order(db: Session, handcraft_order_id: str) -> Optional[HandcraftOrder]:
    return db.query(HandcraftOrder).filter(HandcraftOrder.id == handcraft_order_id).first()


def get_handcraft_order_by_receipt_code(db: Session, code: str) -> Optional[HandcraftOrder]:
    """Look up a handcraft order by its 5-char opaque receipt code.

    Case-insensitive: the alphabet is uppercase but users may type lowercase
    when transcribing from the printed slip.
    """
    return db.query(HandcraftOrder).filter_by(receipt_code=code.upper()).first()


_BREAKDOWN_STATUS_RANK = {"未送出": 0, "制作中": 1, "已收回": 2}


def get_handcraft_jewelry_breakdown(
    db: Session, hc_id: str, only_with_customer: bool = False
) -> list[dict]:
    """Aggregated jewelry view for HC detail.

    Returns one group per (kind, identity) — `kind` is "jewelry" or "part"
    depending on whether the output row's `jewelry_id` or `part_id` is set,
    and `identity` is that id. Each group sums qty / received_qty and lists
    per-row entries with the resolved customer name + its source
    ("order" via OrderItemLink, or "manual" via customer_name override).
    """
    from models.order import Order, OrderItemLink
    from collections import defaultdict

    rows = (
        db.query(HandcraftJewelryItem)
        .filter(HandcraftJewelryItem.handcraft_order_id == hc_id)
        .order_by(HandcraftJewelryItem.id.asc())
        .all()
    )
    if not rows:
        return []

    # Bulk-resolve OrderItemLink → Order for from-order rows
    row_ids = [r.id for r in rows]
    link_rows = (
        db.query(
            OrderItemLink.handcraft_jewelry_item_id,
            OrderItemLink.order_id,
            Order.customer_name,
        )
        .join(Order, Order.id == OrderItemLink.order_id)
        .filter(OrderItemLink.handcraft_jewelry_item_id.in_(row_ids))
        .all()
    )
    link_by_item = {lr.handcraft_jewelry_item_id: lr for lr in link_rows}

    # Resolve jewelry / part display name + image
    jewelry_ids = {r.jewelry_id for r in rows if r.jewelry_id}
    part_ids_only = {r.part_id for r in rows if r.part_id and not r.jewelry_id}
    jewelry_map = {
        j.id: j for j in db.query(Jewelry).filter(Jewelry.id.in_(jewelry_ids)).all()
    } if jewelry_ids else {}
    part_map = {
        p.id: p for p in db.query(Part).filter(Part.id.in_(part_ids_only)).all()
    } if part_ids_only else {}

    # Group rows by (kind, identity). Preserve first-seen order for stable
    # group ordering in the UI (matches the iteration of `rows` which is id-asc).
    grouped: dict[tuple[str, str], list[HandcraftJewelryItem]] = defaultdict(list)
    group_order: list[tuple[str, str]] = []
    for r in rows:
        kind = "jewelry" if r.jewelry_id else "part"
        identity = r.jewelry_id or r.part_id
        key = (kind, identity)
        if key not in grouped:
            group_order.append(key)
        grouped[key].append(r)

    result = []
    for kind, identity in group_order:
        group_rows = grouped[(kind, identity)]
        if kind == "jewelry":
            obj = jewelry_map.get(identity)
        else:
            obj = part_map.get(identity)
        name = obj.name if obj else identity
        image = getattr(obj, "image", None) if obj else None

        entries = []
        for r in group_rows:
            if r.customer_name is not None:
                customer = r.customer_name
                source = "manual"
                source_order_id = None
            else:
                link = link_by_item.get(r.id)
                if link:
                    customer = link.customer_name
                    source = "order"
                    source_order_id = link.order_id
                else:
                    customer = None
                    source = "manual"
                    source_order_id = None
            entries.append({
                "hc_jewelry_item_id": r.id,
                "qty": float(r.qty),
                "received_qty": float(r.received_qty or 0),
                "customer_name": customer,
                "source": source,
                "source_order_id": source_order_id,
                "is_locked": source == "order",
            })

        if only_with_customer:
            entries = [
                e for e in entries
                if e["customer_name"] and e["customer_name"].strip()
            ]
            if not entries:
                continue

        # Group-level aggregate status: the lowest rank wins so the UI shows
        # the most upstream state (any 未送出 → 未送出 for the whole group).
        status = min(
            group_rows,
            key=lambda r: _BREAKDOWN_STATUS_RANK.get(r.status, 99),
        ).status

        result.append({
            "kind": kind,
            "jewelry_id": identity,
            "jewelry_name": name,
            "jewelry_image": image,
            "total_qty": sum(float(r.qty) for r in group_rows),
            "received_qty": sum(float(r.received_qty or 0) for r in group_rows),
            "status": status,
            "entries": entries,
        })
    return result


def _has_sorting_info(db: Session, hc_id: str) -> bool:
    """True iff at least one HandcraftJewelryItem in the order has a resolvable
    non-empty customer name (either manual customer_name or via OrderItemLink)."""
    # 复用 breakdown 的解析逻辑，避免重复实现。性能足够：单订单查询。
    groups = get_handcraft_jewelry_breakdown(db, hc_id, only_with_customer=True)
    return len(groups) > 0


def list_handcraft_orders(db: Session, status: str = None, supplier_name: str = None) -> list:
    # An explicitly empty / whitespace-only supplier_name means "caller
    # asked for this supplier but the value is empty" — return no rows
    # instead of falling through to an unfiltered query. supplier_name=None
    # (parameter not provided) still returns all rows.
    if supplier_name is not None and not supplier_name.strip():
        return []
    q = db.query(HandcraftOrder)
    if status is not None:
        q = q.filter(HandcraftOrder.status == status)
    clause = keyword_filter(supplier_name, HandcraftOrder.supplier_name)
    if clause is not None:
        q = q.filter(clause)
    return q.order_by(HandcraftOrder.created_at.desc(), HandcraftOrder.id.desc()).all()


def get_handcraft_supplier_names(db: Session) -> list[str]:
    rows = db.query(HandcraftOrder.supplier_name).distinct().all()
    return [row[0] for row in rows]


def _attach_loss_qty(db, items, order_id: str, item_type: str) -> list:
    """Enrich items with loss_qty from production_loss table."""
    from models.production_loss import ProductionLoss
    losses = (
        db.query(ProductionLoss)
        .filter(ProductionLoss.order_id == order_id, ProductionLoss.item_type == item_type)
        .all()
    )
    loss_map = {l.item_id: float(l.loss_qty) for l in losses}
    for item in items:
        item.loss_qty = loss_map.get(item.id)
    return items


def handcraft_atomic_picking_join_clause():
    """SQL ON clause for the LEFT JOIN that surfaces a part item's picking
    actual_qty override.

    Pairs `HandcraftPickingWeight` with `HandcraftPartItem` on the atomic key
    `(part_item_id, atom_part_id == pi.part_id)`, requires `actual_qty` is set
    AND a matching `HandcraftPickingRecord` exists (i.e. the row was 勾选'd).
    Filling actual_qty without 勾选 is treated as a draft and ignored.

    Composite part items are intentionally excluded from the override
    system: their picking-weight rows live under each atom's id, which never
    matches `pi.part_id`, so composites always deduct/report `pi.qty`. Atom
    `actual_qty` rows on composites are write-only metadata for the picking
    UI and have no effect on stock, PDFs, kanban, or receipt caps.

    Usage:

        query.outerjoin(
            HandcraftPickingWeight, handcraft_atomic_picking_join_clause()
        )
    """
    picked_exists = exists().where(
        and_(
            HandcraftPickingRecord.handcraft_part_item_id == HandcraftPartItem.id,
            HandcraftPickingRecord.part_id == HandcraftPartItem.part_id,
        )
    )
    return and_(
        HandcraftPickingWeight.part_item_id == HandcraftPartItem.id,
        HandcraftPickingWeight.atom_part_id == HandcraftPartItem.part_id,
        HandcraftPickingWeight.actual_qty.is_not(None),
        picked_exists,
    )


def handcraft_effective_qty_expr():
    """SQL column expression for a part item's effective sent quantity:
    `coalesce(picking actual_qty, pi.qty)`. Pair with the join clause above.
    """
    return func.coalesce(HandcraftPickingWeight.actual_qty, HandcraftPartItem.qty)


def load_actual_qty_map(db: Session, order_id: str) -> dict[tuple[int, str], float]:
    """Load picking actual_qty overrides keyed by (part_item_id, atom_part_id).

    The key shape lets callers look up `(pi.id, pi.part_id)` to get the atomic
    override (or fall back). Composite expansions live under a different
    `atom_part_id` and naturally miss that lookup.

    Gate: only rows that have a matching `HandcraftPickingRecord` are
    included — filling actual_qty without 勾选 is treated as a draft and
    excluded. Mirrors `handcraft_atomic_picking_join_clause`.
    """
    rows = (
        db.query(HandcraftPickingWeight)
        .join(
            HandcraftPickingRecord,
            and_(
                HandcraftPickingRecord.handcraft_part_item_id
                == HandcraftPickingWeight.part_item_id,
                HandcraftPickingRecord.part_id
                == HandcraftPickingWeight.atom_part_id,
            ),
        )
        .filter(
            HandcraftPickingWeight.handcraft_order_id == order_id,
            HandcraftPickingWeight.actual_qty.is_not(None),
        )
        .all()
    )
    return {
        (r.part_item_id, r.atom_part_id): float(r.actual_qty)
        for r in rows
    }


def _attach_actual_qty(db: Session, items: list, order_id: str) -> list:
    """Attach picking actual_qty to atomic part items only."""
    if not items:
        return items
    actual_by_key = load_actual_qty_map(db, order_id)
    for it in items:
        it.actual_qty = actual_by_key.get((it.id, it.part_id))
    return items


def get_handcraft_parts(db: Session, order_id: str) -> list:
    items = (
        db.query(HandcraftPartItem)
        .filter(HandcraftPartItem.handcraft_order_id == order_id)
        .order_by(HandcraftPartItem.id.asc())
        .all()
    )
    items = _attach_part_colors(db, items)
    items = _attach_loss_qty(db, items, order_id, "handcraft_part")
    return _attach_actual_qty(db, items, order_id)


def get_handcraft_jewelries(db: Session, order_id: str) -> list:
    items = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order_id
    ).all()
    return _attach_loss_qty(db, items, order_id, "handcraft_jewelry")


def update_handcraft_order(db: Session, order_id: str, data: dict) -> HandcraftOrder:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if "supplier_name" in data and data["supplier_name"] is not None:
        if order.status != "pending":
            raise ValueError("只有待处理状态的订单可以修改手工商家")
        name = data["supplier_name"].strip()
        if not name:
            raise ValueError("手工商家名称不能为空")
        order.supplier_name = name
    if "created_at" in data and data["created_at"] is not None:
        order.created_at = _replace_date(order.created_at, data["created_at"])
    db.flush()
    return order


def update_handcraft_delivery_images(db: Session, order_id: str, delivery_images: Optional[list]) -> HandcraftOrder:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    order.delivery_images = _normalize_delivery_images(delivery_images)
    db.flush()
    return order


def add_handcraft_part(db: Session, order_id: str, item: dict) -> HandcraftPartItem:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot add part: order {order_id} status is '{order.status}', must be 'pending'")
    _require_part(db, item["part_id"])
    # Weight is no longer stored on the legacy part_item columns — it goes to
    # handcraft_picking_weight. The columns remain for back-compat (read by
    # ensure_schema_compat backfill) but new writes always go through the
    # picking_weight table.
    new_item = HandcraftPartItem(
        handcraft_order_id=order_id,
        part_id=item["part_id"],
        qty=item["qty"],
        weight=None,
        weight_unit=None,
        bom_qty=item.get("bom_qty"),
        unit=item.get("unit", "个"),
        note=item.get("note"),
    )
    db.add(new_item)
    db.flush()

    # If the caller supplied a weight, route it to handcraft_picking_weight —
    # but only for atomic parts. Composite parts can't be weighed at the
    # part_item level (weights are per-atom after expansion); silently drop
    # rather than raise, since the legacy add-modal doesn't know about this.
    incoming_weight = item.get("weight")
    if incoming_weight is not None:
        part = db.query(Part).filter_by(id=item["part_id"]).one_or_none()
        if part is not None and not part.is_composite:
            from services.handcraft_picking_weight import upsert_weight
            unit_val = item.get("weight_unit") or "kg"
            upsert_weight(db, order_id, new_item.id, item["part_id"], float(incoming_weight), unit_val)

    return _attach_part_colors(db, [new_item])[0]


def update_handcraft_part(db: Session, order_id: str, item_id: int, data: dict) -> HandcraftPartItem:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot update part: order {order_id} status is '{order.status}', must be 'pending'")
    item = db.query(HandcraftPartItem).filter(
        HandcraftPartItem.id == item_id,
        HandcraftPartItem.handcraft_order_id == order_id,
    ).first()
    if item is None:
        raise ValueError(f"HandcraftPartItem {item_id} not found in order {order_id}")

    # Route weight to handcraft_picking_weight table; reject for composites.
    # Distinguish "field present in payload" (caller intends to change it) from
    # "field absent" (preserve existing). A unit-only PATCH must NOT delete the
    # existing weight row — only an explicit `weight: null` clears it.
    weight_present = "weight" in data
    unit_present = "weight_unit" in data
    if weight_present or unit_present:
        from services.handcraft_picking_weight import upsert_weight, delete_weight
        part = db.query(Part).filter_by(id=item.part_id).one_or_none()
        if part is None:
            raise ValueError(f"配件 {item.part_id} 不存在")
        if part.is_composite:
            raise ValueError("组合配件不支持直接编辑重量；请在配货模拟中按 atom 输入")
        weight_val = data.pop("weight", None) if weight_present else None
        unit_val = data.pop("weight_unit", None) if unit_present else None

        # Treat weight==0 the same as null/absent so behavior matches both
        # the picking endpoint schema (gt=0) and the modal's blur-on-empty
        # semantics ("clear input → DELETE the row").
        is_clear = weight_present and (
            weight_val is None or float(weight_val) == 0
        )
        if is_clear:
            # Explicit clear
            delete_weight(db, order_id, item.id, item.part_id)
        else:
            existing = (
                db.query(HandcraftPickingWeight)
                .filter_by(part_item_id=item.id, atom_part_id=item.part_id)
                .one_or_none()
            )
            new_weight = weight_val if weight_present else (
                float(existing.weight) if existing is not None else None
            )
            new_unit = unit_val if unit_present else (
                existing.weight_unit if existing is not None else "kg"
            )
            if new_weight is None:
                # Unit-only PATCH with no prior weight — nothing to write.
                pass
            else:
                upsert_weight(db, order_id, item.id, item.part_id, float(new_weight), new_unit or "kg")

    # `qty_changed` gates the picking-override sync below. Compare against the
    # current value so a no-op PATCH (same qty resubmitted) doesn't churn the
    # picking_weight row or muddy the audit log.
    qty_changed = (
        "qty" in data
        and data["qty"] is not None
        and Decimal(str(data["qty"])) != Decimal(str(item.qty))
    )
    for field in ("qty", "unit", "note"):
        if field in data and data[field] is not None:
            setattr(item, field, data[field])
    if "bom_qty" in data:
        item.bom_qty = data["bom_qty"]  # allow setting to None to clear
    for wf in ("weight", "weight_unit"):
        data.pop(wf, None)  # safety: should already be popped above

    # When qty is edited on an atomic part item that already has an
    # actual_qty override, propagate so the picking record matches the new
    # plan. Composite parts have per-atom overrides at a different key and
    # aren't shadowed by the override system — skip them.
    if qty_changed:
        part_obj = db.query(Part).filter_by(id=item.part_id).one_or_none()
        if part_obj is not None and not part_obj.is_composite:
            override_row = (
                db.query(HandcraftPickingWeight)
                .filter_by(part_item_id=item.id, atom_part_id=item.part_id)
                .one_or_none()
            )
            if override_row is not None and override_row.actual_qty is not None:
                override_row.actual_qty = Decimal(str(data["qty"])).quantize(
                    Decimal("0.0001")
                )

    db.flush()
    return _attach_part_colors(db, [item])[0]


def delete_handcraft_part(db: Session, order_id: str, item_id: int) -> None:
    from models.order import OrderItemLink

    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot delete part: order {order_id} status is '{order.status}', must be 'pending'")
    item = db.query(HandcraftPartItem).filter(
        HandcraftPartItem.id == item_id,
        HandcraftPartItem.handcraft_order_id == order_id,
    ).first()
    if item is None:
        raise ValueError(f"HandcraftPartItem {item_id} not found in order {order_id}")
    # Order-linked rows must be unlinked at the source order, not deleted here.
    # Otherwise the cascade-less FK on OrderItemLink raises IntegrityError → 500.
    has_order_link = db.query(OrderItemLink.id).filter_by(
        handcraft_part_item_id=item.id
    ).first() is not None
    if has_order_link:
        raise ValueError("订单来源行不能在此删除；请先在订单详情解除关联")
    remaining = db.query(HandcraftPartItem).filter(
        HandcraftPartItem.handcraft_order_id == order_id,
        HandcraftPartItem.id != item_id,
    ).count()
    if remaining == 0:
        raise ValueError(f"Cannot delete the last part from order {order_id}; an order must have at least one part item")
    # Clean up any picking records for this part item before deleting.
    db.query(HandcraftPickingRecord).filter_by(
        handcraft_part_item_id=item_id
    ).delete(synchronize_session=False)
    db.flush()
    db.delete(item)
    db.flush()


def add_handcraft_jewelry(db: Session, order_id: str, item: dict) -> HandcraftJewelryItem:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if order.status not in ("pending", "processing"):
        raise ValueError(f"Cannot add jewelry: order {order_id} status is '{order.status}', must be 'pending' or 'processing'")
    # Manual customer attribution rows are pending-only: once parts have been
    # dispatched, the user can't just bolt on a new customer's share without
    # also sending additional stock.
    customer_name = item.get("customer_name")
    if customer_name is not None and order.status != "pending":
        raise ValueError("发出后不可新增手填客户分拣行；请在 pending 状态完成")
    jewelry_id = item.get("jewelry_id")
    part_id = item.get("part_id")
    if jewelry_id and part_id:
        raise ValueError("产出项不能同时指定 jewelry_id 和 part_id")
    if jewelry_id:
        _require_jewelry(db, jewelry_id)
    elif part_id:
        _require_part(db, part_id)
    else:
        raise ValueError("产出项必须指定 jewelry_id 或 part_id")
    item_status = "制作中" if order.status == "processing" else "未送出"
    default_unit = "套" if jewelry_id else "个"
    new_item = HandcraftJewelryItem(
        handcraft_order_id=order_id,
        jewelry_id=jewelry_id,
        part_id=part_id,
        qty=item["qty"],
        weight=item.get("weight"),
        weight_unit=item.get("weight_unit"),
        received_qty=0,
        status=item_status,
        unit=item.get("unit") or default_unit,
        note=item.get("note"),
        customer_name=customer_name,
    )
    db.add(new_item)
    db.flush()
    return new_item


def update_handcraft_jewelry(db: Session, order_id: str, item_id: int, data: dict) -> HandcraftJewelryItem:
    from models.order import OrderItemLink

    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    item = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.id == item_id,
        HandcraftJewelryItem.handcraft_order_id == order_id,
    ).first()
    if item is None:
        raise ValueError(f"HandcraftJewelryItem {item_id} not found in order {order_id}")

    # customer_name has looser rules than the production-affecting fields:
    # editable in pending OR processing (it's pure metadata, doesn't move stock).
    # But order-linked rows derive their customer from Order.customer_name; the
    # edit must be done at the source order, not here.
    if "customer_name" in data:
        if order.status == "completed":
            raise ValueError("已完成的手工单不能修改客户名")
        has_order_link = (
            db.query(OrderItemLink.id)
            .filter_by(handcraft_jewelry_item_id=item.id)
            .first()
            is not None
        )
        if has_order_link:
            raise ValueError("订单来源行的客户名需在对应订单详情修改")
        item.customer_name = data["customer_name"]

    # All other fields stay pending-only — they affect production.
    other_fields = {k: v for k, v in data.items() if k != "customer_name"}
    if other_fields:
        if order.status != "pending":
            raise ValueError(
                f"Cannot update jewelry: order {order_id} status is '{order.status}', "
                f"must be 'pending'"
            )
        for field in ("qty", "unit", "note"):
            if field in other_fields and other_fields[field] is not None:
                setattr(item, field, other_fields[field])
        for wf in ("weight", "weight_unit"):
            if wf in other_fields:
                setattr(item, wf, other_fields[wf])

    db.flush()
    return item


def delete_handcraft_jewelry(db: Session, order_id: str, item_id: int) -> None:
    from models.order import OrderItemLink, OrderTodoBatchJewelry

    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if order.status == "completed":
        raise ValueError("已完成的手工单不能删除饰品项")
    item = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.id == item_id,
        HandcraftJewelryItem.handcraft_order_id == order_id,
    ).first()
    if item is None:
        raise ValueError(f"HandcraftJewelryItem {item_id} not found in order {order_id}")
    # Two non-cascading inbound FKs point at handcraft_jewelry_item.id:
    #   - OrderItemLink.handcraft_jewelry_item_id (the live link)
    #   - OrderTodoBatchJewelry.handcraft_jewelry_item_id (the batch ref,
    #     which can outlive the link — delete_link does not null it out)
    # Either dangling reference would raise IntegrityError → 500 on
    # db.delete(item). Guard symmetrically before any mutation.
    has_order_link = db.query(OrderItemLink.id).filter_by(
        handcraft_jewelry_item_id=item.id
    ).first() is not None
    if has_order_link:
        raise ValueError("订单来源行不能在此删除；请先在订单详情解除关联")
    has_batch_ref = db.query(OrderTodoBatchJewelry.id).filter_by(
        handcraft_jewelry_item_id=item.id
    ).first() is not None
    if has_batch_ref:
        raise ValueError("此行由订单批次创建；请先通过订单详情撤销批次关联")
    # In processing, manual rows can still be removed — they're customer-
    # attribution metadata, not stock-coupled. But a row that has already
    # taken receipts (received_qty > 0) is referenced by HandcraftReceiptItem
    # rows whose FK is non-cascading, so deleting it would raise
    # IntegrityError → 500. Block before we get there and tell the user to
    # revert the receipt first.
    if order.status != "pending" and float(item.received_qty or 0) > 0:
        raise ValueError("此行已有回收记录，不能删除；请先撤销回收单")
    remaining = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order_id,
        HandcraftJewelryItem.id != item_id,
    ).count()
    if remaining == 0:
        raise ValueError(f"Cannot delete the last jewelry from order {order_id}; an order must have at least one jewelry item")
    db.delete(item)
    db.flush()


def delete_handcraft_order(db: Session, order_id: str) -> None:
    from models.handcraft_receipt import HandcraftReceipt, HandcraftReceiptItem
    from sqlalchemy import or_

    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")

    part_items = get_handcraft_parts(db, order_id)
    jewelry_items = get_handcraft_jewelries(db, order_id)

    # Reverse HandcraftReceiptItem stock operations
    part_item_ids = [p.id for p in part_items]
    jewelry_item_ids = [j.id for j in jewelry_items]
    filter_clauses = []
    if part_item_ids:
        filter_clauses.append(HandcraftReceiptItem.handcraft_part_item_id.in_(part_item_ids))
    if jewelry_item_ids:
        filter_clauses.append(HandcraftReceiptItem.handcraft_jewelry_item_id.in_(jewelry_item_ids))

    related_receipt_items = []
    if filter_clauses:
        related_receipt_items = db.query(HandcraftReceiptItem).filter(
            or_(*filter_clauses)
        ).all()

    affected_receipt_ids = {ri.handcraft_receipt_id for ri in related_receipt_items}

    # Block deletion if any related receipt is paid
    for receipt_id in affected_receipt_ids:
        receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
        if receipt and receipt.status == "已付款":
            raise ValueError(f"手工单关联的回收单 {receipt_id} 已付款，无法删除手工单")

    for ri in related_receipt_items:
        if ri.item_type == "part":
            deduct_stock(db, "part", ri.item_id, float(ri.qty), "手工收回撤回")
        else:
            # Part output items have item_type="jewelry" in receipt but
            # actual stock is "part". Check the source HandcraftJewelryItem.
            oi = db.query(HandcraftJewelryItem).filter(
                HandcraftJewelryItem.id == ri.handcraft_jewelry_item_id
            ).first()
            if oi and oi.part_id and not oi.jewelry_id:
                deduct_stock(db, "part", ri.item_id, float(ri.qty), "手工收回撤回")
            else:
                deduct_stock(db, "jewelry", ri.item_id, float(ri.qty), "手工收回撤回")
        db.delete(ri)
    db.flush()

    # Clean up empty receipts, recalc non-empty ones
    for receipt_id in affected_receipt_ids:
        remaining = db.query(HandcraftReceiptItem).filter(
            HandcraftReceiptItem.handcraft_receipt_id == receipt_id
        ).count()
        if remaining == 0:
            receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
            if receipt:
                db.delete(receipt)
        else:
            from services.handcraft_receipt import _recalc_total
            receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
            if receipt:
                _recalc_total(db, receipt)

    # Reverse sent stock for parts. Uses effective qty (actual_qty override
    # when set, pi.qty otherwise) so reversal mirrors what send actually
    # deducted — `part_items` was loaded via get_handcraft_parts, which
    # already attached `actual_qty` to atomic items.
    if order.status != "pending":
        part_totals: dict[str, float] = {}
        for part_item in part_items:
            effective = (
                float(part_item.actual_qty)
                if part_item.actual_qty is not None
                else float(part_item.qty)
            )
            part_totals[part_item.part_id] = part_totals.get(part_item.part_id, 0.0) + effective
        for part_id, total_sent in part_totals.items():
            add_stock(db, "part", part_id, total_sent, "手工发出撤回")

    from models.restock_request import RestockRequest
    db.query(RestockRequest).filter(
        RestockRequest.handcraft_order_id == order_id
    ).delete(synchronize_session=False)
    db.flush()
    db.query(HandcraftPickingRecord).filter(
        HandcraftPickingRecord.handcraft_order_id == order_id
    ).delete(synchronize_session=False)
    db.flush()

    # Clean up non-cascading inbound FKs before bulk-deleting items / the
    # order itself. Three FKs point at things we're about to drop:
    #   - OrderItemLink.handcraft_{part,jewelry}_item_id → rows dropped
    #     (the production assignment they represented dies with the HC)
    #   - OrderTodoBatchJewelry.handcraft_jewelry_item_id → nulled out
    #     so the order batch survives and can be re-scheduled
    #   - OrderTodoBatch.handcraft_order_id → nulled out (same reason;
    #     this is what bites *delete the HandcraftOrder row itself*)
    # Mirrors the cleanup pattern in services.order_todo.delete_batch.
    from models.order import OrderItemLink, OrderTodoBatch, OrderTodoBatchJewelry
    if part_item_ids:
        db.query(OrderItemLink).filter(
            OrderItemLink.handcraft_part_item_id.in_(part_item_ids)
        ).delete(synchronize_session=False)
    if jewelry_item_ids:
        db.query(OrderItemLink).filter(
            OrderItemLink.handcraft_jewelry_item_id.in_(jewelry_item_ids)
        ).delete(synchronize_session=False)
        db.query(OrderTodoBatchJewelry).filter(
            OrderTodoBatchJewelry.handcraft_jewelry_item_id.in_(jewelry_item_ids)
        ).update({"handcraft_jewelry_item_id": None}, synchronize_session=False)
    db.query(OrderTodoBatch).filter(
        OrderTodoBatch.handcraft_order_id == order_id
    ).update({"handcraft_order_id": None}, synchronize_session=False)
    db.flush()

    db.query(HandcraftPartItem).filter(HandcraftPartItem.handcraft_order_id == order_id).delete(synchronize_session=False)
    db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.handcraft_order_id == order_id).delete(synchronize_session=False)
    db.flush()
    db.delete(order)
    db.flush()


_HANDCRAFT_VALID_STATUSES = {"pending", "processing", "completed"}
_HANDCRAFT_STATUS_RANK = {"pending": 0, "processing": 1, "completed": 2}


def update_handcraft_order_status(db: Session, order_id: str, status: str) -> HandcraftOrder:
    if status not in _HANDCRAFT_VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Valid values: {', '.join(sorted(_HANDCRAFT_VALID_STATUSES))}")
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    current = order.status
    if _HANDCRAFT_STATUS_RANK.get(status, -1) <= _HANDCRAFT_STATUS_RANK.get(current, 99):
        raise ValueError(f"Cannot change status from '{current}' to '{status}': only forward transitions are allowed")
    if current == "pending" and status == "processing":
        raise ValueError("Use POST /send to dispatch a pending order; it deducts inventory and updates item statuses")
    if current == "processing" and status == "completed":
        raise ValueError("Use POST /receive to complete a processing order; items must be fully received first")
    order.status = status
    db.flush()
    return order


def list_handcraft_pending_receive_items(
    db: Session,
    keyword: str = None,
    supplier_name: str = None,
    date_on: date_type = None,
    exclude_part_item_ids: list[int] = None,
    exclude_jewelry_item_ids: list[int] = None,
) -> list:
    """Return part items and jewelry items from processing handcraft orders
    that still have remaining qty to receive."""
    results = []

    # Part items. Effective qty = picking actual_qty override when set, else pi.qty.
    effective_qty_expr = handcraft_effective_qty_expr()
    pq = (
        db.query(
            HandcraftPartItem.id,
            HandcraftPartItem.handcraft_order_id,
            HandcraftOrder.supplier_name,
            HandcraftPartItem.part_id.label("item_id"),
            Part.name.label("item_name"),
            Part.image.label("item_image"),
            Part.is_composite.label("is_composite"),
            Part.color,
            effective_qty_expr.label("effective_qty"),
            HandcraftPartItem.received_qty,
            HandcraftPartItem.unit,
            HandcraftOrder.created_at,
        )
        .join(HandcraftOrder, HandcraftPartItem.handcraft_order_id == HandcraftOrder.id)
        .join(Part, HandcraftPartItem.part_id == Part.id)
        .outerjoin(HandcraftPickingWeight, handcraft_atomic_picking_join_clause())
        .filter(
            HandcraftPartItem.status == "制作中",
            func.coalesce(HandcraftPartItem.received_qty, 0) < effective_qty_expr,
        )
    )
    if supplier_name:
        pq = pq.filter(HandcraftOrder.supplier_name == supplier_name)
    if date_on:
        pq = pq.filter(func.cast(HandcraftOrder.created_at, Date) == date_on)
    if exclude_part_item_ids:
        pq = pq.filter(HandcraftPartItem.id.notin_(exclude_part_item_ids))
    clause = keyword_filter(keyword, Part.id, Part.name)
    if clause is not None:
        pq = pq.filter(clause)
    pq = pq.order_by(HandcraftOrder.created_at.desc(), HandcraftOrder.id.desc(), HandcraftPartItem.id.desc())

    for row in pq.all():
        results.append({
            "id": row.id,
            "handcraft_order_id": row.handcraft_order_id,
            "supplier_name": row.supplier_name,
            "item_id": row.item_id,
            "item_name": row.item_name,
            "item_image": row.item_image,
            "item_type": "part",
            "is_output": False,
            "is_composite": row.is_composite,
            "color": row.color,
            "qty": float(row.effective_qty),
            "received_qty": float(row.received_qty or 0),
            "unit": row.unit,
            "created_at": row.created_at,
        })

    # Jewelry/output items (may be jewelry or part output)
    jq = (
        db.query(
            HandcraftJewelryItem.id,
            HandcraftJewelryItem.handcraft_order_id,
            HandcraftOrder.supplier_name,
            HandcraftJewelryItem.jewelry_id,
            HandcraftJewelryItem.part_id,
            Jewelry.name.label("jewelry_name"),
            Jewelry.image.label("jewelry_image"),
            Part.name.label("part_name"),
            Part.image.label("part_image"),
            Part.is_composite.label("part_is_composite"),
            HandcraftJewelryItem.qty,
            HandcraftJewelryItem.received_qty,
            HandcraftJewelryItem.unit,
            HandcraftOrder.created_at,
        )
        .join(HandcraftOrder, HandcraftJewelryItem.handcraft_order_id == HandcraftOrder.id)
        .outerjoin(Jewelry, HandcraftJewelryItem.jewelry_id == Jewelry.id)
        .outerjoin(Part, HandcraftJewelryItem.part_id == Part.id)
        .filter(
            HandcraftJewelryItem.status == "制作中",
            func.coalesce(HandcraftJewelryItem.received_qty, 0) < HandcraftJewelryItem.qty,
        )
    )
    if supplier_name:
        jq = jq.filter(HandcraftOrder.supplier_name == supplier_name)
    if date_on:
        jq = jq.filter(func.cast(HandcraftOrder.created_at, Date) == date_on)
    if exclude_jewelry_item_ids:
        jq = jq.filter(HandcraftJewelryItem.id.notin_(exclude_jewelry_item_ids))
    clause = keyword_filter(
        keyword, Jewelry.id, Jewelry.name, Part.id, Part.name,
    )
    if clause is not None:
        jq = jq.filter(clause)
    jq = jq.order_by(HandcraftOrder.created_at.desc(), HandcraftOrder.id.desc(), HandcraftJewelryItem.id.desc())

    for row in jq.all():
        if row.jewelry_id:
            item_id = row.jewelry_id
            item_name = row.jewelry_name
            item_image = row.jewelry_image
            item_type = "jewelry"
        else:
            item_id = row.part_id
            item_name = row.part_name
            item_image = row.part_image
            item_type = "part"
        results.append({
            "id": row.id,
            "handcraft_order_id": row.handcraft_order_id,
            "supplier_name": row.supplier_name,
            "item_id": item_id,
            "item_name": item_name,
            "item_image": item_image,
            "item_type": item_type,
            "is_output": True,
            "is_composite": bool(row.part_is_composite) if row.part_id else False,
            "color": None,
            "qty": int(row.qty),
            "received_qty": int(row.received_qty or 0),
            "unit": row.unit,
            "created_at": row.created_at,
        })

    # Merge the two sub-query results into a globally sorted list. Each
    # sub-query's order_by only sorts its own rows; without this, rows from
    # an older order's part branch can appear before rows from a newer
    # order's jewelry branch. Python sort is stable, so within a single
    # (created_at, handcraft_order_id) group the part-then-jewelry append
    # order (and each sub-query's internal id-desc order) is preserved.
    results.sort(
        key=lambda r: (r["created_at"], r["handcraft_order_id"]),
        reverse=True,
    )
    return results
