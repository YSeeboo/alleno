from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PurchaseOrderItemCreate(BaseModel):
    part_id: str
    qty: float = Field(gt=0)
    unit: Optional[str] = "个"
    price: Optional[float] = Field(None, ge=0)
    note: Optional[str] = None


class PurchaseOrderCreate(BaseModel):
    vendor_name: str
    items: List[PurchaseOrderItemCreate] = Field(min_length=1)
    status: str = "未付款"
    note: Optional[str] = None

    @field_validator("vendor_name")
    @classmethod
    def vendor_name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("商家名称不能为空")
        return v


class PurchaseOrderItemUpdate(BaseModel):
    qty: float = Field(None, gt=0)
    unit: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    note: Optional[str] = None


class PurchaseOrderStatusUpdate(BaseModel):
    status: str


class PurchaseOrderDeliveryImagesUpdate(BaseModel):
    delivery_images: List[str] = Field(default_factory=list, max_length=4)


class PurchaseOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_order_id: str
    part_id: str
    qty: float
    unit: Optional[str] = None
    price: Optional[float] = None
    amount: Optional[float] = None
    note: Optional[str] = None


class PurchaseOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    vendor_name: str
    status: str
    total_amount: Optional[float] = None
    note: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None
    delivery_images: list[str] = Field(default_factory=list)
    items: list[PurchaseOrderItemResponse] = Field(default_factory=list)
