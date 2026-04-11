"""Generate a PDF for the order parts summary (配件汇总), with large images for picking."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from io import BytesIO

from PIL import Image as PILImage, UnidentifiedImageError
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFont, stringWidth
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from services.order import get_parts_summary
from services.plating_export import download_pdf_image_bytes
from time_utils import now_beijing

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN_X = 48
_MARGIN_TOP = 36
_MARGIN_BOTTOM = 30
_CONTENT_WIDTH = _PAGE_WIDTH - _MARGIN_X * 2
_ROW_HEIGHT = 80
_HEADER_ROW_HEIGHT = 26
_IMAGE_PADDING = 3
_FONT = "STSong-Light"

# Columns: 配件编号, 图片, 配件名称, 总需求量, 剩余需求量
_COL_RATIOS = [18, 18, 38, 13, 13]
_HEADERS = ["配件编号", "图片", "配件名称", "总需求量", "剩余需求量"]


@lru_cache(maxsize=1)
def _register_fonts() -> bool:
    registerFont(UnicodeCIDFont(_FONT))
    return True


def _col_widths() -> list[float]:
    total = sum(_COL_RATIOS)
    widths = [_CONTENT_WIDTH * r / total for r in _COL_RATIOS]
    widths[-1] = _CONTENT_WIDTH - sum(widths[:-1])
    return widths


def build_parts_summary_pdf(
    db: Session,
    order_id: str,
    customer_name: str,
    part_ids: list[str] | None = None,
) -> tuple[bytes, str]:
    """Build a parts summary PDF. If part_ids is given, only those rows are rendered,
    preserving the order of the list (so frontend-side sorting/filtering is honored).

    Raises ValueError if the final row set is empty — callers should surface this
    to the user rather than returning a blank PDF (prevents silent data loss when
    the frontend state is stale or the caller sends wrong ids)."""
    _register_fonts()

    summary = get_parts_summary(db, order_id)
    if part_ids is not None:
        # Dedupe while preserving the caller's order.
        requested = list(dict.fromkeys(part_ids))
        summary_ids = {r["part_id"] for r in summary}
        missing = [pid for pid in requested if pid not in summary_ids]
        if missing:
            # Reject on ANY missing id, not just "all missing". A partial
            # mismatch usually means the frontend state is stale (e.g. BOM
            # changed after the table was loaded) — silently dropping rows
            # would give the user a PDF that looks complete but isn't.
            shown = ", ".join(missing[:5])
            more = f" 等 {len(missing)} 项" if len(missing) > 5 else ""
            raise ValueError(f"以下配件不在订单配件汇总中: {shown}{more}")
        wanted = set(requested)
        rows = [r for r in summary if r.get("part_id") in wanted]
        order_map = {pid: i for i, pid in enumerate(requested)}
        rows.sort(key=lambda r: order_map[r["part_id"]])
    else:
        rows = list(summary)

    if not rows:
        raise ValueError("没有可导出的配件（订单配件汇总为空）")

    # Prefetch images concurrently once, deduped by URL. This bounds worst-case
    # latency to roughly one download-timeout instead of N × timeout, and avoids
    # re-downloading the same image when multiple rows share it.
    image_cache = _prefetch_images(rows)

    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    filename = f"配件汇总_{order_id}.pdf"
    pdf.setTitle(filename)

    col_widths = _col_widths()

    header_block_h = 60  # title + info line + small gap
    first_page_available = (
        _PAGE_HEIGHT - _MARGIN_TOP - _MARGIN_BOTTOM - header_block_h - _HEADER_ROW_HEIGHT
    )
    rows_per_page_first = max(1, int(first_page_available // _ROW_HEIGHT))
    rest_available = _PAGE_HEIGHT - _MARGIN_TOP - _MARGIN_BOTTOM - _HEADER_ROW_HEIGHT
    rows_per_page_rest = max(1, int(rest_available // _ROW_HEIGHT))

    page = 0
    idx = 0
    while idx < len(rows) or page == 0:
        if page > 0:
            pdf.showPage()
        y = _PAGE_HEIGHT - _MARGIN_TOP

        if page == 0:
            y = _draw_header(pdf, y, order_id, customer_name)

        _draw_table_header(pdf, y, col_widths)
        y -= _HEADER_ROW_HEIGHT

        max_rows = rows_per_page_first if page == 0 else rows_per_page_rest
        count = 0
        while idx < len(rows) and count < max_rows:
            _draw_row(pdf, rows[idx], y, col_widths, image_cache)
            y -= _ROW_HEIGHT
            idx += 1
            count += 1
        page += 1

    pdf.save()
    return buf.getvalue(), filename


def _prefetch_images(rows: list[dict]) -> dict[str, bytes]:
    """Download all unique part_image URLs concurrently. Returns {url: bytes}.
    Failed downloads map to empty bytes (rendered as missing image)."""
    urls = {r.get("part_image") for r in rows if r.get("part_image")}
    if not urls:
        return {}
    cache: dict[str, bytes] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(urls))) as pool:
        for url, data in zip(urls, pool.map(_safe_download, urls)):
            cache[url] = data or b""
    return cache


def _safe_download(url: str) -> bytes | None:
    try:
        return download_pdf_image_bytes(url)
    except Exception:
        return None


def _draw_header(pdf, y: float, order_id: str, customer_name: str) -> float:
    pdf.setFont(_FONT, 16)
    pdf.setFillColor(colors.black)
    title = "配件汇总"
    tw = stringWidth(title, _FONT, 16)
    pdf.drawString((_PAGE_WIDTH - tw) / 2, y, title)
    y -= 24

    pdf.setFont(_FONT, 10)
    date_str = now_beijing().strftime("%Y-%m-%d %H:%M")
    info = f"订单号: {order_id}    客户: {customer_name or '-'}    生成时间: {date_str}"
    pdf.drawString(_MARGIN_X, y, info)
    y -= 20
    return y


def _draw_table_header(pdf, top_y: float, col_widths: list[float]) -> None:
    x = _MARGIN_X
    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(0.5)
    for i, hdr in enumerate(_HEADERS):
        w = col_widths[i]
        pdf.setFillColor(colors.HexColor("#e8e8e8"))
        pdf.rect(x, top_y - _HEADER_ROW_HEIGHT, w, _HEADER_ROW_HEIGHT, stroke=1, fill=1)
        pdf.setFillColor(colors.black)
        pdf.setFont(_FONT, 10)
        tw = stringWidth(hdr, _FONT, 10)
        pdf.drawString(x + (w - tw) / 2, top_y - _HEADER_ROW_HEIGHT + 9, hdr)
        x += w


def _draw_row(
    pdf,
    row: dict,
    top_y: float,
    col_widths: list[float],
    image_cache: dict[str, bytes],
) -> None:
    x = _MARGIN_X
    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(0.5)
    for w in col_widths:
        pdf.rect(x, top_y - _ROW_HEIGHT, w, _ROW_HEIGHT, stroke=1, fill=0)
        x += w

    cells = []
    cx = _MARGIN_X
    for w in col_widths:
        cells.append((cx, top_y - _ROW_HEIGHT, w, _ROW_HEIGHT))
        cx += w

    pdf.setFillColor(colors.black)

    image_url = row.get("part_image") or ""
    image_bytes = image_cache.get(image_url) if image_url else None

    _centered(pdf, row.get("part_id", ""), *cells[0], font_size=10)
    _draw_image_in_box(pdf, image_bytes, *cells[1])
    _centered_wrap(pdf, row.get("part_name") or "", *cells[2])
    _centered(pdf, _fmt_qty(row.get("total_qty")), *cells[3], font_size=11)
    _centered(pdf, _fmt_qty(row.get("remaining_qty")), *cells[4], font_size=11)


def _centered(pdf, text: str, x: float, y: float, w: float, h: float, font_size: int = 10) -> None:
    pdf.setFont(_FONT, font_size)
    tw = stringWidth(text or "", _FONT, font_size)
    pdf.drawString(x + (w - tw) / 2, y + h / 2 - font_size / 2 + 1, text or "")


def _centered_wrap(pdf, text: str, x: float, y: float, w: float, h: float) -> None:
    font_size = 10
    pdf.setFont(_FONT, font_size)
    lines = simpleSplit(text or "", _FONT, font_size, max(w - 8, 1))[:3]
    if not lines:
        return
    line_h = 13
    total_h = len(lines) * line_h
    cy = y + (h + total_h) / 2 - font_size
    for line in lines:
        tw = stringWidth(line, _FONT, font_size)
        pdf.drawString(x + (w - tw) / 2, cy, line)
        cy -= line_h


def _draw_image_in_box(pdf, image_bytes: bytes | None, x: float, y: float, w: float, h: float) -> None:
    if not image_bytes:
        return
    placement = _fit_image(image_bytes, w - _IMAGE_PADDING * 2, h - _IMAGE_PADDING * 2)
    if placement is None:
        return
    image_reader, draw_w, draw_h = placement
    offset_x = x + (w - draw_w) / 2
    offset_y = y + (h - draw_h) / 2
    pdf.drawImage(
        image_reader, offset_x, offset_y,
        width=draw_w, height=draw_h,
        preserveAspectRatio=True, mask="auto",
    )


def _fit_image(image_bytes: bytes, max_w: float, max_h: float):
    try:
        with PILImage.open(BytesIO(image_bytes)) as raw:
            raw.copy()
    except (UnidentifiedImageError, OSError):
        return None
    reader = ImageReader(BytesIO(image_bytes))
    img_w, img_h = reader.getSize()
    if img_w <= 0 or img_h <= 0:
        return None
    scale = min(max_w / img_w, max_h / img_h)
    return reader, max(1, img_w * scale), max(1, img_h * scale)


def _fmt_qty(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)
