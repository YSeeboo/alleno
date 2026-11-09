from datetime import datetime
from decimal import Decimal
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from openpyxl import load_workbook
from sqlalchemy.orm import sessionmaker

from api.deps import get_current_user
from main import app
from models.part import Part
from models.plating_receipt import PlatingReceipt, PlatingReceiptItem
from models.plating_reconciliation import PlatingReconciliation
from models.user import User
from services.inventory import add_stock, get_stock
from services.part import create_part
from services.plating import create_plating_order, get_plating_items, send_plating_order
from services.plating_receipt import (
    add_plating_receipt_items, create_plating_receipt, update_plating_receipt_item,
    update_plating_receipt_status,
)
from services.plating_reconciliation import DETAIL_HEADERS, list_reconciliation, update_price

URL = "/api/plating-reconciliation"


def receipt(db, *, vendor="Vendor A", price=Decimal("2"), qty=5, date=datetime(2026, 11, 9, 23, 59, 59)):
    part = create_part(db, {"name": "=配件样例", "category": "小配件"})
    add_stock(db, "part", part.id, 100, "初始库存")
    order = create_plating_order(db, vendor, [{"part_id": part.id, "qty": 20, "plating_method": "金色"}])
    send_plating_order(db, order.id)
    poi = get_plating_items(db, order.id)[0]
    r = create_plating_receipt(db, vendor, [{"plating_order_item_id": poi.id, "part_id": part.id, "qty": qty, "price": price, "note": "=1+1"}])
    r.created_at = date
    db.flush()
    item = db.query(PlatingReceiptItem).filter_by(plating_receipt_id=r.id).one()
    return r, item, part, order


