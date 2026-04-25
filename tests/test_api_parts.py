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


def test_list_parts_multi_keyword_and(client):
    """Regression: '背镂空 桃心' must find '背镂空满钻桃心'.

    Before the keyword_filter migration, this failed because the whole
    string (including the space) was passed to a single ILIKE '%...%'.
    """
    client.post("/api/parts/", json={"name": "背镂空满钻桃心", "category": "吊坠"})
    client.post("/api/parts/", json={"name": "背镂空圆环", "category": "吊坠"})
    client.post("/api/parts/", json={"name": "满钻桃心", "category": "吊坠"})

    resp = client.get("/api/parts/", params={"name": "背镂空 桃心"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "背镂空满钻桃心"


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
    assert part["purchase_cost"] == 2.8
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
    assert part["purchase_cost"] == 2.2
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


def test_import_response_includes_image(client):
    """Import response results should include image field."""
    file_bytes = _build_xlsx([
        ["名称", "类目", "入库数量"],
        ["测试吊坠", "吊坠", 10],
    ])
    resp = client.post(
        "/api/parts/import?filename=test.xlsx",
        content=file_bytes,
        headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) > 0
    assert "image" in data["results"][0]


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


def test_create_variant_from_variant_resolves_to_root(client):
    """Creating a variant from another variant should resolve to root and succeed (re-plating)."""
    root, gold_variant = _create_root_and_variant(client)  # gold_variant is G
    # Create S variant from the G variant (返镀 scenario)
    resp = client.post(f"/api/parts/{gold_variant['id']}/create-variant", json={"color_code": "S"})
    assert resp.status_code == 201
    silver = resp.json()
    assert silver["color"] == "白K"
    assert silver["parent_part_id"] == root["id"]  # linked to root, not to gold variant
    assert silver["name"] == f"{root['name']}_白K"


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


def test_update_variant_full_payload_allows_other_fields(client):
    """Frontend sends full payload including color="" and parent_part_id="".
    This should not block updates to other fields like unit or image."""
    _, variant = _create_root_and_variant(client)
    resp = client.patch(f"/api/parts/{variant['id']}", json={
        "name": variant["name"],
        "image": "",
        "color": "",
        "unit": "条",
        "parent_part_id": "",
    })
    assert resp.status_code == 200
    assert resp.json()["unit"] == "条"


# ── Spec variant tests ──


def test_create_spec_variant(client):
    root = client.post("/api/parts/", json={"name": "链条", "category": "链条"}).json()
    resp = client.post(f"/api/parts/{root['id']}/create-variant", json={"spec": "45cm"})
    assert resp.status_code == 201
    v = resp.json()
    assert v["spec"] == "45cm"
    assert v["color"] is None
    assert v["parent_part_id"] == root["id"]
    assert v["name"] == "链条_45cm"


def test_create_color_and_spec_variant(client):
    root = client.post("/api/parts/", json={"name": "链条", "category": "链条"}).json()
    resp = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "G", "spec": "45cm"})
    assert resp.status_code == 201
    v = resp.json()
    assert v["color"] == "金色"
    assert v["spec"] == "45cm"
    assert v["name"] == "链条_金色_45cm"


def test_create_spec_variant_duplicate_rejected(client):
    root = client.post("/api/parts/", json={"name": "链条", "category": "链条"}).json()
    resp1 = client.post(f"/api/parts/{root['id']}/create-variant", json={"spec": "45cm"})
    assert resp1.status_code == 201
    resp2 = client.post(f"/api/parts/{root['id']}/create-variant", json={"spec": "45cm"})
    # Returns existing variant (idempotent)
    assert resp2.status_code == 201
    assert resp2.json()["id"] == resp1.json()["id"]


def test_create_variant_color_only_backward_compat(client):
    """Only color_code (no spec) should still work as before."""
    root = client.post("/api/parts/", json={"name": "链条", "category": "链条"}).json()
    resp = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "S"})
    assert resp.status_code == 201
    assert resp.json()["color"] == "白K"
    assert resp.json()["spec"] is None


def test_create_variant_neither_color_nor_spec_rejected(client):
    root = client.post("/api/parts/", json={"name": "链条", "category": "链条"}).json()
    resp = client.post(f"/api/parts/{root['id']}/create-variant", json={})
    assert resp.status_code == 400


