"""BOM output association without legacy checklists; isolated PostgreSQL only."""
from decimal import Decimal

import pytest

from models.bom import Bom
from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem, HandcraftPartItem
from models.inventory_log import InventoryLog
from models.jewelry import Jewelry
from models.material_production import OrderMaterialDemand as Demand, MaterialProductionAllocation as Material
from models.order import Order, OrderItem, OrderTodoItem, OrderItemLink, OrderTodoBatch, OrderTodoBatchJewelry
from models.part import Part
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.production_allocation import ProductionAllocation
from services.bom import set_bom, delete_bom_item
from services.handcraft import (
    get_handcraft_jewelry_breakdown, list_suppliers_with_sorting, list_handcraft_orders_with_sorting,
    update_handcraft_jewelry, delete_handcraft_jewelry, delete_handcraft_order,
)
from services.order import update_order_item, delete_order_item, delete_order, update_order_status
from services.order_todo import create_batch, create_link
from services.plating import update_plating_item, delete_plating_item, delete_plating_order
from services.production_allocation import order_production, production_uses, replace_order_source, replace_order_sources


@pytest.fixture
def material(db):
    db.add_all([
        Jewelry(id="finished", name="商品", unit="条"), Part(id="A", name="配件 A", unit="个"),
        Part(id="raw", name="投入原料", unit="个"),
        Order(id="OR-0015", customer_name="客户甲"), Order(id="OR-B", customer_name="客户乙"),
        HandcraftOrder(id="HC-A", supplier_name="手工商", status="processing"),
        PlatingOrder(id="EP-A", supplier_name="电镀商"),
    ])
    db.flush()
    a = OrderItem(order_id="OR-0015", jewelry_id="finished", quantity=10, unit_price=1, customer_code="货号甲")
    a2 = OrderItem(order_id="OR-0015", jewelry_id="finished", quantity=5, unit_price=1, customer_code="货号乙")
    b = OrderItem(order_id="OR-B", jewelry_id="finished", quantity=10, unit_price=1)
    direct = OrderItem(order_id="OR-0015", part_id="A", quantity=10, unit_price=1)
    output = HandcraftJewelryItem(handcraft_order_id="HC-A", part_id="A", qty=40, unit="个")
    output2 = HandcraftJewelryItem(handcraft_order_id="HC-A", part_id="A", qty=40, unit="个")
    input_row = HandcraftPartItem(handcraft_order_id="HC-A", part_id="raw", qty=80)
    plated = PlatingOrderItem(plating_order_id="EP-A", part_id="raw", receive_part_id="A", qty=40, unit="个")
    db.add_all([a, a2, b, direct, output, output2, input_row, plated,
                Bom(id="BM-A", jewelry_id="finished", part_id="A", qty_per_unit=2)])
    db.flush()
    return dict(a=a, a2=a2, b=b, direct=direct, output=output, output2=output2, input=input_row, plated=plated)


def source(db, f, key="output"):
    kind, parent = ("plating", "EP-A") if key == "plated" else ("handcraft", "HC-A")
    return next(row for row in production_uses(db, kind, parent) if row["source_item_id"] == f[key].id)


def entry(db, line, qty, part="A"):
    result = {"order_item_id": line.id, "quantity": qty}
    if part:
        demand = next(row for row in order_production(db, line.order_id)["materials"]
                      if row["order_item_id"] == line.id and row["material_part_id"] == part)
        result.update(material_part_id=part, demand_revision=demand["demand_revision"])
    return result


def payload(db, f, entries, key="output"):
    current = source(db, f, key)
    return {"source_type": current["source_type"], "source_item_id": current["source_item_id"],
            "revision": current["revision"], "allocations": entries}


def save(db, f, entries, key="output", order="OR-0015"):
    body = payload(db, f, entries, key)
    return replace_order_source(db, order, body["source_type"], body["source_item_id"], body["revision"], entries)


