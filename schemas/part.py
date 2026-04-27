from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


SizeTier = Literal["small", "medium"]


class PartCreate(BaseModel):
    name: str
    category: str
    image: Optional[str] = None
    color: Optional[str] = None
    spec: Optional[str] = None
    unit: Optional[str] = None
    plating_process: Optional[str] = None
    parent_part_id: Optional[str] = None
    wholesale_price: Optional[float] = None
    size_tier: Optional[SizeTier] = None


class PartUpdate(BaseModel):
    name: Optional[str] = None
    image: Optional[str] = None
    category: Optional[str] = None
    color: Optional[str] = None
    spec: Optional[str] = None
    unit: Optional[str] = None
    plating_process: Optional[str] = None
    parent_part_id: Optional[str] = None
    assembly_cost: Optional[float] = None
    wholesale_price: Optional[float] = None
    size_tier: Optional[SizeTier] = None


class PartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    image: Optional[str] = None
    category: str
    color: Optional[str] = None
    spec: Optional[str] = None
    unit: Optional[str] = None
    unit_cost: Optional[float] = None
    purchase_cost: Optional[float] = None
    bead_cost: Optional[float] = None
    plating_cost: Optional[float] = None
    plating_process: Optional[str] = None
    assembly_cost: Optional[float] = None
    wholesale_price: Optional[float] = None
    parent_part_id: Optional[str] = None
    is_composite: bool = False
    size_tier: SizeTier = "small"


class PartVariantCreate(BaseModel):
    color_code: Optional[str] = None
    spec: Optional[str] = None


class FindOrCreateVariantResponse(BaseModel):
    part: Optional[PartResponse] = None
    suggested_name: Optional[str] = None


class PartImportRowResult(BaseModel):
    row_number: int
    part_id: str
    name: str
    image: Optional[str] = None
    action: str
    stock_added: float


class PartImportResponse(BaseModel):
    imported_count: int
    created_count: int
    updated_count: int
    stock_entry_count: int
    results: list[PartImportRowResult]


class PartCostLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    part_id: str
    field: str
    cost_before: Optional[float] = None
    cost_after: Optional[float] = None
    unit_cost_before: Optional[float] = None
    unit_cost_after: Optional[float] = None
    source_id: Optional[str] = None
    created_at: datetime


class CostDiffItem(BaseModel):
    part_id: str
    part_name: str
    field: str
    current_value: Optional[float] = None
    new_value: float


class BatchCostUpdateItem(BaseModel):
    part_id: str
    field: str
    value: float = Field(ge=0)
    source_id: Optional[str] = None


class BatchCostUpdateRequest(BaseModel):
    updates: list[BatchCostUpdateItem] = Field(min_length=1)


class BatchCostUpdateResultItem(BaseModel):
    part_id: str
    field: str
    updated: bool


class BatchCostUpdateResponse(BaseModel):
    updated_count: int
    results: list[BatchCostUpdateResultItem]
