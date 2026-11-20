from copy import deepcopy
from uuid import uuid4

import pytest

from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem, HandcraftPartItem
from models.inventory_log import InventoryLog
from models.production_allocation import ProductionAllocation
from models.production_creation import ProductionCreation
from models.supplier import Supplier
from schemas.production_allocation import OrderHandcraftCreate
from services.order_production_creation import create_order_handcraft
from services.production_allocation import order_production
from tests.test_production_allocation import fixture  # noqa: F401 - shared isolated fixtures


def payload(line, **changes):
    data = {"supplier_name": "手工商", "parts": [{"part_id": "raw", "qty": 20, "unit": "个"}],
            "jewelries": [{"part_id": "gold", "qty": 25, "unit": "个"}],
            "order_item_id": line.id, "allocated_quantity": 20, "request_key": str(uuid4())}
    data.update(changes)
    return OrderHandcraftCreate(**data).model_dump()


def test_new_task_allocates_only_exact_line_and_retains_public_plan(db, fixture):
    a, repeated, other, _ = fixture["lines"]
    result = create_order_handcraft(db, "OR-1", payload(a))
    assert result["production_order_id"] != "HC-1"
    assert result["public_quantity"] == 5 and not result["appended"]
    rows = db.query(ProductionAllocation).all()
    assert [(r.order_item_id, r.quantity) for r in rows] == [(a.id, 20)]
    assert db.query(HandcraftPartItem).filter_by(handcraft_order_id=result["production_order_id"]).one().status == "未送出"
    assert db.query(InventoryLog).count() == 0
    assert db.query(Supplier).filter_by(name="手工商", type="handcraft").count() == 1
    assert order_production(db, "OR-1")["lines"][1]["allocated"] == 0


def test_explicit_append_adds_new_output_without_merging_old_rows(db, fixture):
    old_id, old_qty = fixture["output_part"].id, fixture["output_part"].qty
    result = create_order_handcraft(db, "OR-1", payload(fixture["lines"][0], append_to_order_id="HC-1"))
    assert result["production_order_id"] == "HC-1" and result["appended"]
    assert result["source_item_id"] != old_id
    assert db.get(HandcraftJewelryItem, old_id).qty == old_qty
    assert db.query(HandcraftJewelryItem).filter_by(handcraft_order_id="HC-1").count() == 3
    assert db.query(InventoryLog).count() == 0


@pytest.mark.parametrize("invalid", ["foreign", "mismatch", "unit", "quantity", "capacity", "customer", "target", "completed"])
def test_invalid_request_creates_no_partial_task_or_plan(db, fixture, invalid):
    data = payload(fixture["lines"][0])
    if invalid == "foreign": data["order_item_id"] = fixture["lines"][2].id
    if invalid == "mismatch": data["jewelries"][0]["part_id"] = "raw"
    if invalid == "unit": data["jewelries"][0]["unit"] = "条"
    if invalid == "quantity": data["allocated_quantity"] = 26
    if invalid == "capacity": data["allocated_quantity"] = data["jewelries"][0]["qty"] = 101
    if invalid == "customer": data["jewelries"][0]["customer_name"] = "猜测客户"
    if invalid == "target": data["append_to_order_id"] = "missing"
    if invalid == "completed":
        from models.order import Order
        db.get(Order, "OR-1").status = "已完成"
        db.flush()
    with pytest.raises(ValueError): create_order_handcraft(db, "OR-1", data)
    assert db.query(HandcraftOrder).count() == 1
    assert db.query(HandcraftJewelryItem).count() == 2
    assert db.query(ProductionAllocation).count() == 0
    assert db.query(ProductionCreation).count() == 0
    assert db.query(Supplier).count() == 0


def test_idempotent_retry_returns_original_even_after_status_changes(db, fixture):
    from models.order import Order
    data = payload(fixture["lines"][0])
    result = create_order_handcraft(db, "OR-1", data)
    db.get(Order, "OR-1").status = "已完成"
    db.flush()
    assert create_order_handcraft(db, "OR-1", data) == result
    assert db.query(HandcraftOrder).count() == 2
    changed = deepcopy(data); changed["note"] = "different request"
    with pytest.raises(ValueError, match="不同内容"): create_order_handcraft(db, "OR-1", changed)
    with pytest.raises(ValueError, match="不同内容"): create_order_handcraft(db, "OR-2", data)


def test_creation_and_existing_source_share_demand_limit(db, fixture):
    from services.production_allocation import replace_order_source, production_uses
    a = fixture["lines"][0]
    source = production_uses(db, "plating", "EP-1")[0]
    replace_order_source(db, "OR-1", "plating", source["source_item_id"], source["revision"], [{"order_item_id": a.id, "quantity": 90}])
    with pytest.raises(ValueError, match="剩余生产需求"):
        create_order_handcraft(db, "OR-1", payload(a))
    assert db.query(HandcraftOrder).count() == 1


def test_api_requires_both_order_and_handcraft_permissions(client, db, fixture):
    from api.deps import get_current_user
    from main import app
    from models.user import User
    body = payload(fixture["lines"][0])
    for permissions in [["orders"], ["handcraft"], []]:
        app.dependency_overrides[get_current_user] = lambda p=permissions: User(id=123, username="limited", permissions=p, is_admin=False)
        assert client.post("/api/orders/OR-1/production/handcraft", json=body).status_code == 403
    assert db.query(HandcraftOrder).count() == 1


