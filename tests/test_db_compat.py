from sqlalchemy import create_engine, inspect, text

from database import ensure_schema_compat


def test_ensure_schema_compat_adds_vendor_receipt_order_id():
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE vendor_receipt (
                id INTEGER PRIMARY KEY,
                vendor_name VARCHAR NOT NULL,
                order_type VARCHAR NOT NULL,
                item_type VARCHAR NOT NULL,
                item_id VARCHAR NOT NULL,
                qty FLOAT NOT NULL,
                note VARCHAR,
                created_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE plating_order (
                id VARCHAR PRIMARY KEY,
                supplier_name VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                created_at DATETIME,
                completed_at DATETIME,
                note TEXT
            )
        """))

    ensure_schema_compat(engine)

    with engine.begin() as conn:
        vendor_columns = {col["name"] for col in inspect(conn).get_columns("vendor_receipt")}
        plating_columns = {col["name"] for col in inspect(conn).get_columns("plating_order")}

    assert "order_id" in vendor_columns
    assert "delivery_images" in plating_columns
