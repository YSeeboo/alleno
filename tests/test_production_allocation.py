"""Use only the isolated PostgreSQL selected by tests/conftest.py."""
from decimal import Decimal

import pytest

from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem, HandcraftPartItem
from models.inventory_log import InventoryLog
from models.jewelry import Jewelry
from models.order import Order, OrderItem, OrderItemLink, OrderTodoItem, OrderTodoBatch, OrderTodoBatchJewelry
from models.part import Part
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.production_allocation import ProductionAllocation
from models.production_loss import ProductionLoss
from services.production_allocation import order_production, production_uses, replace_order_source
from services.order import update_order_item, delete_order_item, delete_order, update_order_status
from services.plating import update_plating_item, delete_plating_item, delete_plating_order
from services.handcraft import update_handcraft_jewelry, delete_handcraft_jewelry, delete_handcraft_order
from services.order_todo import create_link, batch_link, create_batch


@pytest.fixture
def fixture(db):
    db.add_all([Part(id="raw", name="原色扣头", unit="个"), Part(id="gold", name="金色扣头", unit="个"),
                Jewelry(id="necklace", name="项链", unit="条"),
                Order(id="OR-1", customer_name="甲"), Order(id="OR-2", customer_name="乙"),
                PlatingOrder(id="EP-1", supplier_name="电镀商"), HandcraftOrder(id="HC-1", supplier_name="手工商")])
    db.flush()
    lines = [OrderItem(order_id="OR-1", part_id="gold", quantity=100, unit_price=1),
             OrderItem(order_id="OR-1", part_id="gold", quantity=30, unit_price=1),
             OrderItem(order_id="OR-2", part_id="gold", quantity=100, unit_price=1),
             OrderItem(order_id="OR-1", jewelry_id="necklace", quantity=50, unit_price=1)]
    plating = PlatingOrderItem(plating_order_id="EP-1", part_id="raw", receive_part_id="gold", qty=150)
    jewelry = HandcraftJewelryItem(handcraft_order_id="HC-1", jewelry_id="necklace", qty=60, unit="条")
    output_part = HandcraftJewelryItem(handcraft_order_id="HC-1", part_id="gold", qty=40, unit="个")
    input_part = HandcraftPartItem(handcraft_order_id="HC-1", part_id="gold", qty=60)
    db.add_all([*lines, plating, jewelry, output_part, input_part])
    db.flush()
    return {"lines": lines, "plating": plating, "jewelry": jewelry, "output_part": output_part, "input_part": input_part}


def view(db, f, kind="plating"):
    return production_uses(db, kind, "EP-1" if kind == "plating" else "HC-1")[0]


def save(db, f, quantities, order="OR-1", kind="plating", source=None, revision=None):
    source = source or (f["plating"] if kind == "plating" else f["jewelry"])
    sources = production_uses(db, kind, "EP-1" if kind == "plating" else "HC-1")
    current = next(row for row in sources if row["source_item_id"] == source.id)
    return replace_order_source(db, order, kind, source.id, revision or current["revision"],
                                [{"order_item_id": line.id, "quantity": qty} for line, qty in quantities])


def test_exact_lines_and_other_customer_protected(db, fixture):
    a, a2, b, _ = fixture["lines"]
    save(db, fixture, [(b, 60)], order="OR-2")
    result = save(db, fixture, [(a, 70), (a2, 20)])
    assert result["allocated"] == 150
    assert result["public_unallocated"] == 0
    with pytest.raises(ValueError, match="容量"):
        save(db, fixture, [(a, 71), (a2, 20)])
    assert db.query(ProductionAllocation).count() == 3
    save(db, fixture, [(a, 10), (a2, 0)])
    result = view(db, fixture)
    assert [(r["order_item_id"], r["quantity"]) for r in result["allocations"]] == [(b.id, 60), (a.id, 10)]
    assert result["public_unallocated"] == 80
    assert db.query(InventoryLog).count() == 0
    assert fixture["plating"].received_qty == 0