def test_or0015_preview_and_confirmation_need_no_todo_or_fake_order_part(db, material):
    f = material
    data = order_production(db, "OR-0015")
    assert [(r["order_item_id"], r["quantity"]) for r in data["materials"]] == [(f["a"].id, 20), (f["a2"].id, 10)]
    assert db.query(Demand).count() == db.query(OrderTodoItem).count() == 0
    assert {(s["source_type"], s["source_item_id"]) for s in data["sources"]} == {
        ("handcraft", f["output"].id), ("handcraft", f["output2"].id), ("plating", f["plated"].id)}
    result = save(db, f, [entry(db, f["a"], 15)])
    assert result["allocated"] == 15 and result["public_unallocated"] == 25
    assert result["allocations"][0]["purpose"] == "material"
    assert db.query(Material).count() == db.query(Demand).count() == 1
    assert db.query(ProductionAllocation).count() == db.query(OrderTodoItem).count() == db.query(InventoryLog).count() == 0
    assert db.query(OrderItem).count() == 4
    assert db.get(Order, "OR-0015").status == "生产中"
    assert f["output"].received_qty == 0
    assert all(r["allocated"] == 0 for r in order_production(db, "OR-0015")["lines"])


def test_direct_and_material_purposes_share_physical_capacity_and_revision(db, material):
    f = material
    save(db, f, [entry(db, f["b"], 20)], order="OR-B")
    original = source(db, f)["revision"]
    with pytest.raises(ValueError, match="容量"):
        save(db, f, [entry(db, f["a"], 15), entry(db, f["direct"], 6, None)])
    result = save(db, f, [entry(db, f["a"], 15), entry(db, f["direct"], 5, None)])
    assert result["allocated"] == 40 and result["revision"] != original
    assert {row["purpose"] for row in result["allocations"]} == {"product", "material"}
    save(db, f, [entry(db, f["a"], 0), entry(db, f["direct"], 0, None)])
    assert source(db, f)["allocations"][0]["order_id"] == "OR-B"
    assert source(db, f)["allocated"] == 20
    assert db.get(Order, "OR-0015").status == "生产中"


def test_demand_limit_is_per_exact_line_across_handcraft_and_plating(db, material):
    f = material
    save(db, f, [entry(db, f["a"], 15)])
    with pytest.raises(ValueError, match="订单明细"):
        save(db, f, [entry(db, f["a"], 6)], "plated")
    save(db, f, [entry(db, f["a"], 5)], "plated")
    save(db, f, [entry(db, f["a2"], 10)], "output2")
    assert [row["allocated"] for row in order_production(db, "OR-0015")["materials"]] == [20, 10]


def test_plating_matches_received_component_not_issued_material(db, material):
    db.add(Bom(id="BM-RAW", jewelry_id="finished", part_id="raw", qty_per_unit=1))
    db.flush()
    with pytest.raises(ValueError, match="不匹配"):
        save(db, material, [entry(db, material["a"], 1, "raw")], "plated")
    assert db.query(Material).count() == 0


def test_material_plans_never_count_as_final_product_or_fulfillment(db, material):
    from services.order_fulfillment import activate, order_summary
    from models.order_fulfillment import StockReservation, CustomerShipment
    save(db, material, [entry(db, material["a"], 20)])
    activate(db, "OR-0015", True)
    summary = order_summary(db, "OR-0015")
    assert summary["completed_items"] == 0
    assert all(row["planned"] == row["shipped"] == row["reserved"] == 0 for row in summary["lines"])
    assert db.query(StockReservation).count() == db.query(CustomerShipment).count() == db.query(InventoryLog).count() == 0


@pytest.mark.parametrize("change", ["coefficient", "remove", "order", "unit"])
def test_stale_demand_rejected_and_get_does_not_rewrite_snapshot(db, material, change):
    f = material
    old = entry(db, f["a"], 10)
    save(db, f, [old])
    if change == "coefficient":
        set_bom(db, "finished", "A", 1)
    elif change == "remove":
        delete_bom_item(db, "BM-A")
    elif change == "order":
        update_order_item(db, "OR-0015", f["a"].id, {"quantity": 8})
    else:
        db.get(Part, "A").unit = "米"
        db.flush()
    current = order_production(db, "OR-0015")["materials"][0]
    assert current["demand_changed"] and current["snapshot_quantity"] == 20
    with pytest.raises(ValueError, match="变化|单位"):
        save(db, f, [old])
    assert db.query(Demand).one().qty_per_unit == 2
    save(db, f, [{**old, "quantity": 0}])
    assert db.query(Material).count() == 0


