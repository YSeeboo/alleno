"""Tests that get_db() commits on success and rolls back on failure.

These tests use client_real_get_db, which overrides get_db() with a generator
that matches the production implementation (commit on success, rollback on
exception). Unlike the `client` fixture, no shared session is injected, so
each HTTP request is an independent transaction.
"""


def test_write_visible_in_next_request(client_real_get_db):
    """Data written in one request must be visible in a subsequent request.

    This proves that get_db() committed after the POST completed.
    If commit() were missing, the GET would return 404.
    """
    resp = client_real_get_db.post("/api/parts/", json={"name": "CommitCheck", "category": "小配件"})
    assert resp.status_code == 201
    part_id = resp.json()["id"]

    # A separate request — new session, no shared state
    resp2 = client_real_get_db.get(f"/api/parts/{part_id}")
    assert resp2.status_code == 200
    assert resp2.json()["name"] == "CommitCheck"


def test_failed_request_does_not_persist(client_real_get_db):
    """A request that raises an error must not leave partial data behind.

    We verify this by attempting an invalid operation and confirming the
    total part count did not increase.
    """
    # Baseline
    baseline = client_real_get_db.get("/api/parts/")
    assert baseline.status_code == 200
    count_before = len(baseline.json())

    # Invalid request — missing required field, Pydantic rejects before DB
    resp = client_real_get_db.post("/api/parts/", json={})
    assert resp.status_code == 422

    after = client_real_get_db.get("/api/parts/")
    assert len(after.json()) == count_before


def test_service_exception_mid_loop_rolls_back_flush(client_real_get_db):
    """Partial DB writes flushed before a service ValueError must be rolled back.

    Scenario:
      - A plating receipt creation lists two items.
      - The first item is valid: add_stock() flushes an InventoryLog row.
      - The second item references a non-existent PlatingOrderItem: ValueError is raised.
      - service_errors() converts it to HTTPException(400).
      - get_db() must call rollback(), undoing the first flush.

    Proof: stock of the first part is queried before and after the failed
    receipt creation; it must not have increased.
    """
    c = client_real_get_db

    # --- setup (each request commits independently) ---
    part1_id = c.post("/api/parts/", json={"name": "RollbackPart1", "category": "小配件"}).json()["id"]
    part2_id = c.post("/api/parts/", json={"name": "RollbackPart2", "category": "链条"}).json()["id"]

    c.post(f"/api/inventory/part/{part1_id}/add", json={"qty": 30.0, "reason": "init"})
    c.post(f"/api/inventory/part/{part2_id}/add", json={"qty": 30.0, "reason": "init"})

    order_id = c.post("/api/plating/", json={
        "supplier_name": "RollbackSupplier",
        "items": [
            {"part_id": part1_id, "qty": 10.0},
            {"part_id": part2_id, "qty": 10.0},
        ],
    }).json()["id"]

    c.post(f"/api/plating/{order_id}/send")

    # stock after send: 30 - 10 = 20 for each part
    stock_before = c.get(f"/api/inventory/part/{part1_id}").json()["current"]
    assert stock_before == 20.0

    # Resolve real item IDs from the committed order
    items = c.get(f"/api/plating/{order_id}/items").json()
    item1_id = next(i["id"] for i in items if i["part_id"] == part1_id)

    # --- the failing receipt creation ---
    # First item is valid (triggers add_stock + flush for part1).
    # Second item references a non-existent PlatingOrderItem — ValueError mid-loop.
    resp = c.post("/api/plating-receipts/", json={
        "vendor_name": "RollbackSupplier",
        "items": [
            {"plating_order_item_id": item1_id, "part_id": part1_id, "qty": 5.0},
            {"plating_order_item_id": 999999, "part_id": part2_id, "qty": 5.0},
        ],
    })
    assert resp.status_code == 400

    # Rollback must have undone the add_stock flush for part1
    stock_after = c.get(f"/api/inventory/part/{part1_id}").json()["current"]
    assert stock_after == stock_before  # unchanged; rollback worked
