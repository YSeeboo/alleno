from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

from models.inventory_log import InventoryLog
from models.part import Part, PartCostLog
from models.plating_order import CompositePlatingTarget
from services.composite_plating import composite_plating_target
from services.inventory import add_stock, get_stock
from services.part import create_part, create_part_variant
from services.part_bom import set_part_bom
from services.part_import import _build_xlsx_bytes


def test_part_category_options_drive_create_list_and_excel(client):
    catalog = client.get("/api/parts/categories").json()
    options = {row["value"]: row["label"] for row in catalog["options"]}
    assert options == {
        "吊坠": "吊坠／挂件", "链条": "链条", "扣具": "扣具", "连接件": "连接件",
        "耳饰配件": "耳饰配件", "珠子": "珠子／散珠", "底托": "底托／镶嵌件", "线材": "线材／绳带",
    }
    template = client.get("/api/parts/import-template")
    with ZipFile(BytesIO(template.content)) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode()
        assert '<formula1>"' + ",".join(options.values()) + '"</formula1>' in sheet

    for i, (value, label) in enumerate(list(options.items())[2:], 1):
        response = client.post("/api/parts/", json={"name": label, "category": label})
        assert response.status_code == 201, response.text
        part = response.json()
        assert (part["id"], part["category"], part["size_tier"]) == (f"PJ-{i:05d}", value, "small")
        response = client.get("/api/parts/", params={"category": label.replace("／", "/")})
        assert response.json() == [part]

    data = _build_xlsx_bytes([["名称", "类目", "入库数量"], ["珍珠", "珠子/散珠", 0]])
    response = client.post("/api/parts/import?filename=parts.xlsx", content=data)
    assert response.status_code == 200, response.text
    part_id = response.json()["results"][0]["part_id"]
    assert client.get(f"/api/parts/{part_id}").json()["category"] == "珠子"


def test_unclassified_includes_legacy_empty_unknown_and_variant_without_parent_match(client, db):
    root = create_part(db, {"name": "旧链料", "category": "链条"})
    variant = create_part_variant(db, root.id, "G")
    variant.category = "小配件"
    db.add_all([Part(id="PJ-EMPTY", name="空类目"), Part(id="PJ-UNKNOWN", name="特殊", category="旧类目")])
    db.flush()
    pending = client.get("/api/parts/categories").json()["unclassified_value"]
    response = client.get("/api/parts/", params={"category": pending})
    assert response.status_code == 200, response.text
    assert {p["id"]: p["category"] for p in response.json()} == {
        variant.id: "小配件", "PJ-EMPTY": None, "PJ-UNKNOWN": "旧类目",
    }


def test_batch_reclassify_changes_only_selected_categories(client, db):
    child = create_part(db, {"name": "开口圈", "category": "小配件", "unit": "个", "purchase_cost": Decimal("1.2")})
    source = create_part(db, {"name": "耳针组件", "category": "小配件", "unit": "个", "size_tier": "medium"})
    bom = set_part_bom(db, source.id, child.id, Decimal("2"))
    target = composite_plating_target(db, source.id, "G", create=True)["part"]
    add_stock(db, "part", source.id, 12, "分类前库存")
    before = {key: getattr(source, key) for key in Part.__table__.columns.keys() if key != "category"}
    costs_before = db.query(PartCostLog).count()
    stock_logs_before = db.query(InventoryLog).count()

    url = "/api/parts/batch-update-category"
    assert client.post(url, json={"part_ids": [source.id, "MISSING"], "category": "耳饰配件"}).status_code == 400
    assert source.category == target.category == "小配件"
    result = client.post(url, json={"part_ids": [source.id, target.id, source.id], "category": "耳饰配件"})
    assert result.status_code == 200, result.text
    assert result.json() == {"updated_count": 2}
    assert source.category == target.category == "耳饰配件" and child.category == "小配件"
    assert {key: getattr(source, key) for key in before} == before
    assert (bom.child_part_id, bom.qty_per_unit) == (child.id, Decimal("2"))
    assert db.get(CompositePlatingTarget, (source.id, "G")).target_part_id == target.id
    assert composite_plating_target(db, source.id, "G")["part"].id == target.id
    assert db.query(PartCostLog).count() == costs_before
    assert db.query(InventoryLog).count() == stock_logs_before
    assert get_stock(db, "part", source.id) == 12
    response = client.post(url, json={"part_ids": [source.id, target.id], "category": "耳饰配件"})
    assert response.json() == {"updated_count": 0}
