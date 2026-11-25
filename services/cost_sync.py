from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, Optional

from sqlalchemy.orm import Session

from models.handcraft_order import HandcraftJewelryItem
from models.handcraft_receipt import HandcraftReceiptItem
from models.jewelry import Jewelry
from models.part import Part
from models.purchase_order import PurchaseOrder, PurchaseOrderItem, PurchaseOrderItemAddon
from services.part import update_part_cost

_Q7 = Decimal("0.0000001")


def _compare(current_value, new_value) -> bool:
    """Return True if values differ. None vs 0 counts as different."""
    if current_value is None and new_value is None:
        return False
    if current_value is None or new_value is None:
        return True
    cur = Decimal(str(current_value)).quantize(_Q7, rounding=ROUND_HALF_UP)
    new = Decimal(str(new_value)).quantize(_Q7, rounding=ROUND_HALF_UP)
    return cur != new


def _build_purchase_price_map(order: PurchaseOrder) -> Dict[str, Optional[float]]:
    """Last row wins: track every row including price=None."""
    price_map: Dict[str, Optional[float]] = {}
    for item in order.items:
        price_map[item.part_id] = float(item.price) if item.price is not None else None
    return price_map


def auto_set_initial_purchase_costs(db: Session, order: PurchaseOrder) -> None:
    """Sync purchase_cost for all parts in order, using last-row-wins."""
    price_map = _build_purchase_price_map(order)
    for part_id, new_price in price_map.items():
        if new_price is None:
            continue
        part = db.get(Part, part_id)
        if part is None:
            continue
        update_part_cost(db, part_id, "purchase_cost", new_price, source_id=order.id)


def detect_purchase_cost_diffs(db: Session, order: PurchaseOrder) -> list[dict]:
    price_map = _build_purchase_price_map(order)
    diffs = []
    for part_id, new_price in price_map.items():
        if new_price is None:
            continue
        part = db.get(Part, part_id)
        if part is None:
            continue
        current = float(part.purchase_cost) if part.purchase_cost is not None else None
        if _compare(current, new_price):
            diffs.append({
                "part_id": part_id,
                "part_name": part.name,
                "field": "purchase_cost",
                "current_value": current,
                "new_value": new_price,
            })
    return diffs


def detect_addon_cost_diffs(
    db: Session, item: PurchaseOrderItem, addon: PurchaseOrderItemAddon,
) -> list[dict]:
    if addon.type != "bead_stringing":
        return []

    part = db.get(Part, item.part_id)
    if part is None:
        return []

    new_value = float(addon.unit_cost)
    current = float(part.bead_cost) if part.bead_cost is not None else None

    if _compare(current, new_value):
        return [{
            "part_id": item.part_id,
            "part_name": part.name,
            "field": "bead_cost",
            "current_value": current,
            "new_value": new_value,
        }]
    return []


def auto_set_initial_purchase_cost(db: Session, item: PurchaseOrderItem, source_id: Optional[str] = None) -> None:
    """Sync item price to part purchase_cost. Skips if price is None or same value."""
    if item.price is None:
        return
    part = db.get(Part, item.part_id)
    if part is None:
        return
    update_part_cost(db, item.part_id, "purchase_cost", float(item.price), source_id=source_id)


def auto_set_initial_bead_cost(db: Session, item: PurchaseOrderItem, addon: PurchaseOrderItemAddon, source_id: Optional[str] = None) -> None:
    """Sync addon unit_cost to part bead_cost. Skips if not bead_stringing or same value."""
    if addon.type != "bead_stringing":
        return
    part = db.get(Part, item.part_id)
    if part is None:
        return
    update_part_cost(db, item.part_id, "bead_cost", float(addon.unit_cost), source_id=source_id)


def detect_plating_cost_diffs(db: Session, receipt) -> list[dict]:
    from models.plating_order import PlatingOrderItem

    # Last row wins: track every row including price=None
    price_map: Dict[str, Optional[float]] = {}
    for ri in receipt.items:
        poi = db.get(PlatingOrderItem, ri.plating_order_item_id)
        if poi is None:
            continue
        receive_id = poi.receive_part_id or poi.part_id
        price_map[receive_id] = float(ri.price) if ri.price is not None else None

    diffs = []
    for part_id, new_price in price_map.items():
        if new_price is None:
            continue
        part = db.get(Part, part_id)
        if part is None:
            continue
        current = float(part.plating_cost) if part.plating_cost is not None else None
        if _compare(current, new_price):
            diffs.append({
                "part_id": part_id,
                "part_name": part.name,
                "field": "plating_cost",
                "current_value": current,
                "new_value": new_price,
            })
    return diffs


def prepare_handcraft_receipt_cost_updates(
    db: Session, items: Iterable[HandcraftReceiptItem], receipt_id: str,
) -> list[dict]:
    """Initialize unset output costs; return existing cost changes for confirmation."""
    prices: dict[tuple[str, str], Decimal] = {}
    for item in items:
        # Material returns never update costs. Both kinds of output use "jewelry".
        if item.item_type != "jewelry" or item.price is None or item.handcraft_jewelry_item_id is None:
            continue
        output = db.get(HandcraftJewelryItem, item.handcraft_jewelry_item_id)
        if output is None:
            continue
        # The last priced row for the same output wins.
        if output.jewelry_id:
            prices["handcraft_cost", output.jewelry_id] = item.price
        elif output.part_id:
            prices["assembly_cost", output.part_id] = item.price

    diffs = []
    for (field, item_id), new_price in prices.items():
        model = Part if field == "assembly_cost" else Jewelry
        target = db.get(model, item_id)
        if target is None:
            continue
        current = getattr(target, field)
        if current is None:
            # Recheck under a row lock so a concurrent cost write isn't overwritten.
            db.refresh(target, with_for_update={"key_share": True})
            current = getattr(target, field)
            if current is None:
                update_part_cost(db, item_id, field, float(new_price), source_id=receipt_id)
                continue
        if _compare(current, new_price):
            diffs.append({
                "part_id": item_id,  # Also carries jewelry IDs for handcraft_cost.
                "part_name": target.name,
                "field": field,
                "current_value": float(current),
                "new_value": float(new_price),
            })
    return diffs