def test_reconfirm_current_bom_requires_total_to_fit_and_explicitly_updates_snapshot(db, material):
    f = material
    save(db, f, [entry(db, f["a"], 12)])
    save(db, f, [entry(db, f["a"], 8)], "output2")
    set_bom(db, "finished", "A", 1)
    with pytest.raises(ValueError, match="订单明细"):
        save(db, f, [entry(db, f["a"], 3)])
    save(db, f, [entry(db, f["a"], 2)])
    demand = db.query(Demand).one()
    assert demand.qty_per_unit == 1 and demand.order_quantity == 10
    assert not order_production(db, "OR-0015")["materials"][0]["demand_changed"]


@pytest.mark.parametrize("key,quantity,ok", [("output", "1.5", False), ("plated", "1.2345", True),
                                           ("plated", "1.23456", False), ("output", "NaN", False),
                                           ("output", -1, False)])
def test_material_precision(db, material, key, quantity, ok):
    values = [entry(db, material["a"], quantity)]
    if ok:
        save(db, material, values, key)
        assert db.query(Material).one().quantity == Decimal(quantity)
    else:
        with pytest.raises(ValueError):
            save(db, material, values, key)
        assert db.query(Material).count() == db.query(Demand).count() == 0


def test_sorting_projects_material_shares_not_whole_output(db, material):
    f = material
    save(db, f, [entry(db, f["a"], 15)])
    save(db, f, [entry(db, f["b"], 10)], order="OR-B")
    groups = get_handcraft_jewelry_breakdown(db, "HC-A")
    entries = [r for r in groups[0]["entries"] if r["hc_jewelry_item_id"] == f["output"].id]
    assert [r["qty"] for r in entries] == [15, 10, 15]
    assert entries[0]["is_locked"] and entries[0]["source_purpose"] == "material"
    assert entries[0]["received_qty"] is None
    assert list_suppliers_with_sorting(db) == ["手工商"]
    sorting = list_handcraft_orders_with_sorting(db, "手工商")
    assert [row["id"] for row in sorting["orders"]] == ["HC-A"]
    assert not sorting["has_more"]
    sorted_entries = sorting["orders"][0]["breakdown"][0]["entries"]
    assert [row["qty"] for row in sorted_entries] == [15, 10]


def test_order_source_and_legacy_mutation_guards_include_material_shares(db, material):
    f = material
    save(db, f, [entry(db, f["a"], 15)])
    for action in [
        lambda: update_order_item(db, "OR-0015", f["a"].id, {"quantity": 7}),
        lambda: delete_order_item(db, "OR-0015", f["a"].id), lambda: delete_order(db, "OR-0015"),
        lambda: update_order_status(db, "OR-0015", "已取消"),
        lambda: update_handcraft_jewelry(db, "HC-A", f["output"].id, {"qty": 14}),
        lambda: update_handcraft_jewelry(db, "HC-A", f["output"].id, {"customer_name": "覆盖"}),
        lambda: delete_handcraft_jewelry(db, "HC-A", f["output"].id), lambda: delete_handcraft_order(db, "HC-A"),
        lambda: create_batch(db, "OR-0015", [("finished", 1)]),
        lambda: create_link(db, {"order_id": "OR-B", "handcraft_jewelry_item_id": f["output"].id}),
    ]:
        with pytest.raises(ValueError):
            action()
    update_order_item(db, "OR-0015", f["a"].id, {"quantity": 8})
    assert order_production(db, "OR-0015")["materials"][0]["demand_changed"]


def test_plating_material_guards(db, material):
    f = material
    save(db, f, [entry(db, f["a"], 15)], "plated")
    for action in [lambda: update_plating_item(db, "EP-A", f["plated"].id, {"qty": 14}),
                   lambda: update_plating_item(db, "EP-A", f["plated"].id, {"receive_part_id": None}),
                   lambda: delete_plating_item(db, "EP-A", f["plated"].id), lambda: delete_plating_order(db, "EP-A")]:
        with pytest.raises(ValueError):
            action()


