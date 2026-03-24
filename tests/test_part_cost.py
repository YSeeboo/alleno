import pytest
from decimal import Decimal

from models.part import Part
from services.part import create_part, update_part, create_part_variant


@pytest.fixture
def part(db):
    return create_part(db, {"name": "测试配件", "category": "吊坠"})


def test_update_part_cost_purchase(db, part):
    from services.part import update_part_cost
    log = update_part_cost(db, part.id, "purchase_cost", 2.5, source_id="CG-0001")
    assert log is not None
    assert log.field == "purchase_cost"
    assert log.cost_before is None
    assert log.cost_after == Decimal("2.5")
    assert log.unit_cost_before is None or log.unit_cost_before == 0
    assert log.unit_cost_after == Decimal("2.5")
    assert log.source_id == "CG-0001"
    assert part.purchase_cost == Decimal("2.5")
    assert part.unit_cost == Decimal("2.5")


def test_update_part_cost_accumulates(db, part):
    from services.part import update_part_cost
    update_part_cost(db, part.id, "purchase_cost", 2.5)
    update_part_cost(db, part.id, "bead_cost", 0.15)
    update_part_cost(db, part.id, "plating_cost", 1.0)
    assert part.unit_cost == Decimal("3.65")


def test_update_part_cost_no_change_returns_none(db, part):
    from services.part import update_part_cost
    update_part_cost(db, part.id, "purchase_cost", 2.5)
    result = update_part_cost(db, part.id, "purchase_cost", 2.5)
    assert result is None


def test_update_part_cost_invalid_field(db, part):
    from services.part import update_part_cost
    with pytest.raises(ValueError, match="无效"):
        update_part_cost(db, part.id, "invalid_field", 1.0)


def test_update_part_cost_logs_recorded(db, part):
    from services.part import update_part_cost, list_part_cost_logs
    update_part_cost(db, part.id, "purchase_cost", 2.5, source_id="CG-0001")
    update_part_cost(db, part.id, "bead_cost", 0.15, source_id="CG-0001")
    logs = list_part_cost_logs(db, part.id)
    assert len(logs) == 2
    assert logs[0].field == "bead_cost"  # DESC order
    assert logs[1].field == "purchase_cost"


def test_update_part_ignores_unit_cost(db, part):
    from services.part import update_part_cost
    update_part_cost(db, part.id, "purchase_cost", 2.5)
    updated = update_part(db, part.id, {"name": "新名称", "unit_cost": 999})
    assert updated.unit_cost == Decimal("2.5")
    assert updated.name == "新名称"


def test_create_variant_inherits_purchase_and_bead_cost(db, part):
    """Variants should inherit purchase_cost and bead_cost from parent, but not plating_cost."""
    from services.part import update_part_cost
    update_part_cost(db, part.id, "purchase_cost", 2.5)
    update_part_cost(db, part.id, "bead_cost", 0.15)
    update_part_cost(db, part.id, "plating_cost", 1.0)
    variant = create_part_variant(db, part.id, "G")
    assert float(variant.purchase_cost) == 2.5
    assert float(variant.bead_cost) == 0.15
    assert variant.plating_cost is None
    assert float(variant.unit_cost) == 2.65  # 2.5 + 0.15, no plating


# --- API Tests ---

def test_api_part_response_includes_cost_fields(client, db):
    from models.part import Part as PartModel
    p = PartModel(id="PJ-DZ-99999", name="API测试配件", category="吊坠")
    db.add(p)
    db.flush()
    resp = client.get("/api/parts/PJ-DZ-99999")
    assert resp.status_code == 200
    data = resp.json()
    assert "purchase_cost" in data
    assert "bead_cost" in data
    assert "plating_cost" in data
    assert data["purchase_cost"] is None


def test_api_get_cost_logs(client, db):
    from services.part import update_part_cost
    p = Part(id="PJ-DZ-99998", name="日志测试配件", category="吊坠")
    db.add(p)
    db.flush()
    update_part_cost(db, p.id, "purchase_cost", 2.5, source_id="CG-0001")
    update_part_cost(db, p.id, "bead_cost", 0.15, source_id="CG-0001")

    resp = client.get(f"/api/parts/{p.id}/cost-logs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["field"] == "bead_cost"
    assert data[0]["source_id"] == "CG-0001"
    assert data[1]["field"] == "purchase_cost"


def test_api_get_cost_logs_empty(client, db):
    p = Part(id="PJ-DZ-99997", name="空日志配件", category="吊坠")
    db.add(p)
    db.flush()
    resp = client.get(f"/api/parts/{p.id}/cost-logs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_api_update_part_ignores_unit_cost(client, db):
    from services.part import update_part_cost
    p = Part(id="PJ-DZ-99996", name="忽略成本配件", category="吊坠")
    db.add(p)
    db.flush()
    update_part_cost(db, p.id, "purchase_cost", 5.0)

    resp = client.patch("/api/parts/PJ-DZ-99996", json={"unit_cost": 999})
    assert resp.status_code == 200
    assert resp.json()["unit_cost"] == 5.0
