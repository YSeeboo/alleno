"""Customer order starts with a confirmed production link, not a manual button."""
import pytest

from models.order import Order, OrderTodoItem, OrderTodoBatch, OrderTodoBatchJewelry
from models.handcraft_order import HandcraftOrder
from models.inventory_log import InventoryLog
from models.purchase_order import PurchaseOrder, PurchaseOrderItem
from services.production_allocation import order_production, production_uses, replace_order_source
from services.order_todo import create_link, delete_link, batch_link, link_supplier
from services.order_production_creation import create_order_handcraft
from tests.test_production_allocation import fixture  # noqa: F401
from tests.test_order_production_creation import payload


def allocate(db, line, kind, output, qty):
    parent = 'HC-1' if kind == 'handcraft' else 'EP-1'
    source = next(s for s in production_uses(db, kind, parent) if s['source_item_id'] == output.id)
    return replace_order_source(db, line.order_id, kind, output.id, source['revision'],
                                [{'order_item_id': line.id, 'quantity': qty}])


@pytest.mark.parametrize('kind', ['handcraft', 'plating'])
def test_confirmed_positive_allocation_starts_only_its_order(client, db, fixture, kind):
    line = fixture['lines'][3 if kind == 'handcraft' else 0]
    output = fixture['jewelry' if kind == 'handcraft' else 'plating']
    # Merely discovering a matching production candidate must not start an order.
    order_production(db, 'OR-1')
    assert db.get(Order, 'OR-1').status == '待生产'
    allocate(db, line, kind, output, 1)
    assert client.get('/api/orders/OR-1').json()['status'] == '生产中'
    assert db.get(Order, 'OR-2').status == '待生产'
    allocate(db, line, kind, output, 0)
    assert db.get(Order, 'OR-1').status == '生产中'  # Starting is not undone by unlinking.
    assert db.query(InventoryLog).count() == 0


@pytest.mark.parametrize('kind', ['handcraft', 'plating'])
def test_zero_or_rejected_allocation_never_starts_order(db, fixture, kind):
    line = fixture['lines'][3 if kind == 'handcraft' else 0]
    output = fixture['jewelry' if kind == 'handcraft' else 'plating']
    allocate(db, line, kind, output, 0)
    assert db.get(Order, 'OR-1').status == '待生产'
    with pytest.raises(ValueError):
        allocate(db, line, kind, output, line.quantity + 1)
    assert db.get(Order, 'OR-1').status == '待生产'


@pytest.mark.parametrize('kind', ['handcraft', 'plating'])
def test_real_api_commits_link_and_started_status_together(client_real_get_db, db, fixture, kind):
    line = fixture['lines'][3 if kind == 'handcraft' else 0]
    output = fixture['jewelry' if kind == 'handcraft' else 'plating']
    source = next(s for s in production_uses(db, kind, 'HC-1' if kind == 'handcraft' else 'EP-1')
                  if s['source_item_id'] == output.id)
    body = {'source_type': kind, 'source_item_id': output.id, 'revision': source['revision'],
            'allocations': [{'order_item_id': line.id, 'quantity': line.quantity + 1}]}
    db.commit()
    assert client_real_get_db.put('/api/orders/OR-1/production', json=body).status_code == 400
    assert client_real_get_db.get('/api/orders/OR-1').json()['status'] == '待生产'
    body['allocations'][0]['quantity'] = 1
    assert client_real_get_db.put('/api/orders/OR-1/production', json=body).status_code == 200
    assert client_real_get_db.get('/api/orders/OR-1').json()['status'] == '生产中'
    assert client_real_get_db.get('/api/fulfillment/orders/OR-1').json()['status'] == '生产中'
    db.expire_all()
    assert db.get(Order, 'OR-1').status == '生产中'


@pytest.mark.parametrize('append', [False, True])
def test_order_handcraft_creation_or_append_starts_order_before_dispatch(db, fixture, append):
    body = payload(fixture['lines'][0], **({'append_to_order_id': 'HC-1'} if append else {}))
    result = create_order_handcraft(db, 'OR-1', body)
    assert db.get(Order, 'OR-1').status == '生产中'
    assert db.get(HandcraftOrder, result['production_order_id']).status == 'pending'
    assert db.get(Order, 'OR-2').status == '待生产'


