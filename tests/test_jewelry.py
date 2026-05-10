import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.jewelry import copy_jewelry, create_jewelry, get_jewelry, list_jewelries, update_jewelry, set_status, delete_jewelry, JEWELRY_CATEGORIES
from services.bom import set_bom, get_bom
from services.part import create_part


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


# ---------------------------------------------------------------------------
# copy_jewelry tests
# ---------------------------------------------------------------------------


def _seed_part(db, name="珍珠", category="小配件"):
    return create_part(db, {"name": name, "category": category, "unit": "颗"})


def test_copy_jewelry_basic_info(db):
    src = create_jewelry(db, {
        "name": "源套装",
        "category": "套装",
        "color": "金",
        "unit": "套",
        "retail_price": 200.0,
        "wholesale_price": 120.0,
        "image": "src.jpg",
        "structure_image": "src-struct.jpg",
        "handcraft_cost": 30.0,
    })
    new = copy_jewelry(db, src.id, {"name": "源套装-副本"})
    assert new.id != src.id
    assert new.id.startswith("SP-SET-")
    assert new.name == "源套装-副本"
    assert new.category == "套装"
    assert new.color == "金"
    assert new.unit == "套"
    assert float(new.retail_price) == 200.0
    assert float(new.wholesale_price) == 120.0
    assert new.image == "src.jpg"
    assert new.structure_image == "src-struct.jpg"
    assert float(new.handcraft_cost) == 30.0
    assert new.status == "active"


def test_copy_jewelry_clones_bom(db):
    src = create_jewelry(db, {"name": "S", "category": "单件"})
    p1 = _seed_part(db, name="珍珠")
    p2 = _seed_part(db, name="链子")
    set_bom(db, src.id, p1.id, 2.5)
    set_bom(db, src.id, p2.id, 1.0)

    new = copy_jewelry(db, src.id, {"name": "S-副本"})
    rows = get_bom(db, new.id)
    parts = {r.part_id: float(r.qty_per_unit) for r in rows}
    assert parts == {p1.id: 2.5, p2.id: 1.0}


def test_copy_jewelry_override_fields(db):
    src = create_jewelry(db, {"name": "S", "category": "单件", "color": "金", "retail_price": 50.0})
    new = copy_jewelry(db, src.id, {"name": "S-副本", "color": "银", "retail_price": 80.0})
    assert new.name == "S-副本"
    assert new.color == "银"
    assert float(new.retail_price) == 80.0


def test_copy_jewelry_ignores_category_in_override(db):
    src = create_jewelry(db, {"name": "S", "category": "套装"})
    new = copy_jewelry(db, src.id, {"name": "S-副本", "category": "单件"})
    assert new.category == "套装"
    assert new.id.startswith("SP-SET-")


def test_copy_jewelry_source_not_found(db):
    with pytest.raises(ValueError, match="Jewelry not found"):
        copy_jewelry(db, "SP-PCS-99999", {"name": "X"})


def test_copy_jewelry_empty_bom(db):
    src = create_jewelry(db, {"name": "S", "category": "单件"})
    new = copy_jewelry(db, src.id, {"name": "S-副本"})
    assert get_bom(db, new.id) == []
