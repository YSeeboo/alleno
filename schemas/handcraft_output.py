from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from schemas.handcraft_summary import ReceiptBatch


class OutputQuantities(BaseModel):
    unit: str
    expected_qty: float
    actual_received_qty: float
    loss_total_qty: float
    unreceived_qty: float


class OutputProduct(BaseModel):
    output_key: str
    output_type: Literal["jewelry", "part"]
    output_id: str
    output_name: str | None = None
    output_image: str | None = None


class OutputItem(OutputQuantities, OutputProduct):
    supplier_name: str
    source_count: int
    reference_date_count: int


class OutputGroup(BaseModel):
    key: str
    source_count: int
    pending_source_count: int
    items: list[OutputItem]


class OutputOverview(BaseModel):
    groups: list[OutputGroup]
    total: int
    source_count: int
    supplier_count: int
    output_count: int
    reference_date_count: int
    totals: list[OutputQuantities]


class OutputSource(OutputQuantities):
    handcraft_jewelry_item_id: int
    handcraft_order_id: str
    supplier_name: str
    dispatch_date: date | None = None
    dispatch_date_basis: Literal["actual", "document_reference"]
    archived_at: datetime | None = None
    note: str | None = None
    document_note: str | None = None
    receipt_count: int


class OutputSourceList(BaseModel):
    items: list[OutputSource]
    total: int


class OutputReceiptList(BaseModel):
    items: list[ReceiptBatch]
    total: int


class OutputOptions(BaseModel):
    suppliers: list[str]
    outputs: list[OutputProduct]
    has_more: bool = False
