from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator
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


class OrderHandcraftShare(BaseModel):
    order_item_id: int = Field(gt=0, strict=True)
    allocated_quantity: int = Field(gt=0, strict=True, lt=1000000000)


class OrderHandcraftBatchCreate(HandcraftCreate):
    # Positionally pairs each exact order line with one NEW output; never merge.
    allocations: list[OrderHandcraftShare] = Field(min_length=1, max_length=100)
    request_key: str = Field(min_length=8, max_length=80)

    @model_validator(mode="after")
    def exact_output_rows(self):
        if len(self.jewelries) != len(self.allocations):
            raise ValueError("每条订单明细必须对应一条独立产出")
        if len({row.order_item_id for row in self.allocations}) != len(self.allocations):
            raise ValueError("不能重复选择同一订单明细")
        return self
