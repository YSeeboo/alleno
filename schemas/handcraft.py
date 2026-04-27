from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schemas.part import SizeTier


class HandcraftPartIn(BaseModel):
    part_id: str
    qty: float = Field(gt=0)
    weight: Optional[float] = Field(None, ge=0)
    weight_unit: Optional[str] = None
    bom_qty: Optional[float] = None
    unit: Optional[str] = "个"
    note: Optional[str] = None


class HandcraftJewelryIn(BaseModel):
    jewelry_id: Optional[str] = None
    part_id: Optional[str] = None
    qty: int = Field(gt=0)
    weight: Optional[float] = Field(None, ge=0)
    weight_unit: Optional[str] = None
    unit: Optional[str] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def exactly_one_output_id(self):
        if not self.jewelry_id and not self.part_id:
            raise ValueError("产出项必须指定 jewelry_id 或 part_id")
        if self.jewelry_id and self.part_id:
            raise ValueError("产出项不能同时指定 jewelry_id 和 part_id")
        return self


class HandcraftCreate(BaseModel):
    supplier_name: str
    parts: List[HandcraftPartIn] = Field(min_length=1)
    jewelries: List[HandcraftJewelryIn] = Field(default_factory=list)
    note: Optional[str] = None
    created_at: Optional[date] = None

    @field_validator("supplier_name")
    @classmethod
    def supplier_name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("手工商家名称不能为空")
        return v


class HandcraftUpdate(BaseModel):
    supplier_name: Optional[str] = None
    created_at: Optional[date] = None



class HandcraftJewelryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    handcraft_order_id: str
    jewelry_id: Optional[str] = None
    part_id: Optional[str] = None
    qty: int
    weight: Optional[float] = Field(None, ge=0)
    weight_unit: Optional[str] = None
    received_qty: Optional[int] = None
    status: str
    unit: Optional[str] = None
    note: Optional[str] = None
    loss_qty: Optional[float] = None


class HandcraftPartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    handcraft_order_id: str
    part_id: str
    qty: float
    weight: Optional[float] = Field(None, ge=0)
    weight_unit: Optional[str] = None
    received_qty: Optional[float] = 0
    status: str = "未送出"
    bom_qty: Optional[float] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    note: Optional[str] = None
    loss_qty: Optional[float] = None


class HandcraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    supplier_name: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    note: Optional[str] = None
    delivery_images: List[str] = Field(default_factory=list)


class HandcraftDeliveryImagesUpdate(BaseModel):
    delivery_images: List[str] = Field(default_factory=list, max_length=10)


class HandcraftSuggestJewelryItem(BaseModel):
    jewelry_id: str
    qty: int = Field(gt=0)


class HandcraftSuggestRequest(BaseModel):
    jewelry_items: List[HandcraftSuggestJewelryItem] = Field(min_length=1)


class HandcraftSuggestPartItem(BaseModel):
    part_id: str
    part_name: str
    size_tier: SizeTier
    theoretical_qty: float
    buffer: int
    suggested_qty: int


# --- Picking simulation (配货模拟) ---


class HandcraftPickingVariant(BaseModel):
    """One picking row inside a part_item group. For atomic items this is the
    only row; for composites this is one expanded atom."""
    part_id: str
    part_name: str
    part_image: Optional[str] = None
    needed_qty: float
    suggested_qty: Optional[int] = None
    current_stock: float
    picked: bool


class HandcraftPickingGroup(BaseModel):
    part_item_id: int
    parent_part_id: str
    parent_part_name: str
    parent_part_image: Optional[str] = None
    parent_is_composite: bool
    parent_qty: float
    parent_bom_qty: Optional[float] = None
    rows: List[HandcraftPickingVariant]


class HandcraftPickingProgress(BaseModel):
    total: int
    picked: int


class HandcraftPickingResponse(BaseModel):
    handcraft_order_id: str
    supplier_name: str
    status: str
    groups: List[HandcraftPickingGroup]
    progress: HandcraftPickingProgress


class HandcraftPickingMarkRequest(BaseModel):
    part_item_id: int
    part_id: str
