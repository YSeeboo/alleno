from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text

from database import Base
from time_utils import now_beijing


class HandcraftOrder(Base):
    __tablename__ = "handcraft_order"

    id = Column(String, primary_key=True)
    supplier_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=now_beijing)
    completed_at = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)


class HandcraftPartItem(Base):
    __tablename__ = "handcraft_part_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    handcraft_order_id = Column(String, ForeignKey("handcraft_order.id"), nullable=False)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty = Column(Numeric(10, 4), nullable=False)
    bom_qty = Column(Numeric(10, 4), nullable=True)
    unit = Column(String, nullable=True, default="个")
    note = Column(Text, nullable=True)


class HandcraftJewelryItem(Base):
    __tablename__ = "handcraft_jewelry_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    handcraft_order_id = Column(String, ForeignKey("handcraft_order.id"), nullable=False)
    jewelry_id = Column(String, ForeignKey("jewelry.id"), nullable=False)
    qty = Column(Integer, nullable=False)
    received_qty = Column(Integer, nullable=True, default=0)
    status = Column(String, nullable=False, default="未送出")
    unit = Column(String, nullable=True, default="套")
    note = Column(Text, nullable=True)
