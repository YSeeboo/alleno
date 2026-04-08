from sqlalchemy import Column, DateTime, Index, Integer, Numeric, String, Text

from database import Base
from time_utils import now_beijing


class InventoryLog(Base):
    __tablename__ = "inventory_log"
    __table_args__ = (
        Index("ix_invlog_type_id", "item_type", "item_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_type = Column(String, nullable=False)   # part / jewelry
    item_id = Column(String, nullable=False)
    change_qty = Column(Numeric(18, 4), nullable=False)
    reason = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
