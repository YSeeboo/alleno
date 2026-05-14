"""Generate a printable picking list PDF for handcraft 配货模拟.

Layout: A4, 45×45pt images. Each handcraft_part_item is rendered as a
section: a header row showing the part_item's parent part + qty, followed
by one or more atom rows. By default, already-picked rows are filtered out.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFont, stringWidth
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from services._pdf_helpers import prefetch_images, fit_image
from services.handcraft_picking import get_handcraft_picking_simulation
from time_utils import now_beijing

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN_X = 40
_MARGIN_TOP = 36
_MARGIN_BOTTOM = 30
_CONTENT_WIDTH = _PAGE_WIDTH - _MARGIN_X * 2  # 515pt
_IMAGE_SIZE = 45
_GROUP_HEADER_H = 22
_ROW_H = 50
_HEADER_ROW_H = 24
_FONT = "STSong-Light"

_FOOTER_FONT_SIZE = 8
_FOOTER_COLOR = colors.HexColor("#888888")
_FOOTER_RIGHT_TEXT = "Allen Shop · 饰品店管理系统"

# Column widths sum to 515pt:
# 配件编号(60) 配件(175) 重量(60) 实际(55) 建议(55) 库存(55) 完成(55)
_COL_W = [60, 175, 60, 55, 55, 55, 55]
_HEADERS = ["配件编号", "配件", "重量", "实际", "建议", "库存", "完成"]


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


@lru_cache(maxsize=1)
def _register_fonts() -> bool:
    registerFont(UnicodeCIDFont(_FONT))
    return True


def _filter_groups(groups, include_picked: bool):
    """When include_picked=False, drop rows that are already picked.
    Groups with no remaining rows are dropped entirely."""
    if include_picked:
        return groups
    out = []
    for g in groups:
        rows = [r for r in g.rows if not r.picked]
        if rows:
            out.append(g.model_copy(update={"rows": rows}))
    return out


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


def build_handcraft_picking_list_pdf(
    db: Session,
    handcraft_order_id: str,
    include_picked: bool = False,
) -> tuple[bytes, str]:
    """Build the PDF. Returns (bytes, suggested_filename). Raises ValueError if
    nothing to export (empty order, or all rows picked & include_picked=False)."""
    from models.handcraft_order import HandcraftOrder
    _register_fonts()
    sim = get_handcraft_picking_simulation(db, handcraft_order_id)
    groups = _filter_groups(sim.groups, include_picked=include_picked)
    if not groups:
        raise ValueError("无可导出内容")

    # Supplier-facing PDF: opaque receipt_code instead of the sequential HC id.
    hc = db.query(HandcraftOrder).filter_by(id=handcraft_order_id).one()
    receipt_code = hc.receipt_code

    image_urls = [g.atom_part_image for g in groups if g.atom_part_image]
    image_cache = prefetch_images(image_urls)

    buf = BytesIO()
    c = _NumberedCanvas(buf, pagesize=A4)

    title = f"手工单配货清单 — 回执编号 {receipt_code}"
    subtitle = (
        f"商家: {sim.supplier_name}    "
        f"导出时间: {now_beijing().strftime('%Y-%m-%d %H:%M')}"
    )

    y = _PAGE_HEIGHT - _MARGIN_TOP

    def _draw_title():
        nonlocal y
        c.setFont(_FONT, 14)
        c.setFillColor(colors.black)
        c.drawString(_MARGIN_X, y, title)
        y -= 18
        c.setFont(_FONT, 9)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawString(_MARGIN_X, y, subtitle)
        y -= 14

    def _draw_table_header():
        nonlocal y
        c.setFillColor(colors.HexColor("#fafbfc"))
        c.rect(_MARGIN_X, y - _HEADER_ROW_H, _CONTENT_WIDTH, _HEADER_ROW_H, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont(_FONT, 9)
        x = _MARGIN_X
        for i, label in enumerate(_HEADERS):
            tw = stringWidth(label, _FONT, 9)
            c.drawString(x + (_COL_W[i] - tw) / 2, y - _HEADER_ROW_H + 8, label)
            x += _COL_W[i]
        y -= _HEADER_ROW_H

    def _ensure_space(needed: float):
        nonlocal y
        if y - needed < _MARGIN_BOTTOM + 30:
            c.showPage()
            y = _PAGE_HEIGHT - _MARGIN_TOP
            _draw_title()
            _draw_table_header()

    _draw_title()
    _draw_table_header()

    for g in groups:
        _ensure_space(_GROUP_HEADER_H)
        # Group header row (light blue background): atom-level summary.
        c.setFillColor(colors.HexColor("#eef3fb"))
        c.rect(_MARGIN_X, y - _GROUP_HEADER_H, _CONTENT_WIDTH, _GROUP_HEADER_H, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont(_FONT, 9)
        header_text = (
            f"{g.atom_part_id}  {g.atom_part_name}"
            f"  合计 {_fmt_qty(g.total_needed_qty)}"
            f"  建议 {g.total_suggested_qty}"
            f"  库存 {_fmt_qty(g.current_stock)}"
        )
        c.drawString(_MARGIN_X + 8, y - _GROUP_HEADER_H + 8, header_text)
        y -= _GROUP_HEADER_H

        for r in g.rows:
            _ensure_space(_ROW_H)
            # Row border
            c.setFillColor(colors.white)
            c.rect(_MARGIN_X, y - _ROW_H, _CONTENT_WIDTH, _ROW_H, fill=0, stroke=1)
            x = _MARGIN_X

            # Col 0: 配件编号 (atom)
            c.setFillColor(colors.black)
            c.setFont(_FONT, 9)
            c.drawString(x + 4, y - _ROW_H / 2 - 3, g.atom_part_id)
            x += _COL_W[0]

            # Col 1: 配件 (image + name; from group, with composite parent annotation)
            if g.atom_part_image and g.atom_part_image in image_cache and image_cache[g.atom_part_image]:
                placement = fit_image(image_cache[g.atom_part_image], _IMAGE_SIZE, _IMAGE_SIZE)
                if placement is not None:
                    reader, draw_w, draw_h = placement
                    img_x = x + 4
                    img_y = y - _ROW_H + (_ROW_H - draw_h) / 2
                    c.drawImage(reader, img_x, img_y, width=draw_w, height=draw_h,
                                preserveAspectRatio=True, mask="auto")
            c.setFillColor(colors.black)
            label = g.atom_part_name
            if r.is_composite_expansion and r.parent_composite_name:
                label = f"{label}  ←{r.parent_composite_name}"
            c.drawString(x + 4 + _IMAGE_SIZE + 6, y - _ROW_H / 2 - 3, label)
            x += _COL_W[1]

            # Col 2: 重量
            if r.weight is None:
                weight_text = "—"
            else:
                weight_text = f"{_fmt_qty(r.weight)} {r.weight_unit or ''}".strip()
            c.drawString(x + 4, y - _ROW_H / 2 - 3, weight_text)
            x += _COL_W[2]

            # Col 3: 实际 — actual_qty if user overrode, else needed_qty
            actual_or_needed = r.actual_qty if r.actual_qty is not None else r.needed_qty
            c.drawString(x + 4, y - _ROW_H / 2 - 3, _fmt_qty(actual_or_needed))
            x += _COL_W[3]

            # Col 4: 建议 (blue)
            sug = "-" if r.suggested_qty is None else str(r.suggested_qty)
            c.setFillColor(colors.HexColor("#1890ff"))
            c.drawString(x + 4, y - _ROW_H / 2 - 3, sug)
            c.setFillColor(colors.black)
            x += _COL_W[4]

            # Col 5: 库存 (red if insufficient — group-level threshold to
            # match the picking modal's stock-low coloring)
            stock_color = (
                colors.HexColor("#d03050")
                if g.current_stock < g.total_suggested_qty
                else colors.black
            )
            c.setFillColor(stock_color)
            c.drawString(x + 4, y - _ROW_H / 2 - 3, _fmt_qty(g.current_stock))
            c.setFillColor(colors.black)
            x += _COL_W[5]

            # Col 6: 完成 (checkbox, crossed if already picked)
            box_size = 12
            box_x = x + (_COL_W[6] - box_size) / 2
            box_y = y - _ROW_H / 2 - 6
            c.rect(box_x, box_y, box_size, box_size, fill=0, stroke=1)
            if r.picked:
                c.line(box_x, box_y, box_x + box_size, box_y + box_size)
                c.line(box_x + box_size, box_y, box_x, box_y + box_size)

            y -= _ROW_H

    c.save()
    pdf_bytes = buf.getvalue()
    buf.close()
    filename = f"手工单配货清单-{receipt_code}.pdf"
    return pdf_bytes, filename
