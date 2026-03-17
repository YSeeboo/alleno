import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from sqlalchemy import create_engine, inspect, text
from services.part import create_part, get_part, list_parts, update_part, delete_part, PART_CATEGORIES
from database import ensure_optional_columns


# ---------------------------------------------------------------------------
# Category validation tests
# ---------------------------------------------------------------------------

def test_create_part_valid_category_generates_prefixed_id(db):
    part = create_part(db, {"name": "金吊坠", "category": "吊坠"})
    assert part.id == "PJ-DZ-00001"
    assert part.name == "金吊坠"
    assert part.category == "吊坠"


def test_create_part_category_lt(db):
    part = create_part(db, {"name": "银链", "category": "链条"})
    assert part.id == "PJ-LT-00001"


def test_create_part_category_x(db):
    part = create_part(db, {"name": "小扣", "category": "小配件"})
    assert part.id == "PJ-X-00001"


def test_create_part_sequential_ids_same_category(db):
    p1 = create_part(db, {"name": "A", "category": "吊坠"})
    p2 = create_part(db, {"name": "B", "category": "吊坠"})
    assert p1.id == "PJ-DZ-00001"
    assert p2.id == "PJ-DZ-00002"


def test_create_part_sequential_ids_different_categories(db):
    p1 = create_part(db, {"name": "A", "category": "吊坠"})
    p2 = create_part(db, {"name": "B", "category": "链条"})
    assert p1.id == "PJ-DZ-00001"
    assert p2.id == "PJ-LT-00001"


def test_create_part_invalid_category_raises(db):
    with pytest.raises(ValueError, match="Invalid category"):
        create_part(db, {"name": "X", "category": "扣件"})


def test_create_part_missing_category_raises(db):
    with pytest.raises(ValueError, match="Invalid category"):
        create_part(db, {"name": "X"})


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

def test_get_part_found(db):
    create_part(db, {"name": "铜吊坠", "category": "吊坠"})
    part = get_part(db, "PJ-DZ-00001")
    assert part is not None
    assert part.name == "铜吊坠"


def test_get_part_not_found(db):
    assert get_part(db, "PJ-DZ-99999") is None


def test_list_parts_all(db):
    create_part(db, {"name": "A", "category": "吊坠"})
    create_part(db, {"name": "B", "category": "链条"})
    assert len(list_parts(db)) == 2


def test_list_parts_filter_category(db):
    create_part(db, {"name": "A", "category": "吊坠"})
    create_part(db, {"name": "B", "category": "链条"})
    results = list_parts(db, category="吊坠")
    assert len(results) == 1
    assert results[0].name == "A"


def test_list_parts_filter_name(db):
    create_part(db, {"name": "铜吊坠", "category": "吊坠"})
    create_part(db, {"name": "银链条", "category": "链条"})
    results = list_parts(db, name="铜")
    assert len(results) == 1
    assert results[0].name == "铜吊坠"


def test_list_parts_filter_name_no_match(db):
    create_part(db, {"name": "铜吊坠", "category": "吊坠"})
    results = list_parts(db, name="金")
    assert len(results) == 0


def test_update_part_partial(db):
    create_part(db, {"name": "铜吊坠", "category": "吊坠"})
    part = update_part(db, "PJ-DZ-00001", {"name": "铜吊坠V2"})
    assert part.name == "铜吊坠V2"
    assert part.category == "吊坠"  # untouched


def test_update_part_invalid_category_raises(db):
    create_part(db, {"name": "铜吊坠", "category": "吊坠"})
    with pytest.raises(ValueError, match="Invalid category"):
        update_part(db, "PJ-DZ-00001", {"category": "非法分类"})


def test_update_part_not_found(db):
    with pytest.raises(ValueError):
        update_part(db, "PJ-DZ-99999", {"name": "X"})


def test_delete_part(db):
    create_part(db, {"name": "铜吊坠", "category": "吊坠"})
    delete_part(db, "PJ-DZ-00001")
    assert get_part(db, "PJ-DZ-00001") is None


def test_delete_part_not_found(db):
    with pytest.raises(ValueError):
        delete_part(db, "PJ-DZ-99999")


def test_ensure_optional_columns_adds_missing_image(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE part (id TEXT PRIMARY KEY, name TEXT NOT NULL)'))
        conn.execute(text('CREATE TABLE jewelry (id TEXT PRIMARY KEY, name TEXT NOT NULL)'))

    monkeypatch.setattr("database.engine", engine)
    ensure_optional_columns()

    inspector = inspect(engine)
    assert "image" in {column["name"] for column in inspector.get_columns("part")}
    assert "image" in {column["name"] for column in inspector.get_columns("jewelry")}
