from sqlalchemy import Column, Integer, String, Float, DateTime

from database import Base
from time_utils import now_beijing


class VendorReceipt(Base):
    __tablename__ = "vendor_receipt"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_name = Column(String, nullable=False)
    order_type = Column(String, nullable=False)   # "plating" | "handcraft"
    item_type = Column(String, nullable=False)    # "part" | "jewelry"
    item_id = Column(String, nullable=False)      # PJ-XXXX 或 SP-XXXX
    qty = Column(Float, nullable=False)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
