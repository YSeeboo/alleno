import json

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from database import Base
from time_utils import now_beijing


class PurchaseOrder(Base):
    __tablename__ = "purchase_order"

    id = Column(String, primary_key=True)
    vendor_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="未付款")
    total_amount = Column(Numeric(12, 3), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
    paid_at = Column(DateTime, nullable=True)
    delivery_images_raw = Column("delivery_images", Text, nullable=True)

    items = relationship("PurchaseOrderItem", backref="purchase_order", lazy="select")

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


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_order_id = Column(String, ForeignKey("purchase_order.id"), nullable=False)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty = Column(Numeric(10, 4), nullable=False)
    unit = Column(String, nullable=True, default="个")
    price = Column(Numeric(12, 3), nullable=True)
    amount = Column(Numeric(12, 3), nullable=True)
    note = Column(Text, nullable=True)