def test_target_matching_not_input_and_no_upstream_implicit_link(db, fixture):
    data = order_production(db, "OR-1")
    plating = next(s for s in data["sources"] if s["source_type"] == "plating")
    assert plating["product_id"] == "gold"
    assert plating["input_part_id"] == "raw"
    assert all(s["source_type"] == "plating" or s["source_item_id"] != fixture["input_part"].id or s["product_type"] != "part" or s["planned"] == 40 for s in data["sources"])
    with pytest.raises(ValueError, match="不匹配"):
        save(db, fixture, [(fixture["lines"][3], 10)])
    assert db.query(ProductionAllocation).count() == 0


@pytest.mark.parametrize("qty", [-1, "NaN", "Infinity", "0.00001", "1.5", "10000000000"])
def test_invalid_quantity_never_writes(db, fixture, qty):
    with pytest.raises(ValueError):
        save(db, fixture, [(fixture["lines"][0], qty)])
    assert db.query(ProductionAllocation).count() == 0


def test_duplicate_and_cross_order_payload_rejected_atomically(db, fixture):
    a, _, b, _ = fixture["lines"]
    for values in [[(a, 1), (a, 2)], [(a, 1), (b, 2)]]:
        with pytest.raises(ValueError):
            save(db, fixture, values)
        assert db.query(ProductionAllocation).count() == 0


def test_all_source_types_share_order_demand_limit(db, fixture):
    a = fixture["lines"][0]
    save(db, fixture, [(a, 80)])
    with pytest.raises(ValueError, match="订单明细"):
        save(db, fixture, [(a, 21)], kind="handcraft", source=fixture["output_part"])
    save(db, fixture, [(a, 20)], kind="handcraft", source=fixture["output_part"])
    assert order_production(db, "OR-1")["lines"][0]["allocated"] == 100


def test_stale_revision_and_empty_replace(db, fixture):
    a = fixture["lines"][0]
    revision = view(db, fixture)["revision"]
    result = save(db, fixture, [(a, 10)])
    db.expire_all()
    assert result["revision"] == view(db, fixture)["revision"]
    with pytest.raises(ValueError, match="刷新"):
        save(db, fixture, [(a, 20)], revision=revision)
    save(db, fixture, [])
    assert db.query(ProductionAllocation).count() == 0


@pytest.mark.parametrize("legacy", ["link", "batch", "manual"])
def test_legacy_source_not_guessed_or_double_claimed(db, fixture, legacy):
    if legacy == "link":
        db.add(OrderItemLink(order_id="OR-1", handcraft_jewelry_item_id=fixture["jewelry"].id))
    elif legacy == "batch":
        batch = OrderTodoBatch(order_id="OR-1")
        db.add(batch)
        db.flush()
        db.add(OrderTodoBatchJewelry(batch_id=batch.id, jewelry_id="necklace", quantity=10,
                                   handcraft_jewelry_item_id=fixture["jewelry"].id))
    else:
        fixture["jewelry"].customer_name = "手填客户"
    db.flush()
    assert view(db, fixture, "handcraft")["legacy_claim"]
    with pytest.raises(ValueError, match="旧关联"):
        save(db, fixture, [(fixture["lines"][3], 10)], kind="handcraft")
    assert db.query(ProductionAllocation).count() == 0


def test_legacy_demand_blocks_new_source_even_on_another_row(db, fixture):
    batch = OrderTodoBatch(order_id="OR-1", handcraft_order_id="HC-1")
    db.add(batch)
    db.flush()
    db.add(OrderTodoBatchJewelry(batch_id=batch.id, jewelry_id="necklace", quantity=10))
    db.flush()
    with pytest.raises(ValueError, match="旧生产安排"):
        save(db, fixture, [(fixture["lines"][3], 10)], kind="handcraft")


def test_new_source_blocks_old_single_and_batch_links(db, fixture):
    a, _, b, _ = fixture["lines"]
    save(db, fixture, [(a, 10)])
    todo = OrderTodoItem(order_id="OR-2", part_id="gold", required_qty=10)
    db.add(todo)
    db.flush()
    with pytest.raises(ValueError, match="旧整行"):
        create_link(db, {"order_todo_item_id": todo.id, "plating_order_item_id": fixture["plating"].id})
    with pytest.raises(ValueError, match="旧整行"):
        batch_link(db, "OR-2", plating_order_item_ids=[fixture["plating"].id])
    with pytest.raises(ValueError, match="混用"):
        create_batch(db, "OR-1", [("necklace", 5)])


