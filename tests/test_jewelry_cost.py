from decimal import Decimal

from services.jewelry_cost import compute_jewelry_cost


class _FakeJewelry:
    def __init__(self, handcraft_cost):
        self.handcraft_cost = handcraft_cost


class _FakeBom:
    def __init__(self, part_id, qty_per_unit):
        self.part_id = part_id
        self.qty_per_unit = qty_per_unit


class _FakePart:
    def __init__(self, id, name, unit_cost):
        self.id = id
        self.name = name
        self.unit_cost = unit_cost


def test_compute_basic():
    jewelry = _FakeJewelry(handcraft_cost=1.0)
    bom_rows = [_FakeBom("PJ-X-1", 10), _FakeBom("PJ-LT-1", 1)]
    part_map = {
        "PJ-X-1": _FakePart("PJ-X-1", "珠", Decimal("0.05")),
        "PJ-LT-1": _FakePart("PJ-LT-1", "链", Decimal("2.0")),
    }
    r = compute_jewelry_cost(jewelry, bom_rows, part_map)
    # 物料 = 10×0.05 + 1×2.0 = 2.5
    assert r["material_cost"] == Decimal("2.5000000")
    assert r["handcraft_cost"] == Decimal("1")
    assert r["total_cost"] == Decimal("3.5000000")
    assert r["has_incomplete_cost"] is False
    assert len(r["bom_details"]) == 2


def test_compute_missing_unit_cost_marks_incomplete():
    jewelry = _FakeJewelry(handcraft_cost=None)
    bom_rows = [_FakeBom("PJ-X-1", 1)]
    part_map = {"PJ-X-1": _FakePart("PJ-X-1", "无价", None)}
    r = compute_jewelry_cost(jewelry, bom_rows, part_map)
    assert r["has_incomplete_cost"] is True
    assert r["material_cost"] == Decimal("0E-7")
    assert r["total_cost"] == Decimal("0E-7")


def test_compute_no_bom_marks_incomplete():
    jewelry = _FakeJewelry(handcraft_cost=5.0)
    r = compute_jewelry_cost(jewelry, [], {})
    assert r["has_incomplete_cost"] is True
    assert r["material_cost"] == Decimal("0")
    # 仍把手工费算进去
    assert r["total_cost"] == Decimal("5")


def test_compute_missing_part_marks_incomplete():
    jewelry = _FakeJewelry(handcraft_cost=0)
    bom_rows = [_FakeBom("PJ-GONE", 3)]
    r = compute_jewelry_cost(jewelry, bom_rows, {})  # part_map 缺这个件
    assert r["has_incomplete_cost"] is True
    assert r["material_cost"] == Decimal("0E-7")


import pytest
from services.jewelry import create_jewelry, update_jewelry
from services.part import create_part, update_part_cost
from services.bom import set_bom
from services.jewelry_cost import attach_jewelry_costs


def test_attach_costs_batch(db):
    p1 = create_part(db, {"name": "珠", "category": "小配件"})
    p2 = create_part(db, {"name": "链", "category": "链条"})
    update_part_cost(db, p1.id, "purchase_cost", 0.05)
    update_part_cost(db, p2.id, "purchase_cost", 2.0)

    j1 = create_jewelry(db, {"name": "项链A", "category": "单件"})
    set_bom(db, j1.id, p1.id, 10)   # 0.5
    set_bom(db, j1.id, p2.id, 1)    # 2.0
    update_jewelry(db, j1.id, {"handcraft_cost": 1.0})

    j2 = create_jewelry(db, {"name": "无BOM件", "category": "单件"})

    attach_jewelry_costs(db, [j1, j2])

    assert j1.material_cost == pytest.approx(2.5)
    assert j1.total_cost == pytest.approx(3.5)
    assert j1.has_incomplete_cost is False

    # 无 BOM → 物料 0、标记不完整、总成本 = 0（无手工费）
    assert j2.material_cost == pytest.approx(0.0)
    assert j2.has_incomplete_cost is True
    assert j2.total_cost == pytest.approx(0.0)


def test_attach_costs_incomplete_when_part_has_no_unit_cost(db):
    p = create_part(db, {"name": "无价件", "category": "小配件"})  # 不设成本 → unit_cost None
    j = create_jewelry(db, {"name": "X", "category": "单件"})
    set_bom(db, j.id, p.id, 3)
    attach_jewelry_costs(db, [j])
    assert j.has_incomplete_cost is True
    assert j.material_cost == pytest.approx(0.0)


def test_attach_costs_empty_list_noop(db):
    assert attach_jewelry_costs(db, []) == []
