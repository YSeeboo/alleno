from typing import Optional
from pydantic import BaseModel, ConfigDict


class JewelryCreate(BaseModel):
    name: str
    category: str
    image: Optional[str] = None
    structure_image: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    retail_price: Optional[float] = None
    wholesale_price: Optional[float] = None
    handcraft_cost: Optional[float] = None
    status: Optional[str] = "active"


class JewelryUpdate(BaseModel):
    name: Optional[str] = None
    image: Optional[str] = None
    structure_image: Optional[str] = None
    category: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    retail_price: Optional[float] = None
    wholesale_price: Optional[float] = None
    handcraft_cost: Optional[float] = None


class JewelryCopyRequest(BaseModel):
    name: str
    image: Optional[str] = None
    structure_image: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    retail_price: Optional[float] = None
    wholesale_price: Optional[float] = None
    handcraft_cost: Optional[float] = None
    # Note: no `category` field — category is forced to source jewelry's.


class JewelrySiblingIn(BaseModel):
    # 全部可选：未传字段沿用基准。category 不接受（沿用基准且锁定）。
    name: Optional[str] = None
    image: Optional[str] = None
    structure_image: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    retail_price: Optional[float] = None
    wholesale_price: Optional[float] = None
    handcraft_cost: Optional[float] = None


class StatusUpdate(BaseModel):
    status: str


class JewelryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    image: Optional[str] = None
    structure_image: Optional[str] = None
    category: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    retail_price: Optional[float] = None
    wholesale_price: Optional[float] = None
    handcraft_cost: Optional[float] = None
    material_cost: Optional[float] = None
    total_cost: Optional[float] = None
    has_incomplete_cost: Optional[bool] = None
    style_group: Optional[str] = None
    status: str
