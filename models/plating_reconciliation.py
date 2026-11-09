from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric

from database import Base


class PlatingReconciliation(Base):
    """Independent pricing only; receipt status remains the payment source of truth."""

    __tablename__ = "plating_reconciliation"
    __table_args__ = (
        CheckConstraint("override_price >= 0", name="ck_plating_reconciliation_price"),
    )

    receipt_item_id = Column(
        Integer, ForeignKey("plating_receipt_item.id", ondelete="CASCADE"), primary_key=True,
    )
    override_price = Column(Numeric(18, 7), nullable=True)
    settled_amount = Column(Numeric(18, 7), nullable=True)
    # A timestamp distinguishes a frozen unpriced item from a legacy paid item.
    settled_at = Column(DateTime, nullable=True)
