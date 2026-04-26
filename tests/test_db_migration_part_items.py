"""Verify ensure_schema_compat() adds part.wholesale_price, order_item.part_id,
makes order_item.jewelry_id nullable, and adds the XOR CHECK constraint."""
from sqlalchemy import inspect, text


def test_part_has_wholesale_price_column(engine):
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("part")}
    assert "wholesale_price" in cols


def test_order_item_has_part_id_column(engine):
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("order_item")}
    assert "part_id" in cols


def test_order_item_jewelry_id_is_nullable(engine):
    insp = inspect(engine)
    cols = {c["name"]: c for c in insp.get_columns("order_item")}
    assert cols["jewelry_id"]["nullable"] is True


def test_xor_check_constraint_rejects_both_null(engine):
    from sqlalchemy.exc import IntegrityError
    with engine.begin() as conn:
        conn.execute(text(
            'INSERT INTO "order" (id, customer_name, status) '
            "VALUES ('OR-CK1', 'check-test', '待生产')"
        ))
        try:
            conn.execute(text(
                "INSERT INTO order_item (order_id, jewelry_id, part_id, quantity, unit_price) "
                "VALUES ('OR-CK1', NULL, NULL, 1, 0)"
            ))
            assert False, "expected IntegrityError"
        except IntegrityError:
            pass


def test_xor_check_constraint_rejects_both_set(engine):
    from sqlalchemy.exc import IntegrityError
    with engine.begin() as conn:
        conn.execute(text(
            'INSERT INTO "order" (id, customer_name, status) '
            "VALUES ('OR-CK2', 'check-test', '待生产')"
        ))
        conn.execute(text(
            "INSERT INTO jewelry (id, name, status) VALUES ('SP-CK', 'j', 'active')"
        ))
        conn.execute(text(
            "INSERT INTO part (id, name) VALUES ('PJ-CK', 'p')"
        ))
        try:
            conn.execute(text(
                "INSERT INTO order_item (order_id, jewelry_id, part_id, quantity, unit_price) "
                "VALUES ('OR-CK2', 'SP-CK', 'PJ-CK', 1, 0)"
            ))
            assert False, "expected IntegrityError"
        except IntegrityError:
            pass
