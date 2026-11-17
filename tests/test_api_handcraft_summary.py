"""Run only with TEST_DATABASE_URL set to a disposable *_test database."""
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event

from models.bom import Bom
from models.part_bom import PartBom
from models.part import Part
from models.jewelry import Jewelry
from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem, HandcraftPickingWeight, HandcraftPickingRecord
from models.handcraft_receipt import HandcraftReceipt, HandcraftReceiptItem
from models.order import Order, OrderItemLink, OrderTodoItem
from models.production_loss import ProductionLoss
from services.handcraft_summary import list_dispatched, list_received


def seed(db):
    db.add_all([Part(id='MAT', name='珍珠', unit='颗'), Part(id='OTHER', name='无关'),
                Part(id='COMP', name='组合扣', is_composite=True), Part(id='MID', name='中间组合', is_composite=True),
                Jewelry(id='J1', name='项链'), Jewelry(id='J2', name='耳饰')])
    db.flush()
    db.add_all([Bom(id='b1', jewelry_id='J1', part_id='COMP', qty_per_unit=1),
                Bom(id='b2', jewelry_id='J2', part_id='MAT', qty_per_unit=2),
                Bom(id='b0', jewelry_id='J1', part_id='OTHER', qty_per_unit=0),
                PartBom(id='p1', parent_part_id='COMP', child_part_id='MID', qty_per_unit=1),
                PartBom(id='p2', parent_part_id='MID', child_part_id='MAT', qty_per_unit=2)])
    order = HandcraftOrder(id='HC1', supplier_name='商家甲', status='processing', created_at=datetime(2026, 11, 1), note='单据备注')
    db.add(order); db.flush()
    material = HandcraftPartItem(handcraft_order_id=order.id, part_id='MAT', qty=100, unit='颗', status='制作中', note='材料备注')
    unknown = HandcraftPartItem(handcraft_order_id=order.id, part_id='OTHER', qty=3, status='制作中')
    output = HandcraftJewelryItem(handcraft_order_id=order.id, jewelry_id='J1', qty=10, received_qty=9, unit='套', status='制作中', note='产出备注')
    second = HandcraftJewelryItem(handcraft_order_id=order.id, jewelry_id='J2', qty=5, unit='对', status='制作中')
    db.add_all([material, unknown, output, second]); db.flush()
    for i, (day, qty, unit) in enumerate([(8, 6, '套'), (15, 2, '套')]):
        receipt = HandcraftReceipt(id=f'HR{i}', supplier_name='商家甲', created_at=datetime(2026, 11, day), note=f'批次单备注{i}')
        db.add(receipt); db.flush()
        db.add(HandcraftReceiptItem(handcraft_receipt_id=receipt.id, handcraft_jewelry_item_id=output.id,
            item_id='J1', item_type='jewelry', qty=qty, unit=unit, note=f'批次明细{i}'))
    db.add(ProductionLoss(order_type='handcraft', order_id=order.id, item_id=output.id,
                          item_type='handcraft_jewelry', loss_qty=1))
    db.flush()
    return order, material, unknown, output, second


def test_empty(db):
    assert list_dispatched(db) == ([], 0)
    assert list_received(db) == ([], 0)


def test_current_nested_bom_shared_material_no_duplicates(db):
    _, material, unknown, output, second = seed(db)
    rows, total = list_dispatched(db)
    assert total == 2
    row = next(r for r in rows if r['handcraft_part_item_id'] == material.id)
    assert row['qty'] == 100
    assert {o['handcraft_jewelry_item_id'] for o in row['outputs']} == {output.id, second.id}
    assert row['relationship_basis'] == 'current_bom'
    assert len(row['receipts']) == 2
    assert next(r for r in rows if r['handcraft_part_item_id'] == unknown.id)['outputs'] == []
    assert list_dispatched(db, output_id='项链')[1] == 1
    assert list_received(db, part_id='珍珠')[1] == 2
    assert list_received(db, part_id='OTHER')[1] == 0


def test_cycles_terminate_and_composite_self_does_not_match(db):
    order, _, _, _, _ = seed(db)
    db.add(PartBom(id='cycle', parent_part_id='MID', child_part_id='COMP', qty_per_unit=1))
    composite_material = HandcraftPartItem(handcraft_order_id=order.id, part_id='COMP', qty=10)
    composite_output = HandcraftJewelryItem(handcraft_order_id=order.id, part_id='COMP', qty=5)
    db.add_all([composite_material, composite_output]); db.flush()
    rows, _ = list_dispatched(db)
    row = next(r for r in rows if r['handcraft_part_item_id'] == composite_material.id)
    assert composite_output.id not in {o['handcraft_jewelry_item_id'] for o in row['outputs']}
    assert list_received(db, output_id='组合扣', part_id='MAT')[1] == 1


