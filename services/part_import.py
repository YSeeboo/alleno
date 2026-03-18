from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import posixpath
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from zipfile import BadZipFile, ZipFile

from sqlalchemy.orm import Session

from models.part import Part
from services.inventory import add_stock
from services.part import PART_CATEGORIES, create_part, get_part, update_part

_XML_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
_CELL_REF_RE = re.compile(r"([A-Z]+)")

_HEADER_ALIASES = {
    "配件编号": "part_id",
    "编号": "part_id",
    "id": "part_id",
    "partid": "part_id",
    "part_id": "part_id",
    "名称": "name",
    "配件名称": "name",
    "name": "name",
    "类目": "category",
    "分类": "category",
    "category": "category",
    "颜色": "color",
    "color": "color",
    "单位": "unit",
    "unit": "unit",
    "单件成本": "unit_cost",
    "成本": "unit_cost",
    "unitcost": "unit_cost",
    "unit_cost": "unit_cost",
    "默认电镀工艺": "plating_process",
    "电镀工艺": "plating_process",
    "默认电镀": "plating_process",
    "platingprocess": "plating_process",
    "plating_process": "plating_process",
    "入库数量": "qty",
    "库存数量": "qty",
    "当前库存": "qty",
    "数量": "qty",
    "qty": "qty",
}

_REQUIRED_HEADERS = ("name", "category", "qty")


@dataclass
class _ImportRow:
    row_number: int
    part_id: str | None
    name: str
    category: str
    color: str | None
    unit: str | None
    unit_cost: float | None
    plating_process: str | None
    qty: float


def import_parts_excel(db: Session, file_bytes: bytes, filename: str | None) -> dict:
    if not file_bytes:
        raise ValueError("导入文件为空")
    if not filename or not filename.lower().endswith(".xlsx"):
        raise ValueError("仅支持 .xlsx 格式的 Excel 文件")

    rows = _load_rows_from_xlsx(file_bytes)
    parsed_rows = _parse_import_rows(rows)
    plans = _build_import_plans(db, parsed_rows)

    created_count = 0
    updated_count = 0
    stock_entry_count = 0
    results = []

    for plan in plans:
        payload = plan["payload"]
        if plan["part"] is None:
            part = create_part(db, payload)
            action = "created"
            created_count += 1
        else:
            part = update_part(db, plan["part"].id, payload)
            action = "updated"
            updated_count += 1

        qty = plan["row"].qty
        if qty > 0:
            add_stock(
                db,
                "part",
                part.id,
                qty,
                reason="Excel导入",
                note=f"Excel导入：{filename} 第 {plan['row'].row_number} 行",
            )
            stock_entry_count += 1

        results.append({
            "row_number": plan["row"].row_number,
            "part_id": part.id,
            "name": part.name,
            "action": action,
            "stock_added": qty,
        })

    return {
        "imported_count": len(results),
        "created_count": created_count,
        "updated_count": updated_count,
        "stock_entry_count": stock_entry_count,
        "results": results,
    }


def build_parts_import_template() -> bytes:
    return _build_xlsx_bytes([
        ["名称", "类目", "颜色", "单位", "单件成本", "默认电镀工艺", "入库数量"],
        ["示例铜扣", "小配件", "金色", "个", 1.5, "真金", 10],
    ])


def _load_rows_from_xlsx(file_bytes: bytes) -> list[list[str]]:
    try:
        with ZipFile(BytesIO(file_bytes)) as zf:
            shared_strings = _read_shared_strings(zf)
            sheet_path = _read_first_sheet_path(zf)
            return _read_sheet_rows(zf, sheet_path, shared_strings)
    except BadZipFile as exc:
        raise ValueError("Excel 文件无法解析，请确认文件未损坏且为 .xlsx 格式") from exc
    except KeyError as exc:
        raise ValueError("Excel 模板结构不完整，无法读取工作表") from exc
    except ET.ParseError as exc:
        raise ValueError("Excel 内容解析失败，请重新保存后再试") from exc


