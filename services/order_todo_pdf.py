"""Generate a PDF for the order todo-list (配件清单), designed for print-based picking."""

from __future__ import annotations

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

from services.order_todo import get_todo
from services.plating_export import download_pdf_image_bytes

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN_X = 48
_MARGIN_TOP = 36
_MARGIN_BOTTOM = 30
_CONTENT_WIDTH = _PAGE_WIDTH - _MARGIN_X * 2
_ROW_HEIGHT = 48
_HEADER_ROW_HEIGHT = 26
_IMAGE_PADDING = 2
_FONT = "STSong-Light"

# Columns: 序号, 配件编号, 图片, 配件名称, 需要数量, 库存数量, 缺口, 完成
_COL_RATIOS = [5, 16, 12, 24, 10, 10, 9, 10]


@lru_cache(maxsize=1)
def _register_fonts() -> bool:
    registerFont(UnicodeCIDFont(_FONT))
    return True


def _col_widths() -> list[float]:
    total = sum(_COL_RATIOS)
    widths = [_CONTENT_WIDTH * r / total for r in _COL_RATIOS]
    widths[-1] = _CONTENT_WIDTH - sum(widths[:-1])
    return widths


def build_order_todo_pdf(
    db: Session,
    order_id: str,
    customer_name: str,
    created_at,
    batch_id: int | None = None,
    supplier_name: str | None = None,
) -> tuple[bytes, str]:
    _register_fonts()

    if batch_id is not None:
        from services.order_todo import get_batches
        batches = get_batches(db, order_id)
        batch_data = next((b for b in batches if b["id"] == batch_id), None)
        if not batch_data:
            raise ValueError(f"批次 {batch_id} 不存在")
        todos = batch_data["items"]
        if not supplier_name and batch_data.get("supplier_name"):
            supplier_name = batch_data["supplier_name"]
    else:
        todos = get_todo(db, order_id)

    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    filename = f"配件清单_{order_id}.pdf"
    pdf.setTitle(filename)

    col_widths = _col_widths()
    headers = ["序号", "配件编号", "图片", "配件名称", "需要数量", "库存数量", "缺口", "完成"]

    # Calculate header height
    header_block_h = 60  # title + info line + gap
    if supplier_name:
        header_block_h += 16

    first_page_available = _PAGE_HEIGHT - _MARGIN_TOP - _MARGIN_BOTTOM - header_block_h - _HEADER_ROW_HEIGHT
    rows_per_page_first = int(first_page_available // _ROW_HEIGHT)

    rest_available = _PAGE_HEIGHT - _MARGIN_TOP - _MARGIN_BOTTOM - _HEADER_ROW_HEIGHT
    rows_per_page_rest = int(rest_available // _ROW_HEIGHT)

    page = 0
    idx = 0
    while idx < len(todos) or page == 0:
        if page > 0:
            pdf.showPage()

        y = _PAGE_HEIGHT - _MARGIN_TOP

        if page == 0:
            y = _draw_header(pdf, y, order_id, customer_name, created_at, supplier_name)

        # Table header
        _draw_table_header(pdf, headers, y, col_widths)
        y -= _HEADER_ROW_HEIGHT

        max_rows = rows_per_page_first if page == 0 else rows_per_page_rest
        count = 0
        while idx < len(todos) and count < max_rows:
            todo = todos[idx]
            _draw_row(pdf, todo, idx + 1, y, col_widths)
            y -= _ROW_HEIGHT
            idx += 1
            count += 1

        page += 1

    pdf.save()
    return buf.getvalue(), filename


def _draw_header(pdf, y: float, order_id: str, customer_name: str, created_at, supplier_name: str | None = None) -> float:
    # Title
    pdf.setFont(_FONT, 16)
    pdf.setFillColor(colors.black)
    title = "配件清单"
    tw = stringWidth(title, _FONT, 16)
    pdf.drawString((_PAGE_WIDTH - tw) / 2, y, title)
    y -= 24

    # Info line: order_id, customer, date
    pdf.setFont(_FONT, 10)
    date_str = ""
    if created_at:
        try:
            date_str = created_at.strftime("%Y-%m-%d")
        except Exception:
            date_str = str(created_at)[:10]

    info = f"订单号: {order_id}    客户: {customer_name or '-'}    创建时间: {date_str}"
    pdf.drawString(_MARGIN_X, y, info)
    y -= 20

    if supplier_name:
        pdf.setFont(_FONT, 9)
        pdf.drawString(_MARGIN_X, y, f"指定手工：{supplier_name}")
        y -= 16

    return y


def _draw_table_header(pdf, headers: list[str], top_y: float, col_widths: list[float]) -> None:
    x = _MARGIN_X
    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(0.5)
    for i, hdr in enumerate(headers):
        w = col_widths[i]
        pdf.setFillColor(colors.HexColor("#e8e8e8"))
        pdf.rect(x, top_y - _HEADER_ROW_HEIGHT, w, _HEADER_ROW_HEIGHT, stroke=1, fill=1)
        pdf.setFillColor(colors.black)
        pdf.setFont(_FONT, 9)
        tw = stringWidth(hdr, _FONT, 9)
        pdf.drawString(x + (w - tw) / 2, top_y - _HEADER_ROW_HEIGHT + 8, hdr)
        x += w


def _draw_row(pdf, todo: dict, seq: int, top_y: float, col_widths: list[float]) -> None:
    x = _MARGIN_X
    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(0.5)

    # Draw cell borders
    for w in col_widths:
        pdf.rect(x, top_y - _ROW_HEIGHT, w, _ROW_HEIGHT, stroke=1, fill=0)
        x += w

    cells = []
    cx = _MARGIN_X
    for w in col_widths:
        cells.append((cx, top_y - _ROW_HEIGHT, w, _ROW_HEIGHT))
        cx += w

    pdf.setFillColor(colors.black)
    pdf.setFont(_FONT, 9)

    # 序号
    _centered(pdf, str(seq), *cells[0])
    # 配件编号
    _centered(pdf, todo.get("part_id", ""), *cells[1])
    # 图片
    _draw_image_in_box(pdf, todo.get("part_image", ""), *cells[2])
    # 配件名称 - may need wrapping
    _centered_wrap(pdf, todo.get("part_name", "") or "", *cells[3])
    # 需要数量
    _centered(pdf, _fmt_qty(todo.get("required_qty")), *cells[4])
    # 库存数量
    _centered(pdf, _fmt_qty(todo.get("stock_qty")), *cells[5])
    # 缺口
    gap = todo.get("gap", 0)
    gap_text = _fmt_qty(gap) if gap and gap > 0 else "0"
    _centered(pdf, gap_text, *cells[6])
    # 完成 - draw checkbox
    _draw_checkbox(pdf, *cells[7])


def _centered(pdf, text: str, x: float, y: float, w: float, h: float) -> None:
    pdf.setFont(_FONT, 9)
    tw = stringWidth(text or "", _FONT, 9)
    pdf.drawString(x + (w - tw) / 2, y + h / 2 - 4, text or "")


def _centered_wrap(pdf, text: str, x: float, y: float, w: float, h: float) -> None:
    pdf.setFont(_FONT, 9)
    lines = simpleSplit(text or "", _FONT, 9, max(w - 6, 1))[:2]
    if not lines:
        return
    line_h = 12
    total_h = len(lines) * line_h
    cy = y + (h + total_h) / 2 - 9
    for line in lines:
        tw = stringWidth(line, _FONT, 9)
        pdf.drawString(x + (w - tw) / 2, cy, line)
        cy -= line_h


def _draw_checkbox(pdf, x: float, y: float, w: float, h: float) -> None:
    """Draw an empty square checkbox centered in the cell."""
    box_size = 12
    bx = x + (w - box_size) / 2
    by = y + (h - box_size) / 2
    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(0.8)
    pdf.rect(bx, by, box_size, box_size, stroke=1, fill=0)


def _draw_image_in_box(pdf, source: str, x: float, y: float, w: float, h: float) -> None:
    """Download and draw a part image centered in the cell."""
    image_bytes = download_pdf_image_bytes(source)
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
            raw.copy()  # validate
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
