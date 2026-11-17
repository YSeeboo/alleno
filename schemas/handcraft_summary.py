from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ReceiptBatch(BaseModel):
    receipt_id: str
    receipt_item_id: int
    receipt_date: date
    qty: float
    unit: str | None = None
    note: str | None = None
    document_note: str | None = None


class OutputIdentity(BaseModel):
    handcraft_jewelry_item_id: int
    output_id: str | None = None
    output_type: Literal["jewelry", "part"]
    output_name: str | None = None
    output_image: str | None = None


class SourceDetail(BaseModel):
    handcraft_order_id: str
    supplier_name: str
    dispatch_date: date
    archived_at: datetime | None = None
    note: str | None = None
    document_note: str | None = None
    unit: str | None = None
    is_completed: bool
    receipts: list[ReceiptBatch] = Field(default_factory=list)
    order_ids: list[str] = Field(default_factory=list)


class DispatchedItem(SourceDetail):
    handcraft_part_item_id: int
    part_id: str
    part_name: str | None = None
    part_image: str | None = None
    qty: float
    weight: float | None = None
    weight_unit: str | None = None
    days_out: int | None = None
    outputs: list[OutputIdentity]
    relationship_basis: Literal["current_bom", "unmatched"]


class ReceivedItem(SourceDetail, OutputIdentity):
    expected_qty: float
    actual_received_qty: float
    unreceived_qty: float
    loss_total_qty: float
    max_loss_qty: float


class DispatchedListResponse(BaseModel):
    items: list[DispatchedItem]
    total: int


class ReceivedListResponse(BaseModel):
    items: list[ReceivedItem]
    total: int
