"""Tests for cutting statistics (裁剪统计) service + API."""

import pytest

from services.part import create_part
from services.jewelry import create_jewelry
from services.bom import set_bom
from services.inventory import add_stock
from services.part_bom import set_part_bom
from services.cutting_stats import (
    _extract_cm,
    _merge_items,
    get_order_cutting_stats,
    get_handcraft_cutting_stats,
)


# ---------------------------------------------------------------------------
# Unit tests for _extract_cm
# ---------------------------------------------------------------------------

class TestExtractCm:
    def test_integer_cm(self):
        assert _extract_cm("金色O字链-18cm") == 18.0

    def test_float_cm(self):
        assert _extract_cm("银色蛇骨链-45.5cm") == 45.5

    def test_no_match(self):
        assert _extract_cm("普通吊坠") is None

    def test_none_input(self):
        assert _extract_cm(None) is None

    def test_empty_string(self):
        assert _extract_cm("") is None

    def test_cm_in_middle(self):
        assert _extract_cm("链条10cm加粗版") == 10.0


# ---------------------------------------------------------------------------
# Unit tests for _merge_items
# ---------------------------------------------------------------------------

class TestMergeItems:
    def test_merge_same_part(self):
        items = [
            {
                "part_id": "PJ-LT-00001",
                "part_name": "链条-18cm",
                "part_image": None,
                "cut_length_cm": 18.0,
                "qty": 30,
                "sources": [{"label": "A", "qty": 30}],
            },
            {
                "part_id": "PJ-LT-00001",
                "part_name": "链条-18cm",
                "part_image": None,
                "cut_length_cm": 18.0,
                "qty": 20,
                "sources": [{"label": "B", "qty": 20}],
            },
        ]
        merged = _merge_items(items)
        assert len(merged) == 1
        assert merged[0]["qty"] == 50
        assert len(merged[0]["sources"]) == 2

    def test_no_merge_different_parts(self):
        items = [
            {
                "part_id": "PJ-LT-00001",
                "part_name": "链条-18cm",
                "part_image": None,
                "cut_length_cm": 18.0,
                "qty": 30,
                "sources": [{"label": "A", "qty": 30}],
            },
            {
                "part_id": "PJ-LT-00002",
                "part_name": "链条-20cm",
                "part_image": None,
                "cut_length_cm": 20.0,
                "qty": 10,
                "sources": [{"label": "B", "qty": 10}],
            },
        ]
        merged = _merge_items(items)
        assert len(merged) == 2

    def test_empty_input(self):
        assert _merge_items([]) == []


# ---------------------------------------------------------------------------
# Integration: order cutting stats
# ---------------------------------------------------------------------------

def _make_chain_part(db, name="金色O字链-18cm"):
    return create_part(db, {"name": name, "category": "链条"})


def _make_non_chain_part(db, name="普通吊坠"):
    return create_part(db, {"name": name, "category": "小配件"})


def test_order_cutting_stats_basic(db):
    """Parts with cm in name appear in cutting stats."""
    chain = _make_chain_part(db)
    pendant = _make_non_chain_part(db)
    jewelry = create_jewelry(db, {"name": "项链A", "category": "单件"})
    set_bom(db, jewelry.id, chain.id, 1.0)
    set_bom(db, jewelry.id, pendant.id, 2.0)

    from services.order import create_order
    order = create_order(db, "TestCustomer", [
        {"jewelry_id": jewelry.id, "quantity": 10, "unit_price": 1.0},
    ])

    stats = get_order_cutting_stats(db, order.id)
    assert len(stats) == 1
    assert stats[0]["part_id"] == chain.id
    assert stats[0]["cut_length_cm"] == 18.0
    assert stats[0]["qty"] == 10  # 1.0 qty_per_unit * 10 order qty


