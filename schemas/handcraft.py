from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class HandcraftPartIn(BaseModel):
    part_id: str
    qty: float = Field(gt=0)
    bom_qty: Optional[float] = None
    note: Optional[str] = None


class HandcraftJewelryIn(BaseModel):
    jewelry_id: str
    qty: int = Field(gt=0)
    note: Optional[str] = None


class HandcraftCreate(BaseModel):
    supplier_name: str
    parts: List[HandcraftPartIn] = Field(min_length=1)
    jewelries: List[HandcraftJewelryIn] = Field(min_length=1)
    note: Optional[str] = None


class ReceiptItem(BaseModel):
    handcraft_jewelry_item_id: int
    qty: int = Field(gt=0)


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


class HandcraftPartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    handcraft_order_id: str
    part_id: str
    qty: float
    bom_qty: Optional[float] = None
    note: Optional[str] = None


class HandcraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    supplier_name: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    note: Optional[str] = None
