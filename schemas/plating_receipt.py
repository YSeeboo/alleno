from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.part import CostDiffItem


class PlatingReceiptItemCreate(BaseModel):
    plating_order_item_id: int
    part_id: str
    qty: float = Field(gt=0)
    unit: Optional[str] = "个"
    price: Optional[float] = Field(None, ge=0)
    note: Optional[str] = None


class PlatingReceiptCreate(BaseModel):
    vendor_name: str
    items: List[PlatingReceiptItemCreate] = Field(min_length=1)
    status: str = "未付款"
    note: Optional[str] = None

    @field_validator("vendor_name")
    @classmethod
    def vendor_name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("商家名称不能为空")
        return v


class PlatingReceiptAddItemsRequest(BaseModel):
    items: List[PlatingReceiptItemCreate] = Field(min_length=1)


class PlatingReceiptItemUpdate(BaseModel):
    qty: float = Field(None, gt=0)
    unit: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    note: Optional[str] = None


class PlatingReceiptStatusUpdate(BaseModel):
    status: str


class PlatingReceiptDeliveryImagesUpdate(BaseModel):
    delivery_images: List[str] = Field(default_factory=list, max_length=9)


class PlatingReceiptItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plating_receipt_id: str
    plating_order_item_id: int
    part_id: str
    qty: float
    unit: Optional[str] = None
    price: Optional[float] = None
    amount: Optional[float] = None
    note: Optional[str] = None
    # Enriched fields (populated by service, not from ORM)
    part_name: Optional[str] = None
    plating_order_id: Optional[str] = None
    plating_method: Optional[str] = None
    source_qty: Optional[float] = None
    source_received_qty: Optional[float] = None


class PlatingReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    vendor_name: str
    status: str
    total_amount: Optional[float] = None
    note: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None
    delivery_images: list[str] = Field(default_factory=list)
    items: list[PlatingReceiptItemResponse] = Field(default_factory=list)
    cost_diffs: list[CostDiffItem] = Field(default_factory=list)
