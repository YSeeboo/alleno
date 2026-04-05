from sqlalchemy import Column, Integer, String, Numeric, Text, DateTime
from database import Base
from time_utils import now_beijing


class ProductionLoss(Base):
    __tablename__ = "production_loss"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_type = Column(String, nullable=False)          # "plating" or "handcraft"
    order_id = Column(String, nullable=False)             # EP-xxx or HC-xxx
    item_id = Column(Integer, nullable=False)             # PlatingOrderItem.id etc.
    item_type = Column(String, nullable=False)            # "plating_item", "handcraft_part", "handcraft_jewelry"
    part_id = Column(String, nullable=True)               # for part losses
    jewelry_id = Column(String, nullable=True)            # for jewelry losses
    loss_qty = Column(Numeric(10, 4), nullable=False)
    deduct_amount = Column(Numeric(18, 7), nullable=True)
    reason = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
