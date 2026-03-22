from io import BytesIO
from zipfile import ZipFile
from xml.sax.saxutils import escape

def test_create_part(client):
    resp = client.post("/api/parts/", json={"name": "Ring Base", "category": "吊坠"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("PJ-DZ-")
    assert data["name"] == "Ring Base"
    assert data["category"] == "吊坠"

def test_create_part_invalid_category(client):
    resp = client.post("/api/parts/", json={"name": "X", "category": "invalid"})
    assert resp.status_code == 400

def test_create_part_missing_name(client):
    resp = client.post("/api/parts/", json={"category": "吊坠"})
    assert resp.status_code == 422

def test_create_part_missing_category(client):
    resp = client.post("/api/parts/", json={"name": "X"})
    assert resp.status_code == 422

def test_list_parts(client):
    client.post("/api/parts/", json={"name": "A", "category": "吊坠"})
    client.post("/api/parts/", json={"name": "B", "category": "链条"})
    resp = client.get("/api/parts/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

def test_list_parts_filter(client):
    client.post("/api/parts/", json={"name": "A", "category": "吊坠"})
    client.post("/api/parts/", json={"name": "B", "category": "链条"})
    resp = client.get("/api/parts/?category=吊坠")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "A"


def test_list_parts_filter_name(client):
    client.post("/api/parts/", json={"name": "铜扣环", "category": "吊坠"})
    client.post("/api/parts/", json={"name": "银链条", "category": "链条"})
    resp = client.get("/api/parts/?name=铜")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "铜扣环"


def test_list_parts_filter_name_no_match(client):
    client.post("/api/parts/", json={"name": "铜扣环", "category": "吊坠"})
    resp = client.get("/api/parts/?name=金")
    assert resp.status_code == 200
    assert resp.json() == []

def test_get_part(client):
    created = client.post("/api/parts/", json={"name": "X", "category": "吊坠"}).json()
    resp = client.get(f"/api/parts/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "X"

def test_get_part_not_found(client):
    resp = client.get("/api/parts/PJ-DZ-99999")
    assert resp.status_code == 404

def test_update_part(client):
    created = client.post("/api/parts/", json={"name": "Old", "category": "吊坠"}).json()
    resp = client.patch(f"/api/parts/{created['id']}", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"

def test_update_part_not_found(client):
    resp = client.patch("/api/parts/PJ-DZ-99999", json={"name": "X"})
    assert resp.status_code == 404

def test_delete_part(client):
    created = client.post("/api/parts/", json={"name": "ToDelete", "category": "吊坠"}).json()
    resp = client.delete(f"/api/parts/{created['id']}")
    assert resp.status_code == 204
    resp2 = client.get(f"/api/parts/{created['id']}")
    assert resp2.status_code == 404

def test_delete_part_not_found(client):
    resp = client.delete("/api/parts/PJ-DZ-99999")
    assert resp.status_code == 404


def _column_name(index):
    result = ""
    current = index + 1
    while current:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _build_xlsx(rows):
    shared_strings = []
    shared_index = {}
    sheet_rows = []

    for row_number, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row):
            if value is None or value == "":
                continue
            ref = f"{_column_name(column_index)}{row_number}"
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                text = str(value)
                if text not in shared_index:
                    shared_index[text] = len(shared_strings)
                    shared_strings.append(text)
                cells.append(f'<c r="{ref}" t="s"><v>{shared_index[text]}</v></c>')
        sheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')

    shared_strings_xml = "".join(
        f"<si><t>{escape(text)}</t></si>"
        for text in shared_strings
    )
    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1" /></sheets>'
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
        '<Override PartName="/xl/sharedStrings.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml" />'
        "</Types>"
    )

    buffer = BytesIO()
    with ZipFile(buffer, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
        zf.writestr(
            "xl/sharedStrings.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                f'count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">'
                f"{shared_strings_xml}</sst>"
            ),
        )
    return buffer.getvalue()


def test_import_parts_excel_creates_parts_and_stock(client):
    file_bytes = _build_xlsx([
        ["名称", "类目", "颜色", "单位", "单件成本", "默认电镀工艺", "入库数量"],
        ["铜扣", "小配件", "金色", "个", 1.25, "真金", 12],
        ["银链", "链条", "银色", "条", 3.5, "白银", 8],
    ])

    resp = client.post(
        "/api/parts/import?filename=parts.xlsx",
        content=file_bytes,
        headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported_count"] == 2
    assert data["created_count"] == 2
    assert data["updated_count"] == 0
    assert data["stock_entry_count"] == 2

    parts = client.get("/api/parts/").json()
    assert len(parts) == 2
    copper = next(item for item in parts if item["name"] == "铜扣")
    silver = next(item for item in parts if item["name"] == "银链")
    assert copper["id"].startswith("PJ-X-")
    assert silver["id"].startswith("PJ-LT-")

    copper_stock = client.get(f"/api/inventory/part/{copper['id']}").json()
    silver_stock = client.get(f"/api/inventory/part/{silver['id']}").json()
    assert copper_stock["current"] == 12.0
    assert silver_stock["current"] == 8.0


def test_import_parts_excel_updates_existing_part_by_id(client):
    created = client.post("/api/parts/", json={"name": "旧铜扣", "category": "小配件"}).json()

    file_bytes = _build_xlsx([
        ["配件编号", "名称", "类目", "颜色", "单位", "单件成本", "默认电镀工艺", "入库数量"],
        [created["id"], "新铜扣", "小配件", "古铜", "个", 2.8, "喷砂", 6],
    ])

    resp = client.post(
        "/api/parts/import?filename=update.xlsx",
        content=file_bytes,
        headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created_count"] == 0
    assert data["updated_count"] == 1

    part = client.get(f"/api/parts/{created['id']}").json()
    assert part["name"] == "新铜扣"
    assert part["color"] == "古铜"
    assert part["unit"] == "个"
    assert part["unit_cost"] == 2.8
    assert part["plating_process"] == "喷砂"

    stock = client.get(f"/api/inventory/part/{created['id']}").json()
    assert stock["current"] == 6.0


def test_import_parts_excel_updates_existing_part_by_name_and_category(client):
    created = client.post("/api/parts/", json={"name": "铜扣", "category": "小配件"}).json()

    file_bytes = _build_xlsx([
        ["名称", "类目", "颜色", "单位", "单件成本", "默认电镀工艺", "入库数量"],
        ["铜扣", "小配件", "古金", "个", 2.2, "拉丝", 4],
    ])

    resp = client.post(
        "/api/parts/import?filename=update-by-name.xlsx",
        content=file_bytes,
        headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created_count"] == 0
    assert data["updated_count"] == 1

    part = client.get(f"/api/parts/{created['id']}").json()
    assert part["name"] == "铜扣"
    assert part["color"] == "古金"
    assert part["unit"] == "个"
    assert part["unit_cost"] == 2.2
    assert part["plating_process"] == "拉丝"

    stock = client.get(f"/api/inventory/part/{created['id']}").json()
    assert stock["current"] == 4.0


def test_import_parts_excel_rolls_back_on_invalid_row(client_real_get_db):
    file_bytes = _build_xlsx([
        ["名称", "类目", "入库数量"],
        ["铜扣", "小配件", 5],
        ["坏数据", "错误类目", 2],
    ])

    resp = client_real_get_db.post(
        "/api/parts/import?filename=broken.xlsx",
        content=file_bytes,
        headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )
    assert resp.status_code == 400
    assert "类目无效" in resp.json()["detail"]

    after = client_real_get_db.get("/api/parts/")
    assert after.status_code == 200
    assert after.json() == []


def test_download_parts_import_template(client):
    resp = client.get("/api/parts/import-template")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "parts-import-template.xlsx" in resp.headers["content-disposition"]

    import_resp = client.post(
        "/api/parts/import?filename=parts-import-template.xlsx",
        content=resp.content,
        headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )
    assert import_resp.status_code == 200
    data = import_resp.json()
    assert data["imported_count"] == 1
    assert data["created_count"] == 1


def _create_root_and_variant(client):
    root = client.post("/api/parts/", json={"name": "铜扣", "category": "小配件"}).json()
    variant = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "G"}).json()
    return root, variant


def test_create_variant(client):
    root, variant = _create_root_and_variant(client)
    assert variant["color"] == "金色"
    assert variant["parent_part_id"] == root["id"]
    assert variant["name"] == f"{root['name']}_金色"
    assert variant["category"] == root["category"]


def test_create_variant_duplicate_color_returns_existing(client):
    root, variant = _create_root_and_variant(client)
    resp = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "G"})
    assert resp.status_code == 201
    assert resp.json()["id"] == variant["id"]


def test_create_variant_from_variant_rejected(client):
    _, variant = _create_root_and_variant(client)
    resp = client.post(f"/api/parts/{variant['id']}/create-variant", json={"color_code": "S"})
    assert resp.status_code == 400
    assert "非原色配件" in resp.json()["detail"]


def test_create_variant_invalid_color_code(client):
    root = client.post("/api/parts/", json={"name": "铜扣", "category": "小配件"}).json()
    resp = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "XX"})
    assert resp.status_code == 400


