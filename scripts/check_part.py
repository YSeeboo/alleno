from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

sql = (
    "SELECT id, name, parent_part_id"
    " FROM part"
    " WHERE id='PJ-X-00030'"
)
r = db.execute(text(sql)).fetchone()
if r:
    print(f"配件: {r[0]} {r[1]} parent={r[2]}")
else:
    print("PJ-X-00030 不存在！")

sql = (
    "SELECT id, change_qty, reason, created_at"
    " FROM inventory_log"
    " WHERE item_type='part' AND item_id='PJ-X-00030'"
    " ORDER BY id DESC LIMIT 10"
)
logs = db.execute(text(sql)).fetchall()
print(f"库存记录数: {len(logs)}")
for l in logs:
    print(f"  {l[3]} qty={l[1]} reason={l[2]}")

sql = (
    "SELECT COALESCE(SUM(change_qty),0)"
    " FROM inventory_log"
    " WHERE item_type='part' AND item_id='PJ-X-00030'"
)
stock = db.execute(text(sql)).scalar()
print(f"当前库存合计: {stock}")