def test_create_spec_variant_not_confused_with_color_spec_variant(client):
    """Bug regression: color+spec variant should not be reused for spec-only request."""
    root = client.post("/api/parts/", json={"name": "链条", "category": "链条"}).json()
    # Create color+spec variant first
    r1 = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "G", "spec": "45cm"})
    assert r1.status_code == 201
    assert r1.json()["name"] == "链条_金色_45cm"
    # Create spec-only variant — must be a different part
    r2 = client.post(f"/api/parts/{root['id']}/create-variant", json={"spec": "45cm"})
    assert r2.status_code == 201
    assert r2.json()["name"] == "链条_45cm"
    assert r2.json()["id"] != r1.json()["id"]


def test_create_spec_variant_whitespace_normalized(client):
    """Whitespace-only spec should be rejected, leading/trailing spaces stripped."""
    root = client.post("/api/parts/", json={"name": "链条", "category": "链条"}).json()
    # Pure whitespace → rejected
    resp = client.post(f"/api/parts/{root['id']}/create-variant", json={"spec": "   "})
    assert resp.status_code == 400
    # Leading/trailing spaces → stripped, creates valid variant
    resp2 = client.post(f"/api/parts/{root['id']}/create-variant", json={"spec": "  45cm  "})
    assert resp2.status_code == 201
    assert resp2.json()["spec"] == "45cm"
    assert resp2.json()["name"] == "链条_45cm"


def test_create_part_spec_whitespace_normalized(client):
    """create_part should strip spec whitespace and store None for blank."""
    resp = client.post("/api/parts/", json={"name": "链条A", "category": "链条", "spec": "  45cm  "})
    assert resp.status_code == 201
    assert resp.json()["spec"] == "45cm"
    resp2 = client.post("/api/parts/", json={"name": "链条B", "category": "链条", "spec": "   "})
    assert resp2.status_code == 201
    assert resp2.json()["spec"] is None


def test_update_part_spec_whitespace_normalized(client):
    """update_part should strip spec whitespace and store None for blank."""
    root = client.post("/api/parts/", json={"name": "链条C", "category": "链条"}).json()
    resp = client.patch(f"/api/parts/{root['id']}", json={"spec": "  50cm  "})
    assert resp.status_code == 200
    assert resp.json()["spec"] == "50cm"
    resp2 = client.patch(f"/api/parts/{root['id']}", json={"spec": "   "})
    assert resp2.status_code == 200
    assert resp2.json()["spec"] is None


def test_create_spec_variant_from_color_variant(client):
    """Creating a spec variant from a color variant should inherit color/image and hang under root."""
    root = client.post("/api/parts/", json={"name": "扁链 4mm", "category": "链条", "image": "root.jpg"}).json()
    gold = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "G"}).json()
    assert gold["name"] == "扁链 4mm_金色"
    # Update gold variant's image to differ from root
    client.patch(f"/api/parts/{gold['id']}", json={"image": "gold.jpg"})
    # Create spec variant from the gold variant
    resp = client.post(f"/api/parts/{gold['id']}/create-variant", json={"spec": "45cm"})
    assert resp.status_code == 201
    v = resp.json()
    assert v["name"] == "扁链 4mm_金色_45cm"
    assert v["parent_part_id"] == root["id"]  # flat: under root, not gold
    assert v["spec"] == "45cm"
    assert v["color"] == "金色"  # inherited from source color variant
    assert v["image"] == "gold.jpg"  # inherited from source, not root
    # Visible in root's variant list
    variants = client.get(f"/api/parts/{root['id']}/variants").json()
    variant_ids = [vv["id"] for vv in variants]
    assert v["id"] in variant_ids
    assert gold["id"] in variant_ids


