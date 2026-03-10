from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text

from database import Base
from time_utils import now_beijing


class PlatingOrder(Base):
    __tablename__ = "plating_order"

    id = Column(String, primary_key=True)
    supplier_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=now_beijing)
    completed_at = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)


class PlatingOrderItem(Base):
    __tablename__ = "plating_order_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plating_order_id = Column(String, ForeignKey("plating_order.id"), nullable=False)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty = Column(Numeric(10, 4), nullable=False)
    received_qty = Column(Numeric(10, 4), nullable=True, default=0)
    status = Column(String, nullable=False, default="未送出")
    plating_method = Column(String, nullable=True)
    note = Column(Text, nullable=True)
