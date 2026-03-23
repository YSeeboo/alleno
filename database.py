import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

from config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


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
            for cost_col in ("purchase_cost", "bead_cost", "plating_cost"):
                if cost_col not in columns:
                    conn.execute(text(f"ALTER TABLE part ADD COLUMN {cost_col} NUMERIC(18,7) NULL"))
                    logger.warning("Added missing part.%s column", cost_col)

        if inspector.has_table("plating_order_item"):
            columns = {col["name"] for col in inspector.get_columns("plating_order_item")}
            if "receive_part_id" not in columns:
                conn.execute(text("ALTER TABLE plating_order_item ADD COLUMN receive_part_id VARCHAR NULL REFERENCES part(id)"))
                logger.warning("Added missing plating_order_item.receive_part_id column")

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
