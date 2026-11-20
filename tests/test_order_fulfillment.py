from uuid import uuid4
import pytest

from models import Order, OrderItem, Part, Jewelry, InventoryLog
from models.order_fulfillment import StockReservation, CustomerShipment, CustomerShipmentItem
from services import order_fulfillment as service
from services.inventory import add_stock, deduct_stock, get_stock
from services.order import update_order_item, update_order_status, delete_order_item


@pytest.fixture
def fulfillment(db):
    db.add_all([Part(id="p", name="金色链条", unit="条", category="链条"), Jewelry(id="j", name="项链", unit="条", category="单件"),
                Order(id="A", customer_name="客户甲"), Order(id="B", customer_name="客户乙")])
    db.flush()
    lines = [OrderItem(order_id="A", part_id="p", quantity=50, unit_price=1),
             OrderItem(order_id="A", jewelry_id="j", quantity=30, unit_price=1),
             OrderItem(order_id="A", part_id="p", quantity=20, unit_price=1),
             OrderItem(order_id="B", part_id="p", quantity=50, unit_price=1)]
    db.add_all(lines); db.flush()
    add_stock(db, "part", "p", 100, "真实测试入库")
    add_stock(db, "jewelry", "j", 50, "真实测试入库")
    service.activate(db, "A", True); service.activate(db, "B", True)
    return lines


def draft(db, lines, *, order_id="A", key=None):
    return service.create_shipment(db, {"order_id": order_id, "request_key": key or str(uuid4()),
                                        "lines": [{"order_item_id": line.id, "quantity": qty} for line, qty in lines]})


def test_legacy_never_infers_shipments_and_requires_explicit_activation(db):
    db.add(Order(id="old", customer_name="旧客户", status="已完成")); db.flush()
    summary = service.order_summary(db, "old")
    assert not summary["managed"] and summary["completed_items"] is None and summary["percent"] is None
    with pytest.raises(ValueError, match="历史"):
        service.activate(db, "old", True)
    db.add(Order(id="pending", customer_name="旧待生产")); db.flush()
    with pytest.raises(ValueError, match="必须核实"):
        service.activate(db, "pending", False)
    assert db.query(CustomerShipment).count() == 0 and db.query(InventoryLog).count() == 0


def test_reservations_do_not_change_stock_and_protect_other_customers(db, fulfillment):
    a, _, sibling, b = fulfillment
    service.reserve(db, "B", b.id, 50, 0)
    service.reserve(db, "A", sibling.id, 10, 0)
    with pytest.raises(ValueError, match="公共可用"):
        service.reserve(db, "A", a.id, 41, 0)
    service.reserve(db, "A", a.id, 40, 0)
    assert get_stock(db, "part", "p") == 100
    assert service.stock_balance(db, "part", "p")["public_available"] == 0
    service.reserve(db, "A", a.id, 20, 40)
    assert service.stock_balance(db, "part", "p")["public_available"] == 20
    with pytest.raises(ValueError, match="已变化"):
        service.reserve(db, "A", a.id, 21, 40)


def test_all_outbound_protects_reservations(db, fulfillment):
    service.reserve(db, "B", fulfillment[3].id, 50, 0)
    with pytest.raises(ValueError, match="预留"):
        deduct_stock(db, "part", "p", 51, "其他出库")
    deduct_stock(db, "part", "p", 50, "实际材料发出")
    assert get_stock(db, "part", "p") == 50


def test_draft_no_inventory_effect_void_has_no_effect(db, fulfillment):
    record = draft(db, [(fulfillment[0], 50)])
    assert record["status"] == "draft" and get_stock(db, "part", "p") == 100
    assert db.query(StockReservation).count() == 0
    service.void_shipment(db, record["id"])
    with pytest.raises(ValueError, match="作废"):
        service.confirm_shipment(db, record["id"], True)
    assert get_stock(db, "part", "p") == 100