def test_failed_creation_rolls_back_auto_started_status(db, fixture, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError('supplier failure after allocation')
    monkeypatch.setattr('services.order_production_creation.ensure_supplier', fail)
    with pytest.raises(ValueError, match='supplier failure'):
        create_order_handcraft(db, 'OR-1', payload(fixture['lines'][0]))
    assert db.get(Order, 'OR-1').status == '待生产'


@pytest.mark.parametrize('kind', ['handcraft_jewelry', 'handcraft_part', 'plating'])
def test_legacy_exact_links_also_start_order(db, fixture, kind):
    if kind == 'handcraft_jewelry':
        body = {'order_id': 'OR-1', 'handcraft_jewelry_item_id': fixture['jewelry'].id}
    else:
        todo = OrderTodoItem(order_id='OR-1', part_id='gold', required_qty=10)
        db.add(todo); db.flush()
        body = {'order_todo_item_id': todo.id,
                'plating_order_item_id' if kind == 'plating' else 'handcraft_part_item_id':
                    fixture['plating' if kind == 'plating' else 'input_part'].id}
    link = create_link(db, body)
    assert db.get(Order, 'OR-1').status == '生产中'
    delete_link(db, link.id)
    assert db.get(Order, 'OR-1').status == '生产中'


@pytest.mark.parametrize('kind', ['handcraft', 'plating', 'purchase', 'unmatched'])
def test_batch_links_start_only_for_successful_handcraft_or_plating(db, fixture, kind):
    todo = OrderTodoItem(order_id='OR-1', part_id='raw' if kind == 'unmatched' else 'gold', required_qty=10)
    db.add(todo); db.flush()
    if kind == 'purchase':
        db.add(PurchaseOrder(id='PO-1', vendor_name='采购商')); db.flush()
        row = PurchaseOrderItem(purchase_order_id='PO-1', part_id='gold', qty=10)
        db.add(row); db.flush()
        body = {'purchase_order_item_ids': [row.id]}
    else:
        body = {'handcraft_part_item_ids': [fixture['input_part'].id]} if kind == 'handcraft' else {
            'plating_order_item_ids': [fixture['plating'].id]}
    result = batch_link(db, 'OR-1', **body)
    assert result['linked'] == (0 if kind == 'unmatched' else 1)
    assert db.get(Order, 'OR-1').status == ('生产中' if kind in {'handcraft', 'plating'} else '待生产')


def test_single_purchase_link_does_not_count_as_production(db, fixture):
    db.add(PurchaseOrder(id='PO-1', vendor_name='采购商')); db.flush()
    row = PurchaseOrderItem(purchase_order_id='PO-1', part_id='gold', qty=10)
    todo = OrderTodoItem(order_id='OR-1', part_id='gold', required_qty=10)
    db.add_all([row, todo]); db.flush()
    create_link(db, {'order_todo_item_id': todo.id, 'purchase_order_item_id': row.id})
    assert db.get(Order, 'OR-1').status == '待生产'


def test_legacy_batch_supplier_link_starts_order(db, fixture):
    batch = OrderTodoBatch(order_id='OR-1')
    db.add(batch); db.flush()
    db.add(OrderTodoBatchJewelry(batch_id=batch.id, jewelry_id='necklace', quantity=5)); db.flush()
    result = link_supplier(db, 'OR-1', batch.id, '手工商')
    assert result['handcraft_order_id']
    assert db.get(Order, 'OR-1').status == '生产中'


@pytest.mark.parametrize('status', ['已完成', '已取消'])
def test_legacy_association_does_not_reopen_closed_history(db, fixture, status):
    order = db.get(Order, 'OR-1')
    order.status = status; db.flush()
    create_link(db, {'order_id': order.id, 'handcraft_jewelry_item_id': fixture['jewelry'].id})
    assert order.status == status


def test_finished_production_is_not_customer_order_completion(db, fixture):
    allocate(db, fixture['lines'][3], 'handcraft', fixture['jewelry'], 50)
    db.get(HandcraftOrder, 'HC-1').status = 'completed'; db.flush()
    assert db.get(Order, 'OR-1').status == '生产中'
    assert db.query(InventoryLog).count() == 0
