from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schemas.part import CostDiffItem


class HandcraftReceiptItemCreate(BaseModel):
    handcraft_part_item_id: Optional[int] = None
    handcraft_jewelry_item_id: Optional[int] = None
    qty: float = Field(gt=0)
    weight: Optional[float] = Field(None, ge=0)
    weight_unit: Optional[str] = None
    unit: Optional[str] = "个"
    price: Optional[float] = Field(None, ge=0)
    note: Optional[str] = None

    @model_validator(mode="after")
    def exactly_one_item_id(self):
        has_part = self.handcraft_part_item_id is not None
        has_jewelry = self.handcraft_jewelry_item_id is not None
        if has_part == has_jewelry:
            raise ValueError("必须且只能指定 handcraft_part_item_id 或 handcraft_jewelry_item_id 其中之一")
        # Jewelry items must have integer qty
        if has_jewelry and self.qty != int(self.qty):
            raise ValueError("饰品收回数量必须为整数")
        return self


class HandcraftReceiptCreate(BaseModel):
    supplier_name: str
    items: List[HandcraftReceiptItemCreate] = Field(min_length=1)
    status: str = "未付款"
    note: Optional[str] = None
    created_at: Optional[date] = None

    @field_validator("supplier_name")
    @classmethod
    def supplier_name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("商家名称不能为空")
        return v


class HandcraftReceiptUpdate(BaseModel):
    created_at: Optional[date] = None


class HandcraftReceiptAddItemsRequest(BaseModel):
    items: List[HandcraftReceiptItemCreate] = Field(min_length=1)


class HandcraftReceiptItemUpdate(BaseModel):
    qty: float = Field(None, gt=0)
    weight: Optional[float] = Field(None, ge=0)
    weight_unit: Optional[str] = None
    unit: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    note: Optional[str] = None


class HandcraftReceiptStatusUpdate(BaseModel):
    status: str


class HandcraftReceiptDeliveryImagesUpdate(BaseModel):
    delivery_images: List[str] = Field(default_factory=list, max_length=9)


class HandcraftReceiptItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    handcraft_receipt_id: str
    handcraft_part_item_id: Optional[int] = None
    handcraft_jewelry_item_id: Optional[int] = None
    item_id: str
    item_type: str
    qty: float
    weight: Optional[float] = Field(None, ge=0)
    weight_unit: Optional[str] = None
    unit: Optional[str] = None
    price: Optional[float] = None
    amount: Optional[float] = None
    note: Optional[str] = None
    # Enriched fields (populated by service, not from ORM)
    item_name: Optional[str] = None
    handcraft_order_id: Optional[str] = None
    color: Optional[str] = None
    source_qty: Optional[float] = None
    source_received_qty: Optional[float] = None


class HandcraftReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    supplier_name: str
    status: str
    total_amount: Optional[float] = None
    note: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None
    delivery_images: list[str] = Field(default_factory=list)
    items: list[HandcraftReceiptItemResponse] = Field(default_factory=list)
    cost_diffs: list[CostDiffItem] = Field(default_factory=list)
