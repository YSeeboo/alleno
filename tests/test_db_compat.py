from sqlalchemy import inspect, text

from database import ensure_schema_compat


def test_ensure_schema_compat_restores_missing_columns(engine):
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE "vendor_receipt" DROP COLUMN IF EXISTS order_id'))
        conn.execute(text('ALTER TABLE "plating_order" DROP COLUMN IF EXISTS delivery_images'))
        conn.execute(text('ALTER TABLE "handcraft_order" DROP COLUMN IF EXISTS delivery_images'))

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


def test_ensure_schema_compat_upgrades_price_columns_to_seven_decimals(engine):
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE "jewelry" ALTER COLUMN retail_price TYPE NUMERIC(10,2)'))
        conn.execute(text('ALTER TABLE "jewelry" ALTER COLUMN wholesale_price TYPE NUMERIC(10,2)'))
        conn.execute(text('ALTER TABLE "part" ALTER COLUMN unit_cost TYPE NUMERIC(10,2)'))
        conn.execute(text('ALTER TABLE "order" ALTER COLUMN total_amount TYPE NUMERIC(10,2)'))
        conn.execute(text('ALTER TABLE "order_item" ALTER COLUMN unit_price TYPE NUMERIC(10,2)'))
        conn.execute(text('ALTER TABLE "purchase_order" ALTER COLUMN total_amount TYPE NUMERIC(12,2)'))
        conn.execute(text('ALTER TABLE "purchase_order_item" ALTER COLUMN price TYPE NUMERIC(12,2)'))
        conn.execute(text('ALTER TABLE "purchase_order_item" ALTER COLUMN amount TYPE NUMERIC(12,2)'))

    ensure_schema_compat(engine)

    with engine.begin() as conn:
        inspector = inspect(conn)

        def col_type(table_name: str, column_name: str):
            column = next(col for col in inspector.get_columns(table_name) if col["name"] == column_name)
            return column["type"]

        for table, col in [
            ("jewelry", "retail_price"), ("jewelry", "wholesale_price"),
            ("part", "unit_cost"),
            ("order", "total_amount"), ("order_item", "unit_price"),
            ("purchase_order", "total_amount"),
            ("purchase_order_item", "price"), ("purchase_order_item", "amount"),
        ]:
            ct = col_type(table, col)
            assert ct.scale == 7, f"{table}.{col} scale={ct.scale}, expected 7"
            assert ct.precision == 18, f"{table}.{col} precision={ct.precision}, expected 18"


def test_ensure_schema_compat_upgrades_from_numeric_14_7(engine):
    """Columns already at NUMERIC(14,7) should still be upgraded to NUMERIC(18,7)."""
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE "jewelry" ALTER COLUMN retail_price TYPE NUMERIC(14,7)'))

    ensure_schema_compat(engine)

    with engine.begin() as conn:
        inspector = inspect(conn)
        column = next(col for col in inspector.get_columns("jewelry") if col["name"] == "retail_price")
        assert column["type"].precision == 18
        assert column["type"].scale == 7
