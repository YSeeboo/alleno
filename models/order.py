from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text

from database import Base
from time_utils import now_beijing


class Order(Base):
    __tablename__ = "order"

    id = Column(String, primary_key=True)
    customer_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="待生产")
    total_amount = Column(Numeric(18, 7), nullable=True)
    packaging_cost = Column(Numeric(18, 7), nullable=True)
    barcode_text = Column(Text, nullable=True)
    barcode_image = Column(String, nullable=True)
    mark_text = Column(Text, nullable=True)
    mark_image = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing)


class OrderItem(Base):
    __tablename__ = "order_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("order.id"), nullable=False, index=True)
    jewelry_id = Column(String, ForeignKey("jewelry.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(18, 7), nullable=False)
    remarks = Column(Text, nullable=True)
    customer_code = Column(String, nullable=True)


class OrderTodoItem(Base):
    __tablename__ = "order_todo_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("order.id"), nullable=False, index=True)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    required_qty = Column(Numeric(10, 4), nullable=False)
    batch_id = Column(Integer, ForeignKey("order_todo_batch.id"), nullable=True)


class OrderTodoBatch(Base):
    __tablename__ = "order_todo_batch"
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("order.id"), nullable=False, index=True)
    handcraft_order_id = Column(String, ForeignKey("handcraft_order.id"), nullable=True)
    created_at = Column(DateTime, default=now_beijing)


class OrderTodoBatchJewelry(Base):
    __tablename__ = "order_todo_batch_jewelry"
    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("order_todo_batch.id"), nullable=False)
    jewelry_id = Column(String, ForeignKey("jewelry.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    handcraft_jewelry_item_id = Column(Integer, ForeignKey("handcraft_jewelry_item.id"), nullable=True)


class OrderItemLink(Base):
    __tablename__ = "order_item_link"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 配件项关联 TodoList 行
    order_todo_item_id = Column(Integer, ForeignKey("order_todo_item.id"), nullable=True, index=True)
    # 饰品项直接关联订单
    order_id = Column(String, ForeignKey("order.id"), nullable=True)
    # 四选一：关联的生产项（unique 保证同一生产项只能关联一个订单）
    plating_order_item_id = Column(Integer, ForeignKey("plating_order_item.id"), nullable=True, unique=True)
    handcraft_part_item_id = Column(Integer, ForeignKey("handcraft_part_item.id"), nullable=True, unique=True)
    handcraft_jewelry_item_id = Column(Integer, ForeignKey("handcraft_jewelry_item.id"), nullable=True, unique=True)
    purchase_order_item_id = Column(Integer, ForeignKey("purchase_order_item.id"), nullable=True, unique=True)
