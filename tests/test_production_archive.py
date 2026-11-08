from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, text

from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.inventory_log import InventoryLog
from services import production_archive as archive
from services.handcraft import (
    create_handcraft_order, send_handcraft_order, get_handcraft_parts,
    list_handcraft_orders, list_handcraft_pending_receive_items,
)
from services.handcraft_receipt import create_handcraft_receipt, update_handcraft_receipt_status
from services.inventory import add_stock, get_stock
from services.kanban import get_kanban, change_order_status, get_orders_for_vendor
from services.part import create_part
from services.plating import (
    create_plating_order, send_plating_order, list_plating_orders,
    list_pending_receive_items, delete_plating_order,
)
from services.plating_receipt import create_plating_receipt
from services.production_loss import confirm_plating_loss
from services.plating_summary import list_dispatched, list_received


BEFORE = date(2026, 10, 29)


@pytest.fixture
def sample(db, monkeypatch):
    monkeypatch.setattr(archive, "now_beijing", lambda: datetime(2026, 10, 29, 16))
    part = create_part(db, {"name": "归档配件", "category": "小配件"})
    output = create_part(db, {"name": "归档产出", "category": "小配件"})
    add_stock(db, "part", part.id, 1000, "入库")
    old = BEFORE - timedelta(days=1)
    po = create_plating_order(db, "历史电镀厂", [{"part_id": part.id, "qty": 100}], created_at=old)
    send_plating_order(db, po.id)
    pi = db.query(PlatingOrderItem).filter_by(plating_order_id=po.id).one()
    pr = create_plating_receipt(db, po.supplier_name, [
        {"plating_order_item_id": pi.id, "part_id": part.id, "qty": 20, "price": 2},
    ], status="已付款")
    ho = create_handcraft_order(db, "历史手工厂", [{"part_id": part.id, "qty": 80}],
                                [{"part_id": output.id, "qty": 50}], created_at=old)
    send_handcraft_order(db, ho.id)
    hp = get_handcraft_parts(db, ho.id)[0]
    hj = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=ho.id).one()
    hr = create_handcraft_receipt(db, ho.supplier_name, [
        {"handcraft_part_item_id": hp.id, "qty": 5, "price": 1},
        {"handcraft_jewelry_item_id": hj.id, "qty": 10, "price": 3},
    ])
    pending = create_plating_order(db, "历史草稿厂", [{"part_id": part.id, "qty": 5}], created_at=old)
    today = create_plating_order(db, "今天电镀厂", [{"part_id": part.id, "qty": 5}], created_at=BEFORE)
    completed = create_plating_order(db, "完成电镀厂", [{"part_id": part.id, "qty": 5}], created_at=old)
    send_plating_order(db, completed.id)
    ci = db.query(PlatingOrderItem).filter_by(plating_order_id=completed.id).one()
    create_plating_receipt(db, completed.supplier_name, [
        {"plating_order_item_id": ci.id, "part_id": part.id, "qty": 5},
    ])
    return locals()


def apply(db, plan):
    return archive.apply_archive_plan(db, plan, operator="admin", reason="历史业务结案，不再追踪；未收不视为实收")


def test_preview_is_read_only_and_excludes_today_and_completed(db, sample):
    plan = archive.build_archive_plan(db, BEFORE)
    assert {r["id"] for r in plan["snapshot"]["plating"]} == {sample["po"].id, sample["pending"].id}
    assert {r["id"] for r in plan["snapshot"]["handcraft"]} == {sample["ho"].id}
    assert all(o.archived_at is None for o in db.query(PlatingOrder).all())
    assert sample["ho"].archived_at is None
    assert plan["timezone"] == "Asia/Shanghai"
    assert archive.plan_digest(plan) == plan["digest"]


def test_archive_preserves_every_business_field_inventory_and_payments(db, sample):
    plan = archive.build_archive_plan(db, BEFORE)
    logs_before = [(r.id, r.change_qty, r.reason) for r in db.query(InventoryLog).order_by(InventoryLog.id)]
    stock_before = get_stock(db, "part", sample["part"].id)
    assert apply(db, plan) == 3
    assert sample["po"].status == sample["ho"].status == "processing"
    assert sample["pending"].status == "pending"
    assert sample["pi"].received_qty == Decimal(20)
    assert sample["hp"].received_qty == Decimal(5)
    assert sample["hj"].received_qty == 10
    assert sample["pr"].status == "已付款"
    assert sample["hr"].status == "未付款"
    assert get_stock(db, "part", sample["part"].id) == stock_before
    assert logs_before == [(r.id, r.change_qty, r.reason) for r in db.query(InventoryLog).order_by(InventoryLog.id)]
    orders = {"plating": [sample["po"], sample["pending"]], "handcraft": [sample["ho"]]}
    assert archive._snapshot(db, orders) == plan["snapshot"]
    assert sample["po"].archive_batch_id == plan["batch_id"]
    assert sample["po"].archived_by == "admin"
    assert sample["po"].completed_at is None


