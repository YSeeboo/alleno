from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text

from database import Base
from time_utils import now_beijing


class InventoryLog(Base):
    __tablename__ = "inventory_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_type = Column(String, nullable=False)   # part / jewelry
    item_id = Column(String, nullable=False)
    change_qty = Column(Numeric(10, 4), nullable=False)
    reason = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
