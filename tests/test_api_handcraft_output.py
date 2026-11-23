"""Output overview regression on the guarded disposable test database only."""
from datetime import date, datetime

import pytest
from sqlalchemy import event

from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
from models.handcraft_receipt import HandcraftReceipt, HandcraftReceiptItem
from models.part import Part
from models.production_loss import ProductionLoss
from services.handcraft_output import output_overview, output_sources, output_receipts, output_options
from tests.test_api_handcraft_summary import seed


def fixture(db):
    order, material, _, first, second = seed(db)
    db.add(Part(id='J1', name='同编号组合配件', is_composite=True))
    db.add_all([
        HandcraftOrder(id='HC2', supplier_name='商家甲', status='processing', created_at=datetime(2026, 11, 2)),
        HandcraftOrder(id='HC3', supplier_name='商家乙', status='completed', created_at=datetime(2026, 11, 3)),
        HandcraftOrder(id='HC4', supplier_name='商家乙', status='processing', created_at=datetime(2026, 8, 1), archived_at=datetime(2026, 10, 1)),
        HandcraftOrder(id='DRAFT', supplier_name='草稿商家', status='pending'),
    ]); db.flush()
    same = HandcraftJewelryItem(handcraft_order_id='HC2', jewelry_id='J1', qty=20, unit='套', dispatched_at=datetime(2026, 11, 20, 12))
    other = HandcraftJewelryItem(handcraft_order_id='HC3', jewelry_id='J1', qty=8, unit='对')
    part = HandcraftJewelryItem(handcraft_order_id='HC3', part_id='J1', qty=6, unit='个')
    archived = HandcraftJewelryItem(handcraft_order_id='HC4', jewelry_id='J2', qty=10, unit='条')
    draft = HandcraftJewelryItem(handcraft_order_id='DRAFT', jewelry_id='J1', qty=100)
    db.add_all([same, other, part, archived, draft]); db.flush()
    return first, second, same, other, part, archived, draft


def test_empty_and_response_schema(client):
    data = client.get('/api/handcraft-summary/output-overview').json()
    assert data == dict(groups=[], totals=[], total=0, source_count=0, supplier_count=0, output_count=0, reference_date_count=0)
    assert client.get('/api/handcraft-summary/output-options').json() == dict(suppliers=[], outputs=[], has_more=False)


def test_multi_selection_intersection_typed_identity_and_units(db):
    fixture(db)
    data = output_overview(db)
    assert (data['source_count'], data['supplier_count'], data['output_count'], data['reference_date_count']) == (5, 2, 3, 4)
    units = {row['unit']: row for row in data['totals']}
    assert (units['套']['expected_qty'], units['套']['actual_received_qty'], units['套']['loss_total_qty'], units['套']['unreceived_qty']) == (30, 8, 1, 21)
    assert set(units) == {'套', '对', '个'}
    assert units['对']['expected_qty'] == 13
    assert output_overview(db, output_keys=['jewelry:J1', 'part:J1'])['source_count'] == 4
    assert output_overview(db, supplier_names=['商家甲', '商家乙'], output_keys=['part:J1'])['source_count'] == 1
    assert output_overview(db, supplier_names=['商家甲'], output_keys=['part:J1'])['source_count'] == 0


@pytest.mark.parametrize('view', ['merchant', 'product'])
def test_whole_group_pagination_totals_are_not_page_totals(db, view):
    fixture(db)
    first = output_overview(db, view=view, limit=1)
    second = output_overview(db, view=view, skip=1, limit=1)
    assert first['total'] == (2 if view == 'merchant' else 3)
    assert first['source_count'] == second['source_count'] == 5
    assert first['totals'] == second['totals']
    assert first['groups'][0]['key'] != second['groups'][0]['key']
    all_groups = output_overview(db, view=view)['groups']
    merged = next(item for group in all_groups for item in group['items'] if item['supplier_name'] == '商家甲' and item['output_key'] == 'jewelry:J1')
    assert merged['source_count'] == 2 and merged['unreceived_qty'] == 21
    assert sum(item['source_count'] for group in all_groups for item in group['items']) == 5


