import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.jewelry import create_jewelry, get_jewelry, list_jewelries, update_jewelry, set_status, delete_jewelry, JEWELRY_CATEGORIES


# ---------------------------------------------------------------------------
# Category validation tests
# ---------------------------------------------------------------------------

def test_create_jewelry_valid_category_set(db):
    j = create_jewelry(db, {"name": "金套装", "category": "套装"})
    assert j.id == "SP-SET-00001"
    assert j.category == "套装"
    assert j.status == "active"


def test_create_jewelry_valid_category_pcs(db):
    j = create_jewelry(db, {"name": "玫瑰戒指", "category": "单件"})
    assert j.id == "SP-PCS-00001"


def test_create_jewelry_valid_category_pair(db):
    j = create_jewelry(db, {"name": "耳环一对", "category": "单对"})
    assert j.id == "SP-PAIR-00001"


def test_create_jewelry_sequential_ids_same_category(db):
    j1 = create_jewelry(db, {"name": "A", "category": "单件"})
    j2 = create_jewelry(db, {"name": "B", "category": "单件"})
    assert j1.id == "SP-PCS-00001"
    assert j2.id == "SP-PCS-00002"


def test_create_jewelry_sequential_ids_different_categories(db):
    j1 = create_jewelry(db, {"name": "A", "category": "套装"})
    j2 = create_jewelry(db, {"name": "B", "category": "单对"})
    assert j1.id == "SP-SET-00001"
    assert j2.id == "SP-PAIR-00001"


def test_create_jewelry_invalid_category_raises(db):
    with pytest.raises(ValueError, match="Invalid category"):
        create_jewelry(db, {"name": "X", "category": "戒指"})


def test_create_jewelry_missing_category_raises(db):
    with pytest.raises(ValueError, match="Invalid category"):
        create_jewelry(db, {"name": "X"})


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

def test_get_jewelry(db):
    create_jewelry(db, {"name": "玫瑰戒指", "category": "单件"})
    j = get_jewelry(db, "SP-PCS-00001")
    assert j.name == "玫瑰戒指"


def test_get_jewelry_not_found(db):
    assert get_jewelry(db, "SP-PCS-99999") is None


def test_list_jewelries_filter_status(db):
    create_jewelry(db, {"name": "A", "category": "单件"})
    j2 = create_jewelry(db, {"name": "B", "category": "单件"})
    set_status(db, j2.id, "inactive")
    active = list_jewelries(db, status="active")
    assert len(active) == 1


def test_list_jewelries_filter_category(db):
    create_jewelry(db, {"name": "A", "category": "套装"})
    create_jewelry(db, {"name": "B", "category": "单对"})
    assert len(list_jewelries(db, category="套装")) == 1


def test_set_status_valid(db):
    create_jewelry(db, {"name": "A", "category": "单件"})
    j = set_status(db, "SP-PCS-00001", "inactive")
    assert j.status == "inactive"


def test_set_status_invalid(db):
    create_jewelry(db, {"name": "A", "category": "单件"})
    with pytest.raises(ValueError, match="Invalid status"):
        set_status(db, "SP-PCS-00001", "deleted")


def test_update_jewelry_partial(db):
    create_jewelry(db, {"name": "A", "category": "套装"})
    j = update_jewelry(db, "SP-SET-00001", {"name": "B"})
    assert j.name == "B"
    assert j.category == "套装"


def test_update_jewelry_category_raises(db):
    # Any attempt to change category should fail — the ID encodes the category.
    create_jewelry(db, {"name": "A", "category": "套装"})
    with pytest.raises(ValueError, match="Category cannot be changed after creation"):
        update_jewelry(db, "SP-SET-00001", {"category": "非法分类"})


def test_update_jewelry_valid_category_still_raises(db):
    # Even passing a valid (but different) category is disallowed.
    create_jewelry(db, {"name": "A", "category": "套装"})
    with pytest.raises(ValueError, match="Category cannot be changed after creation"):
        update_jewelry(db, "SP-SET-00001", {"category": "单件"})


def test_delete_jewelry(db):
    create_jewelry(db, {"name": "A", "category": "单件"})
    delete_jewelry(db, "SP-PCS-00001")
    assert get_jewelry(db, "SP-PCS-00001") is None


def test_delete_jewelry_not_found(db):
    with pytest.raises(ValueError):
        delete_jewelry(db, "SP-PCS-99999")