def test_ship_existing_stock_without_production_and_idempotent_confirmation(db, fulfillment):
    record = draft(db, [(fulfillment[0], 20)])
    with pytest.raises(ValueError, match="核对"):
        service.confirm_shipment(db, record["id"], False)
    service.confirm_shipment(db, record["id"], True)
    service.confirm_shipment(db, record["id"], True)
    assert get_stock(db, "part", "p") == 80
    assert db.query(InventoryLog).filter_by(reason="客户逐笔出货").count() == 1
    assert service.order_summary(db, "A")["completed_items"] == 0
    assert db.get(Order, "A").status == "待生产"
    with pytest.raises(ValueError, match="独立凭据"):
        service.void_shipment(db, record["id"])


def test_confirmation_uses_own_line_reservation_not_sibling(db, fulfillment):
    a, _, sibling, b = fulfillment
    service.reserve(db, "B", b.id, 50, 0)
    service.reserve(db, "A", sibling.id, 20, 0)
    service.reserve(db, "A", a.id, 20, 0)
    record = draft(db, [(a, 31)])
    with pytest.raises(ValueError, match="库存不足"):
        service.confirm_shipment(db, record["id"], True)
    assert db.get(StockReservation, a.id).quantity == 20
    assert db.get(CustomerShipment, record["id"]).status == "draft"
    record2 = draft(db, [(a, 30)])
    service.confirm_shipment(db, record2["id"], True)
    assert db.get(StockReservation, a.id).quantity == 0
    assert db.get(StockReservation, sibling.id).quantity == 20
    assert db.get(StockReservation, b.id).quantity == 50
    assert get_stock(db, "part", "p") == 70


def test_whole_request_validation_and_same_product_aggregation(db, fulfillment):
    a, jewelry, sibling, b = fulfillment
    service.reserve(db, "B", b.id, 40, 0)
    record = draft(db, [(a, 50), (sibling, 20), (jewelry, 10)])
    with pytest.raises(ValueError, match="库存不足"):
        service.confirm_shipment(db, record["id"], True)
    assert get_stock(db, "part", "p") == 100 and get_stock(db, "jewelry", "j") == 50
    assert db.query(InventoryLog).filter_by(reason="客户逐笔出货").count() == 0


def test_stale_draft_revalidates_demand_and_reservations(db, fulfillment):
    a, _, _, b = fulfillment
    stale = draft(db, [(a, 40)])
    actual = draft(db, [(a, 20)])
    service.confirm_shipment(db, actual["id"], True)
    with pytest.raises(ValueError, match="剩余待发"):
        service.confirm_shipment(db, stale["id"], True)
    another = draft(db, [(a, 30)])
    service.reserve(db, "B", b.id, 50, 0)
    deduct_stock(db, "part", "p", 20, "其他真实出库")
    with pytest.raises(ValueError, match="公共可用"):
        service.confirm_shipment(db, another["id"], True)


def test_all_lines_shipped_completes_without_legacy_double_deduction(db, fulfillment):
    a, jewelry, sibling, b = fulfillment
    service.reserve(db, "B", b.id, 20, 0)
    record = draft(db, [(a, 50), (jewelry, 30), (sibling, 20)])
    service.confirm_shipment(db, record["id"], True)
    assert db.get(Order, "A").status == "已完成"
    assert get_stock(db, "part", "p") == 30 and get_stock(db, "jewelry", "j") == 20
    summary = service.order_summary(db, "A")
    assert summary["completed_items"] == 3 and summary["percent"] == 100
    from services.order_cost_snapshot import get_cost_snapshot
    snapshot = get_cost_snapshot(db, "A")
    assert snapshot is not None and snapshot.has_incomplete_cost == 1
    service.confirm_shipment(db, record["id"], True)
    assert get_stock(db, "part", "p") == 30
    with pytest.raises(ValueError, match="回库"):
        update_order_status(db, "A", "生产中")


