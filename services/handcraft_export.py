from sqlalchemy.orm import Session

from models.handcraft_order import HandcraftPartItem
from models.part import Part
from services.handcraft import get_handcraft_order
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
        weight = float(item.weight) if item.weight is not None else None
        weight_unit = item.weight_unit or "g"
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
                "note": item.note or "",
            }
        )

    return {
        "order": order,
        "details": detail_rows,
        "delivery_images": list(order.delivery_images or []),
    }


__all__ = [
    "build_export_filename",
    "download_image_bytes",
    "download_pdf_image_bytes",
    "format_excel_date",
    "format_short_date",
    "get_handcraft_export_payload",
    "sanitize_filename_part",
]
