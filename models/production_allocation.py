"""Quantity plans, deliberately separate from legacy links and stock movements."""
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, UniqueConstraint

from database import Base
from time_utils import now_beijing


class ProductionAllocation(Base):
    __tablename__ = "production_allocation"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_item_id = Column(Integer, ForeignKey("order_item.id"), nullable=False, index=True)
    plating_order_item_id = Column(Integer, ForeignKey("plating_order_item.id"), index=True)
    # Only output rows: HandcraftPartItem records issued inputs, not production.
    handcraft_jewelry_item_id = Column(Integer, ForeignKey("handcraft_jewelry_item.id"), index=True)
    quantity = Column(Numeric(14, 4), nullable=False)
    created_at = Column(DateTime, nullable=False, default=now_beijing)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_production_allocation_positive"),
        CheckConstraint(
            "(plating_order_item_id IS NULL) <> (handcraft_jewelry_item_id IS NULL)",
            name="ck_production_allocation_source_xor",
        ),
        UniqueConstraint("order_item_id", "plating_order_item_id", name="uq_allocation_order_plating"),
        UniqueConstraint("order_item_id", "handcraft_jewelry_item_id", name="uq_allocation_order_handcraft"),
    )
