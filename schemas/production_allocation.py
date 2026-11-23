from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field
from schemas.handcraft import HandcraftCreate


class AllocationQuantity(BaseModel):
    order_item_id: int = Field(gt=0)
    quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=4, allow_inf_nan=False)
    material_part_id: str | None = Field(default=None, min_length=1)
    demand_revision: str | None = Field(default=None, min_length=64, max_length=64)


class AllocationReplace(BaseModel):
    source_type: Literal["plating", "handcraft"]
    source_item_id: int = Field(gt=0)
    revision: str = Field(min_length=64, max_length=64)
    allocations: list[AllocationQuantity] = Field(max_length=500)


class AllocationBatch(BaseModel):
    sources: list[AllocationReplace] = Field(min_length=1, max_length=100)


class OrderHandcraftCreate(HandcraftCreate):
    order_item_id: int = Field(gt=0, strict=True)
    allocated_quantity: int = Field(gt=0, strict=True, lt=1000000000)
    request_key: str = Field(min_length=8, max_length=80)