def test_physical_receipts_losses_surplus_and_batches(db):
    order, material, _, output, _ = seed(db)
    # Material returns and unrelated/wrong-kind losses must not inflate output receipts.
    db.add(HandcraftReceiptItem(handcraft_receipt_id='HR0', handcraft_part_item_id=material.id,
        item_id='MAT', item_type='part', qty=40, unit='颗'))
    db.add(ProductionLoss(order_type='plating', order_id=order.id, item_id=output.id, item_type='plating_item', loss_qty=100))
    db.flush()
    rows, total = list_received(db, output_id='J1')
    assert total == 1
    row = rows[0]
    assert (row['expected_qty'], row['actual_received_qty'], row['loss_total_qty'], row['unreceived_qty']) == (10, 8, 1, 1)
    assert row['unit'] == '套'
    assert [(b['receipt_id'], b['receipt_date'], b['qty'], b['unit'], b['note'], b['document_note']) for b in row['receipts']] == [
        ('HR0', date(2026, 11, 8), 6, '套', '批次明细0', '批次单备注0'),
        ('HR1', date(2026, 11, 15), 2, '套', '批次明细1', '批次单备注1')]
    assert row['note'] == '产出备注' and row['document_note'] == '单据备注'


def test_receipt_date_selects_sources_not_period_totals(db):
    seed(db)
    rows, total = list_received(db, date_from=date(2026, 11, 14), date_to=date(2026, 11, 16))
    assert total == 1
    assert rows[0]['actual_received_qty'] == 8 and len(rows[0]['receipts']) == 2
    assert list_received(db, date_from=date(2026, 11, 17))[1] == 0
    assert list_dispatched(db, date_to=date(2026, 10, 31))[1] == 0
    assert list_dispatched(db, date_from=date(2026, 11, 1), date_to=date(2026, 11, 1))[1] == 2


@pytest.mark.parametrize('direction', [list_dispatched, list_received])
def test_archive_pending_and_source_pagination(db, direction):
    order, _, _, _, _ = seed(db)
    assert direction(db, supplier_name='不存在')[1] == 0
    ids = []
    key = 'handcraft_part_item_id' if direction is list_dispatched else 'handcraft_jewelry_item_id'
    for skip in (0, 1):
        rows, total = direction(db, skip=skip, limit=1)
        assert total == 2 and len(rows) == 1
        ids.append(rows[0][key])
    assert len(set(ids)) == 2
    order.archived_at = datetime(2026, 11, 17); db.flush()
    assert direction(db)[1] == 0 and direction(db, archive='archived')[1] == 2
    assert direction(db, archive='all')[1] == 2
    if direction is list_received:
        assert all(r['max_loss_qty'] == 0 for r in direction(db, archive='all')[0])
    order.status = 'pending'; db.flush()
    assert direction(db, archive='all')[1] == 0


def test_actual_picking_gate_and_weights(db):
    order, material, _, _, _ = seed(db)
    db.add(HandcraftPickingWeight(handcraft_order_id=order.id, part_item_id=material.id,
        atom_part_id='MAT', actual_qty=88, weight=300, weight_unit='g'))
    db.flush()
    assert list_dispatched(db, part_id='MAT')[0][0]['qty'] == 100
    db.add(HandcraftPickingRecord(handcraft_order_id=order.id, handcraft_part_item_id=material.id, part_id='MAT')); db.flush()
    row = list_dispatched(db, part_id='MAT')[0][0]
    assert row['qty'] == 88 and row['weight'] == 300 and row['weight_unit'] == 'g'
    composite = HandcraftPartItem(handcraft_order_id=order.id, part_id='COMP', qty=7)
    db.add(composite); db.flush()
    db.add_all([HandcraftPickingWeight(handcraft_order_id=order.id, part_item_id=composite.id, atom_part_id='MAT', actual_qty=999, weight=200, weight_unit='g'),
                HandcraftPickingWeight(handcraft_order_id=order.id, part_item_id=composite.id, atom_part_id='OTHER', weight=Decimal('0.3'), weight_unit='kg')]); db.flush()
    row = list_dispatched(db, part_id='COMP')[0][0]
    assert row['qty'] == 7 and row['weight'] == .5 and row['weight_unit'] == 'kg'


def test_source_specific_order_links_and_literal_search(db):
    _, material, unknown, output, second = seed(db)
    db.add_all([Order(id='O-A', customer_name='甲'), Order(id='O-B', customer_name='乙')]); db.flush()
    todo = OrderTodoItem(order_id='O-A', part_id='MAT', required_qty=100)
    db.add(todo); db.flush()
    db.add_all([OrderItemLink(handcraft_part_item_id=material.id, order_todo_item_id=todo.id),
                OrderItemLink(handcraft_jewelry_item_id=output.id, order_id='O-B')]); db.flush()
    assert list_dispatched(db, order_id='O-A')[1] == 1
    assert list_dispatched(db, order_id='O-B')[1] == 0
    assert list_received(db, order_id='O-B')[0][0]['order_ids'] == ['O-B']
    assert list_received(db, order_id='O-A')[1] == 0
    assert list_dispatched(db, part_id='%')[1] == 0
    assert list_received(db, output_id='_')[1] == 0


