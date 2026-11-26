"""Batch creation on a newly created isolated *_test PostgreSQL database only."""
from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError

from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem, HandcraftPartItem
from models.inventory_log import InventoryLog
from models.order import Order
from models.production_allocation import ProductionAllocation
from models.production_creation import ProductionCreation
from models.supplier import Supplier
from schemas.production_allocation import OrderHandcraftBatchCreate
from services.order_production_creation import create_order_handcraft_batch
from tests.test_production_allocation import fixture  # noqa: F401


def payload(fixture, **changes):
    a, repeated, _, jewelry = fixture['lines']
    data = dict(supplier_name='手工商', request_key=str(uuid4()),
                parts=[dict(part_id='raw', qty=20, unit='个'), dict(part_id='raw', qty=7, unit='个')],
                jewelries=[dict(part_id='gold', qty=25, unit='个'), dict(part_id='gold', qty=12, unit='个'),
                           dict(jewelry_id='necklace', qty=9, unit='条')],
                allocations=[dict(order_item_id=a.id, allocated_quantity=20),
                             dict(order_item_id=repeated.id, allocated_quantity=10),
                             dict(order_item_id=jewelry.id, allocated_quantity=8)])
    data.update(changes)
    return OrderHandcraftBatchCreate(**data).model_dump()


@pytest.mark.parametrize('append', [False, True])
def test_batch_maps_repeated_and_different_products_to_exact_new_outputs(db, fixture, append):
    old = [(r.id, r.qty) for r in db.query(HandcraftJewelryItem).all()]
    data = payload(fixture, append_to_order_id='HC-1' if append else None)
    result = create_order_handcraft_batch(db, 'OR-1', data)
    assert result['appended'] is append
    assert db.query(HandcraftOrder).count() == (1 if append else 2)
    assert [(db.get(HandcraftJewelryItem, i).id, db.get(HandcraftJewelryItem, i).qty) for i, _ in old] == old
    for row, share, output in zip(result['rows'], data['allocations'], data['jewelries']):
        actual = db.get(HandcraftJewelryItem, row['source_item_id'])
        allocation = db.query(ProductionAllocation).filter_by(handcraft_jewelry_item_id=actual.id).one()
        assert actual.handcraft_order_id == result['production_order_id']
        assert actual.part_id == output.get('part_id') and actual.jewelry_id == output.get('jewelry_id')
        assert actual.qty == output['qty'] and allocation.order_item_id == share['order_item_id']
        assert allocation.quantity == share['allocated_quantity']
        assert row['public_quantity'] == output['qty'] - share['allocated_quantity']
    assert db.query(HandcraftPartItem).filter_by(handcraft_order_id=result['production_order_id']).count() == (3 if append else 2)
    assert db.query(InventoryLog).count() == 0
    assert db.query(ProductionCreation).count() == 1


@pytest.mark.parametrize('invalid', ['foreign', 'unit', 'mismatch', 'capacity', 'supplier', 'completed', 'archived'])
def test_invalid_batch_leaves_no_outputs_allocations_or_suppliers(db, fixture, invalid):
    data = payload(fixture)
    if invalid == 'foreign': data['allocations'][1]['order_item_id'] = fixture['lines'][2].id
    if invalid == 'unit': data['jewelries'][1]['unit'] = '条'
    if invalid == 'mismatch': data['jewelries'][1]['part_id'] = 'raw'
    if invalid == 'capacity': data['allocations'][1]['allocated_quantity'] = 31
    if invalid in ['supplier', 'completed', 'archived']:
        data['append_to_order_id'] = 'HC-1'
        parent = db.get(HandcraftOrder, 'HC-1')
        if invalid == 'supplier': data['supplier_name'] = '其他商家'
        if invalid == 'completed': parent.status = 'completed'
        if invalid == 'archived':
            from time_utils import now_beijing
            parent.archived_at = now_beijing()
        db.flush()
    with pytest.raises(ValueError): create_order_handcraft_batch(db, 'OR-1', data)
    assert db.query(HandcraftOrder).count() == 1
    assert db.query(HandcraftJewelryItem).count() == 2
    assert db.query(HandcraftPartItem).count() == 1
    assert db.query(ProductionAllocation).count() == db.query(ProductionCreation).count() == db.query(Supplier).count() == 0


