"""Generate a printable picking list PDF for 配货模拟.

Layout: A4, 45×45pt images, 7 columns (配件编号 / 配件 / 单份 / 份数 /
总数量 / 库存 / 完成). Part rows with multiple variants use ReportLab row
spans. By default, already-picked rows are filtered out — the PDF is a
to-do list."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFont, stringWidth
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from schemas.order import PickingPartRow
from services._pdf_helpers import prefetch_images, fit_image
from services.picking import get_picking_simulation
from time_utils import now_beijing

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN_X = 40
_MARGIN_TOP = 36
_MARGIN_BOTTOM = 30
_CONTENT_WIDTH = _PAGE_WIDTH - _MARGIN_X * 2  # 515pt
_IMAGE_SIZE = 45
_ROW_MIN_H = 55
_VARIANT_ROW_H = 20  # inner row under a part when it has >1 variant
_HEADER_ROW_H = 24
_FONT = "STSong-Light"

_FOOTER_FONT_SIZE = 8
_FOOTER_COLOR = colors.HexColor("#888888")
_FOOTER_RIGHT_TEXT = "Allen Shop · 饰品店管理系统"


class _NumberedCanvas(canvas.Canvas):
    """ReportLab Canvas subclass that stamps 第 N / M 页 footers on all pages."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        # showPage() is called between pages but NOT after the last page,
        # so the last page's state is still "current". Capture it now.
        self._saved_page_states.append(dict(self.__dict__))
        total = len(self._saved_page_states)
        for i, state in enumerate(self._saved_page_states, 1):
            self.__dict__.update(state)
            self._draw_page_footer(i, total)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_page_footer(self, page_num: int, total: int) -> None:
        self.saveState()
        self.setFont(_FONT, _FOOTER_FONT_SIZE)
        self.setFillColor(_FOOTER_COLOR)
        footer_y = _MARGIN_BOTTOM - 16
        left_text = f"第 {page_num} / {total} 页"
        self.drawString(_MARGIN_X, footer_y, left_text)
        right_tw = stringWidth(_FOOTER_RIGHT_TEXT, _FONT, _FOOTER_FONT_SIZE)
        self.drawString(_PAGE_WIDTH - _MARGIN_X - right_tw, footer_y, _FOOTER_RIGHT_TEXT)
        self.restoreState()

# Column widths (7 columns), sum = 515pt
_COL_W = [55, 185, 45, 45, 60, 55, 70]
_HEADERS = ["配件编号", "配件", "单份", "份数", "总数量", "库存", "完成"]


@lru_cache(maxsize=1)
def _register_fonts() -> bool:
    registerFont(UnicodeCIDFont(_FONT))
    return True


def build_picking_list_pdf(
    db: Session,
    order_id: str,
    customer_name: str,
    include_picked: bool = False,
) -> tuple[bytes, str]:
    """Build the picking list PDF. Raises ValueError when there is nothing
    to pick (empty order, or all variants picked and include_picked=False)."""
    _register_fonts()

    sim = get_picking_simulation(db, order_id)
    rows = _filter_rows(sim.rows, include_picked=include_picked)
    if not rows:
        raise ValueError("没有需要配货的配件")

    image_cache = prefetch_images(r.part_image for r in rows)

    buf = BytesIO()
    pdf = _NumberedCanvas(buf, pagesize=A4)
    filename = f"配货清单_{order_id}.pdf"
    pdf.setTitle(filename)

    _render(pdf, rows, order_id, customer_name, image_cache)

    pdf.save()
    return buf.getvalue(), filename


def _filter_rows(
    rows: list[PickingPartRow], include_picked: bool
) -> list[PickingPartRow]:
    """When include_picked=False: drop variants that are picked; drop parts
    with no variants left."""
    if include_picked:
        return list(rows)

    out: list[PickingPartRow] = []
    for r in rows:
        remaining = [v for v in r.variants if not v.picked]
        if not remaining:
            continue
        out.append(
            PickingPartRow(
                part_id=r.part_id,
                part_name=r.part_name,
                part_image=r.part_image,
                current_stock=r.current_stock,
                is_composite_child=r.is_composite_child,
                variants=remaining,
                total_required=round(sum(v.subtotal for v in remaining), 10),
            )
        )
    return out


def _render(pdf, rows, order_id, customer_name, image_cache):
    """Draw the title block, table header, and each part's row(s). Handles
    page breaks when the next part won't fit."""
    y = _PAGE_HEIGHT - _MARGIN_TOP
    y = _draw_title_block(pdf, y, order_id, customer_name, len(rows))
    y = _draw_table_header(pdf, y)

    for row in rows:
        needed = _row_height(row)
        if y - needed < _MARGIN_BOTTOM:
            pdf.showPage()
            y = _PAGE_HEIGHT - _MARGIN_TOP
            y = _draw_table_header(pdf, y)
        _draw_part_row(pdf, row, y, image_cache)
        y -= needed


def _row_height(row: PickingPartRow) -> float:
    n = len(row.variants)
    if n <= 1:
        return _ROW_MIN_H
    # First variant shares the image row; each extra variant adds a thin row.
    return _ROW_MIN_H + (n - 1) * _VARIANT_ROW_H


def _draw_title_block(pdf, y, order_id, customer_name, part_count) -> float:
    pdf.setFont(_FONT, 14)
    pdf.setFillColor(colors.black)
    title = f"配货清单 · 订单 {order_id}"
    pdf.drawString(_MARGIN_X, y - 12, title)
    pdf.setFont(_FONT, 9)
    date_str = now_beijing().strftime("%Y-%m-%d %H:%M")
    pdf.drawString(_MARGIN_X, y - 28,
                   f"客户: {customer_name or '-'}    生成时间: {date_str}    共 {part_count} 配件")
    return y - 40


