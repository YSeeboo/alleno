from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class HandcraftPartIn(BaseModel):
    part_id: str
    qty: float
    bom_qty: Optional[float] = None
    note: Optional[str] = None


class HandcraftJewelryIn(BaseModel):
    jewelry_id: str
    qty: int
    note: Optional[str] = None


class HandcraftCreate(BaseModel):
    supplier_name: str
    parts: List[HandcraftPartIn]
    jewelries: List[HandcraftJewelryIn]
    note: Optional[str] = None


class ReceiptItem(BaseModel):
    handcraft_jewelry_item_id: int
    qty: int


class ReceiptRequest(BaseModel):
    receipts: List[ReceiptItem]


class HandcraftJewelryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    handcraft_order_id: str
    jewelry_id: str
    qty: int
    received_qty: Optional[int] = None
    status: str
    note: Optional[str] = None


class HandcraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    supplier_name: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    note: Optional[str] = None
