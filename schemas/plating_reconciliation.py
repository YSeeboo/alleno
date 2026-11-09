from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_serializer


class ReconciliationPriceUpdate(BaseModel):
    override_price: Decimal | None = Field(..., ge=0, max_digits=18, decimal_places=7)


class ReconciliationTotals(BaseModel):
    due: Decimal
    paid: Decimal
    pending: Decimal
    unpriced_count: int

    @field_serializer("due", "paid", "pending")
    def serialize_amount(self, value):
        return format(value, "f")


class ReconciliationMerchant(ReconciliationTotals):
    vendor_name: str
    receipt_count: int
    item_count: int


class ReconciliationRow(BaseModel):
    receipt_item_id: int
    receipt_id: str
    created_at: datetime | None
    vendor_name: str
    status: Literal["未付款", "已付款"]
    part_id: str
    part_name: str
    plating_order_id: str
    plating_order_item_id: int
    plating_method: str | None
    archived: bool
    qty: Decimal
    unit: str | None
    weight: Decimal | None
    weight_unit: str | None
    price: Decimal | None
    override_price: Decimal | None
    amount: Decimal | None
    note: str | None

    @field_serializer("qty", "weight", "price", "override_price", "amount")
    def serialize_decimal(self, value):
        return format(value, "f") if value is not None else None


class ReconciliationResponse(BaseModel):
    totals: ReconciliationTotals
    merchants: list[ReconciliationMerchant]
    items: list[ReconciliationRow]
    total: int
