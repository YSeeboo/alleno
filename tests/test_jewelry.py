import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.jewelry import create_jewelry, get_jewelry, list_jewelries, update_jewelry, set_status, delete_jewelry


def test_create_jewelry_id(db):
    j = create_jewelry(db, {"name": "玫瑰戒指"})
    assert j.id == "SP-0001"
    assert j.status == "active"


def test_get_jewelry(db):
    create_jewelry(db, {"name": "玫瑰戒指"})
    j = get_jewelry(db, "SP-0001")
    assert j.name == "玫瑰戒指"


def test_get_jewelry_not_found(db):
    assert get_jewelry(db, "SP-9999") is None


def test_list_jewelries_filter_status(db):
    create_jewelry(db, {"name": "A"})
    j2 = create_jewelry(db, {"name": "B"})
    set_status(db, j2.id, "inactive")
    active = list_jewelries(db, status="active")
    assert len(active) == 1


def test_list_jewelries_returns_latest_first(db):
    create_jewelry(db, {"name": "A"})
    create_jewelry(db, {"name": "B"})
    results = list_jewelries(db)
    assert [item.id for item in results] == ["SP-0002", "SP-0001"]


def test_list_jewelries_filter_category(db):
    create_jewelry(db, {"name": "A", "category": "戒指"})
    create_jewelry(db, {"name": "B", "category": "项链"})
    assert len(list_jewelries(db, category="戒指")) == 1


def test_set_status_valid(db):
    create_jewelry(db, {"name": "A"})
    j = set_status(db, "SP-0001", "inactive")
    assert j.status == "inactive"


def test_set_status_invalid(db):
    create_jewelry(db, {"name": "A"})
    with pytest.raises(ValueError, match="Invalid status"):
        set_status(db, "SP-0001", "deleted")


def test_update_jewelry_partial(db):
    create_jewelry(db, {"name": "A", "category": "戒指"})
    j = update_jewelry(db, "SP-0001", {"name": "B"})
    assert j.name == "B"
    assert j.category == "戒指"


def test_delete_jewelry(db):
    create_jewelry(db, {"name": "A"})
    delete_jewelry(db, "SP-0001")
    assert get_jewelry(db, "SP-0001") is None


def test_delete_jewelry_not_found(db):
    with pytest.raises(ValueError):
        delete_jewelry(db, "SP-9999")
