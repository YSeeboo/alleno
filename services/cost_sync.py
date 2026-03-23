from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from models.part import Part
from models.purchase_order import PurchaseOrder, PurchaseOrderItem, PurchaseOrderItemAddon

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


def detect_purchase_cost_diffs(db: Session, order: PurchaseOrder) -> list[dict]:
    price_map = {}
    for item in order.items:
        if item.price is not None:
            price_map[item.part_id] = float(item.price)

    diffs = []
    for part_id, new_price in price_map.items():
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


def detect_plating_cost_diffs(db: Session, receipt) -> list[dict]:
    from models.plating_order import PlatingOrderItem

    price_map = {}
    for ri in receipt.items:
        if ri.price is None:
            continue
        poi = db.get(PlatingOrderItem, ri.plating_order_item_id)
        if poi is None:
            continue
        receive_id = poi.receive_part_id or poi.part_id
        price_map[receive_id] = float(ri.price)

    diffs = []
    for part_id, new_price in price_map.items():
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
