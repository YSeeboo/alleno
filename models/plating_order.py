import json

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
    delivery_images_raw = Column("delivery_images", Text, nullable=True)

    @property
    def delivery_images(self):
        if not self.delivery_images_raw:
            return []
        try:
            value = json.loads(self.delivery_images_raw)
        except (TypeError, ValueError):
            return []
        return value if isinstance(value, list) else []

    @delivery_images.setter
    def delivery_images(self, value):
        cleaned = [str(item).strip() for item in (value or []) if str(item).strip()]
        self.delivery_images_raw = json.dumps(cleaned, ensure_ascii=True) if cleaned else None


class PlatingOrderItem(Base):
    __tablename__ = "plating_order_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plating_order_id = Column(String, ForeignKey("plating_order.id"), nullable=False, index=True)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty = Column(Numeric(10, 4), nullable=False)
    weight = Column(Numeric(10, 4), nullable=True)
    weight_unit = Column(String, nullable=True, default="g")
    received_qty = Column(Numeric(10, 4), nullable=True, default=0)
    status = Column(String, nullable=False, default="未送出")
    plating_method = Column(String, nullable=True)
    unit = Column(String, nullable=True, default="个")
    note = Column(Text, nullable=True)
    receive_part_id = Column(String, ForeignKey("part.id"), nullable=True)