def test_archived_orders_disappear_from_active_lists_selectors_and_kanban(db, sample):
    plan = archive.build_archive_plan(db, BEFORE)
    apply(db, plan)
    assert {o.id for o in list_plating_orders(db)} == {sample["today"].id, sample["completed"].id}
    assert {o.id for o in list_plating_orders(db, archive="archived")} == {sample["po"].id, sample["pending"].id}
    assert len(list_plating_orders(db, archive="all")) == 4
    assert list_handcraft_orders(db) == []
    assert list_handcraft_orders(db, archive="archived")[0].id == sample["ho"].id
    assert list_pending_receive_items(db) == []
    assert list_handcraft_pending_receive_items(db) == []
    assert get_orders_for_vendor(db, sample["ho"].supplier_name, "handcraft") == []
    kanban = get_kanban(db)
    assert kanban.pending_return.total == 0
    assert {v.vendor_name for v in kanban.pending_dispatch.vendors} == {"今天电镀厂"}
    assert {v.vendor_name for v in kanban.returned.vendors} == {"完成电镀厂"}
    _, active_total = list_dispatched(db)
    archived, archived_total = list_dispatched(db, archive="archived")
    assert active_total == 2
    assert archived_total == 2
    assert all(r["archived_at"] is not None and r["days_out"] is None for r in archived)
    received, total = list_received(db, archive="archived")
    assert total == 1 and received[0]["actual_received_qty"] == 20


def test_api_can_read_archived_history_but_cannot_write(client, db, sample):
    apply(db, archive.build_archive_plan(db, BEFORE))
    for kind, key in (("plating", "po"), ("handcraft", "ho")):
        order = sample[key]
        history = client.get(f"/api/{kind}/", params={"archive": "archived"})
        assert history.status_code == 200
        assert order.id in {o["id"] for o in history.json()}
        detail = client.get(f"/api/{kind}/{order.id}")
        assert detail.status_code == 200
        assert detail.json()["archived_at"] is not None
        assert detail.json()["status"] == "processing"
        assert client.patch(f"/api/{kind}/{order.id}", json={"created_at": "2026-10-29"}).status_code == 409
        assert client.delete(f"/api/{kind}/{order.id}").status_code == 409
        assert client.post(f"/api/{kind}/{order.id}/send").status_code == 409
        assert client.get(f"/api/{kind}/", params={"archive": "invalid"}).status_code == 422


def test_archived_service_writes_and_receipts_are_rejected(db, sample):
    apply(db, archive.build_archive_plan(db, BEFORE))
    with pytest.raises(ValueError, match="已历史归档"):
        send_plating_order(db, sample["pending"].id)
    with pytest.raises(ValueError, match="已历史归档"):
        delete_plating_order(db, sample["po"].id)
    with pytest.raises(ValueError, match="已历史归档"):
        change_order_status(db, sample["ho"].id, "handcraft", "completed")
    with pytest.raises(ValueError, match="已历史归档"):
        confirm_plating_loss(db, sample["po"].id, sample["pi"].id, 80)
    # Savepoints mirror API rollback while retaining the fixture for both checks.
    with pytest.raises(ValueError, match="已历史归档"):
        with db.begin_nested():
            create_plating_receipt(db, sample["po"].supplier_name, [{
                "plating_order_item_id": sample["pi"].id, "part_id": sample["part"].id, "qty": 1,
            }])
    with pytest.raises(ValueError, match="已历史归档"):
        with db.begin_nested():
            create_handcraft_receipt(db, sample["ho"].supplier_name, [{
                "handcraft_jewelry_item_id": sample["hj"].id, "qty": 1,
            }])
    # Financial settlement remains available; archiving does not forgive debts.
    update_handcraft_receipt_status(db, sample["hr"].id, "已付款")
    assert sample["hr"].status == "已付款"


@pytest.mark.parametrize("change", ["qty", "payment", "date", "new_order"])
def test_stale_preview_is_rejected_before_any_archive(db, sample, change):
    plan = archive.build_archive_plan(db, BEFORE)
    if change == "qty":
        sample["pi"].qty += 1
    elif change == "payment":
        update_handcraft_receipt_status(db, sample["hr"].id, "已付款")
    elif change == "date":
        sample["po"].created_at = datetime(2026, 10, 29)
    else:
        create_plating_order(db, "补录旧单", [{"part_id": sample["part"].id, "qty": 1}], created_at=BEFORE - timedelta(days=1))
    db.flush()
    with pytest.raises(ValueError, match="已变化"):
        apply(db, plan)
    assert sample["po"].archived_at is None
    assert sample["ho"].archived_at is None


def test_restore_only_this_batch_without_business_changes(db, sample):
    plan = archive.build_archive_plan(db, BEFORE)
    apply(db, plan)
    assert archive.restore_archive_plan(db, plan) == 3
    assert sample["po"].archived_at is None
    assert sample["ho"].archive_reason is None
    assert len(list_plating_orders(db)) == 4
    assert archive.build_archive_plan(db, BEFORE)["snapshot"] == plan["snapshot"]