def test_order_cutting_stats_no_match(db):
    """No parts with cm -> empty result."""
    pendant = _make_non_chain_part(db)
    jewelry = create_jewelry(db, {"name": "耳环A", "category": "单件"})
    set_bom(db, jewelry.id, pendant.id, 1.0)

    from services.order import create_order
    order = create_order(db, "TestCustomer", [
        {"jewelry_id": jewelry.id, "quantity": 5, "unit_price": 2.0},
    ])

    stats = get_order_cutting_stats(db, order.id)
    assert stats == []


def test_order_cutting_stats_composite_expansion(db):
    """Composite parts should be BOM-expanded; their children with cm appear."""
    # child chain part
    child_chain = _make_chain_part(db, name="银色链条-20cm")
    # parent composite part (no cm in name)
    parent = create_part(db, {"name": "组合吊坠A", "category": "小配件"})
    set_part_bom(db, parent.id, child_chain.id, 2.0)  # 2 chains per composite

    jewelry = create_jewelry(db, {"name": "项链B", "category": "单件"})
    set_bom(db, jewelry.id, parent.id, 1.0)

    from services.order import create_order
    order = create_order(db, "TestCustomer", [
        {"jewelry_id": jewelry.id, "quantity": 5, "unit_price": 3.0},
    ])

    stats = get_order_cutting_stats(db, order.id)
    assert len(stats) == 1
    assert stats[0]["part_id"] == child_chain.id
    assert stats[0]["cut_length_cm"] == 20.0
    # 5 order qty * 1.0 bom_per_unit * 2.0 child_per_unit = 10
    assert stats[0]["qty"] == 10.0
    assert "[BOM展开]" in stats[0]["sources"][0]["label"]


def test_order_cutting_stats_diamond_dag(db):
    """Diamond DAG: root -> left -> shared -> chain, root -> right -> shared -> chain.
    The shared composite should be counted from BOTH paths, not deduplicated."""
    chain = _make_chain_part(db, name="链条-10cm")
    shared = create_part(db, {"name": "共享组合", "category": "小配件"})
    set_part_bom(db, shared.id, chain.id, 1.0)

    left = create_part(db, {"name": "左组合", "category": "小配件"})
    set_part_bom(db, left.id, shared.id, 1.0)

    right = create_part(db, {"name": "右组合", "category": "小配件"})
    set_part_bom(db, right.id, shared.id, 1.0)

    root = create_part(db, {"name": "根组合", "category": "小配件"})
    set_part_bom(db, root.id, left.id, 1.0)
    set_part_bom(db, root.id, right.id, 1.0)

    jewelry = create_jewelry(db, {"name": "DAG项链", "category": "单件"})
    set_bom(db, jewelry.id, root.id, 1.0)

    from services.order import create_order
    order = create_order(db, "TestCustomer", [
        {"jewelry_id": jewelry.id, "quantity": 5, "unit_price": 1.0},
    ])

    stats = get_order_cutting_stats(db, order.id)
    assert len(stats) == 1
    assert stats[0]["part_id"] == chain.id
    # 5 order * 1.0 root * (1.0 left * 1.0 shared + 1.0 right * 1.0 shared) * 1.0 chain = 10
    assert stats[0]["qty"] == 10.0


def test_order_cutting_stats_deducts_stock(db):
    """Cutting qty should be remaining_qty, not total_qty. Stock on hand reduces the count."""
    chain = _make_chain_part(db, name="链条-10cm")
    add_stock(db, "part", chain.id, 99, "入库")

    jewelry = create_jewelry(db, {"name": "项链C", "category": "单件"})
    set_bom(db, jewelry.id, chain.id, 1.0)

    from services.order import create_order
    order = create_order(db, "TestCustomer", [
        {"jewelry_id": jewelry.id, "quantity": 100, "unit_price": 1.0},
    ])

    stats = get_order_cutting_stats(db, order.id)
    assert len(stats) == 1
    assert stats[0]["qty"] == 1  # 100 needed - 99 in stock = 1


