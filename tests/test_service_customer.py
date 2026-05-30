"""Unit tests for services/customer.list_distinct_customer_names."""
from services.customer import list_distinct_customer_names
from services.order import create_order
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock
from services.handcraft import create_handcraft_order, add_handcraft_jewelry


def _seed_part_jewelry(db):
    part = create_part(db, {"name": "P-C", "category": "小配件", "color": "古铜"})
    jewelry = create_jewelry(db, {"name": "J-C", "category": "单件"})
    add_stock(db, "part", part.id, 100.0, "init")
    return part, jewelry


def test_empty_db_returns_empty(db):
    assert list_distinct_customer_names(db) == []


def test_dedupes_across_two_sources(db):
    """Order.customer_name + HandcraftJewelryItem.customer_name union into a
    single deduped list. (HandcraftOrder has no customer_name column.)"""
    part, jewelry = _seed_part_jewelry(db)

    # Source 1: Order.customer_name (sales order)
    create_order(db, "张三", [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10}])

    # Source 2: HandcraftJewelryItem.customer_name (manual attribution on HC row)
    hc = create_handcraft_order(db, "S-A", [{"part_id": part.id, "qty": 1.0}])
    add_handcraft_jewelry(db, hc.id, {
        "jewelry_id": jewelry.id, "qty": 2, "customer_name": "李四",
    })

    # Same name from each source — must dedupe to a single entry
    create_order(db, "王五", [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10}])
    hc2 = create_handcraft_order(db, "S-B", [{"part_id": part.id, "qty": 1.0}])
    add_handcraft_jewelry(db, hc2.id, {
        "jewelry_id": jewelry.id, "qty": 1, "customer_name": "王五",
    })

    names = list_distinct_customer_names(db)
    assert sorted(names) == sorted(["张三", "李四", "王五"])


def test_query_filters_case_insensitive_substring(db):
    part, jewelry = _seed_part_jewelry(db)
    create_order(db, "Alice", [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10}])
    create_order(db, "alex",  [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10}])
    create_order(db, "Bob",   [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10}])

    assert sorted(list_distinct_customer_names(db, query="al")) == ["Alice", "alex"]
    assert sorted(list_distinct_customer_names(db, query="AL")) == ["Alice", "alex"]
    assert list_distinct_customer_names(db, query="Z") == []


def test_excludes_empty_and_whitespace_names(db):
    """Empty strings must not appear in the result."""
    part, jewelry = _seed_part_jewelry(db)
    create_order(db, "Real", [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10}])
    names = list_distinct_customer_names(db)
    assert "" not in names
    assert "Real" in names


def test_limit_truncates(db):
    part, jewelry = _seed_part_jewelry(db)
    for i in range(60):
        create_order(db, f"C{i:03d}", [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10}])
    names = list_distinct_customer_names(db, limit=10)
    assert len(names) == 10