def test_old_plating_match_uses_return_target(db, fixture):
    todo = OrderTodoItem(order_id="OR-1", part_id="gold", required_qty=10)
    db.add(todo)
    db.flush()
    link = create_link(db, {"order_todo_item_id": todo.id, "plating_order_item_id": fixture["plating"].id})
    assert link.order_todo_item_id == todo.id


def test_order_and_plating_mutations_guard_allocations(db, fixture):
    a = fixture["lines"][0]
    save(db, fixture, [(a, 50)])
    for change in [lambda: update_order_item(db, "OR-1", a.id, {"quantity": 49}),
                   lambda: delete_order_item(db, "OR-1", a.id), lambda: delete_order(db, "OR-1"),
                   lambda: update_order_status(db, "OR-1", "已取消"),
                   lambda: update_plating_item(db, "EP-1", fixture["plating"].id, {"qty": 49}),
                   lambda: update_plating_item(db, "EP-1", fixture["plating"].id, {"receive_part_id": None}),
                   lambda: update_plating_item(db, "EP-1", fixture["plating"].id, {"unit": "米"}),
                   lambda: delete_plating_item(db, "EP-1", fixture["plating"].id),
                   lambda: delete_plating_order(db, "EP-1")]:
        with pytest.raises(ValueError):
            change()
    assert fixture["plating"].qty == 150
    assert fixture["plating"].receive_part_id == "gold"
    assert a.quantity == 100
    assert db.query(InventoryLog).count() == 0
    update_plating_item(db, "EP-1", fixture["plating"].id, {"qty": 160})
    update_order_item(db, "OR-1", a.id, {"quantity": 80})


def test_handcraft_output_edit_and_delete_guards(db, fixture):
    save(db, fixture, [(fixture["lines"][3], 20)], kind="handcraft")
    for change in [lambda: update_handcraft_jewelry(db, "HC-1", fixture["jewelry"].id, {"qty": 19}),
                   lambda: update_handcraft_jewelry(db, "HC-1", fixture["jewelry"].id, {"customer_name": "覆盖"}),
                   lambda: delete_handcraft_jewelry(db, "HC-1", fixture["jewelry"].id),
                   lambda: delete_handcraft_order(db, "HC-1")]:
        with pytest.raises(ValueError):
            change()
    assert fixture["jewelry"].customer_name is None


def test_receipts_and_losses_do_not_become_own_stock_or_shipments(db, fixture):
    save(db, fixture, [(fixture["lines"][0], 50)])
    fixture["plating"].received_qty = 80
    db.add_all([ProductionLoss(order_id="EP-1", order_type="plating", item_id=fixture["plating"].id,
                               item_type="plating_item", part_id="raw", loss_qty=5),
                ProductionLoss(order_id="EP-1", order_type="plating", item_id=fixture["plating"].id,
                               item_type="plating_item", part_id="raw", loss_qty=10)])
    db.flush()
    result = view(db, fixture)
    assert result["received"] == 65
    assert result["loss"] == 15
    assert result["risk"]
    assert result["allocated"] == 50
    assert fixture["lines"][0].quantity == 100
    assert db.query(InventoryLog).count() == 0


@pytest.mark.parametrize("state", ["completed", "archived", "cancelled_order"])
def test_readonly_history_keeps_trace(db, fixture, state):
    a = fixture["lines"][0]
    save(db, fixture, [(a, 50)])
    if state == "completed":
        db.get(PlatingOrder, "EP-1").status = "completed"
    elif state == "archived":
        from time_utils import now_beijing
        db.get(PlatingOrder, "EP-1").archived_at = now_beijing()
    else:
        db.get(Order, "OR-1").status = "已取消"
    db.flush()
    assert order_production(db, "OR-1")["sources"][0]["allocations"][0]["quantity"] == 50
    with pytest.raises(ValueError):
        save(db, fixture, [(a, 40)])


