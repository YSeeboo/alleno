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
# 配件编号(70) 配件(195) 需要(60) 建议(60) 库存(60) 完成(70)
_COL_W = [70, 195, 60, 60, 60, 70]
_HEADERS = ["配件编号", "配件", "需要", "建议", "库存", "完成"]


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
    _register_fonts()
    sim = get_handcraft_picking_simulation(db, handcraft_order_id)
    groups = _filter_groups(sim.groups, include_picked=include_picked)
    if not groups:
        raise ValueError("无可导出内容")

    image_urls = [r.part_image for g in groups for r in g.rows if r.part_image]
    image_cache = prefetch_images(image_urls)

    buf = BytesIO()
    c = _NumberedCanvas(buf, pagesize=A4)

    title = f"手工单配货清单 — {sim.handcraft_order_id}"
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
        # Group header row (light blue background)
        c.setFillColor(colors.HexColor("#eef3fb"))
        c.rect(_MARGIN_X, y - _GROUP_HEADER_H, _CONTENT_WIDTH, _GROUP_HEADER_H, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont(_FONT, 9)
        composite_tag = " [组合]" if g.parent_is_composite else ""
        bom_tag = f"  理论 {_fmt_qty(g.parent_bom_qty)}" if g.parent_bom_qty is not None else ""
        text = (
            f"{g.parent_part_id}  {g.parent_part_name}{composite_tag}"
            f"  × {_fmt_qty(g.parent_qty)}{bom_tag}"
        )
        c.drawString(_MARGIN_X + 8, y - _GROUP_HEADER_H + 8, text)
        y -= _GROUP_HEADER_H

        for r in g.rows:
            _ensure_space(_ROW_H)
            # Row border
            c.setFillColor(colors.white)
            c.rect(_MARGIN_X, y - _ROW_H, _CONTENT_WIDTH, _ROW_H, fill=0, stroke=1)
            x = _MARGIN_X

            # Col 0: 配件编号
            c.setFillColor(colors.black)
            c.setFont(_FONT, 9)
            c.drawString(x + 4, y - _ROW_H / 2 - 3, r.part_id)
            x += _COL_W[0]

            # Col 1: 配件 (image + name)
            if r.part_image and r.part_image in image_cache and image_cache[r.part_image]:
                placement = fit_image(image_cache[r.part_image], _IMAGE_SIZE, _IMAGE_SIZE)
                if placement is not None:
                    reader, draw_w, draw_h = placement
                    img_x = x + 4
                    img_y = y - _ROW_H + (_ROW_H - draw_h) / 2
                    c.drawImage(reader, img_x, img_y, width=draw_w, height=draw_h,
                                preserveAspectRatio=True, mask="auto")
            c.setFillColor(colors.black)
            c.drawString(x + 4 + _IMAGE_SIZE + 6, y - _ROW_H / 2 - 3, r.part_name)
            x += _COL_W[1]

            # Col 2: 需要
            c.drawString(x + 4, y - _ROW_H / 2 - 3, _fmt_qty(r.needed_qty))
            x += _COL_W[2]

            # Col 3: 建议 (blue)
            sug = "-" if r.suggested_qty is None else str(r.suggested_qty)
            c.setFillColor(colors.HexColor("#1890ff"))
            c.drawString(x + 4, y - _ROW_H / 2 - 3, sug)
            c.setFillColor(colors.black)
            x += _COL_W[3]

            # Col 4: 库存 (red if insufficient)
            stock_color = (
                colors.HexColor("#d03050")
                if r.current_stock < r.needed_qty
                else colors.black
            )
            c.setFillColor(stock_color)
            c.drawString(x + 4, y - _ROW_H / 2 - 3, _fmt_qty(r.current_stock))
            c.setFillColor(colors.black)
            x += _COL_W[4]

            # Col 5: 完成 (checkbox, crossed if already picked)
            box_size = 12
            box_x = x + (_COL_W[5] - box_size) / 2
            box_y = y - _ROW_H / 2 - 6
            c.rect(box_x, box_y, box_size, box_size, fill=0, stroke=1)
            if r.picked:
                c.line(box_x, box_y, box_x + box_size, box_y + box_size)
                c.line(box_x + box_size, box_y, box_x, box_y + box_size)

            y -= _ROW_H

    c.save()
    pdf_bytes = buf.getvalue()
    buf.close()
    filename = f"手工单配货清单-{handcraft_order_id}.pdf"
    return pdf_bytes, filename