def test_real_concurrent_creations_cannot_overplan_order_line(db, fixture):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    first = payload(fixture["lines"][0], allocated_quantity=60, jewelries=[{"part_id": "gold", "qty": 60, "unit": "个"}])
    second = deepcopy(first); second["request_key"] = str(uuid4())
    engine = db.get_bind(); db.commit()
    barrier = Barrier(2)
    def run(data):
        with Session(engine) as session:
            session.execute(text("SET LOCAL lock_timeout = '5s'")); barrier.wait(timeout=10)
            try:
                create_order_handcraft(session, "OR-1", data); session.commit(); return "saved"
            except ValueError:
                session.rollback(); return "rejected"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, data) for data in [first, second]]
        assert sorted(f.result(timeout=15) for f in futures) == ["rejected", "saved"]
    db.expire_all()
    assert db.query(HandcraftOrder).count() == 2
    assert db.query(ProductionAllocation).one().quantity == 60


@pytest.mark.parametrize("amount,unit", [(0.00001, "个"), (1000000, "个"), (1, "条")])
def test_material_precision_range_and_unit_cannot_be_silently_converted(db, fixture, amount, unit):
    data = payload(fixture["lines"][0])
    data["parts"][0].update(qty=amount, unit=unit)
    with pytest.raises(ValueError): create_order_handcraft(db, "OR-1", data)
    assert db.query(HandcraftOrder).count() == 1


@pytest.mark.parametrize("after_supplier", [False, True])
def test_error_after_output_insert_rolls_back_creation_even_for_service_caller(db, fixture, monkeypatch, after_supplier):
    import services.order_production_creation as service
    register = service.ensure_supplier
    def fail(*args, **kwargs):
        if after_supplier:
            register(*args, **kwargs)
        raise ValueError("simulated allocation conflict")
    monkeypatch.setattr(service, "ensure_supplier" if after_supplier else "replace_order_source", fail)
    with pytest.raises(ValueError, match="allocation conflict"):
        service.create_order_handcraft(db, "OR-1", payload(fixture["lines"][0]))
    assert db.query(HandcraftOrder).count() == 1
    assert db.query(HandcraftJewelryItem).count() == 2
    assert db.query(ProductionCreation).count() == 0
    assert db.query(Supplier).count() == 0


def test_real_api_commits_once_and_rejects_changed_retries(client_real_get_db, db, fixture):
    body = payload(fixture["lines"][0])
    db.commit()
    response = client_real_get_db.post("/api/orders/OR-1/production/handcraft", json=body)
    assert response.status_code == 201, response.text
    assert client_real_get_db.post("/api/orders/OR-1/production/handcraft", json=body).json() == response.json()
    changed = deepcopy(body); changed["allocated_quantity"] = 5
    assert client_real_get_db.post("/api/orders/OR-1/production/handcraft", json=changed).status_code == 400
    db.expire_all()
    assert db.query(HandcraftOrder).count() == 2
    assert db.query(ProductionCreation).count() == 1
    assert db.query(ProductionAllocation).one().quantity == 20
    assert db.query(Supplier).filter_by(name="手工商", type="handcraft").count() == 1


def test_inline_supplier_preserves_existing_identity_and_other_supplier_types(db, fixture):
    existing = Supplier(name="手工商", type="handcraft")
    db.add_all([existing, Supplier(name="手工商", type="plating")]); db.flush()
    identity, created_at = existing.id, existing.created_at
    create_order_handcraft(db, "OR-1", payload(fixture["lines"][0]))
    db.expire_all()
    assert db.query(Supplier).count() == 2
    assert db.query(Supplier).filter_by(name="手工商", type="handcraft").one().id == identity
    assert db.get(Supplier, identity).created_at == created_at


@pytest.mark.parametrize("append", [False, True])
@pytest.mark.parametrize("same_request", [False, True])
def test_concurrent_retries_and_cross_order_new_supplier_registration(db, fixture, append, same_request):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    first = payload(fixture["lines"][0], append_to_order_id="HC-1" if append else None)
    second = deepcopy(first) if same_request else payload(fixture["lines"][2], append_to_order_id=first["append_to_order_id"])
    engine = db.get_bind(); db.commit()
    barrier = Barrier(2)
    def run(order_id, data):
        with Session(engine) as session:
            session.execute(text("SET LOCAL lock_timeout = '5s'")); barrier.wait(timeout=10)
            result = create_order_handcraft(session, order_id, data)
            session.commit()
            return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, order_id, data) for order_id, data in
                   [("OR-1", first), ("OR-1" if same_request else "OR-2", second)]]
        results = [f.result(timeout=15) for f in futures]
    db.expire_all()
    assert (results[0] == results[1]) is same_request
    count = 1 if same_request else 2
    assert db.query(ProductionCreation).count() == count
    assert db.query(ProductionAllocation).count() == count
    assert db.query(HandcraftOrder).count() == (1 if append else 1 + count)
    assert db.query(HandcraftJewelryItem).count() == 2 + count
    assert db.query(Supplier).filter_by(name="手工商", type="handcraft").count() == 1
    for result in results:
        allocation = db.query(ProductionAllocation).filter_by(handcraft_jewelry_item_id=result["source_item_id"]).one()
        assert allocation.order_item_id == result["order_item_id"]
        assert allocation.quantity == 20


def test_oversized_output_plan_is_rejected_before_database_insert(db, fixture):
    data = payload(fixture["lines"][0])
    data["jewelries"][0]["qty"] = 1000000000
    with pytest.raises(ValueError): create_order_handcraft(db, "OR-1", data)
    assert db.query(HandcraftOrder).count() == 1
    assert db.query(Supplier).count() == 0
