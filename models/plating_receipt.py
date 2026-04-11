import json

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from database import Base
from time_utils import now_beijing


class PlatingReceipt(Base):
    __tablename__ = "plating_receipt"

    id = Column(String, primary_key=True)
    vendor_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="未付款")
    total_amount = Column(Numeric(18, 7), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
    paid_at = Column(DateTime, nullable=True)
    delivery_images_raw = Column("delivery_images", Text, nullable=True)

    items = relationship("PlatingReceiptItem", backref="plating_receipt", lazy="select", order_by="PlatingReceiptItem.id")

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


class PlatingReceiptItem(Base):
    __tablename__ = "plating_receipt_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plating_receipt_id = Column(String, ForeignKey("plating_receipt.id"), nullable=False)
    plating_order_item_id = Column(Integer, ForeignKey("plating_order_item.id"), nullable=False)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty = Column(Numeric(10, 4), nullable=False)
    weight = Column(Numeric(10, 4), nullable=True)
    weight_unit = Column(String, nullable=True, default="g")
    unit = Column(String, nullable=True, default="个")
    price = Column(Numeric(18, 7), nullable=True)
    amount = Column(Numeric(18, 7), nullable=True)
    note = Column(Text, nullable=True)