def test_orphan_adoption_rejects_conflicting_color_spec(client):
    """Orphan with same name but different color/spec should not be adopted."""
    root = client.post("/api/parts/", json={"name": "扁链 4mm", "category": "链条"}).json()
    # Manually create an orphan with matching name but wrong structured fields
    orphan = client.post("/api/parts/", json={
        "name": "扁链 4mm_金色_45cm", "category": "链条", "color": "白K", "spec": "50cm",
    }).json()
    assert orphan["parent_part_id"] is None
    # Creating variant should NOT adopt the orphan — fields conflict
    resp = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "G", "spec": "45cm"})
    assert resp.status_code == 201
    v = resp.json()
    assert v["id"] != orphan["id"]
    assert v["color"] == "金色"
    assert v["spec"] == "45cm"


def test_orphan_adoption_rejects_extra_fields(client):
    """Orphan with extra color/spec not in request should not be adopted."""
    root = client.post("/api/parts/", json={"name": "链条", "category": "链条"}).json()
    # Orphan has same name but extra color field
    client.post("/api/parts/", json={
        "name": "链条_45cm", "category": "链条", "color": "金色", "spec": "45cm",
    })
    # Spec-only request — orphan has extra color, should not be adopted
    resp = client.post(f"/api/parts/{root['id']}/create-variant", json={"spec": "45cm"})
    assert resp.status_code == 201
    v = resp.json()
    assert v["color"] is None
    assert v["spec"] == "45cm"


def test_color_only_variant_after_color_spec_variant(client):
    """Pure color variant should still be creatable after a color+spec variant exists."""
    root = client.post("/api/parts/", json={"name": "链条", "category": "链条"}).json()
    # Create color+spec variant first
    r1 = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "G", "spec": "45cm"})
    assert r1.status_code == 201
    assert r1.json()["name"] == "链条_金色_45cm"
    # Create pure color variant — must succeed as a different part
    r2 = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "G"})
    assert r2.status_code == 201
    assert r2.json()["name"] == "链条_金色"
    assert r2.json()["id"] != r1.json()["id"]
    assert r2.json()["spec"] is None


def test_cross_color_variant_uses_root_attributes(client):
    """Creating a different color variant from a color variant should use root's attributes, not source's."""
    root = client.post("/api/parts/", json={"name": "扁链", "category": "链条", "image": "root.jpg"}).json()
    gold = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "G"}).json()
    client.patch(f"/api/parts/{gold['id']}", json={"image": "gold.jpg"})
    # Create silver variant from gold — should inherit root's image, not gold's
    resp = client.post(f"/api/parts/{gold['id']}/create-variant", json={"color_code": "S"})
    assert resp.status_code == 201
    assert resp.json()["image"] == "root.jpg"


def test_explicit_same_color_spec_variant_inherits_source(client):
    """Explicitly passing same color_code as source should still inherit source's attributes."""
    root = client.post("/api/parts/", json={"name": "扁链", "category": "链条", "image": "root.jpg"}).json()
    gold = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "G"}).json()
    client.patch(f"/api/parts/{gold['id']}", json={"image": "gold.jpg"})
    # Explicit color_code=G + spec from gold variant — same color, should use source
    resp = client.post(f"/api/parts/{gold['id']}/create-variant", json={"color_code": "G", "spec": "45cm"})
    assert resp.status_code == 201
    assert resp.json()["image"] == "gold.jpg"
    assert resp.json()["color"] == "金色"


def test_variant_inherits_all_costs_including_plating(client):
    """Variant should inherit plating_cost from donor so unit_cost is correct."""
    root = client.post("/api/parts/", json={"name": "链条", "category": "链条"}).json()
    # Set all three cost fields on root
    for field, val in [("purchase_cost", 1), ("bead_cost", 2), ("plating_cost", 3)]:
        client.post("/api/parts/batch-update-costs", json={
            "updates": [{"part_id": root["id"], "field": field, "value": val}]
        })
    resp = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "G", "spec": "45cm"})
    assert resp.status_code == 201
    v = resp.json()
    assert v["purchase_cost"] == 1
    assert v["bead_cost"] == 2
    assert v["plating_cost"] == 3
    assert v["unit_cost"] == 6


# --- New variant ID format tests (base+suffix: {root_id}-{G|S|RG}[-{spec}]) ---

def test_variant_id_new_format_color_only(client):
    root, variant = _create_root_and_variant(client)
    # Color G → suffix -G
    assert variant["id"] == f"{root['id']}-G"


