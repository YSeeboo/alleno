"""Additive fulfillment ledger; never infer shipments from legacy order states."""
from sqlalchemy import Column, String, Integer, ForeignKey, Numeric, DateTime, Text, CheckConstraint, UniqueConstraint

from database import Base
from time_utils import now_beijing


class OrderFulfillment(Base):
    __tablename__ = "order_fulfillment"
    order_id = Column(String, ForeignKey("order.id"), primary_key=True)
    activated_at = Column(DateTime, nullable=False, default=now_beijing)


class StockReservation(Base):
    __tablename__ = "stock_reservation"
    order_item_id = Column(Integer, ForeignKey("order_item.id"), primary_key=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    __table_args__ = (CheckConstraint("quantity >= 0", name="ck_stock_reservation_nonnegative"),)


class CustomerShipment(Base):
    __tablename__ = "customer_shipment"
    id = Column(String, primary_key=True)
    order_id = Column(String, ForeignKey("order.id"), nullable=False, index=True)
    request_key = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="draft")
    tracking = Column(Text)
    note = Column(Text)
    created_at = Column(DateTime, nullable=False, default=now_beijing)
    confirmed_at = Column(DateTime)
    __table_args__ = (CheckConstraint("status IN ('draft', 'confirmed', 'void')", name="ck_customer_shipment_status"),)


class CustomerShipmentItem(Base):
    __tablename__ = "customer_shipment_item"
    id = Column(Integer, primary_key=True)
    shipment_id = Column(String, ForeignKey("customer_shipment.id"), nullable=False, index=True)
    order_item_id = Column(Integer, ForeignKey("order_item.id"), nullable=False, index=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    inventory_log_id = Column(Integer, ForeignKey("inventory_log.id"), unique=True)
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_customer_shipment_quantity"),
        UniqueConstraint("shipment_id", "order_item_id", name="uq_customer_shipment_line"),
    )
