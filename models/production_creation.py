"""Idempotency receipts for exact-line production creation, not stock movements."""
from sqlalchemy import Column, DateTime, JSON, String

from database import Base
from time_utils import now_beijing


class ProductionCreation(Base):
    __tablename__ = "production_creation"

    request_key = Column(String(80), primary_key=True)
    # Snapshot identities intentionally survive later plan cancellation/deletion.
    order_id = Column(String, nullable=False, index=True)
    payload_hash = Column(String(64), nullable=False)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=now_beijing)
