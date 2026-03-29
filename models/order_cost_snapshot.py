import json

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from database import Base
from time_utils import now_beijing


class OrderCostSnapshot(Base):
    __tablename__ = "order_cost_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("order.id"), nullable=False)
    total_cost = Column(Numeric(18, 7), nullable=False)
    packaging_cost = Column(Numeric(18, 7), nullable=True)
    total_amount = Column(Numeric(18, 7), nullable=True)
    profit = Column(Numeric(18, 7), nullable=True)
    has_incomplete_cost = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=now_beijing)

    items = relationship("OrderCostSnapshotItem", backref="snapshot",
                         lazy="select", order_by="OrderCostSnapshotItem.id")


class OrderCostSnapshotItem(Base):
    __tablename__ = "order_cost_snapshot_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(Integer, ForeignKey("order_cost_snapshot.id"), nullable=False)
    jewelry_id = Column(String, nullable=False)
    jewelry_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(18, 7), nullable=True)
    handcraft_cost = Column(Numeric(18, 7), nullable=True)
    jewelry_unit_cost = Column(Numeric(18, 7), nullable=False)
    jewelry_total_cost = Column(Numeric(18, 7), nullable=False)
    bom_details_raw = Column("bom_details", Text, nullable=True)

    @property
    def bom_details(self):
        if not self.bom_details_raw:
            return []
        try:
            return json.loads(self.bom_details_raw)
        except (TypeError, ValueError):
            return []

    @bom_details.setter
    def bom_details(self, value):
        self.bom_details_raw = json.dumps(value, ensure_ascii=False) if value else None
