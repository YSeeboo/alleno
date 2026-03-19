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
_CONTENT_WIDTH = _PAGE_WIDTH - _MARGIN_X * 2
_FIRST_PAGE_ROW_HEIGHT = 32
_DETAIL_PAGE_ROW_HEIGHT = 32
_FIRST_PAGE_MAX_ROWS_WITH_IMAGES = 10
_FIRST_PAGE_MAX_ROWS = 14
_DETAIL_PAGE_MAX_ROWS = 16
_HEADER_ROW_HEIGHT = 28
_IMAGE_PADDING = 2
_LABEL_FONT = "STSong-Light"
_LABEL_FONT_BOLD = "Helvetica-Bold"


def build_handcraft_order_pdf(db, order_id: str) -> tuple[bytes, str]:
    payload = get_handcraft_export_payload(db, order_id)
    template_text = _load_template_text()
    _register_fonts()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(build_export_filename(payload["order"].supplier_name, payload["order"].created_at, "pdf"))

    details = payload["details"]
    delivery_images = payload["delivery_images"]

    if len(details) <= _FIRST_PAGE_MAX_ROWS_WITH_IMAGES:
        first_page_images = delivery_images[:2] if len(delivery_images) >= 3 else delivery_images
        _draw_detail_page(
            pdf,
            payload,
            template_text,
            details,
            include_static_header=True,
            page_title=None,
            page_images=first_page_images,
        )
        remaining_images = delivery_images[len(first_page_images):]
        if remaining_images:
            pdf.showPage()
            _draw_images_page(pdf, payload, template_text, remaining_images)
    else:
        remaining_details = list(details)
        page_index = 0
        while remaining_details:
            page_size = _FIRST_PAGE_MAX_ROWS if page_index == 0 else _DETAIL_PAGE_MAX_ROWS
            chunk = remaining_details[:page_size]
            remaining_details = remaining_details[page_size:]
            _draw_detail_page(
                pdf,
                payload,
                template_text,
                chunk,
                include_static_header=page_index == 0,
                page_title="手工单明细（续）" if page_index > 0 else None,
                page_images=[],
            )
            if remaining_details:
                pdf.showPage()
            page_index += 1

        if delivery_images:
            pdf.showPage()
            _draw_images_page(pdf, payload, template_text, delivery_images)

    pdf.save()
    return buffer.getvalue(), build_export_filename(payload["order"].supplier_name, payload["order"].created_at, "pdf")


def _draw_detail_page(pdf, payload: dict, template_text: dict, details: list[dict], include_static_header: bool, page_title: str | None, page_images: list[str]) -> None:
    y = _PAGE_HEIGHT - _MARGIN_TOP

    if include_static_header:
        y = _draw_static_header(pdf, payload, template_text, y)
    else:
        y = _draw_compact_header(pdf, payload, page_title or "手工单明细", y)

    if page_title and include_static_header:
        pdf.setFont(_LABEL_FONT, 12)
        pdf.drawString(_MARGIN_X, y, page_title)
        y -= 18

    table_top = y
    column_widths = _column_widths()
    _draw_table_header(pdf, template_text["detail_headers"], table_top, column_widths)
    y = table_top - _HEADER_ROW_HEIGHT

    row_height = _FIRST_PAGE_ROW_HEIGHT if include_static_header else _DETAIL_PAGE_ROW_HEIGHT
    for detail in details:
        _draw_detail_row(pdf, detail, y, column_widths, row_height)
        y -= row_height

    if page_images:
        y -= 30
        _draw_delivery_images_block(pdf, template_text["delivery_title"], page_images, y)


def _draw_images_page(pdf, payload: dict, template_text: dict, delivery_images: list[str]) -> None:
    y = _PAGE_HEIGHT - 72
    _draw_delivery_images_block(pdf, template_text["delivery_title"], delivery_images, y)


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


def _draw_compact_header(pdf, payload: dict, title: str, y: float) -> float:
    pdf.setFont(_LABEL_FONT_BOLD, 13)
    pdf.setFillColor(colors.black)
    pdf.drawString(_MARGIN_X, y, title)
    y -= 18
    pdf.setFont(_LABEL_FONT, 10)
    supplier_text = f"手工厂：{payload['order'].supplier_name or ''}"
    date_text = format_excel_date(payload["order"].created_at) or ""
    pdf.drawString(_MARGIN_X, y, supplier_text)
    text_width = stringWidth(date_text, _LABEL_FONT, 10)
    pdf.drawString(_PAGE_WIDTH - _MARGIN_X - text_width, y, date_text)
    return y - 16


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
    _draw_centered_paragraph(pdf, detail["name"] or detail["part_id"], *cells[0], font_size=10, max_lines=2)
    _draw_image_in_box(pdf, detail["part_image"], *cells[1])
    _draw_centered_text(pdf, detail["plating_method"], *cells[2], font_size=10)
    _draw_centered_text(pdf, detail["qty_text"], *cells[3], font_size=10)
    _draw_centered_text(pdf, detail["unit"], *cells[4], font_size=10)
    _draw_centered_paragraph(pdf, detail["note"], *cells[5], font_size=10, max_lines=2)


def _draw_delivery_images_block(pdf, title: str, delivery_images: list[str], y: float) -> None:
    pdf.setFont(_LABEL_FONT, 22)
    pdf.setFillColor(colors.black)
    pdf.drawString(_MARGIN_X, y, title)
    y -= 26

    columns = 2
    rows = 1 if len(delivery_images) <= 2 else 2
    gutter = 26
    box_width = (_CONTENT_WIDTH - gutter) / 2
    box_height = 170 if rows == 1 else 135

    for index, source in enumerate(delivery_images[:4]):
        col = index % columns
        row = index // columns
        x = _MARGIN_X + col * (box_width + gutter)
        top_y = y - row * (box_height + 28)
        box_y = top_y - box_height
        _draw_image_in_box(pdf, source, x, box_y, box_width, box_height)


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
    raw_widths = [36.375, 18.6923, 18.6923, 13.0, 13.0, 62.4904]
    total = sum(raw_widths)
    scaled = [(_CONTENT_WIDTH * value / total) for value in raw_widths]
    scaled[-1] = _CONTENT_WIDTH - sum(scaled[:-1])
    return scaled


@lru_cache(maxsize=1)
def _load_template_text() -> dict:
    workbook = load_workbook(_TEMPLATE_PATH, data_only=True)
    sheet = workbook.active
    header_lines = [sheet["A2"].value or "", sheet["A3"].value or "", sheet["A4"].value or ""]
    detail_headers = [sheet.cell(row=7, column=column).value or "" for column in range(1, 7)]
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