def _draw_table_header(pdf, y) -> float:
    x = _MARGIN_X
    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(0.5)
    for w, hdr in zip(_COL_W, _HEADERS):
        pdf.setFillColor(colors.HexColor("#e8e8e8"))
        pdf.rect(x, y - _HEADER_ROW_H, w, _HEADER_ROW_H, stroke=1, fill=1)
        pdf.setFillColor(colors.black)
        pdf.setFont(_FONT, 9)
        tw = stringWidth(hdr, _FONT, 9)
        pdf.drawString(x + (w - tw) / 2, y - _HEADER_ROW_H + 8, hdr)
        x += w
    return y - _HEADER_ROW_H


def _draw_part_row(pdf, row: PickingPartRow, top_y: float, image_cache: dict[str, bytes]) -> None:
    """Draw a part spanning 1+ variant rows. part_id / part / stock / (first
    variant's completion box) sit in the top row; extra variants add thin
    rows with their own 单份/份数/总数 + empty 完成 box."""
    height = _row_height(row)
    x = _MARGIN_X

    # Draw the outer cell borders for the FIRST row of the part (spans full image).
    # For spanned columns (配件编号, 配件, 库存), draw as a single tall cell.
    col_xs = []
    cx = x
    for w in _COL_W:
        col_xs.append(cx)
        cx += w

    # Column 0 (配件编号), col 1 (配件), col 5 (库存) span the whole part height.
    for col_idx in (0, 1, 5):
        pdf.setStrokeColor(colors.black)
        pdf.setLineWidth(0.5)
        pdf.rect(col_xs[col_idx], top_y - height, _COL_W[col_idx], height,
                 stroke=1, fill=0)

    # For columns 2, 3, 4, 6 — each variant gets its own cell (variant slice).
    # First variant sits at the top of the part (height = _ROW_MIN_H); extra
    # variants sit below with _VARIANT_ROW_H each.
    variant_y = top_y
    for i, v in enumerate(row.variants):
        slice_h = _ROW_MIN_H if i == 0 else _VARIANT_ROW_H
        for col_idx in (2, 3, 4, 6):
            pdf.rect(col_xs[col_idx], variant_y - slice_h, _COL_W[col_idx],
                     slice_h, stroke=1, fill=0)
        _draw_variant_values(pdf, v, col_xs, variant_y, slice_h)
        variant_y -= slice_h

    # Fill the spanning columns' text + image.
    _draw_spanning_values(pdf, row, col_xs, top_y, height, image_cache)


def _draw_variant_values(pdf, v, col_xs, variant_top_y, h):
    """单份, 份数, 总数量, 完成(empty)."""
    pdf.setFillColor(colors.black)
    _centered(pdf, _fmt_qty(v.qty_per_unit), col_xs[2], variant_top_y - h,
              _COL_W[2], h, size=10)
    _centered(pdf, str(v.units_count), col_xs[3], variant_top_y - h,
              _COL_W[3], h, size=10)
    _centered(pdf, _fmt_qty(v.subtotal), col_xs[4], variant_top_y - h,
              _COL_W[4], h, size=10, bold=True)
    # Empty checkbox in the 完成 column.
    box_size = 12
    cx = col_xs[6] + (_COL_W[6] - box_size) / 2
    cy = variant_top_y - h + (h - box_size) / 2
    pdf.rect(cx, cy, box_size, box_size, stroke=1, fill=0)


def _draw_spanning_values(pdf, row, col_xs, top_y, height, image_cache):
    # 配件编号 (col 0)
    _centered(pdf, row.part_id, col_xs[0], top_y - height, _COL_W[0], height, size=9)
    # 配件 (col 1): image + name
    img_bytes = image_cache.get(row.part_image or "") if row.part_image else None
    _draw_image_in_cell(pdf, img_bytes, col_xs[1], top_y - height, _COL_W[1], height)
    _draw_name_in_cell(pdf, row, col_xs[1], top_y - height, _COL_W[1], height)
    # 库存 (col 5)
    _centered(pdf, _fmt_qty(row.current_stock), col_xs[5], top_y - height,
              _COL_W[5], height, size=10)


def _draw_image_in_cell(pdf, image_bytes, x, y, w, h):
    if not image_bytes:
        return
    placement = fit_image(image_bytes, _IMAGE_SIZE, _IMAGE_SIZE)
    if placement is None:
        return
    reader, draw_w, draw_h = placement
    # Place image on the left; name wraps on the right.
    offset_x = x + 4
    offset_y = y + (h - draw_h) / 2
    pdf.drawImage(reader, offset_x, offset_y, width=draw_w, height=draw_h,
                  preserveAspectRatio=True, mask="auto")


def _draw_name_in_cell(pdf, row, x, y, w, h):
    text_x = x + _IMAGE_SIZE + 10
    text_w = w - _IMAGE_SIZE - 14
    pdf.setFont(_FONT, 10)
    name = row.part_name
    if row.is_composite_child:
        name = f"{name} [组合]"
    lines = simpleSplit(name, _FONT, 10, max(text_w, 1))[:3]
    if not lines:
        return
    line_h = 13
    total_h = len(lines) * line_h
    cy = y + (h + total_h) / 2 - 10
    for line in lines:
        pdf.drawString(text_x, cy, line)
        cy -= line_h


def _centered(pdf, text, x, y, w, h, size=10, bold=False):
    pdf.setFont(_FONT, size)
    s = text or ""
    tw = stringWidth(s, _FONT, size)
    pdf.drawString(x + (w - tw) / 2, y + h / 2 - size / 2 + 1, s)


def _fmt_qty(v) -> str:
    if v is None:
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == int(f):
        return str(int(f))
    return f"{f:g}"