def test_actual_dispatch_date_reference_date_and_cross_month_receipts(db):
    first, *_ = fixture(db)
    first.dispatched_at = datetime(2026, 11, 5, 23, 59)
    db.query(HandcraftReceipt).filter_by(id='HR1').one().created_at = datetime(2026, 12, 1)
    db.flush()
    filters = dict(date_from=date(2026, 11, 5), date_to=date(2026, 11, 5))
    data = output_overview(db, **filters)
    assert data['source_count'] == 1 and data['reference_date_count'] == 0
    assert data['totals'][0]['actual_received_qty'] == 8
    row = output_sources(db, supplier_name='商家甲', output_key='jewelry:J1', unit='套', **filters)['items'][0]
    assert row['dispatch_date'] == date(2026, 11, 5) and row['dispatch_date_basis'] == 'actual'
    reference = output_sources(db, supplier_name='商家乙', output_key='jewelry:J1', unit='对')['items'][0]
    assert reference['dispatch_date_basis'] == 'document_reference' and reference['dispatch_date'] == date(2026, 11, 3)
    batches = output_receipts(db, first.id)['items']
    assert [batch['receipt_date'] for batch in batches] == [date(2026, 11, 8), date(2026, 12, 1)]


def test_progress_loss_and_legacy_counter_disagreement(db):
    first, second, *_ = fixture(db)
    # Counters include losses / legacy adjustments; they never become real receipts.
    second.received_qty = 5
    db.add(ProductionLoss(order_type='handcraft', order_id='HC1', item_id=second.id,
                          item_type='handcraft_jewelry', loss_qty=5))
    db.flush()
    assert output_overview(db, progress='settled')['source_count'] == 1
    assert output_overview(db, progress='partial')['source_count'] == 1
    assert output_overview(db, progress='unreceived')['source_count'] == 3
    settled = output_overview(db, progress='settled')['totals'][0]
    assert settled['actual_received_qty'] == 0 and settled['loss_total_qty'] == 5 and settled['unreceived_qty'] == 0
    # Clamp BEFORE summing: surplus on one source cannot pay down another.
    db.add(HandcraftReceiptItem(handcraft_receipt_id='HR1', handcraft_jewelry_item_id=first.id,
                               item_id='J1', item_type='jewelry', qty=100, unit='套'))
    db.flush()
    merged = next(row for group in output_overview(db)['groups'] for row in group['items'] if row['supplier_name'] == '商家甲' and row['output_key'] == 'jewelry:J1')
    assert merged['unreceived_qty'] == 20


def test_source_and_batch_pages_are_independent_and_filter_consistent(db):
    first, _, same, *_ = fixture(db)
    filters = dict(supplier_name='商家甲', output_key='jewelry:J1', unit='套')
    page = output_sources(db, **filters, limit=1)
    assert page['total'] == 2 and page['items'][0]['handcraft_jewelry_item_id'] == same.id
    assert output_sources(db, **filters, skip=1, limit=1)['items'][0]['handcraft_jewelry_item_id'] == first.id
    assert output_sources(db, **filters, progress='partial')['total'] == 1
    assert output_sources(db, **filters, supplier_names=['商家乙'])['total'] == 0
    batches = output_receipts(db, first.id, limit=1)
    assert batches['total'] == 2 and len(batches['items']) == 1
    assert output_receipts(db, first.id, skip=1, limit=1)['items'][0]['qty'] == 2


def test_archives_pending_options_and_literal_search(db):
    *_, archived, draft = fixture(db)
    assert output_overview(db, archive='archived')['source_count'] == 1
    assert output_overview(db, archive='all')['source_count'] == 6
    assert output_receipts(db, draft.id) is None
    assert output_receipts(db, archived.id) == dict(items=[], total=0)
    options = output_options(db, q='组合')
    assert options['suppliers'] == ['商家乙', '商家甲']
    assert [row['output_key'] for row in options['outputs']] == ['part:J1']
    assert not output_options(db, q='%')['outputs']
    assert not output_options(db, q='_')['outputs']
    assert {row['output_key'] for row in output_options(db, q='组合', selected_keys=['jewelry:J2'])['outputs']} == {'part:J1', 'jewelry:J2'}
    assert output_options(db, limit=1)['has_more']


def test_queries_read_only_bounded_and_no_cross_product_receipt_loss_multiplication(db):
    first, *_ = fixture(db)
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(db.bind, 'before_cursor_execute', record)
    try:
        data = output_overview(db)
        assert len(statements) <= 4
        assert data['totals'][1]['actual_received_qty'] >= 0
        statements.clear()
        output_sources(db, supplier_name='商家甲', output_key='jewelry:J1', unit='套')
        assert len(statements) <= 2
        statements.clear()
        output_receipts(db, first.id)
        assert len(statements) <= 3
        assert all(statement.lstrip().upper().startswith(('SELECT', 'WITH')) for statement in statements)
    finally:
        event.remove(db.bind, 'before_cursor_execute', record)


