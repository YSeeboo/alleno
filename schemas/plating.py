from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class PlatingItemCreate(BaseModel):
    part_id: str
    qty: float
    plating_method: Optional[str] = None
    note: Optional[str] = None


class PlatingCreate(BaseModel):
    supplier_name: str
    items: List[PlatingItemCreate]
    note: Optional[str] = None


class ReceiptItem(BaseModel):
    plating_order_item_id: int
    qty: float


class ReceiptRequest(BaseModel):
    receipts: List[ReceiptItem]


class PlatingItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plating_order_id: str
    part_id: str
    qty: float
    received_qty: Optional[float] = None
    status: str
    plating_method: Optional[str] = None
    note: Optional[str] = None


class PlatingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    supplier_name: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    note: Optional[str] = None
