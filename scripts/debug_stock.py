"""Debug: compare get_stock ORM result vs raw SQL for a specific part."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import SessionLocal
from services.inventory import get_stock

part_id = sys.argv[1] if len(sys.argv) > 1 else "PJ-X-00030"

db = SessionLocal()

# 1. ORM get_stock
orm_result = get_stock(db, "part", part_id)
print(f"ORM get_stock: {orm_result}")

# 2. Raw SQL
raw = db.execute(text(
    "SELECT COALESCE(SUM(change_qty),0) FROM inventory_log"
    " WHERE item_type='part' AND item_id=:pid"
), {"pid": part_id}).scalar()
print(f"Raw SQL stock: {raw}")

# 3. Row count
count = db.execute(text(
    "SELECT COUNT(*) FROM inventory_log"
    " WHERE item_type='part' AND item_id=:pid"
), {"pid": part_id}).scalar()
print(f"Row count: {count}")

# 4. Check DATABASE_URL
from config import settings
print(f"DATABASE_URL: {settings.DATABASE_URL[:50]}...")

db.close()