def test_order_cutting_stats_fractional_remaining(db):
    """Fractional remaining should NOT be inflated by ceil. e.g. 0.5 stays 0.5, not 1."""
    chain = _make_chain_part(db, name="链条-10cm")
    add_stock(db, "part", chain.id, 95, "入库")

    jewelry = create_jewelry(db, {"name": "项链E", "category": "单件"})
    # 0.5 chain per jewelry * 191 qty = 95.5 total need
    set_bom(db, jewelry.id, chain.id, 0.5)

    from services.order import create_order
    order = create_order(db, "TestCustomer", [
        {"jewelry_id": jewelry.id, "quantity": 191, "unit_price": 1.0},
    ])

    stats = get_order_cutting_stats(db, order.id)
    assert len(stats) == 1
    # Raw remaining: 95.5 - 95 stock = 0.5 (not ceil'd to 1)
    assert stats[0]["qty"] == 0.5


def test_order_cutting_stats_sufficient_shown_with_zero_qty(db):
    """Parts fully covered by stock still appear in stats (qty=0), but PDF filters them out."""
    chain = _make_chain_part(db, name="链条-10cm")
    add_stock(db, "part", chain.id, 200, "入库")

    jewelry = create_jewelry(db, {"name": "项链D", "category": "单件"})
    set_bom(db, jewelry.id, chain.id, 1.0)

    from services.order import create_order
    order = create_order(db, "TestCustomer", [
        {"jewelry_id": jewelry.id, "quantity": 50, "unit_price": 1.0},
    ])

    stats = get_order_cutting_stats(db, order.id)
    assert len(stats) == 1  # Still returned for modal display
    assert stats[0]["qty"] == 0  # But qty is 0 (fully stocked)


def test_order_cutting_stats_not_found(db):
    with pytest.raises(ValueError, match="不存在"):
        get_order_cutting_stats(db, "OR-9999")


# ---------------------------------------------------------------------------
# Integration: handcraft cutting stats
# ---------------------------------------------------------------------------

def test_handcraft_cutting_stats_basic(db):
    """Parts with cm in name appear in handcraft cutting stats."""
    chain = _make_chain_part(db)
    add_stock(db, "part", chain.id, 100, "入库")

    from services.handcraft import create_handcraft_order
    jewelry = create_jewelry(db, {"name": "J1", "category": "单件"})
    order = create_handcraft_order(
        db,
        supplier_name="TestSupplier",
        parts=[{"part_id": chain.id, "qty": 30}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 5}],
    )

    stats = get_handcraft_cutting_stats(db, order.id)
    assert len(stats) == 1
    assert stats[0]["part_id"] == chain.id
    assert stats[0]["cut_length_cm"] == 18.0
    assert stats[0]["qty"] == 30


def test_handcraft_cutting_stats_composite(db):
    """Composite parts should be BOM-expanded in handcraft cutting stats."""
    child_chain = _make_chain_part(db, name="链条-15cm")
    parent = create_part(db, {"name": "组合配件X", "category": "小配件"})
    set_part_bom(db, parent.id, child_chain.id, 3.0)
    add_stock(db, "part", parent.id, 100, "入库")

    from services.handcraft import create_handcraft_order
    jewelry = create_jewelry(db, {"name": "J2", "category": "单件"})
    order = create_handcraft_order(
        db,
        supplier_name="TestSupplier",
        parts=[{"part_id": parent.id, "qty": 10}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 5}],
    )

    stats = get_handcraft_cutting_stats(db, order.id)
    assert len(stats) == 1
    assert stats[0]["part_id"] == child_chain.id
    assert stats[0]["qty"] == 30.0  # 10 * 3.0
    assert "[BOM展开]" in stats[0]["sources"][0]["label"]