def test_late_failure_rolls_back_all_rows_and_append_note(db, fixture, monkeypatch):
    import services.order_production_creation as service
    original = service.replace_order_source
    count = 0
    def fail_second(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2: raise ValueError('late failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(service, 'replace_order_source', fail_second)
    with pytest.raises(ValueError, match='late failure'):
        create_order_handcraft_batch(db, 'OR-1', payload(fixture, append_to_order_id='HC-1', note='must rollback'))
    assert db.query(HandcraftJewelryItem).count() == 2
    assert db.query(HandcraftPartItem).count() == 1
    assert db.get(HandcraftOrder, 'HC-1').note is None
    assert db.get(Order, 'OR-1').status == '待生产'
    assert db.query(ProductionAllocation).count() == db.query(ProductionCreation).count() == 0


def test_batch_retry_after_status_change_and_changed_request_protection(db, fixture):
    data = payload(fixture)
    result = create_order_handcraft_batch(db, 'OR-1', data)
    db.get(Order, 'OR-1').status = '已完成'; db.flush()
    assert create_order_handcraft_batch(db, 'OR-1', data) == result
    changed = deepcopy(data); changed['note'] = 'changed'
    with pytest.raises(ValueError, match='不同内容'): create_order_handcraft_batch(db, 'OR-1', changed)
    assert db.query(ProductionCreation).count() == 1
    assert db.query(HandcraftJewelryItem).count() == 5


def test_batch_schema_requires_unique_exact_one_to_one_rows(db, fixture):
    data = payload(fixture)
    for change in [dict(allocations=[]), dict(allocations=data['allocations'][:1]),
                   dict(allocations=[data['allocations'][0]] * 3),
                   dict(allocations=data['allocations'] * 34, jewelries=data['jewelries'] * 34)]:
        with pytest.raises(ValidationError): OrderHandcraftBatchCreate(**(data | change))


def test_batch_api_requires_both_permissions(client, db, fixture):
    from api.deps import get_current_user
    from main import app
    from models.user import User
    data = payload(fixture)
    for permissions in [[], ['orders'], ['handcraft']]:
        app.dependency_overrides[get_current_user] = lambda p=permissions: User(id=99, username='limited', is_admin=False, permissions=p)
        assert client.post('/api/orders/OR-1/production/handcraft/batch', json=data).status_code == 403
    assert db.query(ProductionCreation).count() == 0


def test_real_batch_api_commits_once_and_rolls_back_invalid_batch(client_real_get_db, db, fixture):
    data = payload(fixture); db.commit()
    endpoint = '/api/orders/OR-1/production/handcraft/batch'
    response = client_real_get_db.post(endpoint, json=data)
    assert response.status_code == 201, response.text
    assert client_real_get_db.post(endpoint, json=data).json() == response.json()
    invalid = deepcopy(data); invalid['request_key'] = str(uuid4()); invalid['allocations'][1]['allocated_quantity'] = 29
    assert client_real_get_db.post(endpoint, json=invalid).status_code == 400
    db.expire_all()
    assert db.query(ProductionCreation).count() == 1
    assert db.query(ProductionAllocation).count() == 3


@pytest.mark.parametrize('same_request', [False, True])
def test_concurrent_batches_append_without_interleaving_exact_outputs(db, fixture, same_request):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    first = payload(fixture, append_to_order_id='HC-1')
    second = deepcopy(first)
    if not same_request:
        # Independent order shares the parent, so parent locking (not only the
        # customer-order lock) must protect mapping the last N inserted rows.
        from models.order import OrderItem
        own = [OrderItem(order_id='OR-2', part_id='gold', quantity=40, unit_price=1),
               OrderItem(order_id='OR-2', jewelry_id='necklace', quantity=40, unit_price=1)]
        db.add_all(own); db.flush()
        second['request_key'] = str(uuid4())
        for row, line in zip(second['allocations'], [fixture['lines'][2], *own]): row['order_item_id'] = line.id
    engine = db.get_bind(); db.commit(); barrier = Barrier(2)
    def run(order_id, data):
        with Session(engine) as session:
            session.execute(text("SET LOCAL lock_timeout = '5s'")); barrier.wait(timeout=10)
            result = create_order_handcraft_batch(session, order_id, data); session.commit()
            return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, 'OR-1', first), pool.submit(run, 'OR-1' if same_request else 'OR-2', second)]
        results = [f.result(timeout=15) for f in futures]
    db.expire_all()
    assert (results[0] == results[1]) is same_request
    assert db.query(ProductionCreation).count() == (1 if same_request else 2)
    for result in results:
        for row in result['rows']:
            actual = db.query(ProductionAllocation).filter_by(handcraft_jewelry_item_id=row['source_item_id']).one()
            assert actual.order_item_id == row['order_item_id']
            assert actual.quantity == row['allocated_quantity']
