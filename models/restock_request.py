from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from database import Base
from time_utils import now_beijing


class RestockRequest(Base):
    """A pending or completed restock request, scoped to a (part, handcraft_order)
    pair. Pure 'todo list' — does not affect inventory or order status.
    Status flows pending -> done (one-way). One row per pair, ever."""

    __tablename__ = "restock_request"

    id = Column(Integer, primary_key=True, autoincrement=True)
    part_id = Column(String, ForeignKey("part.id"), nullable=False, index=True)
    handcraft_order_id = Column(
        String, ForeignKey("handcraft_order.id"), nullable=True, index=True
    )
    source = Column(String, nullable=False)  # "picking" | "manual"
    status = Column(String, nullable=False, default="pending")  # "pending" | "done"
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Note: PostgreSQL treats NULLs as distinct in unique constraints, so two
    # rows with handcraft_order_id=NULL for the same part can coexist. The
    # current API blocks NULL at create time, so this is fine. If a future
    # "global manual" entry path opens up null-hc records, switch to
    # UNIQUE NULLS NOT DISTINCT (PG 15+) or add a separate guard.
    __table_args__ = (
        UniqueConstraint("part_id", "handcraft_order_id", name="uq_restock_part_order"),
    )