def test_restore_refuses_changed_payment_and_keeps_archive(db, sample):
    plan = archive.build_archive_plan(db, BEFORE)
    apply(db, plan)
    update_handcraft_receipt_status(db, sample["hr"].id, "已付款")
    with pytest.raises(ValueError, match="业务记录已变化"):
        archive.restore_archive_plan(db, plan)
    assert sample["po"].archived_at is not None
    assert sample["ho"].archived_at is not None


def test_archived_pending_handcraft_picking_is_read_only(db, sample):
    from services.handcraft_picking import mark_picked, unmark_picked, reset_picking
    from services.handcraft_picking_weight import (
        upsert_weight, delete_weight, upsert_actual_qty, clear_actual_qty,
    )

    order = create_handcraft_order(
        db, "归档草稿手工厂", [{"part_id": sample["part"].id, "qty": 10}],
        created_at=BEFORE - timedelta(days=1),
    )
    part_item = get_handcraft_parts(db, order.id)[0]
    pair = (db, order.id, part_item.id, sample["part"].id)
    mark_picked(*pair)
    upsert_weight(*pair, 0.5)
    upsert_actual_qty(*pair, 8)
    plan = archive.build_archive_plan(db, BEFORE)
    apply(db, plan)
    for write in (
        lambda: mark_picked(*pair), lambda: unmark_picked(*pair),
        lambda: reset_picking(db, order.id), lambda: upsert_weight(*pair, 1),
        lambda: delete_weight(*pair), lambda: upsert_actual_qty(*pair, 10),
        lambda: clear_actual_qty(*pair),
    ):
        with pytest.raises(ValueError, match="已历史归档"):
            write()
    assert archive.build_archive_plan(db, BEFORE)["snapshot"]["handcraft"] == []
    assert archive.restore_archive_plan(db, plan) == 4


def test_customer_batch_cannot_delete_archived_draft_or_reserve_its_stock(db, sample):
    from models.order import Order, OrderTodoBatch, OrderTodoItem
    from services.order_todo import delete_batch, link_supplier

    historical = create_handcraft_order(
        db, "旧配货草稿厂", [{"part_id": sample["part"].id, "qty": 10000}],
        created_at=BEFORE - timedelta(days=1),
    )
    customer = Order(id="ORD-ARCHIVE", customer_name="归档测试客户")
    db.add(customer)
    db.flush()
    old_batch = OrderTodoBatch(order_id=customer.id, handcraft_order_id=historical.id)
    new_batch = OrderTodoBatch(order_id=customer.id)
    db.add_all([old_batch, new_batch])
    db.flush()
    db.add(OrderTodoItem(order_id=customer.id, batch_id=new_batch.id,
                         part_id=sample["part"].id, required_qty=5))
    db.flush()
    apply(db, archive.build_archive_plan(db, BEFORE))
    with pytest.raises(ValueError, match="已历史归档"):
        delete_batch(db, customer.id, old_batch.id)
    assert db.get(HandcraftOrder, historical.id) is historical
    # The 10,000 units on the archived unsent draft must not block new work.
    result = link_supplier(db, customer.id, new_batch.id, "新配货手工厂")
    assert result["handcraft_order_id"] != historical.id
    assert historical.archived_at is not None


def test_repeat_apply_and_wrong_restore_batch_are_rejected(db, sample):
    plan = archive.build_archive_plan(db, BEFORE)
    apply(db, plan)
    with pytest.raises(ValueError, match="已变化"):
        apply(db, plan)
    sample["ho"].archive_batch_id = "different-batch"
    with pytest.raises(ValueError, match="不再属于"):
        archive.restore_archive_plan(db, plan)
    assert sample["po"].archived_at is not None


def test_modified_plan_and_future_cutoff_are_rejected(db, sample):
    plan = archive.build_archive_plan(db, BEFORE)
    plan["before"] = "2026-10-30"
    with pytest.raises(ValueError, match="已被修改"):
        apply(db, plan)
    with pytest.raises(ValueError, match="不能晚于"):
        archive.build_archive_plan(db, BEFORE + timedelta(days=1))


def test_archive_schema_compat_adds_nullable_fields_idempotently(engine):
    # A separate schema exercises migration of old tables without touching data.
    from database import Base, ensure_schema_compat
    schema = "archive_migration_test"
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    migration_engine = create_engine(engine.url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(migration_engine)
        with migration_engine.begin() as conn:
            for table in ("plating_order", "handcraft_order"):
                for field in archive.ARCHIVE_FIELDS:
                    conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {field}"))
            conn.execute(text("INSERT INTO plating_order (id, supplier_name, status) VALUES ('EP-old', '原供应商', 'processing')"))
        ensure_schema_compat(migration_engine)
        ensure_schema_compat(migration_engine)
        with migration_engine.connect() as conn:
            cols = {c["name"] for c in inspect(conn).get_columns("plating_order")}
            assert archive.ARCHIVE_FIELDS <= cols
            row = conn.execute(text("SELECT status, archived_at FROM plating_order")).one()
            assert row.status == "processing" and row.archived_at is None
    finally:
        migration_engine.dispose()
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
