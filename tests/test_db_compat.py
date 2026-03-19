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
        conn.execute(text("""
            CREATE TABLE handcraft_order (
                id VARCHAR PRIMARY KEY,
                supplier_name VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                created_at DATETIME,
                completed_at DATETIME,
                note TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE handcraft_part_item (
                id INTEGER PRIMARY KEY,
                handcraft_order_id VARCHAR NOT NULL,
                part_id VARCHAR NOT NULL,
                qty FLOAT NOT NULL,
                bom_qty FLOAT,
                unit VARCHAR,
                note TEXT
            )
        """))

    ensure_schema_compat(engine)

    with engine.begin() as conn:
        vendor_columns = {col["name"] for col in inspect(conn).get_columns("vendor_receipt")}
        plating_columns = {col["name"] for col in inspect(conn).get_columns("plating_order")}
        handcraft_columns = {col["name"] for col in inspect(conn).get_columns("handcraft_order")}
        handcraft_part_columns = {col["name"] for col in inspect(conn).get_columns("handcraft_part_item")}

    assert "order_id" in vendor_columns
    assert "delivery_images" in plating_columns
    assert "delivery_images" in handcraft_columns
    assert "color" not in handcraft_part_columns
