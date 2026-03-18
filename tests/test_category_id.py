"""Tests for category-based ID generation and category validation."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.part import create_part
from services.jewelry import create_jewelry


def test_part_prefix_isolation(db):
    """PJ-DZ and PJ-LT counters are independent."""
    p_dz = create_part(db, {"name": "A", "category": "吊坠"})
    p_lt = create_part(db, {"name": "B", "category": "链条"})
    assert p_dz.id.startswith("PJ-DZ-")
    assert p_lt.id.startswith("PJ-LT-")
    # Both should be -00001 since their prefixes are independent
    assert p_dz.id.endswith("-00001")
    assert p_lt.id.endswith("-00001")


def test_part_prefix_counter_increments_per_category(db):
    """Second item in same category gets -00002."""
    p1 = create_part(db, {"name": "A1", "category": "吊坠"})
    p2 = create_part(db, {"name": "A2", "category": "吊坠"})
    p3 = create_part(db, {"name": "B1", "category": "链条"})
    assert p1.id == "PJ-DZ-00001"
    assert p2.id == "PJ-DZ-00002"
    assert p3.id == "PJ-LT-00001"


def test_part_small_part_prefix(db):
    p = create_part(db, {"name": "小零件", "category": "小配件"})
    assert p.id.startswith("PJ-X-")


def test_jewelry_prefix_isolation(db):
    j_set = create_jewelry(db, {"name": "A", "category": "套装"})
    j_pcs = create_jewelry(db, {"name": "B", "category": "单件"})
    j_pair = create_jewelry(db, {"name": "C", "category": "单对"})
    assert j_set.id.startswith("SP-SET-")
    assert j_pcs.id.startswith("SP-PCS-")
    assert j_pair.id.startswith("SP-PAIR-")
    assert j_set.id.endswith("-00001")
    assert j_pcs.id.endswith("-00001")
    assert j_pair.id.endswith("-00001")


def test_create_part_invalid_category(db):
    with pytest.raises(ValueError, match="Invalid category"):
        create_part(db, {"name": "X", "category": "未知品类"})


def test_create_part_missing_category(db):
    with pytest.raises(ValueError, match="Invalid category"):
        create_part(db, {"name": "X"})


def test_create_jewelry_invalid_category(db):
    with pytest.raises(ValueError, match="Invalid category"):
        create_jewelry(db, {"name": "X", "category": "未知品类"})


def test_create_jewelry_missing_category(db):
    with pytest.raises(ValueError, match="Invalid category"):
        create_jewelry(db, {"name": "X"})


def test_api_create_part_invalid_category(client, db):
    resp = client.post("/api/parts/", json={"name": "X", "category": "未知"})
    assert resp.status_code == 400


def test_api_create_jewelry_invalid_category(client, db):
    resp = client.post("/api/jewelries/", json={"name": "X", "category": "未知"})
    assert resp.status_code == 400


def test_api_create_part_missing_category(client, db):
    resp = client.post("/api/parts/", json={"name": "X"})
    assert resp.status_code == 422


def test_api_create_jewelry_missing_category(client, db):
    resp = client.post("/api/jewelries/", json={"name": "X"})
    assert resp.status_code == 422
