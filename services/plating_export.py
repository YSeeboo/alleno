from __future__ import annotations

from datetime import datetime
import re
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from models.part import Part
from models.plating_order import PlatingOrderItem
from services.image_processing import prepare_pdf_image_bytes
from services.plating import get_plating_order


def get_plating_export_payload(db: Session, order_id: str) -> dict:
    order = get_plating_order(db, order_id)
    if order is None:
        raise ValueError(f"PlatingOrder not found: {order_id}")

    items = (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == order_id)
        .order_by(PlatingOrderItem.id.asc())
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
                "plating_method": item.plating_method or "",
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


def build_export_filename(supplier_name: str | None, created_at: datetime | None, extension: str) -> str:
    safe_supplier_name = sanitize_filename_part(supplier_name) or "未命名电镀厂"
    short_date = format_short_date(created_at)
    return f"发出_{safe_supplier_name}_{short_date}.{extension.lstrip('.')}"


def format_excel_date(created_at: datetime | None) -> str | None:
    if not created_at:
        return None
    return f"{created_at.year:04d}年 {created_at.month:02d}月 {created_at.day:02d}日"


def format_short_date(created_at: datetime | None) -> str:
    if not created_at:
        return "000000"
    year = created_at.year % 100
    return f"{year:02d}{created_at.month:02d}{created_at.day:02d}"


def sanitize_filename_part(value: str | None) -> str:
    cleaned = re.sub(r'[\\\\/:*?"<>|]+', "_", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned


def download_image_bytes(source: str) -> bytes | None:
    if not source:
        return None

    request = Request(str(source).strip(), headers={"User-Agent": "Allen-Shop/1.0"})
    try:
        with urlopen(request, timeout=10) as response:
            return response.read()
    except Exception:
        return None


def download_pdf_image_bytes(source: str) -> bytes | None:
    return prepare_pdf_image_bytes(download_image_bytes(source))


def format_qty_text(value: float | None) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")