@pytest.mark.parametrize("legacy", ["todo", "batch", "source"])
def test_legacy_conflicts_are_not_guessed(db, material, legacy):
    f = material
    if legacy == "todo":
        todo = OrderTodoItem(order_id="OR-0015", part_id="A", required_qty=20)
        db.add(todo); db.flush()
        db.add(OrderItemLink(order_todo_item_id=todo.id, plating_order_item_id=f["plated"].id))
    elif legacy == "batch":
        batch = OrderTodoBatch(order_id="OR-0015")
        db.add(batch); db.flush()
        db.add(OrderTodoBatchJewelry(batch_id=batch.id, jewelry_id="finished", quantity=1))
    else:
        f["output"].customer_name = "手填"
    db.flush()
    with pytest.raises(ValueError, match="旧"):
        save(db, f, [entry(db, f["a"], 1)])
    assert db.query(Material).count() == 0


def test_batch_rebalances_sources_atomically_in_any_payload_order(db, material):
    f = material
    save(db, f, [entry(db, f["a"], 20)], "output2")
    bodies = [payload(db, f, [entry(db, f["a"], 0)], "output2"),
              payload(db, f, [entry(db, f["a"], 20)])]
    replace_order_sources(db, "OR-0015", bodies)
    assert source(db, f)["allocated"] == 20 and source(db, f, "output2")["allocated"] == 0


def test_batch_failure_restores_old_shares_snapshots_and_status(db, material):
    f = material
    bodies = [payload(db, f, [entry(db, f["a"], 10)]),
              payload(db, f, [entry(db, f["a2"], 11)], "output2")]
    with pytest.raises(ValueError):
        replace_order_sources(db, "OR-0015", bodies)
    assert db.query(Material).count() == db.query(Demand).count() == 0
    assert db.get(Order, "OR-0015").status == "待生产"
    save(db, f, [entry(db, f["a"], 10)])
    bodies = [payload(db, f, [entry(db, f["a"], 0)]), bodies[1]]
    with pytest.raises(ValueError):
        replace_order_sources(db, "OR-0015", bodies)
    assert source(db, f)["allocated"] == 10


def test_batch_stale_duplicate_and_cross_order_cannot_write(db, material):
    f = material
    body = payload(db, f, [entry(db, f["a"], 10)])
    with pytest.raises(ValueError, match="重复"):
        replace_order_sources(db, "OR-0015", [body, body])
    with pytest.raises(ValueError, match="当前订单"):
        save(db, f, [entry(db, f["b"], 1)])
    save(db, f, [entry(db, f["b"], 10)], order="OR-B")
    with pytest.raises(ValueError, match="刷新"):
        replace_order_sources(db, "OR-0015", [body])
    assert db.query(Material).count() == 1


def test_batch_api_validation_and_permissions(client, db, material):
    f = material
    body = {"sources": [payload(db, f, [entry(db, f["a"], 10)])]}
    assert client.post("/api/orders/OR-0015/production/batch", json=body).status_code == 200
    breakdown = client.get("/api/handcraft/HC-A/jewelry-breakdown").json()
    assert breakdown[0]["entries"][0]["source_purpose"] == "material"
    assert client.post("/api/orders/OR-0015/production/batch", json=body).status_code == 400
    assert client.post("/api/orders/OR-0015/production/batch", json={"sources": []}).status_code == 422
    from main import app
    from api.deps import get_current_user
    from models.user import User
    for permissions in [[], ["handcraft"], ["orders"]]:
        app.dependency_overrides[get_current_user] = lambda: User(id=123, username="limited", permissions=permissions, is_admin=False)
        assert client.post("/api/orders/OR-0015/production/batch", json=body).status_code == 403


def test_output_order_column_reads_both_purposes_deduplicates_and_refreshes(client, db, material):
    f = material
    url = f"/api/handcraft/HC-A/jewelries/{f['output'].id}/orders"
    assert client.get(url).json() == []
    save(db, f, [entry(db, f["a"], 5), entry(db, f["a2"], 3), entry(db, f["direct"], 2, None)])
    save(db, f, [entry(db, f["b"], 10)], order="OR-B")
    links = client.get(url).json()
    assert [row["order_id"] for row in links] == ["OR-0015", "OR-B"]
    assert all(row["quantity_managed"] and row["link_id"] is None for row in links)
    assert links[0]["customer_name"] == "客户甲"
    assert client.get(f"/api/handcraft/HC-A/jewelries/{f['output2'].id}/orders").json() == []
    assert client.get(f"/api/handcraft/wrong/jewelries/{f['output'].id}/orders").status_code == 404
    save(db, f, [])
    assert [row["order_id"] for row in client.get(url).json()] == ["OR-B"]
    db.get(HandcraftOrder, "HC-A").status = "completed"
    db.flush()
    assert [row["order_id"] for row in client.get(url).json()] == ["OR-B"]


