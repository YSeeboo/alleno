from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class PlatingItemCreate(BaseModel):
    part_id: str
    qty: float = Field(gt=0)
    plating_method: Optional[str] = None
    unit: Optional[str] = "个"
    note: Optional[str] = None
    receive_part_id: Optional[str] = None


class PlatingCreate(BaseModel):
    supplier_name: str
    items: List[PlatingItemCreate] = Field(min_length=1)
    note: Optional[str] = None


class ReceiptItem(BaseModel):
    plating_order_item_id: int
    qty: float = Field(gt=0)


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
    unit: Optional[str] = None
    note: Optional[str] = None
    receive_part_id: Optional[str] = None


class PlatingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    supplier_name: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    note: Optional[str] = None
    delivery_images: List[str] = Field(default_factory=list)


class PlatingDeliveryImagesUpdate(BaseModel):
    delivery_images: List[str] = Field(default_factory=list, max_length=4)


class PendingReceiveItemResponse(BaseModel):
    id: int
    plating_order_id: str
    supplier_name: str
    part_id: str
    part_name: str
    part_image: Optional[str] = None
    receive_part_id: Optional[str] = None
    receive_part_name: Optional[str] = None
    plating_method: Optional[str] = None
    qty: float
    received_qty: float
    unit: Optional[str] = None
    created_at: Optional[datetime] = None
