"""
End-to-end verification script for Allen Shop service layer.
Run from project root:  python scripts/verify_services.py
Creates verify_test.db (deleted at end).
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./verify_test.db")

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from database import Base

DB_PATH = "verify_test.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

from services.part import create_part
from services.jewelry import create_jewelry
from services.bom import set_bom
from services.inventory import add_stock, get_stock
from services.order import create_order, get_parts_summary
from services.plating import create_plating_order, send_plating_order, receive_plating_items, get_plating_order
from services.handcraft import create_handcraft_order, send_handcraft_order, receive_handcraft_jewelries, get_handcraft_order

print("=" * 60)
print("Flow 1: 创建配件 → 入库 → 查库存")
p1 = create_part(db, {"name": "铜扣", "category": "扣件"})
p2 = create_part(db, {"name": "银链", "category": "链条"})
add_stock(db, "part", p1.id, 500.0, "初始入库")
add_stock(db, "part", p2.id, 300.0, "初始入库")
stock_p1 = get_stock(db, "part", p1.id)
assert stock_p1 == 500.0, f"Expected 500, got {stock_p1}"
print(f"  ✓ {p1.id} 库存 = {stock_p1}")

print("=" * 60)
print("Flow 2: 创建饰品 → 设置 BOM → 创建订单 → 查配件汇总")
j1 = create_jewelry(db, {"name": "玫瑰戒指", "category": "戒指"})
j2 = create_jewelry(db, {"name": "银耳环", "category": "耳环"})
set_bom(db, j1.id, p1.id, 2.0)
set_bom(db, j1.id, p2.id, 1.0)
set_bom(db, j2.id, p1.id, 1.0)
# Order: 3 j1 + 2 j2
order = create_order(db, "张三", [
    {"jewelry_id": j1.id, "quantity": 3, "unit_price": 100.0},
    {"jewelry_id": j2.id, "quantity": 2, "unit_price": 50.0},
])
summary = get_parts_summary(db, order.id)
# p1: 3*2 + 2*1 = 8; p2: 3*1 = 3
assert summary[p1.id] == 8.0, f"p1 expected 8, got {summary[p1.id]}"
assert summary[p2.id] == 3.0, f"p2 expected 3, got {summary[p2.id]}"
print(f"  ✓ {order.id} 配件汇总: {p1.id}={summary[p1.id]}, {p2.id}={summary[p2.id]}")

print("=" * 60)
print("Flow 3: 电镀单 → 发出 → 分两次收回 → status=completed")
plating = create_plating_order(db, "金牌电镀厂", [
    {"part_id": p1.id, "qty": 100, "plating_method": "金色"},
])
send_plating_order(db, plating.id)
assert get_stock(db, "part", p1.id) == 400.0  # 500 - 100
from models.plating_order import PlatingOrderItem
pi = db.query(PlatingOrderItem).filter(PlatingOrderItem.plating_order_id == plating.id).first()
receive_plating_items(db, plating.id, [{"plating_order_item_id": pi.id, "qty": 60}])
assert get_plating_order(db, plating.id).status == "processing"
receive_plating_items(db, plating.id, [{"plating_order_item_id": pi.id, "qty": 40}])
db.refresh(pi)
final_plating = get_plating_order(db, plating.id)
assert final_plating.status == "completed", f"Expected completed, got {final_plating.status}"
assert final_plating.completed_at is not None
assert get_stock(db, "part", p1.id) == 500.0  # fully returned
print(f"  ✓ {plating.id} 最终 status = {final_plating.status}")

print("=" * 60)
print("Flow 4: 手工单 → 发出 → 分两次收回饰品 → status=completed")
handcraft = create_handcraft_order(
    db, "手工坊",
    parts=[{"part_id": p2.id, "qty": 50, "bom_qty": 48.0}],
    jewelries=[{"jewelry_id": j1.id, "qty": 20}],
)
send_handcraft_order(db, handcraft.id)
assert get_stock(db, "part", p2.id) == 250.0  # 300 - 50
from models.handcraft_order import HandcraftJewelryItem
hji = db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.handcraft_order_id == handcraft.id).first()
receive_handcraft_jewelries(db, handcraft.id, [{"handcraft_jewelry_item_id": hji.id, "qty": 12}])
assert get_handcraft_order(db, handcraft.id).status == "processing"
receive_handcraft_jewelries(db, handcraft.id, [{"handcraft_jewelry_item_id": hji.id, "qty": 8}])
db.refresh(hji)
final_hc = get_handcraft_order(db, handcraft.id)
assert final_hc.status == "completed", f"Expected completed, got {final_hc.status}"
assert get_stock(db, "jewelry", j1.id) == 20.0
print(f"  ✓ {handcraft.id} 最终 status = {final_hc.status}")

db.commit()
db.close()
os.remove(DB_PATH)
print("=" * 60)
print("✓ All verification flows passed!")