def test_handcraft_cutting_stats_merge(db):
    """Same chain part sent in two batches should merge."""
    chain = _make_chain_part(db)
    add_stock(db, "part", chain.id, 200, "入库")

    from services.handcraft import create_handcraft_order
    jewelry = create_jewelry(db, {"name": "J3", "category": "单件"})
    order = create_handcraft_order(
        db,
        supplier_name="TestSupplier",
        parts=[
            {"part_id": chain.id, "qty": 20},
            {"part_id": chain.id, "qty": 15},
        ],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 5}],
    )

    stats = get_handcraft_cutting_stats(db, order.id)
    assert len(stats) == 1
    assert stats[0]["qty"] == 35
    assert len(stats[0]["sources"]) == 2


def test_handcraft_cutting_stats_not_found(db):
    with pytest.raises(ValueError, match="不存在"):
        get_handcraft_cutting_stats(db, "HC-9999")


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

def test_api_order_cutting_stats(client, db):
    chain = _make_chain_part(db)
    jewelry = create_jewelry(db, {"name": "项链API", "category": "单件"})
    set_bom(db, jewelry.id, chain.id, 1.0)

    from services.order import create_order
    order = create_order(db, "APICustomer", [
        {"jewelry_id": jewelry.id, "quantity": 8, "unit_price": 1.0},
    ])

    resp = client.get(f"/api/orders/{order.id}/cutting-stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["cut_length_cm"] == 18.0


def test_api_order_cutting_stats_404(client, db):
    resp = client.get("/api/orders/OR-9999/cutting-stats")
    assert resp.status_code == 404


def test_api_order_cutting_stats_pdf(client, db):
    chain = _make_chain_part(db)
    jewelry = create_jewelry(db, {"name": "项链PDF", "category": "单件"})
    set_bom(db, jewelry.id, chain.id, 1.0)

    from services.order import create_order
    order = create_order(db, "PDFCustomer", [
        {"jewelry_id": jewelry.id, "quantity": 5, "unit_price": 1.0},
    ])

    resp = client.post(f"/api/orders/{order.id}/cutting-stats/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_api_order_cutting_stats_pdf_empty(client, db):
    """PDF endpoint should return 400 when no cuttable parts exist."""
    pendant = _make_non_chain_part(db)
    jewelry = create_jewelry(db, {"name": "耳环PDF", "category": "单件"})
    set_bom(db, jewelry.id, pendant.id, 1.0)

    from services.order import create_order
    order = create_order(db, "PDFCustomer2", [
        {"jewelry_id": jewelry.id, "quantity": 5, "unit_price": 1.0},
    ])

    resp = client.post(f"/api/orders/{order.id}/cutting-stats/pdf")
    assert resp.status_code == 400


def test_api_handcraft_cutting_stats(client, db):
    chain = _make_chain_part(db)
    add_stock(db, "part", chain.id, 100, "入库")
    jewelry = create_jewelry(db, {"name": "J-API", "category": "单件"})

    from services.handcraft import create_handcraft_order
    order = create_handcraft_order(
        db,
        supplier_name="TestSupplier",
        parts=[{"part_id": chain.id, "qty": 25}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 5}],
    )

    resp = client.get(f"/api/handcraft/{order.id}/cutting-stats")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["qty"] == 25


def test_api_handcraft_cutting_stats_pdf(client, db):
    chain = _make_chain_part(db)
    add_stock(db, "part", chain.id, 100, "入库")
    jewelry = create_jewelry(db, {"name": "J-PDF", "category": "单件"})

    from services.handcraft import create_handcraft_order
    order = create_handcraft_order(
        db,
        supplier_name="TestSupplier",
        parts=[{"part_id": chain.id, "qty": 15}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 3}],
    )

    resp = client.post(f"/api/handcraft/{order.id}/cutting-stats/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_api_handcraft_cutting_stats_404(client, db):
    resp = client.get("/api/handcraft/HC-9999/cutting-stats")
    assert resp.status_code == 404