def test_api_contract_and_validation(client, db, fixture):
    response = client.get("/api/orders/OR-1/production")
    assert response.status_code == 200
    source = next(s for s in response.json()["sources"] if s["source_type"] == "plating")
    payload = {"source_type": "plating", "source_item_id": fixture["plating"].id,
               "revision": source["revision"], "allocations": [{"order_item_id": fixture["lines"][0].id, "quantity": 50}]}
    assert client.put("/api/orders/OR-1/production", json=payload).status_code == 200
    assert client.get("/api/plating/EP-1/production-uses").json()[0]["allocations"][0]["order_id"] == "OR-1"
    assert client.get("/api/handcraft/HC-1/production-uses").status_code == 200
    assert client.put("/api/orders/OR-1/production", json=payload).status_code == 400
    payload["allocations"][0]["quantity"] = "NaN"
    assert client.put("/api/orders/OR-1/production", json=payload).status_code == 422


def test_concurrent_customers_cannot_overallocate_shared_output(db, engine, fixture):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    from sqlalchemy import text

    a, _, b, _ = fixture["lines"]
    item_id, a_id, b_id = fixture["plating"].id, a.id, b.id
    revision = view(db, fixture)["revision"]
    db.commit()  # Independent transactions must be able to see the fixtures.
    barrier = Barrier(2)

    def allocate(order_id, line_id):
        with Session(engine) as session:
            session.execute(text("SET LOCAL statement_timeout = '10s'"))
            barrier.wait(timeout=10)
            try:
                replace_order_source(session, order_id, "plating", item_id, revision,
                                     [{"order_item_id": line_id, "quantity": 100}])
                session.commit()
                return "saved"
            except ValueError as error:
                session.rollback()
                assert "刷新" in str(error)
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(allocate, "OR-1", a_id), pool.submit(allocate, "OR-2", b_id)]
        assert sorted(f.result(timeout=15) for f in futures) == ["rejected", "saved"]
    db.expire_all()
    assert sum(row.quantity for row in db.query(ProductionAllocation).all()) == 100


def test_concurrent_sources_share_one_order_line_limit(db, engine, fixture):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    from sqlalchemy import text

    line_id = fixture["lines"][0].id
    fixture["output_part"].qty = 100
    db.flush()
    sources = [("plating", fixture["plating"].id, view(db, fixture)["revision"]),
               ("handcraft", fixture["output_part"].id, production_uses(db, "handcraft", "HC-1")[1]["revision"])]
    db.commit()
    barrier = Barrier(2)

    def allocate(source):
        with Session(engine) as session:
            session.execute(text("SET LOCAL statement_timeout = '10s'"))
            barrier.wait(timeout=10)
            try:
                replace_order_source(session, "OR-1", *source,
                                     [{"order_item_id": line_id, "quantity": 80}])
                session.commit()
                return "saved"
            except ValueError as error:
                session.rollback()
                assert "订单明细" in str(error)
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(allocate, source) for source in sources]
        assert sorted(f.result(timeout=15) for f in futures) == ["rejected", "saved"]
    db.expire_all()
    assert sum(row.quantity for row in db.query(ProductionAllocation).all()) == 80


def test_permissions_follow_existing_modules(client, fixture):
    from main import app
    from api.deps import get_current_user
    from models.user import User
    app.dependency_overrides[get_current_user] = lambda: User(id=123, username="no-access", permissions=[], is_admin=False)
    for url in ["/api/orders/OR-1/production", "/api/plating/EP-1/production-uses", "/api/handcraft/HC-1/production-uses"]:
        assert client.get(url).status_code == 403


def test_units_are_not_silently_converted(db, fixture):
    fixture["plating"].unit = "米"
    db.flush()
    assert view(db, fixture)["unit_mismatch"]
    with pytest.raises(ValueError, match="单位"):
        save(db, fixture, [(fixture["lines"][0], 10)])
    assert db.query(ProductionAllocation).count() == 0


def test_unit_change_on_product_does_not_prevent_releasing_old_plan(db, fixture):
    save(db, fixture, [(fixture["lines"][0], 10)])
    db.get(Part, "gold").unit = "米"
    db.flush()
    with pytest.raises(ValueError, match="单位"):
        save(db, fixture, [(fixture["lines"][0], 11)])
    save(db, fixture, [(fixture["lines"][0], 0)])
    assert db.query(ProductionAllocation).count() == 0