def _read_shared_strings(zf: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []

    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    values = []
    for item in root.findall("main:si", _XML_NS):
        text = "".join(node.text or "" for node in item.findall(".//main:t", _XML_NS))
        values.append(text)
    return values


def _read_first_sheet_path(zf: ZipFile) -> str:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    first_sheet = workbook.find("main:sheets/main:sheet", _XML_NS)
    if first_sheet is None:
        raise ValueError("Excel 中没有可读取的工作表")

    rel_id = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
    if not rel_id:
        raise ValueError("Excel 工作表关系丢失，无法读取")

    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for relationship in rels.findall("rel:Relationship", _REL_NS):
        if relationship.attrib.get("Id") != rel_id:
            continue
        target = relationship.attrib.get("Target")
        if not target:
            break
        normalized = posixpath.normpath(posixpath.join("xl", target))
        if normalized.startswith("../"):
            normalized = normalized[3:]
        return normalized

    raise ValueError("Excel 工作表路径缺失，无法读取")


def _read_sheet_rows(zf: ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(zf.read(sheet_path))
    rows = []

    for row_elem in root.findall(".//main:sheetData/main:row", _XML_NS):
        values_by_index = {}
        max_index = -1

        for cell in row_elem.findall("main:c", _XML_NS):
            ref = cell.attrib.get("r", "")
            match = _CELL_REF_RE.match(ref)
            if not match:
                continue
            index = _column_index(match.group(1))
            values_by_index[index] = _cell_value(cell, shared_strings)
            if index > max_index:
                max_index = index

        if max_index < 0:
            rows.append([])
            continue

        row_values = []
        for index in range(max_index + 1):
            row_values.append(values_by_index.get(index, "").strip())
        rows.append(row_values)

    return rows


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", _XML_NS))

    value_node = cell.find("main:v", _XML_NS)
    if value_node is None or value_node.text is None:
        return ""

    raw = value_node.text.strip()
    if cell_type == "s":
        if raw == "":
            return ""
        index = int(raw)
        if index < 0 or index >= len(shared_strings):
            raise ValueError("Excel 共享字符串索引超出范围")
        return shared_strings[index]
    return raw


def _column_index(column_ref: str) -> int:
    result = 0
    for char in column_ref:
        result = result * 26 + ord(char) - ord("A") + 1
    return result - 1


def _parse_import_rows(rows: list[list[str]]) -> list[_ImportRow]:
    if not rows:
        raise ValueError("Excel 中没有可导入的数据")

    header_index = None
    header_map = None
    for index, row in enumerate(rows):
        if not any((cell or "").strip() for cell in row):
            continue
        header_index = index
        header_map = _build_header_map(row)
        break

    if header_map is None or header_index is None:
        raise ValueError("Excel 缺少表头，请使用导入模板")

    missing_headers = [header for header in _REQUIRED_HEADERS if header not in header_map]
    if missing_headers:
        missing_labels = {
            "name": "名称",
            "category": "类目",
            "qty": "入库数量",
        }
        labels = "、".join(missing_labels[item] for item in missing_headers)
        raise ValueError(f"Excel 缺少必填列：{labels}")

    parsed = []
    errors = []

    for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not any((cell or "").strip() for cell in row):
            continue
        try:
            parsed.append(_parse_row(row, header_map, offset))
        except ValueError as exc:
            errors.append(f"第 {offset} 行：{exc}")

    if errors:
        raise ValueError("\n".join(errors))
    if not parsed:
        raise ValueError("Excel 中没有可导入的数据行")
    return parsed


def _build_header_map(header_row: list[str]) -> dict[str, int]:
    header_map = {}
    for index, raw_header in enumerate(header_row):
        normalized = _normalize_header(raw_header)
        if normalized in _HEADER_ALIASES:
            header_map[_HEADER_ALIASES[normalized]] = index
    return header_map


def _normalize_header(value: str) -> str:
    return "".join((value or "").strip().lower().split())


def _parse_row(row: list[str], header_map: dict[str, int], row_number: int) -> _ImportRow:
    part_id = _get_text(row, header_map, "part_id")
    name = _get_text(row, header_map, "name")
    category = _get_text(row, header_map, "category")
    color = _get_text(row, header_map, "color")
    unit = _get_text(row, header_map, "unit")
    plating_process = _get_text(row, header_map, "plating_process")
    unit_cost = _get_number(row, header_map, "unit_cost", row_number, allow_blank=True)
    qty = _get_number(row, header_map, "qty", row_number, allow_blank=True)

    if not name:
        raise ValueError("名称不能为空")
    if not category:
        raise ValueError("类目不能为空")
    if category not in PART_CATEGORIES:
        categories = "、".join(PART_CATEGORIES.keys())
        raise ValueError(f"类目无效，必须是：{categories}")
    if unit_cost is not None and unit_cost < 0:
        raise ValueError("单件成本不能小于 0")
    if qty is None:
        qty = 0.0
    if qty < 0:
        raise ValueError("入库数量不能小于 0")

    return _ImportRow(
        row_number=row_number,
        part_id=part_id or None,
        name=name,
        category=category,
        color=color or None,
        unit=unit or None,
        unit_cost=unit_cost,
        plating_process=plating_process or None,
        qty=qty,
    )


def _get_text(row: list[str], header_map: dict[str, int], key: str) -> str:
    index = header_map.get(key)
    if index is None or index >= len(row):
        return ""
    return (row[index] or "").strip()


def _get_number(
    row: list[str],
    header_map: dict[str, int],
    key: str,
    row_number: int,
    allow_blank: bool,
) -> float | None:
    raw = _get_text(row, header_map, key)
    if raw == "":
        return None if allow_blank else 0.0
    try:
        return float(raw)
    except ValueError as exc:
        label = "单件成本" if key == "unit_cost" else "入库数量"
        raise ValueError(f"{label}必须是数字") from exc


def _build_import_plans(db: Session, rows: list[_ImportRow]) -> list[dict]:
    seen_ids = set()
    seen_keys = set()
    plans = []
    errors = []

    for row in rows:
        unique_key = (row.name, row.category)
        if row.part_id:
            if row.part_id in seen_ids:
                errors.append(f"第 {row.row_number} 行：配件编号 {row.part_id} 在文件中重复")
                continue
            seen_ids.add(row.part_id)
        else:
            if unique_key in seen_keys:
                errors.append(f"第 {row.row_number} 行：名称 + 类目 在文件中重复，请合并后再导入")
                continue
            seen_keys.add(unique_key)

        try:
            plans.append(_build_single_plan(db, row))
        except ValueError as exc:
            errors.append(f"第 {row.row_number} 行：{exc}")

    if errors:
        raise ValueError("\n".join(errors))

    return plans


def _build_single_plan(db: Session, row: _ImportRow) -> dict:
    payload = {
        "name": row.name,
        "color": row.color,
        "unit": row.unit,
        "unit_cost": row.unit_cost,
        "plating_process": row.plating_process,
    }

    if row.part_id:
        part = get_part(db, row.part_id)
        if part is None:
            raise ValueError(f"配件编号不存在：{row.part_id}")
        if part.category != row.category:
            raise ValueError(f"类目与现有配件不一致：{part.category}")
        return {"row": row, "part": part, "payload": payload}

    matches = db.query(Part).filter(Part.name == row.name, Part.category == row.category).all()
    if len(matches) > 1:
        raise ValueError("同名同类目的配件存在多条，系统无法自动判断要更新哪一条")
    if len(matches) == 1:
        return {"row": row, "part": matches[0], "payload": payload}

    create_payload = dict(payload)
    create_payload["category"] = row.category
    return {"row": row, "part": None, "payload": create_payload}


def _build_xlsx_bytes(rows: list[list[object]]) -> bytes:
    sheet_rows = []
    max_columns = 0

    for row_number, row in enumerate(rows, start=1):
        cells = []
        max_columns = max(max_columns, len(row))
        for column_index, value in enumerate(row):
            if value is None or value == "":
                continue
            ref = f"{_column_name(column_index)}{row_number}"
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                text = escape(str(value))
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        sheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')

    last_column = _column_name(max_columns - 1) if max_columns > 0 else "A"
    last_row = len(rows) if rows else 1
    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{last_column}{last_row}"/>'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="配件导入模板" sheetId="1" r:id="rId1" /></sheets>'
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml" />'
        "</Relationships>"
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml" />'
        "</Relationships>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />'
        '<Default Extension="xml" ContentType="application/xml" />'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml" />'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml" />'
        "</Types>"
    )

    buffer = BytesIO()
    with ZipFile(buffer, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
    return buffer.getvalue()


def _column_name(index: int) -> str:
    result = ""
    current = index + 1
    while current:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result
