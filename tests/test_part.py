import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from sqlalchemy import create_engine, inspect, text
from services.part import create_part, get_part, list_parts, update_part, delete_part
from database import ensure_optional_columns


def test_create_part_generates_id(db):
    part = create_part(db, {"name": "铜扣", "category": "扣件"})
    assert part.id == "PJ-0001"
    assert part.name == "铜扣"


def test_create_part_sequential_ids(db):
    p1 = create_part(db, {"name": "A"})
    p2 = create_part(db, {"name": "B"})
    assert p1.id == "PJ-0001"
    assert p2.id == "PJ-0002"


def test_get_part_found(db):
    create_part(db, {"name": "铜扣"})
    part = get_part(db, "PJ-0001")
    assert part is not None
    assert part.name == "铜扣"


def test_get_part_not_found(db):
    assert get_part(db, "PJ-9999") is None


def test_list_parts_all(db):
    create_part(db, {"name": "A", "category": "扣件"})
    create_part(db, {"name": "B", "category": "链条"})
    assert len(list_parts(db)) == 2


def test_list_parts_returns_latest_first(db):
    create_part(db, {"name": "A"})
    create_part(db, {"name": "B"})
    results = list_parts(db)
    assert [part.id for part in results] == ["PJ-0002", "PJ-0001"]


def test_list_parts_filter_category(db):
    create_part(db, {"name": "A", "category": "扣件"})
    create_part(db, {"name": "B", "category": "链条"})
    results = list_parts(db, category="扣件")
    assert len(results) == 1
    assert results[0].name == "A"


def test_list_parts_filter_name(db):
    create_part(db, {"name": "铜扣环"})
    create_part(db, {"name": "银链条"})
    results = list_parts(db, name="铜")
    assert len(results) == 1
    assert results[0].name == "铜扣环"


def test_list_parts_filter_name_no_match(db):
    create_part(db, {"name": "铜扣环"})
    results = list_parts(db, name="金")
    assert len(results) == 0


def test_update_part_partial(db):
    create_part(db, {"name": "铜扣", "category": "扣件"})
    part = update_part(db, "PJ-0001", {"name": "铜扣V2"})
    assert part.name == "铜扣V2"
    assert part.category == "扣件"  # untouched


def test_update_part_not_found(db):
    with pytest.raises(ValueError):
        update_part(db, "PJ-9999", {"name": "X"})


def test_delete_part(db):
    create_part(db, {"name": "铜扣"})
    delete_part(db, "PJ-0001")
    assert get_part(db, "PJ-0001") is None


def test_delete_part_not_found(db):
    with pytest.raises(ValueError):
        delete_part(db, "PJ-9999")


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
