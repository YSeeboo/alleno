"""Service-layer tests for cargo-sorting features."""
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock
from services.handcraft import (
    create_handcraft_order,
    get_handcraft_jewelry_breakdown,
    _has_sorting_info,
    list_suppliers_with_sorting,
)


def _setup_jewelry(db, name="J1"):
    part = create_part(db, {"name": "P1", "category": "小配件", "color": "古铜"})
    add_stock(db, "part", part.id, 100.0, "init")
    jewelry = create_jewelry(db, {"name": name, "category": "单件"})
    return part, jewelry


def test_breakdown_only_with_customer_filters_anonymous_entries(db):
    """only_with_customer=True 跳过无客户的 entry 和无 entry 的 group。"""
    part, j_with = _setup_jewelry(db, "withCust")
    _, j_without = _setup_jewelry(db, "noCust")

    order = create_handcraft_order(
        db,
        supplier_name="S1",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[
            {"jewelry_id": j_with.id, "qty": 1, "customer_name": "王小姐"},
            {"jewelry_id": j_without.id, "qty": 1},  # no customer
        ],
    )

    full = get_handcraft_jewelry_breakdown(db, order.id)
    assert len(full) == 2

    filtered = get_handcraft_jewelry_breakdown(db, order.id, only_with_customer=True)
    assert len(filtered) == 1
    assert filtered[0]["jewelry_id"] == j_with.id
    assert all(e["customer_name"] is not None for e in filtered[0]["entries"])


def test_breakdown_only_with_customer_treats_empty_string_as_none(db):
    """customer_name 为空串或空白时，等同于 None。"""
    part, jewelry = _setup_jewelry(db)
    order = create_handcraft_order(
        db,
        supplier_name="S1",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[
            {"jewelry_id": jewelry.id, "qty": 1, "customer_name": ""},
            {"jewelry_id": jewelry.id, "qty": 1, "customer_name": "   "},
            {"jewelry_id": jewelry.id, "qty": 1, "customer_name": "张小姐"},
        ],
    )

    filtered = get_handcraft_jewelry_breakdown(db, order.id, only_with_customer=True)
    assert len(filtered) == 1
    assert len(filtered[0]["entries"]) == 1
    assert filtered[0]["entries"][0]["customer_name"] == "张小姐"


def test_has_sorting_info_true_when_any_row_has_customer(db):
    part, jewelry = _setup_jewelry(db)
    order = create_handcraft_order(
        db,
        supplier_name="S1",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[
            {"jewelry_id": jewelry.id, "qty": 1},
            {"jewelry_id": jewelry.id, "qty": 1, "customer_name": "李太"},
        ],
    )
    assert _has_sorting_info(db, order.id) is True


def test_has_sorting_info_false_when_no_customer(db):
    part, jewelry = _setup_jewelry(db)
    order = create_handcraft_order(
        db,
        supplier_name="S1",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1}],
    )
    assert _has_sorting_info(db, order.id) is False


def test_has_sorting_info_ignores_blank_customer_name(db):
    part, jewelry = _setup_jewelry(db)
    order = create_handcraft_order(
        db,
        supplier_name="S1",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": "  "}],
    )
    assert _has_sorting_info(db, order.id) is False


def test_list_suppliers_with_sorting_returns_only_qualifying_suppliers(db):
    part, jewelry = _setup_jewelry(db)
    # Supplier A: 有分拣信息
    create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": "C1"}],
    )
    # Supplier B: 无分拣信息
    create_handcraft_order(
        db, supplier_name="商家B",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1}],
    )
    # Supplier A 再来一单（验证去重）
    create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 2, "customer_name": "C2"}],
    )

    suppliers = list_suppliers_with_sorting(db)
    assert suppliers == ["商家A"]


def test_list_suppliers_with_sorting_empty_when_no_orders(db):
    assert list_suppliers_with_sorting(db) == []
