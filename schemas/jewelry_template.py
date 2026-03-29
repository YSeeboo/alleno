from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class JewelryTemplateItemIn(BaseModel):
    part_id: str
    qty_per_unit: float = Field(gt=0)


class JewelryTemplateCreate(BaseModel):
    name: str
    image: Optional[str] = None
    note: Optional[str] = None
    items: List[JewelryTemplateItemIn] = Field(min_length=1)


class JewelryTemplateUpdate(BaseModel):
    name: Optional[str] = None
    image: Optional[str] = None
    note: Optional[str] = None
    items: Optional[List[JewelryTemplateItemIn]] = None  # 如果提供则全量替换


class JewelryTemplateItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    part_id: str
    qty_per_unit: float
    # Enriched
    part_name: Optional[str] = None
    part_image: Optional[str] = None


class JewelryTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    image: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime
    items: list[JewelryTemplateItemResponse] = Field(default_factory=list)