def test_exact_draft_retry_still_works_after_order_completion(db, fulfillment):
    key = str(uuid4())
    contents = [(fulfillment[0], 50), (fulfillment[1], 30), (fulfillment[2], 20)]
    first = draft(db, contents, key=key)
    service.confirm_shipment(db, first["id"], True)
    assert draft(db, contents, key=key)["id"] == first["id"]
    assert db.query(CustomerShipment).count() == 1


def test_legacy_cost_snapshot_remains_strict_without_bom(db, fulfillment):
    from services.order_cost_snapshot import generate_cost_snapshot
    with pytest.raises(ValueError, match="没有 BOM"):
        generate_cost_snapshot(db, "A")


def _concurrent(db, operations):
    """Use real, separately committed PostgreSQL transactions, not shared sessions."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    db.commit()
    engine = db.get_bind()
    barrier = Barrier(len(operations))

    def run(operation):
        with Session(engine) as session:
            # Do not allow a regression to hang the test suite on a deadlock.
            from sqlalchemy import text
            session.execute(text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=10)
            try:
                operation(session)
                session.commit()
                return "saved"
            except ValueError:
                session.rollback()
                return "rejected"

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(run, operation) for operation in operations]
        results = [future.result(timeout=15) for future in futures]
    db.expire_all()
    return results


def test_concurrent_reservations_never_overbook_shared_stock(db, fulfillment):
    a, _, _, b = fulfillment
    deduct_stock(db, "part", "p", 40, "其他真实出库")
    aid, bid = a.id, b.id
    results = _concurrent(db, [lambda s: service.reserve(s, "A", aid, 50, 0),
                               lambda s: service.reserve(s, "B", bid, 50, 0)])
    assert sorted(results) == ["rejected", "saved"]
    balance = service.stock_balance(db, "part", "p")
    assert balance["reserved_total"] == 50 and balance["public_available"] == 10


def test_concurrent_shipments_cannot_double_spend_public_stock(db, fulfillment):
    a, _, _, b = fulfillment
    deduct_stock(db, "part", "p", 40, "其他真实出库")
    ids = [draft(db, [(a, 50)])["id"], draft(db, [(b, 50)], order_id="B")["id"]]
    results = _concurrent(db, [lambda s: service.confirm_shipment(s, ids[0], True),
                               lambda s: service.confirm_shipment(s, ids[1], True)])
    assert sorted(results) == ["rejected", "saved"]
    assert get_stock(db, "part", "p") == 10
    assert db.query(CustomerShipment).filter_by(status="confirmed").count() == 1


def test_concurrent_legacy_outbound_and_reservation_share_capacity(db, fulfillment):
    aid = fulfillment[0].id
    deduct_stock(db, "part", "p", 40, "其他真实出库")
    results = _concurrent(db, [lambda s: service.reserve(s, "A", aid, 50, 0),
                               lambda s: deduct_stock(s, "part", "p", 50, "实际材料发出")])
    assert sorted(results) == ["rejected", "saved"]
    balance = service.stock_balance(db, "part", "p")
    assert balance["stock"] - balance["reserved_total"] == 10


def test_concurrent_duplicate_confirmation_only_deducts_once(db, fulfillment):
    shipment_id = draft(db, [(fulfillment[0], 20)])["id"]
    assert _concurrent(db, [lambda s: service.confirm_shipment(s, shipment_id, True),
                            lambda s: service.confirm_shipment(s, shipment_id, True)]) == ["saved", "saved"]
    assert get_stock(db, "part", "p") == 80
    assert db.query(InventoryLog).filter_by(reason="客户逐笔出货").count() == 1


def test_concurrent_request_key_with_different_orders_is_cleanly_rejected(db, fulfillment):
    aid, bid = fulfillment[0].id, fulfillment[3].id
    key = str(uuid4())
    def create(session, order_id, line_id):
        service.create_shipment(session, {"order_id": order_id, "request_key": key,
                                         "lines": [{"order_item_id": line_id, "quantity": 5}]})
    results = _concurrent(db, [lambda s: create(s, "A", aid), lambda s: create(s, "B", bid)])
    assert sorted(results) == ["rejected", "saved"]
    assert db.query(CustomerShipment).count() == 1


def test_api_failed_confirmation_rolls_back_all_mutations(client_real_get_db, engine):
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        session.add_all([Part(id="rollback-p", name="配件", unit="条", category="链条"),
                         Order(id="rollback-order", customer_name="测试客户")])
        session.flush()
        line = OrderItem(order_id="rollback-order", part_id="rollback-p", quantity=20, unit_price=1)
        session.add(line); session.flush()
        add_stock(session, "part", "rollback-p", 10, "真实测试入库")
        service.activate(session, "rollback-order", True)
        service.reserve(session, "rollback-order", line.id, 5, 0)
        shipment_id = draft(session, [(line, 20)], order_id="rollback-order")["id"]
        line_id = line.id
        session.commit()
    response = client_real_get_db.post(f"/api/fulfillment/shipments/{shipment_id}/confirm", json={"actual_goods_checked": True})
    assert response.status_code == 400
    with Session(engine) as session:
        assert get_stock(session, "part", "rollback-p") == 10
        assert session.get(StockReservation, line_id).quantity == 5
        assert session.get(CustomerShipment, shipment_id).status == "draft"
        assert session.query(CustomerShipmentItem).filter_by(shipment_id=shipment_id).one().inventory_log_id is None


def test_no_foreign_duplicate_excess_or_fractional_lines(db, fulfillment):
    for entries in [[(fulfillment[3], 1)], [(fulfillment[0], 1), (fulfillment[0], 2)], [(fulfillment[0], 51)], [(fulfillment[0], 1.5)]]:
        with pytest.raises(ValueError):
            draft(db, entries)
    assert db.query(CustomerShipment).count() == 0


def test_request_key_retries_and_different_content_rejected(db, fulfillment):
    key = str(uuid4())
    first = draft(db, [(fulfillment[0], 5)], key=key)
    assert draft(db, [(fulfillment[0], 5)], key=key)["id"] == first["id"]
    with pytest.raises(ValueError, match="不同"):
        draft(db, [(fulfillment[0], 6)], key=key)


def test_legacy_mutations_cannot_destroy_verified_fulfillment(db, fulfillment):
    a = fulfillment[0]
    service.reserve(db, "A", a.id, 20, 0)
    with pytest.raises(ValueError, match="预留"):
        update_order_item(db, "A", a.id, {"quantity": 19})
    with pytest.raises(ValueError, match="不能删除"):
        delete_order_item(db, "A", a.id)
    with pytest.raises(ValueError, match="取消本单库存预留"):
        update_order_status(db, "A", "已取消")
    with pytest.raises(ValueError, match="逐笔履约"):
        update_order_status(db, "A", "已完成")


def test_api_permissions_and_confirmation_contract(client, db, fulfillment):
    assert client.get("/api/fulfillment/orders/A").status_code == 200
    assert client.put(f"/api/fulfillment/orders/A/reservations/{fulfillment[0].id}", json={"quantity": 5, "expected_quantity": 0}).status_code == 200
    response = client.post("/api/fulfillment/shipments", json={"order_id": "A", "request_key": str(uuid4()), "lines": [{"order_item_id": fulfillment[0].id, "quantity": 5}]})
    assert response.status_code == 201
    shipment_id = response.json()["id"]
    assert client.post(f"/api/fulfillment/shipments/{shipment_id}/confirm", json={"actual_goods_checked": False}).status_code == 400
    assert client.post(f"/api/fulfillment/shipments/{shipment_id}/confirm", json={"actual_goods_checked": True}).status_code == 200
    from main import app
    from api.deps import get_current_user
    from models.user import User
    app.dependency_overrides[get_current_user] = lambda: User(id=99, username="no-access", permissions=[], is_admin=False)
    assert client.get("/api/fulfillment/shipments").status_code == 403
