from sqlalchemy.orm import Session

from models.handcraft_order import HandcraftPartItem
from models.part import Part
from models.restock_request import RestockRequest
from services.handcraft import get_handcraft_order
from services.handcraft_picking_weight import sum_weight_by_part_item
from services.plating_export import (
    build_export_filename,
    download_image_bytes,
    download_pdf_image_bytes,
    format_excel_date,
    format_qty_text,
    format_short_date,
    sanitize_filename_part,
)


def get_handcraft_export_payload(db: Session, order_id: str) -> dict:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")

    items = (
        db.query(HandcraftPartItem)
        .filter(HandcraftPartItem.handcraft_order_id == order_id)
        .order_by(HandcraftPartItem.id.asc())
        .all()
    )
    part_ids = sorted({item.part_id for item in items})
    parts = {
        part.id: part
        for part in db.query(Part).filter(Part.id.in_(part_ids)).all()
    }

    detail_rows = []
    for item in items:
        part = parts.get(item.part_id)
        qty = float(item.qty) if item.qty is not None else None
        # Weight now lives in handcraft_picking_weight (per atom). SUM normalizes
        # to kg across mixed units, so the display unit is always kg.
        weight = sum_weight_by_part_item(db, item.id, target_unit="kg")
        weight_unit = "kg"
        weight_text = f"{format_qty_text(weight)} {weight_unit}" if weight is not None else ""
        detail_rows.append(
            {
                "part_id": item.part_id,
                "name": part.name if part else item.part_id,
                "part_image": part.image if part else "",
                "plating_method": part.color if part and part.color else "",
                "qty": qty,
                "qty_text": format_qty_text(qty),
                "unit": item.unit or "",
                "weight_text": weight_text,
                "note": item.note or "",
            }
        )

    shortage_rows = _build_shortage_rows(db, order_id)

    return {
        "order": order,
        "details": detail_rows,
        "delivery_images": list(order.delivery_images or []),
        "shortage_rows": shortage_rows,
    }


def _build_shortage_rows(db: Session, order_id: str) -> list[dict]:
    """Pending restock records for this handcraft order, joined with Part for
    name/image/color. Sorted by creation time. Empty list when nothing pending.

    Raises ValueError if any pending row has a null shortfall_qty — the export
    is gated behind a fully-filled 差额 column so suppliers don't receive
    incomplete shortage notices.
    """
    rows = (
        db.query(
            RestockRequest.id,
            RestockRequest.part_id,
            RestockRequest.shortfall_qty,
            RestockRequest.note,
            RestockRequest.created_at,
            Part.name,
            Part.image,
            Part.color,
        )
        .join(Part, Part.id == RestockRequest.part_id)
        .filter(
            RestockRequest.handcraft_order_id == order_id,
            RestockRequest.status == "pending",
        )
        .order_by(RestockRequest.created_at.asc(), RestockRequest.id.asc())
        .all()
    )
    if not rows:
        return []

    missing = [r.part_id for r in rows if r.shortfall_qty is None]
    if missing:
        raise ValueError(
            "以下配件未填写差额：" + ", ".join(missing) + "，请先填写后再导出"
        )

    return [
        {
            "seq": idx,
            "part_id": r.part_id,
            "name": r.name or r.part_id,
            "part_image": r.image or "",
            "color": r.color or "",
            "qty": float(r.shortfall_qty),
            "note": r.note or "",
        }
        for idx, r in enumerate(rows, start=1)
    ]


__all__ = [
    "build_export_filename",
    "download_image_bytes",
    "download_pdf_image_bytes",
    "format_excel_date",
    "format_short_date",
    "get_handcraft_export_payload",
    "sanitize_filename_part",
]