def test_variant_id_new_format_with_spec(client):
    root = client.post("/api/parts/", json={"name": "扁链 3.5mm", "category": "链条"}).json()
    resp = client.post(
        f"/api/parts/{root['id']}/create-variant",
        json={"color_code": "G", "spec": "45cm"},
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == f"{root['id']}-G-45cm"


def test_variant_id_new_format_all_color_codes(client):
    for code, expected_suffix in [("G", "G"), ("S", "S"), ("RG", "RG")]:
        root = client.post(
            "/api/parts/", json={"name": f"片 {code}", "category": "小配件"}
        ).json()
        resp = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": code})
        assert resp.status_code == 201
        assert resp.json()["id"] == f"{root['id']}-{expected_suffix}"


def test_variant_spec_invalid_format_rejected(client):
    root = client.post("/api/parts/", json={"name": "链 A", "category": "链条"}).json()
    for bad_spec in ["大号", "L", "45", "45 cm", "cm45", "45厘米", "abc"]:
        resp = client.post(
            f"/api/parts/{root['id']}/create-variant",
            json={"color_code": "G", "spec": bad_spec},
        )
        assert resp.status_code == 400, f"Expected 400 for spec={bad_spec!r}, got {resp.status_code}"
        assert "规格格式不合法" in resp.json()["detail"]


def test_variant_spec_valid_formats_accepted(client):
    root = client.post("/api/parts/", json={"name": "链 B", "category": "链条"}).json()
    for good_spec in ["45cm", "17.5cm", "8mm", "2m", "0.5m", "100mm"]:
        resp = client.post(
            f"/api/parts/{root['id']}/create-variant",
            json={"color_code": "G", "spec": good_spec},
        )
        assert resp.status_code == 201, f"Expected 201 for spec={good_spec!r}, got {resp.status_code}"
        assert resp.json()["id"] == f"{root['id']}-G-{good_spec}"


def test_variant_id_no_collision_with_flat_root_ids(client):
    """New variant IDs contain '-<letter>' and can never collide with flat root IDs."""
    root, variant = _create_root_and_variant(client)
    # variant ID has at least one non-digit segment after root ID
    suffix = variant["id"][len(root["id"]) + 1 :]  # strip "{root_id}-"
    assert not suffix.isdigit(), f"variant suffix {suffix!r} must not be all digits"


def test_find_or_create_variant_dedupes_old_flat_format_variant(client, db):
    """When an old flat-ID variant exists (simulating pre-migration data),
    create-variant should return it instead of creating a new suffix-ID variant.
    """
    # Create root via API
    root = client.post("/api/parts/", json={"name": "手动老变体 root", "category": "小配件"}).json()
    # Directly craft an "old-format" flat-ID variant (simulate pre-migration data)
    from models.part import Part
    old_variant = Part(
        id="PJ-X-OLDVAR1",  # flat-style arbitrary ID, no -G suffix
        name=f"{root['name']}_金色",
        category=root["category"],
        color="金色",
        parent_part_id=root["id"],
    )
    db.add(old_variant)
    db.flush()
    # Now request creating a 金色 variant through API
    resp = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "G"})
    assert resp.status_code == 201
    # Should return the existing old-format variant, NOT create a new -G one
    assert resp.json()["id"] == "PJ-X-OLDVAR1"


# --- Transition-period / legacy-data safety tests ---

def test_create_variant_from_orphan_color_plus_spec_rejected(client, db):
    """Orphan whose NAME ends with _颜色_规格 must NOT be used as a root."""
    from models.part import Part
    orphan = Part(
        id="PJ-LT-OLDORPH1",
        name="链条_金色_45cm",  # name-pattern match: color+spec suffix
        category="链条",
        color="金色",
        spec="45cm",
        parent_part_id=None,
    )
    db.add(orphan)
    db.flush()
    resp = client.post(
        f"/api/parts/{orphan.id}/create-variant", json={"color_code": "G", "spec": "50cm"}
    )
    assert resp.status_code == 400
    assert "未挂载的变体" in resp.json()["detail"]


