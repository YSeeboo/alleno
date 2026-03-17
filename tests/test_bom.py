import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.part import create_part
from services.jewelry import create_jewelry
from services.bom import set_bom, get_bom, delete_bom_item, calculate_parts_needed


@pytest.fixture
def seeded(db):
    p1 = create_part(db, {"name": "铜扣", "category": "小配件"})
    p2 = create_part(db, {"name": "银链", "category": "链条"})
    j = create_jewelry(db, {"name": "玫瑰戒指", "category": "单件"})
    return db, p1, p2, j


def test_set_bom_creates_new(seeded):
    db, p1, p2, j = seeded
    bom = set_bom(db, j.id, p1.id, 2.0)
    assert bom.id == "BM-0001"
    assert float(bom.qty_per_unit) == 2.0


def test_set_bom_updates_existing(seeded):
    db, p1, p2, j = seeded
    bom1 = set_bom(db, j.id, p1.id, 2.0)
    bom2 = set_bom(db, j.id, p1.id, 5.0)
    # Same record, just updated
    assert bom1.id == bom2.id
    assert float(bom2.qty_per_unit) == 5.0


def test_set_bom_multiple_parts(seeded):
    db, p1, p2, j = seeded
    set_bom(db, j.id, p1.id, 2.0)
    set_bom(db, j.id, p2.id, 1.0)
    rows = get_bom(db, j.id)
    assert len(rows) == 2


def test_get_bom_empty(db):
    j = create_jewelry(db, {"name": "X", "category": "单件"})
    assert get_bom(db, j.id) == []


def test_delete_bom_item(seeded):
    db, p1, p2, j = seeded
    bom = set_bom(db, j.id, p1.id, 2.0)
    delete_bom_item(db, bom.id)
    assert get_bom(db, j.id) == []


def test_delete_bom_item_not_found(db):
    with pytest.raises(ValueError):
        delete_bom_item(db, "BM-9999")


def test_calculate_parts_needed(seeded):
    db, p1, p2, j = seeded
    set_bom(db, j.id, p1.id, 2.0)
    set_bom(db, j.id, p2.id, 3.0)
    needed = calculate_parts_needed(db, j.id, qty=5)
    assert needed[p1.id] == 10.0  # 2 * 5
    assert needed[p2.id] == 15.0  # 3 * 5
