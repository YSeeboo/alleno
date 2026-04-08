from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional

from sqlalchemy.orm import Session

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


def detect_handcraft_jewelry_cost_diffs(db: Session, receipt) -> list[dict]:
    """Detect handcraft_cost diffs for jewelry items in a handcraft receipt."""
    from models.jewelry import Jewelry

    price_map: Dict[str, Optional[float]] = {}
    for ri in receipt.items:
        if ri.item_type != "jewelry" or ri.price is None:
            continue
        price_map[ri.item_id] = float(ri.price)

    diffs = []
    for jewelry_id, new_price in price_map.items():
        jewelry = db.get(Jewelry, jewelry_id)
        if jewelry is None:
            continue
        current = float(jewelry.handcraft_cost) if jewelry.handcraft_cost is not None else None
        if _compare(current, new_price):
            diffs.append({
                "part_id": jewelry_id,       # 复用 CostDiffItem 结构，part_id 字段存 jewelry_id
                "part_name": jewelry.name,
                "field": "handcraft_cost",
                "current_value": current,
                "new_value": new_price,
            })
    return diffs


def auto_set_initial_handcraft_cost(db: Session, jewelry_id: str, price: float) -> None:
    """Sync handcraft receipt jewelry price to Jewelry.handcraft_cost."""
    from models.jewelry import Jewelry
    jewelry = db.get(Jewelry, jewelry_id)
    if jewelry is None:
        return
    new_value = Decimal(str(price)).quantize(_Q7, rounding=ROUND_HALF_UP)
    current = Decimal(str(jewelry.handcraft_cost)).quantize(_Q7, rounding=ROUND_HALF_UP) if jewelry.handcraft_cost is not None else None
    if current == new_value:
        return
    jewelry.handcraft_cost = new_value
    db.flush()


def auto_set_initial_assembly_cost(db: Session, part_id: str, price: float) -> None:
    """Sync handcraft receipt part-output price to Part.assembly_cost and recalc unit_cost."""
    part = db.get(Part, part_id)
    if part is None:
        return
    new_value = Decimal(str(price)).quantize(_Q7, rounding=ROUND_HALF_UP)
    current = Decimal(str(part.assembly_cost)).quantize(_Q7, rounding=ROUND_HALF_UP) if part.assembly_cost is not None else None
    if current == new_value:
        return
    part.assembly_cost = new_value
    db.flush()
    from services.part_bom import recalc_part_unit_cost
    recalc_part_unit_cost(db, part_id)


def detect_handcraft_assembly_cost_diffs(db: Session, receipt) -> list[dict]:
    """Detect assembly_cost diffs for part output items in a handcraft receipt."""
    from models.handcraft_order import HandcraftJewelryItem

    diffs = []
    for ri in receipt.items:
        if ri.handcraft_jewelry_item_id is None or ri.price is None:
            continue
        oi = db.get(HandcraftJewelryItem, ri.handcraft_jewelry_item_id)
        if oi is None or not oi.part_id:
            continue
        part = db.get(Part, oi.part_id)
        if part is None:
            continue
        new_price = float(ri.price)
        current = float(part.assembly_cost) if part.assembly_cost is not None else None
        if _compare(current, new_price):
            diffs.append({
                "part_id": oi.part_id,
                "part_name": part.name,
                "field": "assembly_cost",
                "current_value": current,
                "new_value": new_price,
            })
    return diffs


def detect_handcraft_bead_cost_diffs(db: Session, receipt) -> list[dict]:
    """Detect bead_cost diffs for part items in a handcraft receipt."""
    price_map: Dict[str, Optional[float]] = {}
    for ri in receipt.items:
        if ri.item_type != "part" or ri.price is None:
            continue
        price_map[ri.item_id] = float(ri.price)

    diffs = []
    for part_id, new_price in price_map.items():
        part = db.get(Part, part_id)
        if part is None:
            continue
        current = float(part.bead_cost) if part.bead_cost is not None else None
        if _compare(current, new_price):
            diffs.append({
                "part_id": part_id,
                "part_name": part.name,
                "field": "bead_cost",
                "current_value": current,
                "new_value": new_price,
            })
    return diffs