def data(client, **params):
    response = client.get(URL + "/", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def change(client, item, price):
    return client.patch(f"{URL}/items/{item.id}", json={"override_price": price})


def test_override_persists_independently_and_clears_to_original(client, db):
    r, item, part, _ = receipt(db)
    _, other, _, _ = receipt(db)
    stock = get_stock(db, "part", part.id)
    cost = db.get(Part, part.id).plating_cost
    assert change(client, item, "0.1234567").status_code == 204
    db.expire_all()
    original = db.get(PlatingReceiptItem, item.id)
    assert original.price == 2 and original.amount == 10
    assert db.get(PlatingReceipt, r.id).total_amount == 10
    assert db.get(Part, part.id).plating_cost == cost
    assert get_stock(db, "part", part.id) == stock
    rows = {row["receipt_item_id"]: row for row in data(client)["items"]}
    assert Decimal(rows[item.id]["amount"]) == Decimal("0.6172835")
    assert rows[other.id]["override_price"] is None
    assert change(client, item, "0").status_code == 204
    zero = next(row for row in data(client)["items"] if row["receipt_item_id"] == item.id)
    assert zero["override_price"] == "0.0000000" and zero["amount"] == "0.0000000"
    assert change(client, item, "0.0000001").status_code == 204
    tiny = next(row for row in data(client)["items"] if row["receipt_item_id"] == item.id)
    assert tiny["override_price"] == "0.0000001"
    assert change(client, item, None).status_code == 204
    assert Decimal(data(client)["totals"]["due"]) == 20
    # A fresh session sees committed persistence, not only ORM identity-map state.
    assert change(client, item, "1.5").status_code == 204
    db.commit()
    with sessionmaker(bind=db.get_bind())() as fresh:
        assert fresh.get(PlatingReconciliation, item.id).override_price == Decimal("1.5")


def test_payment_snapshots_reopen_and_legacy_paid_fallback(client, db):
    r, item, _, _ = receipt(db)
    assert change(client, item, "1.25").status_code == 204
    response = client.patch(f"/api/plating-receipts/{r.id}/status", json={"status": "已付款"})
    assert response.status_code == 200, response.text
    snapshot = db.get(PlatingReconciliation, item.id)
    assert snapshot.settled_amount == Decimal("6.25") and snapshot.settled_at is not None
    assert Decimal(data(client)["totals"]["paid"]) == Decimal("6.25")
    assert change(client, item, "3").status_code == 400
    assert change(client, item, None).status_code == 400
    assert db.get(PlatingReceipt, r.id).total_amount == 10
    assert client.patch(f"/api/plating-receipts/{r.id}/status", json={"status": "未付款"}).status_code == 200
    assert snapshot.settled_at is None and snapshot.settled_amount is None
    assert snapshot.override_price == Decimal("1.25")
    assert change(client, item, "1.5").status_code == 204
    update_plating_receipt_status(db, r.id, "已付款")
    assert snapshot.settled_amount == Decimal("7.5")
    legacy, _, _, _ = receipt(db, price=3)
    legacy.status = "已付款"
    legacy.paid_at = datetime(2026, 12, 1)
    db.flush()
    totals = data(client, date_from="2026-11-01", date_to="2026-11-30")["totals"]
    assert Decimal(totals["paid"]) == Decimal("22.5")  # Not filtered by paid_at.


def test_shared_filters_pagination_and_export_detail_first(client, db):
    r, item, _, _ = receipt(db, vendor="A")
    receipt(db, vendor="B", date=datetime(2026, 11, 10))
    receipt(db, vendor="A", date=datetime(2026, 10, 31, 23, 59, 59))
    _, unknown, _, _ = receipt(db, vendor="A", price=None)
    assert change(client, item, "1.5").status_code == 204
    params = dict(vendor_name="A", date_from="2026-11-01", date_to="2026-11-09", status="未付款")
    result = data(client, limit=1, **params)
    assert result["total"] == 2 and len(result["items"]) == 1
    assert len(result["merchants"]) == 1
    assert result["totals"]["unpriced_count"] == 1
    assert Decimal(result["totals"]["pending"]) == Decimal("7.5")
    export = client.get(URL + "/excel", params=params)
    assert export.status_code == 200, export.text
    wb = load_workbook(BytesIO(export.content), data_only=False)
    assert wb.sheetnames == ["回收明细", "商家汇总"] and wb.active.title == "回收明细"
    ws = wb.active
    assert list(next(ws.values)) == DETAIL_HEADERS
    assert ws.max_row == 3 and ws.max_column == 10  # All filtered rows, not page 1 only.
    priced = next(row for row in list(ws.values)[1:] if row[8] != "待定价")
    assert priced[6:9] == (2, 1.5, 7.5)
    assert ws["B2"].data_type == "s" and ws["J2"].data_type == "s"
    assert wb["商家汇总"]["B2"].value == 7.5
    assert not data(client, vendor_name="missing")["items"]
    assert client.get(URL + "/", params={"date_from": "2026-11-10", "date_to": "2026-11-01"}).status_code == 400
    assert client.get(URL + "/excel", params={"date_from": "2026-11-10", "date_to": "2026-11-01"}).status_code == 400
    assert client.get(URL + "/", params={"status": "bogus"}).status_code == 422


def test_excel_numbers_have_no_trailing_decimal_separator(client, db):
    receipt(db, qty=5, price=Decimal("2"))
    receipt(db, qty=5.25, price=Decimal("2.5"))
    _, zero, _, _ = receipt(db, qty=1, price=Decimal("0"))
    _, tiny, _, _ = receipt(db, qty=1, price=Decimal("0.0000001"))
    assert change(client, zero, "0").status_code == 204
    assert change(client, tiny, "0.0000001").status_code == 204
    response = client.get(URL + "/excel")
    assert response.status_code == 200, response.text
    wb = load_workbook(BytesIO(response.content))
    rows = list(wb["回收明细"].iter_rows(min_row=2))
    integer = next(row for row in rows if row[3].value == 5)
    fractional = next(row for row in rows if row[3].value == 5.25)
    free = next(row for row in rows if row[8].value == 0)
    small = next(row for row in rows if row[7].value == 0.0000001)
    assert integer[3].number_format == integer[6].number_format == integer[8].number_format == "0"
    assert fractional[3].number_format == "0.00"
    assert fractional[6].number_format == "0.0"
    assert fractional[8].value == 13.125 and fractional[8].number_format == "0.000"
    assert free[7].number_format == free[8].number_format == "0"
    assert small[6].number_format == small[7].number_format == small[8].number_format == "0.0000000"
    for row in rows:
        assert row[7].font.color.type == "rgb"
        assert row[7].font.color.rgb == "FFFF0000"  # Includes zero and blank overrides.
        assert row[6].font != row[7].font and row[8].font != row[7].font
        for index in (3, 6, 7, 8):
            if row[index].value is not None:
                assert row[index].data_type == "n"  # Remain usable for Excel calculations.
    assert wb["回收明细"]["H1"].font.color.rgb == "00FFFFFF"
    assert wb["商家汇总"]["B2"].number_format == "0.0000000"
    assert wb["商家汇总"]["C2"].number_format == "0"


def test_excel_weight_matches_detail_without_padding_decimal_places(client, db):
    _, item, _, _ = receipt(db)
    for value, unit, expected in [
        ("0.4500000", "kg", "0.45 kg"),
        ("10.0000000", "g", "10 g"),
        ("12.3400000", "g", "12.34 g"),
        ("0.0000001", "kg", "0.0000001 kg"),
        ("0.0000000", "g", "0 g"),
        ("100.0000000", None, "100 g"),
        (None, "kg", None),
    ]:
        item.weight = Decimal(value) if value is not None else None
        item.weight_unit = unit
        db.flush()
        response = client.get(URL + "/excel")
        assert response.status_code == 200, response.text
        wb = load_workbook(BytesIO(response.content))
        assert wb["回收明细"]["F2"].value == expected


def test_unpriced_is_not_free_and_can_be_priced_only_in_reconciliation(client, db):
    r, item, _, _ = receipt(db, price=None)
    result = data(client)
    assert result["items"][0]["amount"] is None and result["totals"]["unpriced_count"] == 1
    assert change(client, item, "0").status_code == 204
    assert data(client)["totals"]["unpriced_count"] == 0
    update_plating_receipt_status(db, r.id, "已付款")
    assert db.get(PlatingReconciliation, item.id).settled_amount == 0
    assert data(client)["items"][0]["price"] is None
    # Existing original payment behavior remains available for unpriced receipts;
    # its frozen unknown amount must still be identified, not counted as free.
    unpriced, _, _, _ = receipt(db, price=None)
    update_plating_receipt_status(db, unpriced.id, "已付款")
    assert data(client, status="已付款")["totals"]["unpriced_count"] == 1


def test_validation_archives_and_lifecycle_cleanup(client, db):
    r, item, _, order = receipt(db)
    for price in ["-1", "1.12345678", "NaN", "Infinity", "100000000000"]:
        assert change(client, item, price).status_code == 422, price
    assert client.patch(f"{URL}/items/{item.id}", json={}).status_code == 422
    order.archived_at = datetime(2026, 11, 9)
    db.flush()
    assert change(client, item, "1").status_code == 400
    assert data(client)["items"][0]["archived"] is True
    order.archived_at = None
    db.flush()
    assert change(client, item, "1").status_code == 204
    assert client.delete(f"/api/plating-receipts/{r.id}").status_code == 204
    db.expire_all()
    assert db.get(PlatingReconciliation, item.id) is None


def test_permission_is_inherited_by_list_export_and_price(client, db):
    _, item, _, _ = receipt(db)
    app.dependency_overrides[get_current_user] = lambda: User(id=9, username="no-plating", permissions=[], is_admin=False, is_active=True)
    for method, path, body in [("get", URL + "/", None), ("get", URL + "/excel", None), ("patch", f"{URL}/items/{item.id}", {"override_price": "1"})]:
        response = client.request(method, path, json=body)
        assert response.status_code == 403, response.text


def test_whole_receipt_locks_all_rows_and_item_delete_cascades(client, db):
    r, first, part, order = receipt(db)
    # A second source order, same merchant/receipt, with its own independent price.
    other_order = create_plating_order(db, r.vendor_name, [{"part_id": part.id, "qty": 10, "plating_method": "银色"}])
    send_plating_order(db, other_order.id)
    poi = get_plating_items(db, other_order.id)[0]
    add_plating_receipt_items(db, r.id, [{"plating_order_item_id": poi.id, "part_id": part.id, "qty": 3, "price": 4}])
    second = db.query(PlatingReceiptItem).filter_by(plating_receipt_id=r.id, plating_order_item_id=poi.id).one()
    assert change(client, first, "1").status_code == 204
    assert change(client, second, "2").status_code == 204
    update_plating_receipt_status(db, r.id, "已付款")
    assert Decimal(data(client)["totals"]["paid"]) == 11
    assert change(client, second, "3").status_code == 400
    assert client.put(f"/api/plating-receipts/{r.id}/items/{first.id}", json={"qty": 6}).status_code == 400
    update_plating_receipt_status(db, r.id, "未付款")
    assert client.delete(f"/api/plating-receipts/{r.id}/items/{second.id}").status_code == 204
    db.expire_all()
    assert db.get(PlatingReconciliation, second.id) is None
    assert Decimal(data(client)["totals"]["due"]) == 5
    assert client.put(f"/api/plating-receipts/{r.id}/items/{first.id}", json={"qty": 6, "price": 3}).status_code == 200
    assert Decimal(data(client)["items"][0]["amount"]) == 6  # Override follows this row's actual quantity.
    assert change(client, first, None).status_code == 204
    assert Decimal(data(client)["items"][0]["amount"]) == 18


def test_payment_waits_for_price_transaction_and_freezes_committed_override(db):
    r, item, _, _ = receipt(db)
    receipt_id, item_id = r.id, item.id
    db.commit()
    Session = sessionmaker(bind=db.get_bind())
    started = Event()
    finished = Event()

    def pay():
        with Session() as payer:
            started.set()
            update_plating_receipt_status(payer, receipt_id, "已付款")
            payer.commit()
            finished.set()

    with Session() as editor, ThreadPoolExecutor(max_workers=1) as pool:
        update_price(editor, item_id, Decimal("1.25"))  # Holds parent row lock.
        future = pool.submit(pay)
        try:
            assert started.wait(5)
            assert not finished.wait(0.2), "Payment must not bypass an in-flight price write"
        finally:
            editor.commit()
        future.result(timeout=10)
    with Session() as fresh:
        assert fresh.get(PlatingReconciliation, item_id).settled_amount == Decimal("6.25")
        assert fresh.get(PlatingReceipt, receipt_id).status == "已付款"


def test_real_request_commit_and_invalid_price_rollback(client_real_get_db, engine):
    Session = sessionmaker(bind=engine)
    with Session() as setup:
        r, item, _, _ = receipt(setup)
        receipt_id, item_id = r.id, item.id
        setup.commit()
    client = client_real_get_db
    path = f"{URL}/items/{item_id}"
    assert client.patch(path, json={"override_price": "1.1234567"}).status_code == 204
    assert client.patch(path, json={"override_price": "99999999999.9999999"}).status_code == 400
    with Session() as fresh:
        assert fresh.get(PlatingReconciliation, item_id).override_price == Decimal("1.1234567")
    assert client.patch(f"/api/plating-receipts/{receipt_id}/status", json={"status": "已付款"}).status_code == 200
    with Session() as fresh:
        assert fresh.get(PlatingReconciliation, item_id).settled_amount == Decimal("5.6172835")
    assert client.patch(path, json={"override_price": "2"}).status_code == 400


def test_payment_refreshes_values_loaded_before_parent_lock(db):
    r, item, _, _ = receipt(db)
    update_price(db, item.id, Decimal("1"))
    receipt_id, item_id = r.id, item.id
    db.commit()
    Session = sessionmaker(bind=db.get_bind())
    with Session() as payer, Session() as editor:
        cached_item = payer.get(PlatingReceiptItem, item_id)
        cached_price = payer.get(PlatingReconciliation, item_id)
        assert cached_item.qty == 5 and cached_price.override_price == 1
        update_price(editor, item_id, Decimal("1.5"))
        update_plating_receipt_item(editor, receipt_id, item_id, {"qty": 6})
        editor.commit()
        update_plating_receipt_status(payer, receipt_id, "已付款")
        payer.commit()
        assert cached_price.settled_amount == Decimal("9")