def test_create_variant_allows_root_with_legit_yuan_se_color(client, db):
    """Sanity: a real root with color='原色' (base/unplated marker) is NOT an orphan."""
    from models.part import Part
    legit_root = Part(
        id="PJ-X-LEGITROOT",
        name="黑珍珠 6mm",
        category="小配件",
        color="原色",  # legitimate base marker, not a plated color
        parent_part_id=None,
    )
    db.add(legit_root)
    db.flush()
    resp = client.post(
        f"/api/parts/{legit_root.id}/create-variant", json={"color_code": "G"}
    )
    assert resp.status_code == 201
    assert resp.json()["parent_part_id"] == legit_root.id
    assert resp.json()["color"] == "金色"


def test_create_variant_allows_root_with_plated_color_column(client, db):
    """Regression: a legit root may carry color='金色' in its column without the
    name ending in `_金色`. Don't treat it as an orphan."""
    from models.part import Part
    legit_root = Part(
        id="PJ-X-GOLDROOT",
        name="金色扣环 12mm",  # name does NOT end with _金色
        category="小配件",
        color="金色",  # legit column value, not an orphan signal
        parent_part_id=None,
    )
    db.add(legit_root)
    db.flush()
    resp = client.post(
        f"/api/parts/{legit_root.id}/create-variant", json={"color_code": "S"}
    )
    assert resp.status_code == 201
    assert resp.json()["parent_part_id"] == legit_root.id


def test_create_variant_allows_root_with_spec_column(client, db):
    """Regression: a legit root may carry spec='45cm' without the name ending
    with a color/spec suffix. Don't treat it as an orphan (caught by reviewer)."""
    from models.part import Part
    legit_root = Part(
        id="PJ-LT-SPECROOT",
        name="某链条",  # plain root name, no variant suffix
        category="链条",
        spec="45cm",  # legit spec column on a root — must NOT trigger orphan guard
        parent_part_id=None,
    )
    db.add(legit_root)
    db.flush()
    resp = client.post(
        f"/api/parts/{legit_root.id}/create-variant", json={"color_code": "G"}
    )
    assert resp.status_code == 201
    assert resp.json()["parent_part_id"] == legit_root.id
    assert resp.json()["color"] == "金色"


def test_find_existing_variant_skips_corrupted_child(client, db):
    """If a child's name matches but color/spec column is wrong, don't reuse — create new."""
    from models.part import Part
    root = client.post("/api/parts/", json={"name": "铜 X", "category": "小配件"}).json()
    # Corrupted child: name looks like spec-only variant "铜 X_45cm" but color column is set
    corrupted = Part(
        id="PJ-X-CORRUPT1",
        name=f"{root['name']}_45cm",
        category=root["category"],
        color="金色",  # wrong: request is spec-only, but this child has color
        spec="45cm",
        parent_part_id=root["id"],
    )
    db.add(corrupted)
    db.flush()
    # Request spec-only (no color)
    resp = client.post(f"/api/parts/{root['id']}/create-variant", json={"spec": "45cm"})
    assert resp.status_code == 201
    # Must not return the corrupted child
    assert resp.json()["id"] != "PJ-X-CORRUPT1"
    # Should be a fresh variant with new-format ID
    assert resp.json()["id"] == f"{root['id']}-45cm"


def test_find_existing_variant_picks_exact_match_among_multiple_orphans(client, db):
    """Multiple same-name orphans: picker must match color+spec exactly, not just the first row."""
    from models.part import Part
    root = client.post("/api/parts/", json={"name": "多孤儿 root", "category": "小配件"}).json()
    # Orphan A: name matches, but wrong color
    orphan_wrong = Part(
        id="PJ-X-MULTI1",
        name=f"{root['name']}_金色",
        category=root["category"],
        color="白K",  # wrong color
        parent_part_id=None,
    )
    # Orphan B: name matches AND color matches (the correct one)
    orphan_right = Part(
        id="PJ-X-MULTI2",
        name=f"{root['name']}_金色",
        category=root["category"],
        color="金色",  # exact match
        parent_part_id=None,
    )
    db.add_all([orphan_wrong, orphan_right])
    db.flush()
    # Request 金色 variant — should pick orphan_right, not orphan_wrong
    resp = client.post(f"/api/parts/{root['id']}/create-variant", json={"color_code": "G"})
    assert resp.status_code == 201
    assert resp.json()["id"] == "PJ-X-MULTI2"
