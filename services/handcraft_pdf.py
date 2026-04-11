from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from openpyxl import load_workbook
from PIL import Image as PILImage, UnidentifiedImageError
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFont, stringWidth
from reportlab.pdfgen import canvas

from services.handcraft_export import (
    build_export_filename,
    download_pdf_image_bytes as download_image_bytes,
    format_excel_date,
    get_handcraft_export_payload,
)
from services.plating_excel import _TEMPLATE_PATH

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN_X = 48
_MARGIN_TOP = 32
_MARGIN_BOTTOM = 30
_CONTENT_WIDTH = _PAGE_WIDTH - _MARGIN_X * 2
_FIRST_PAGE_ROW_HEIGHT = 32
_DETAIL_PAGE_ROW_HEIGHT = 32
_DETAIL_PAGE_MAX_ROWS = 23
_HEADER_ROW_HEIGHT = 28
_IMAGE_PADDING = 2
_MAX_IMAGE_HEIGHT = 200
_MIN_IMAGE_HEIGHT = 80
_IMAGE_GAP = 10
_IMAGE_ROW_GAP = 28
_LABEL_FONT = "STSong-Light"
_LABEL_FONT_BOLD = "Helvetica-Bold"


def _compute_image_layout(image_count: int, available_space: float):
    """Return (cols, rows, image_height) or None if images don't fit."""
    if image_count == 0:
        return None

    space = available_space - _IMAGE_GAP
    if space <= 0:
        return None

    if image_count == 1:
        h = min(space, _MAX_IMAGE_HEIGHT)
        return (1, 1, h) if h >= _MIN_IMAGE_HEIGHT else None

    if image_count == 2:
        h_single = (space - _IMAGE_ROW_GAP) / 2
        if h_single >= _MAX_IMAGE_HEIGHT:
            return (1, 2, _MAX_IMAGE_HEIGHT)
        h_double = min(space, _MAX_IMAGE_HEIGHT)
        return (2, 1, h_double) if h_double >= _MIN_IMAGE_HEIGHT else None

    # 3-4 images: 2 columns, 2 rows
    h = (space - _IMAGE_ROW_GAP) / 2
    h = min(h, _MAX_IMAGE_HEIGHT)
    return (2, 2, h) if h >= _MIN_IMAGE_HEIGHT else None