def test_same_product_different_sources_never_merge(db):
    _, _, _, output, _ = seed(db)
    second = HandcraftOrder(id='HC2', supplier_name='商家甲', status='processing', created_at=datetime(2026, 11, 2))
    db.add(second); db.flush()
    db.add(HandcraftJewelryItem(handcraft_order_id=second.id, jewelry_id='J1', qty=30)); db.flush()
    rows, total = list_received(db, output_id='J1')
    assert total == 2 and {r['expected_qty'] for r in rows} == {10, 30}


def test_no_receipt_full_loss_and_counter_disagreement(db):
    order, _, _, _, second = seed(db)
    rows, _ = list_received(db, output_id='J2')
    assert rows[0]['receipts'] == [] and rows[0]['max_loss_qty'] == 5
    second.received_qty = 5
    db.add(ProductionLoss(order_type='handcraft', order_id=order.id, item_id=second.id, item_type='handcraft_jewelry', loss_qty=5)); db.flush()
    row = list_received(db, output_id='J2')[0][0]
    assert row['actual_received_qty'] == 0 and row['unreceived_qty'] == 0 and row['is_completed']
    # Counter-only legacy history is not invented into physical receipts.
    db.query(ProductionLoss).filter_by(item_id=second.id).delete(); db.flush()
    row = list_received(db, output_id='J2')[0][0]
    assert row['actual_received_qty'] == 0 and row['unreceived_qty'] == 5 and row['max_loss_qty'] == 0


def test_query_count_bounded_and_read_only(db):
    seed(db)
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(db.bind, 'before_cursor_execute', record)
    try:
        list_dispatched(db)
        assert len(statements) <= 7
        statements.clear()
        list_received(db)
        assert len(statements) <= 7
        assert all(s.lstrip().upper().startswith(('SELECT', 'WITH')) for s in statements)
    finally:
        event.remove(db.bind, 'before_cursor_execute', record)


def test_api_schema_validation_and_source_loss_endpoint(client, db):
    _, _, _, output, _ = seed(db)
    for endpoint in ['dispatched', 'received']:
        response = client.get(f'/api/handcraft-summary/{endpoint}')
        assert response.status_code == 200, response.text
        assert response.json()['total'] == 2
        for params in [{'archive': 'bad'}, {'skip': -1}, {'limit': 201}, {'date_from': '2026-02-30'}]:
            assert client.get(f'/api/handcraft-summary/{endpoint}', params=params).status_code == 422
    response = client.post(f'/api/handcraft/HC1/items/{output.id}/confirm-loss', json={'item_type': 'jewelry', 'loss_qty': 1})
    assert response.status_code == 200, response.text
    row = client.get('/api/handcraft-summary/received', params={'output_id': 'J1'}).json()['items'][0]
    assert row['actual_received_qty'] == 8 and row['loss_total_qty'] == 2 and row['unreceived_qty'] == 0


def test_api_requires_handcraft_permission(client):
    from api.deps import get_current_user
    from main import app
    from models.user import User
    user = User(id=999, username='limited', password_hash='', is_admin=False, is_active=True, permissions=['plating'])
    app.dependency_overrides[get_current_user] = lambda: user
    for endpoint in ['dispatched', 'received']:
        assert client.get(f'/api/handcraft-summary/{endpoint}').status_code == 403
    user.permissions = ['handcraft']
    assert client.get('/api/handcraft-summary/dispatched').status_code == 200


def test_duplicate_material_sources_and_cross_order_outputs(db):
    order, material, _, _, _ = seed(db)
    duplicate = HandcraftPartItem(handcraft_order_id=order.id, part_id='MAT', qty=25)
    other_order = HandcraftOrder(id='HC-OTHER', supplier_name='商家甲', status='processing')
    db.add_all([duplicate, other_order]); db.flush()
    orphan = HandcraftPartItem(handcraft_order_id=other_order.id, part_id='MAT', qty=12)
    db.add(orphan); db.flush()
    rows, total = list_dispatched(db, part_id='MAT')
    assert total == 3
    assert sorted(r['qty'] for r in rows) == [12, 25, 100]
    assert next(r for r in rows if r['handcraft_part_item_id'] == orphan.id)['outputs'] == []
    rows, total = list_dispatched(db, part_id='MAT', output_id='J1')
    assert total == 2 and {r['handcraft_part_item_id'] for r in rows} == {material.id, duplicate.id}