def test_output_order_column_keeps_legacy_link_contract(client, db, material):
    f = material
    link = OrderItemLink(order_id="OR-0015", handcraft_jewelry_item_id=f["output"].id)
    db.add(link); db.flush()
    response = client.get(f"/api/handcraft/HC-A/jewelries/{f['output'].id}/orders")
    assert response.status_code == 200
    assert response.json() == [{"order_id": "OR-0015", "customer_name": "客户甲", "link_id": link.id}]


def test_batch_failure_uses_real_request_rollback(client_real_get_db, db, material):
    from sqlalchemy.orm import Session
    bodies = [payload(db, material, [entry(db, material["a"], 10)]),
              payload(db, material, [entry(db, material["a2"], 11)], "output2")]
    db.commit()
    response = client_real_get_db.post("/api/orders/OR-0015/production/batch", json={"sources": bodies})
    assert response.status_code == 400
    with Session(db.get_bind()) as fresh:
        assert fresh.query(Material).count() == fresh.query(Demand).count() == 0
        assert fresh.get(Order, "OR-0015").status == "待生产"


def test_concurrent_sources_cannot_overfill_one_material_demand(db, engine, material):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    bodies = [payload(db, material, [entry(db, material["a"], 15)], key) for key in ["output", "plated"]]
    db.commit()
    barrier = Barrier(2)

    def allocate(body):
        with Session(engine) as session:
            session.execute(text("SET LOCAL statement_timeout = '10s'"))
            barrier.wait(timeout=10)
            try:
                replace_order_sources(session, "OR-0015", [body])
                session.commit()
                return "saved"
            except ValueError as error:
                session.rollback()
                assert "订单明细" in str(error)
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(allocate, body) for body in bodies]
        assert sorted(f.result(timeout=15) for f in futures) == ["rejected", "saved"]
    db.expire_all()
    assert sum(row.quantity for row in db.query(Material)) == 15


def test_concurrent_direct_and_material_customers_share_one_output(db, engine, material):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    f = material
    a_body = payload(db, f, [entry(db, f["a"], 20), entry(db, f["direct"], 10, None)])
    b_body = payload(db, f, [entry(db, f["b"], 20)])
    db.commit()
    barrier = Barrier(2)

    def allocate(order, body):
        with Session(engine) as session:
            session.execute(text("SET LOCAL statement_timeout = '10s'"))
            barrier.wait(timeout=10)
            try:
                replace_order_sources(session, order, [body])
                session.commit()
                return "saved"
            except ValueError as error:
                session.rollback()
                assert "刷新" in str(error)
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(allocate, "OR-0015", a_body), pool.submit(allocate, "OR-B", b_body)]
        assert sorted(f.result(timeout=15) for f in futures) == ["rejected", "saved"]
    db.expire_all()
    assert source(db, f)["allocated"] in [20, 30]


def test_bom_edit_and_confirmation_serialize_and_reject_old_preview(db, engine, material):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    f = material
    body = payload(db, f, [entry(db, f["a"], 20)])
    db.commit()
    set_bom(db, "finished", "A", 1)  # Hold the BOM advisory lock until commit.
    started = Event()

    def confirm():
        with Session(engine) as session:
            session.execute(text("SET LOCAL statement_timeout = '10s'"))
            started.set()
            try:
                replace_order_sources(session, "OR-0015", [body])
            except ValueError as error:
                session.rollback()
                assert "BOM" in str(error)
                return "rejected"
            raise AssertionError("A stale BOM preview must not allocate")

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(confirm)
        assert started.wait(timeout=10)
        db.commit()
        assert future.result(timeout=15) == "rejected"
    db.expire_all()
    assert db.query(Material).count() == db.query(Demand).count() == 0