def _max_rows_with_images(image_count: int, total_available: float, row_height: float) -> int:
    """Max data rows that fit while also fitting images."""
    if image_count == 0:
        return int(total_available // row_height)

    max_possible = int(total_available // row_height)
    for rows in range(max_possible, 0, -1):
        remaining = total_available - rows * row_height
        layout = _compute_image_layout(image_count, remaining)
        if layout is not None:
            return rows
    return 0


def build_handcraft_order_pdf(db, order_id: str) -> tuple[bytes, str]:
    payload = get_handcraft_export_payload(db, order_id)
    template_text = _load_template_text()
    _register_fonts()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(build_export_filename(payload["order"].supplier_name, payload["order"].created_at, "pdf"))

    details = payload["details"]
    for i, d in enumerate(details, 1):
        d["seq"] = i
    delivery_images = payload["delivery_images"]
    image_count = len(delivery_images)

    # Measure first-page available space dynamically
    first_page_available = _measure_first_page_available(pdf, payload, template_text)
    detail_page_available = _PAGE_HEIGHT - _MARGIN_TOP - _MARGIN_BOTTOM - _HEADER_ROW_HEIGHT

    first_page_max = _max_rows_with_images(image_count, first_page_available, _FIRST_PAGE_ROW_HEIGHT)

    if len(details) <= first_page_max:
        # All data + images fit on one page
        _draw_detail_page(
            pdf, payload, template_text, details,
            include_static_header=True,
            page_images=delivery_images,
        )
    else:
        remaining_details = list(details)
        page_index = 0
        last_page_images: list[str] = []

        while remaining_details:
            if page_index == 0:
                page_available = first_page_available
                row_h = _FIRST_PAGE_ROW_HEIGHT
                page_size = _max_rows_with_images(0, page_available, row_h)
            else:
                page_available = detail_page_available
                row_h = _DETAIL_PAGE_ROW_HEIGHT
                page_size = _DETAIL_PAGE_MAX_ROWS

            chunk = remaining_details[:page_size]
            remaining_details = remaining_details[page_size:]

            is_last_data_page = len(remaining_details) == 0

            page_images: list[str] = []
            if is_last_data_page and delivery_images:
                rows_used = len(chunk)
                space_left = page_available - rows_used * row_h
                layout = _compute_image_layout(image_count, space_left)
                if layout is not None:
                    page_images = delivery_images

            _draw_detail_page(
                pdf, payload, template_text, chunk,
                include_static_header=(page_index == 0),
                page_images=page_images,
            )
            last_page_images = page_images

            if remaining_details or ((inline_images or dedicated_images) and not page_images and is_last_data_page):
                pdf.showPage()
            page_index += 1

        # If last data page couldn't fit inline images, dedicate a page
        if inline_images and not last_page_images:
            _draw_images_page(pdf, payload, template_text, inline_images)
        # 5+ images always get dedicated pages
        if dedicated_images:
            if last_page_images:
                pdf.showPage()
            _draw_images_page(pdf, payload, template_text, dedicated_images)

    pdf.save()
    return buffer.getvalue(), build_export_filename(payload["order"].supplier_name, payload["order"].created_at, "pdf")


def _measure_first_page_available(pdf, payload: dict, template_text: dict) -> float:
    """Calculate available space on first page after static header + table header."""
    y = _PAGE_HEIGHT - _MARGIN_TOP

    if template_text["logo_bytes"]:
        logo = _fit_image(template_text["logo_bytes"], 116, 38)
        if logo is not None:
            _, _, draw_height = logo
            y -= draw_height + 12

    for line in template_text["header_lines"]:
        if line:
            y -= 14

    y -= 10  # gap before supplier line
    y -= 10  # supplier line to table

    y -= _HEADER_ROW_HEIGHT
    return y - _MARGIN_BOTTOM


def _draw_detail_page(pdf, payload: dict, template_text: dict, details: list[dict],
                      include_static_header: bool, page_images: list[str]) -> None:
    y = _PAGE_HEIGHT - _MARGIN_TOP

    if include_static_header:
        y = _draw_static_header(pdf, payload, template_text, y)
    # No compact header on continuation pages — start directly with table

    table_top = y
    column_widths = _column_widths()
    _draw_table_header(pdf, template_text["detail_headers"], table_top, column_widths)
    y = table_top - _HEADER_ROW_HEIGHT

    row_height = _FIRST_PAGE_ROW_HEIGHT if include_static_header else _DETAIL_PAGE_ROW_HEIGHT
    for detail in details:
        _draw_detail_row(pdf, detail, y, column_widths, row_height)
        y -= row_height

    if page_images:
        image_count = len(page_images)
        remaining_space = y - _MARGIN_BOTTOM
        layout = _compute_image_layout(image_count, remaining_space)
        if layout is not None:
            cols, rows, image_height = layout
            y -= _IMAGE_GAP
            _draw_images_block(pdf, page_images, y, cols, rows, image_height)


def _draw_images_page(pdf, payload: dict, template_text: dict, delivery_images: list[str]) -> None:
    y = _PAGE_HEIGHT - _MARGIN_TOP
    image_count = len(delivery_images)
    available = y - _MARGIN_BOTTOM
    layout = _compute_image_layout(image_count, available)
    if layout is not None:
        cols, rows, image_height = layout
        _draw_images_block(pdf, delivery_images, y, cols, rows, image_height)


def _draw_images_block(pdf, images: list[str], y: float, cols: int, rows: int, image_height: float) -> None:
    """Draw images in a grid layout starting from y downward."""
    gutter = 26
    if cols == 1:
        box_width = _CONTENT_WIDTH
    else:
        box_width = (_CONTENT_WIDTH - gutter) / 2

    for index, source in enumerate(images[:cols * rows]):
        col = index % cols
        row = index // cols
        x = _MARGIN_X + col * (box_width + gutter)
        top_y = y - row * (image_height + _IMAGE_ROW_GAP)
        box_y = top_y - image_height
        _draw_image_in_box(pdf, source, x, box_y, box_width, image_height)


def _draw_static_header(pdf, payload: dict, template_text: dict, y: float) -> float:
    if template_text["logo_bytes"]:
        logo = _fit_image(template_text["logo_bytes"], 116, 38)
        if logo is not None:
            image_reader, draw_width, draw_height = logo
            pdf.drawImage(
                image_reader,
                (_PAGE_WIDTH - draw_width) / 2,
                y - draw_height,
                width=draw_width,
                height=draw_height,
                preserveAspectRatio=True,
                mask="auto",
            )
            y -= draw_height + 12

    pdf.setFont(_LABEL_FONT, 10)
    pdf.setFillColor(colors.black)
    for line in template_text["header_lines"]:
        if line:
            pdf.drawString(_MARGIN_X, y, line)
            y -= 14

    y -= 10
    supplier_text = f"{template_text['customer_prefix']}{payload['order'].supplier_name or ''}"
    date_text = format_excel_date(payload["order"].created_at) or ""
    pdf.setFont(_LABEL_FONT, 10)
    pdf.drawString(_MARGIN_X, y, supplier_text)
    text_width = stringWidth(date_text, _LABEL_FONT, 10)
    pdf.drawString(_PAGE_WIDTH - _MARGIN_X - text_width, y, date_text)
    return y - 10


def _draw_table_header(pdf, headers: list[str], top_y: float, column_widths: list[float]) -> None:
    x = _MARGIN_X
    pdf.setStrokeColor(colors.HexColor("#000000"))
    pdf.setLineWidth(0.5)
    for index, header in enumerate(headers):
        width = column_widths[index]
        pdf.setFillColor(colors.HexColor("#d9d9d9"))
        pdf.rect(x, top_y - _HEADER_ROW_HEIGHT, width, _HEADER_ROW_HEIGHT, stroke=1, fill=1)
        _draw_header_text(pdf, header, x + 4, top_y - _HEADER_ROW_HEIGHT + 3, width - 8, _HEADER_ROW_HEIGHT - 6)
        x += width


def _draw_detail_row(pdf, detail: dict, top_y: float, column_widths: list[float], row_height: float) -> None:
    x = _MARGIN_X
    pdf.setStrokeColor(colors.HexColor("#000000"))
    pdf.setLineWidth(0.5)
    pdf.setFillColor(colors.white)
    for width in column_widths:
        pdf.rect(x, top_y - row_height, width, row_height, stroke=1, fill=0)
        x += width

    cells = _cell_positions(column_widths, top_y, row_height)
    pdf.setFillColor(colors.black)
    _draw_centered_text(pdf, str(detail.get("seq", "")), *cells[0], font_size=10)
    _draw_centered_paragraph(pdf, detail["name"] or detail["part_id"], *cells[1], font_size=10, max_lines=2)
    _draw_image_in_box(pdf, detail["part_image"], *cells[2])
    _draw_centered_text(pdf, detail["plating_method"], *cells[3], font_size=10)
    _draw_centered_text(pdf, detail["qty_text"], *cells[4], font_size=10)
    _draw_centered_text(pdf, detail["unit"], *cells[5], font_size=10)
    _draw_centered_paragraph(pdf, detail["note"], *cells[6], font_size=10, max_lines=2)


def _draw_image_in_box(pdf, source: str, x: float, y: float, width: float, height: float) -> None:
    image_bytes = download_image_bytes(source)
    if not image_bytes:
        return
    placement = _fit_image(image_bytes, width - _IMAGE_PADDING * 2, height - _IMAGE_PADDING * 2)
    if placement is None:
        return

    image_reader, draw_width, draw_height = placement
    offset_x = x + (width - draw_width) / 2
    offset_y = y + (height - draw_height) / 2
    pdf.drawImage(
        image_reader,
        offset_x,
        offset_y,
        width=draw_width,
        height=draw_height,
        preserveAspectRatio=True,
        mask="auto",
    )


def _fit_image(image_bytes: bytes, max_width: float, max_height: float):
    try:
        with PILImage.open(BytesIO(image_bytes)) as raw_image:
            image = raw_image.copy()
    except (UnidentifiedImageError, OSError):
        return None

    img_width, img_height = image.size
    if img_width <= 0 or img_height <= 0:
        return None

    scale = min(max_width / img_width, max_height / img_height)
    draw_width = max(1, img_width * scale)
    draw_height = max(1, img_height * scale)
    return ImageReader(BytesIO(image_bytes)), draw_width, draw_height


def _draw_centered_text(pdf, text: str, x: float, y: float, width: float, height: float, font_size: int) -> None:
    lines = simpleSplit(text or "", _LABEL_FONT, font_size, max(width, 1))[:2]
    if not lines:
        return
    pdf.setFont(_LABEL_FONT, font_size)
    total_height = len(lines) * (font_size + 2)
    current_y = y + (height + total_height) / 2 - font_size
    for line in lines:
        line_width = stringWidth(line, _LABEL_FONT, font_size)
        pdf.drawString(x + max(0, (width - line_width) / 2), current_y, line)
        current_y -= font_size + 2


def _draw_centered_paragraph(pdf, text: str, x: float, y: float, width: float, height: float, font_size: int, max_lines: int) -> None:
    lines = simpleSplit(text or "", _LABEL_FONT, font_size, max(width - 6, 1))[:max_lines]
    if not lines:
        return
    pdf.setFont(_LABEL_FONT, font_size)
    line_gap = font_size + 2
    total_height = len(lines) * line_gap
    current_y = y + (height + total_height) / 2 - font_size
    for line in lines:
        line_width = stringWidth(line, _LABEL_FONT, font_size)
        pdf.drawString(x + max(0, (width - line_width) / 2), current_y, line)
        current_y -= line_gap


def _cell_positions(column_widths: list[float], top_y: float, row_height: float) -> list[tuple[float, float, float, float]]:
    positions = []
    x = _MARGIN_X
    for width in column_widths:
        positions.append((x, top_y - row_height, width, row_height))
        x += width
    return positions


def _column_widths() -> list[float]:
    raw_widths = [6.0, 36.375, 18.6923, 18.6923, 13.0, 13.0, 62.4904]
    total = sum(raw_widths)
    scaled = [(_CONTENT_WIDTH * value / total) for value in raw_widths]
    scaled[-1] = _CONTENT_WIDTH - sum(scaled[:-1])
    return scaled


@lru_cache(maxsize=1)
def _load_template_text() -> dict:
    workbook = load_workbook(_TEMPLATE_PATH, data_only=True)
    sheet = workbook.active
    header_lines = [sheet["A2"].value or "", sheet["A3"].value or "", sheet["A4"].value or ""]
    detail_headers = ["序号"] + [sheet.cell(row=7, column=column).value or "" for column in range(1, 7)]
    customer_prefix = sheet["A6"].value or "顾客: "
    delivery_title = sheet["A13"].value or "发货图片："
    logo_bytes = None
    images = getattr(sheet, "_images", [])
    if images:
        try:
            logo_bytes = images[0]._data()
        except Exception:
            logo_bytes = None
    workbook.close()
    return {
        "header_lines": header_lines,
        "detail_headers": detail_headers,
        "customer_prefix": customer_prefix,
        "delivery_title": delivery_title,
        "logo_bytes": logo_bytes,
    }


@lru_cache(maxsize=1)
def _register_fonts() -> bool:
    registerFont(UnicodeCIDFont(_LABEL_FONT))
    return True


def _draw_header_text(pdf, text: str, x: float, y: float, width: float, height: float) -> None:
    parts = (text or "").split("\n", 1)
    title = parts[0] if parts else ""
    subtitle = parts[1] if len(parts) > 1 else ""

    if title:
        pdf.setFont(_LABEL_FONT, 8)
        pdf.setFillColor(colors.black)
        title_width = stringWidth(title, _LABEL_FONT, 8)
        pdf.drawString(x + max(0, (width - title_width) / 2), y + height - 13, title)

    if subtitle:
        pdf.setFont("Helvetica", 4.5)
        pdf.setFillColor(colors.black)
        subtitle_width = stringWidth(subtitle, "Helvetica", 4.5)
        pdf.drawString(x + max(0, (width - subtitle_width) / 2), y + 4, subtitle)
