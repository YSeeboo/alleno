import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

from config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def _ensure_indexes(conn, inspector):
    """Create missing indexes defined in model metadata."""
    import models  # noqa: F401 — ensure all models are loaded
    for table in Base.metadata.tables.values():
        if not inspector.has_table(table.name):
            continue
        existing = {idx["name"] for idx in inspector.get_indexes(table.name)}
        for idx in table.indexes:
            if idx.name not in existing:
                cols = ", ".join(c.name for c in idx.columns)
                conn.execute(text(
                    f'CREATE INDEX IF NOT EXISTS "{idx.name}" ON "{table.name}" ({cols})'
                ))
                logger.warning("Created missing index %s on %s", idx.name, table.name)


def ensure_schema_compat(target_engine=None):
    target_engine = target_engine or engine
    with target_engine.begin() as conn:
        inspector = inspect(conn)

        if inspector.has_table("vendor_receipt"):
            columns = {col["name"] for col in inspector.get_columns("vendor_receipt")}
            if "order_id" not in columns:
                conn.execute(text("ALTER TABLE vendor_receipt ADD COLUMN order_id VARCHAR NULL"))
                logger.warning("Added missing vendor_receipt.order_id column")

        if inspector.has_table("plating_order"):
            columns = {col["name"] for col in inspector.get_columns("plating_order")}
            if "delivery_images" not in columns:
                conn.execute(text("ALTER TABLE plating_order ADD COLUMN delivery_images TEXT NULL"))
                logger.warning("Added missing plating_order.delivery_images column")

        if inspector.has_table("handcraft_order"):
            columns = {col["name"] for col in inspector.get_columns("handcraft_order")}
            if "delivery_images" not in columns:
                conn.execute(text("ALTER TABLE handcraft_order ADD COLUMN delivery_images TEXT NULL"))
                logger.warning("Added missing handcraft_order.delivery_images column")

        if inspector.has_table("part"):
            columns = {col["name"] for col in inspector.get_columns("part")}
            if "parent_part_id" not in columns:
                conn.execute(text("ALTER TABLE part ADD COLUMN parent_part_id VARCHAR NULL REFERENCES part(id)"))
                logger.warning("Added missing part.parent_part_id column")
            if "spec" not in columns:
                conn.execute(text("ALTER TABLE part ADD COLUMN spec VARCHAR NULL"))
                logger.warning("Added missing part.spec column")
            for cost_col in ("purchase_cost", "bead_cost", "plating_cost", "assembly_cost"):
                if cost_col not in columns:
                    conn.execute(text(f"ALTER TABLE part ADD COLUMN {cost_col} NUMERIC(18,7) NULL"))
                    logger.warning("Added missing part.%s column", cost_col)

        if inspector.has_table("plating_order_item"):
            columns = {col["name"] for col in inspector.get_columns("plating_order_item")}
            if "receive_part_id" not in columns:
                conn.execute(text("ALTER TABLE plating_order_item ADD COLUMN receive_part_id VARCHAR NULL REFERENCES part(id)"))
                logger.warning("Added missing plating_order_item.receive_part_id column")

        # Upgrade qty columns from Numeric(10,4) to Numeric(18,4)
        _qty_columns = [
            ("inventory_log", "change_qty", "NUMERIC(18,4)"),
        ]
        for table, col, new_type in _qty_columns:
            if not inspector.has_table(table):
                continue
            for c in inspector.get_columns(table):
                if c["name"] != col:
                    continue
                ct = c["type"]
                needs_upgrade = (
                    hasattr(ct, "precision") and ct.precision is not None
                    and ct.precision < 18
                )
                if needs_upgrade:
                    conn.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN {col} TYPE {new_type}'))
                    logger.warning("Upgraded %s.%s to %s", table, col, new_type)
                break

        # Upgrade price/amount columns to Numeric(18,7)
        _price_columns = [
            ("jewelry", "retail_price", "NUMERIC(18,7)"),
            ("jewelry", "wholesale_price", "NUMERIC(18,7)"),
            ("part", "unit_cost", "NUMERIC(18,7)"),
            ("order", "total_amount", "NUMERIC(18,7)"),
            ("order_item", "unit_price", "NUMERIC(18,7)"),
            ("purchase_order", "total_amount", "NUMERIC(18,7)"),
            ("purchase_order_item", "price", "NUMERIC(18,7)"),
            ("purchase_order_item", "amount", "NUMERIC(18,7)"),
            ("plating_receipt", "total_amount", "NUMERIC(18,7)"),
            ("plating_receipt_item", "price", "NUMERIC(18,7)"),
            ("plating_receipt_item", "amount", "NUMERIC(18,7)"),
        ]
        for table, col, new_type in _price_columns:
            if not inspector.has_table(table):
                continue
            for c in inspector.get_columns(table):
                if c["name"] != col:
                    continue
                ct = c["type"]
                needs_upgrade = (
                    hasattr(ct, "scale") and hasattr(ct, "precision")
                    and (ct.scale < 7 or ct.precision < 18)
                )
                if needs_upgrade:
                    conn.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN {col} TYPE {new_type}'))
                    logger.warning("Upgraded %s.%s to %s", table, col, new_type)
                break

        # HandcraftPartItem: add received_qty and status columns + data migration
        if inspector.has_table("handcraft_part_item"):
            columns = {col["name"] for col in inspector.get_columns("handcraft_part_item")}
            if "received_qty" not in columns:
                conn.execute(text("ALTER TABLE handcraft_part_item ADD COLUMN received_qty NUMERIC(10,4) DEFAULT 0"))
                logger.warning("Added missing handcraft_part_item.received_qty column")
            if "status" not in columns:
                conn.execute(text("ALTER TABLE handcraft_part_item ADD COLUMN status VARCHAR NOT NULL DEFAULT '未送出'"))
                logger.warning("Added missing handcraft_part_item.status column")
                # Data migration: fix status for existing rows
                conn.execute(text(
                    "UPDATE handcraft_part_item SET status = '制作中' "
                    "WHERE handcraft_order_id IN (SELECT id FROM handcraft_order WHERE status = 'processing')"
                ))
                conn.execute(text(
                    "UPDATE handcraft_part_item SET status = '已收回' "
                    "WHERE handcraft_order_id IN (SELECT id FROM handcraft_order WHERE status = 'completed')"
                ))

        # Migrate historical supplier/vendor names into supplier table
        if inspector.has_table("supplier"):
            _supplier_migrations = [
                ("plating_order", "supplier_name", "plating"),
                ("handcraft_order", "supplier_name", "handcraft"),
                ("purchase_order", "vendor_name", "parts"),
                ("plating_receipt", "vendor_name", "plating"),
                ("handcraft_receipt", "supplier_name", "handcraft"),
            ]
            for table, col, stype in _supplier_migrations:
                if inspector.has_table(table):
                    conn.execute(text(
                        f'INSERT INTO supplier (name, type, created_at) '
                        f'SELECT DISTINCT TRIM({col}), :stype, now() FROM "{table}" '
                        f'WHERE {col} IS NOT NULL AND TRIM({col}) != \'\' '
                        f'ON CONFLICT (name, type) DO NOTHING'
                    ), {"stype": stype})
            # Backfill NULL created_at for rows from earlier migration runs
            conn.execute(text(
                "UPDATE supplier SET created_at = now() WHERE created_at IS NULL"
            ))

        if inspector.has_table("jewelry"):
            columns = {col["name"] for col in inspector.get_columns("jewelry")}
            if "handcraft_cost" not in columns:
                conn.execute(text("ALTER TABLE jewelry ADD COLUMN handcraft_cost NUMERIC(18,7) NULL"))
                logger.warning("Added missing jewelry.handcraft_cost column")

        if inspector.has_table("order"):
            columns = {col["name"] for col in inspector.get_columns("order")}
            if "packaging_cost" not in columns:
                conn.execute(text('ALTER TABLE "order" ADD COLUMN packaging_cost NUMERIC(18,7) NULL'))
                logger.warning("Added missing order.packaging_cost column")

        # --- order extra info fields ---
        if inspector.has_table("order"):
            cols = [c["name"] for c in inspector.get_columns("order")]
            for col_name, col_type in [
                ("barcode_text", "TEXT"),
                ("barcode_image", "VARCHAR"),
                ("mark_text", "TEXT"),
                ("mark_image", "VARCHAR"),
                ("note", "TEXT"),
            ]:
                if col_name not in cols:
                    conn.execute(text(
                        f'ALTER TABLE "order" ADD COLUMN {col_name} {col_type}'
                    ))
                    logger.warning("Added missing order.%s column", col_name)

        # --- order_item.customer_code ---
        if inspector.has_table("order_item"):
            cols = [c["name"] for c in inspector.get_columns("order_item")]
            if "customer_code" not in cols:
                conn.execute(text(
                    "ALTER TABLE order_item ADD COLUMN customer_code VARCHAR"
                ))
                logger.warning("Added missing order_item.customer_code column")

        if inspector.has_table("order_item_link"):
            columns = {col["name"] for col in inspector.get_columns("order_item_link")}
            if "purchase_order_item_id" not in columns:
                conn.execute(text(
                    "ALTER TABLE order_item_link ADD COLUMN purchase_order_item_id INTEGER NULL "
                    "REFERENCES purchase_order_item(id) UNIQUE"
                ))
                logger.warning("Added missing order_item_link.purchase_order_item_id column")

        # --- order_todo_item.batch_id ---
        if inspector.has_table("order_todo_item"):
            columns = {col["name"] for col in inspector.get_columns("order_todo_item")}
            if "batch_id" not in columns:
                conn.execute(text(
                    "ALTER TABLE order_todo_item ADD COLUMN batch_id INTEGER"
                ))
                logger.warning("Added missing order_todo_item.batch_id column")

        # --- order_todo_batch_jewelry.handcraft_jewelry_item_id ---
        if inspector.has_table("order_todo_batch_jewelry"):
            columns = {col["name"] for col in inspector.get_columns("order_todo_batch_jewelry")}
            if "handcraft_jewelry_item_id" not in columns:
                conn.execute(text(
                    "ALTER TABLE order_todo_batch_jewelry ADD COLUMN handcraft_jewelry_item_id INTEGER"
                ))
                logger.warning("Added missing order_todo_batch_jewelry.handcraft_jewelry_item_id column")
                # Backfill for existing linked batches: pair by jewelry_id + row order
                # Uses row_number() to handle duplicate jewelry_ids within the same batch
                result = conn.execute(text(
                    """
                    UPDATE order_todo_batch_jewelry bj
                    SET handcraft_jewelry_item_id = matched.hji_id
                    FROM (
                        SELECT bj_ranked.bj_id, hji_ranked.hji_id
                        FROM (
                            SELECT bj.id AS bj_id, bj.jewelry_id, b.handcraft_order_id,
                                   ROW_NUMBER() OVER (PARTITION BY bj.batch_id, bj.jewelry_id ORDER BY bj.id) AS rn
                            FROM order_todo_batch_jewelry bj
                            JOIN order_todo_batch b ON b.id = bj.batch_id
                            WHERE b.handcraft_order_id IS NOT NULL
                              AND bj.handcraft_jewelry_item_id IS NULL
                        ) bj_ranked
                        JOIN (
                            SELECT hji.id AS hji_id, hji.jewelry_id, hji.handcraft_order_id,
                                   ROW_NUMBER() OVER (PARTITION BY hji.handcraft_order_id, hji.jewelry_id ORDER BY hji.id) AS rn
                            FROM handcraft_jewelry_item hji
                        ) hji_ranked
                        ON bj_ranked.handcraft_order_id = hji_ranked.handcraft_order_id
                           AND bj_ranked.jewelry_id = hji_ranked.jewelry_id
                           AND bj_ranked.rn = hji_ranked.rn
                    ) matched
                    WHERE bj.id = matched.bj_id
                    """
                ))
                if result.rowcount:
                    logger.warning("Backfilled %d order_todo_batch_jewelry.handcraft_jewelry_item_id rows", result.rowcount)

        # --- handcraft_jewelry_item.part_id ---
        if inspector.has_table("handcraft_jewelry_item"):
            cols = [c["name"] for c in inspector.get_columns("handcraft_jewelry_item")]
            if "part_id" not in cols:
                conn.execute(text(
                    "ALTER TABLE handcraft_jewelry_item ADD COLUMN part_id VARCHAR REFERENCES part(id)"
                ))
                logger.warning("Added missing handcraft_jewelry_item.part_id column")
            # Make jewelry_id nullable (for part output items)
            conn.execute(text(
                "ALTER TABLE handcraft_jewelry_item ALTER COLUMN jewelry_id DROP NOT NULL"
            ))

        # Trim whitespace from supplier/vendor name columns
        _name_columns = [
            ("plating_order", "supplier_name"),
            ("handcraft_order", "supplier_name"),
            ("plating_receipt", "vendor_name"),
            ("purchase_order", "vendor_name"),
            ("handcraft_receipt", "supplier_name"),
        ]
        for table, col in _name_columns:
            if inspector.has_table(table):
                result = conn.execute(text(
                    f'UPDATE "{table}" SET {col} = TRIM({col}) '
                    f'WHERE {col} != TRIM({col})'
                ))
                if result.rowcount:
                    logger.warning("Trimmed %d rows in %s.%s", result.rowcount, table, col)

        _ensure_indexes(conn, inspector)


def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