def test_list_variants_from_root(client):
    root, variant = _create_root_and_variant(client)
    resp = client.get(f"/api/parts/{root['id']}/variants")
    assert resp.status_code == 200
    ids = [v["id"] for v in resp.json()]
    assert variant["id"] in ids
    assert root["id"] not in ids


def test_list_variants_from_variant_includes_root(client):
    root, variant = _create_root_and_variant(client)
    resp = client.get(f"/api/parts/{variant['id']}/variants")
    assert resp.status_code == 200
    ids = [v["id"] for v in resp.json()]
    assert root["id"] in ids
    assert variant["id"] in ids


def test_update_variant_parent_part_id_rejected(client):
    _, variant = _create_root_and_variant(client)
    resp = client.patch(f"/api/parts/{variant['id']}", json={"parent_part_id": None})
    assert resp.status_code == 400
    assert "变体配件" in resp.json()["detail"]


def test_update_variant_color_rejected(client):
    _, variant = _create_root_and_variant(client)
    resp = client.patch(f"/api/parts/{variant['id']}", json={"color": "白K"})
    assert resp.status_code == 400
    assert "变体配件" in resp.json()["detail"]


def test_delete_root_with_variants_rejected(client):
    root, _ = _create_root_and_variant(client)
    resp = client.delete(f"/api/parts/{root['id']}")
    assert resp.status_code == 400
    assert "变体" in resp.json()["detail"]


def test_delete_variant_then_root_succeeds(client):
    root, variant = _create_root_and_variant(client)
    assert client.delete(f"/api/parts/{variant['id']}").status_code == 204
    assert client.delete(f"/api/parts/{root['id']}").status_code == 204


def test_update_variant_rehang_rejected(client):
    root2 = client.post("/api/parts/", json={"name": "银链", "category": "链条"}).json()
    _, variant = _create_root_and_variant(client)
    resp = client.patch(f"/api/parts/{variant['id']}", json={"parent_part_id": root2["id"]})
    assert resp.status_code == 400
    assert "变体配件" in resp.json()["detail"]
