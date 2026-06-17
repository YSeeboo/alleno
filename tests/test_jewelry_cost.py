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