@pytest.mark.parametrize('params', [
    {'date_from': '2026-11-02', 'date_to': '2026-11-01'}, {'date_from': '2026-02-30'},
    {'progress': 'bad'}, {'view': 'bad'}, {'archive': 'bad'}, {'skip': -1}, {'limit': 51},
    {'output_keys': 'J1'}, {'output_keys': 'jewelry:'}, {'supplier_names': ' '},
    [('output_keys', 'jewelry:J1')] * 101,
])
def test_api_rejects_invalid_filters(client, params):
    assert client.get('/api/handcraft-summary/output-overview', params=params).status_code == 422


def test_api_response_and_permissions(client, db):
    first, *_, draft = fixture(db)
    response = client.get('/api/handcraft-summary/output-overview', params=[('output_keys', 'jewelry:J1'), ('output_keys', 'part:J1')])
    assert response.status_code == 200, response.text
    assert response.json()['source_count'] == 4
    assert client.get('/api/handcraft-summary/output-sources', params=dict(supplier_name='商家甲', output_key='jewelry:J1', unit='套')).json()['total'] == 2
    assert client.get(f'/api/handcraft-summary/output-sources/{first.id}/receipts').json()['total'] == 2
    assert client.get(f'/api/handcraft-summary/output-sources/{draft.id}/receipts').status_code == 404
    from api.deps import get_current_user
    from main import app
    from models.user import User
    app.dependency_overrides[get_current_user] = lambda: User(id=999, username='limited', is_admin=False, is_active=True, permissions=['plating'])
    for path in ['output-overview', 'output-options', 'output-sources?supplier_name=商家甲&output_key=jewelry:J1', f'output-sources/{first.id}/receipts']:
        assert client.get('/api/handcraft-summary/' + path).status_code == 403


def test_new_dispatch_and_processing_append_record_time_but_no_history_backfill(db, monkeypatch):
    import services.handcraft as handcraft
    order, _, _, first, second = seed(db)
    assert first.dispatched_at is None
    order.status = 'pending'; db.flush()
    monkeypatch.setattr(handcraft, 'batch_get_stock', lambda *args: {'MAT': 1000, 'OTHER': 1000})
    monkeypatch.setattr(handcraft, 'deduct_stock', lambda *args: None)
    stamp = datetime(2026, 11, 23, 12, 30)
    monkeypatch.setattr(handcraft, 'now_beijing', lambda: stamp)
    handcraft.send_handcraft_order(db, order.id)
    assert first.dispatched_at == second.dispatched_at == stamp
    appended = handcraft.add_handcraft_jewelry(db, order.id, dict(jewelry_id='J2', qty=3))
    assert appended.dispatched_at == stamp
    with pytest.raises(ValueError):
        handcraft.send_handcraft_order(db, order.id)
    assert first.dispatched_at == stamp


def test_failed_dispatch_does_not_stamp_sources(db, monkeypatch):
    import services.handcraft as handcraft
    order, _, _, first, _ = seed(db)
    order.status = 'pending'; db.flush()
    monkeypatch.setattr(handcraft, 'batch_get_stock', lambda *args: {'MAT': 0, 'OTHER': 0})
    with pytest.raises(ValueError, match='库存不足'):
        handcraft.send_handcraft_order(db, order.id)
    assert first.dispatched_at is None and order.status == 'pending'


def test_dispatch_schema_compat_is_additive_idempotent_and_never_backfills(db):
    from database import ensure_schema_compat
    from sqlalchemy import inspect, text

    first, *_ = fixture(db)
    source_id, original_qty = first.id, first.qty
    db.commit()
    # Emulate the pre-feature schema ONLY on the disposable pytest engine.
    with db.bind.begin() as conn:
        conn.execute(text('ALTER TABLE handcraft_jewelry_item DROP COLUMN dispatched_at'))
    ensure_schema_compat(db.bind)
    ensure_schema_compat(db.bind)
    columns = {column['name']: column for column in inspect(db.bind).get_columns('handcraft_jewelry_item')}
    assert columns['dispatched_at']['nullable']
    db.expire_all()
    legacy = db.get(HandcraftJewelryItem, source_id)
    assert legacy.dispatched_at is None and legacy.qty == original_qty
