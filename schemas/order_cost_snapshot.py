from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class BomDetailItem(BaseModel):
    part_id: str
    part_name: Optional[str] = None
    unit_cost: Optional[float] = None
    qty_per_unit: float
    subtotal: Optional[float] = None


class OrderCostSnapshotItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    snapshot_id: int
    jewelry_id: str
    jewelry_name: Optional[str] = None
    quantity: int
    unit_price: Optional[float] = None
    handcraft_cost: Optional[float] = None
    jewelry_unit_cost: float
    jewelry_total_cost: float
    bom_details: list[BomDetailItem] = Field(default_factory=list)


class OrderCostSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: str
    total_cost: float
    packaging_cost: Optional[float] = None
    total_amount: Optional[float] = None
    profit: Optional[float] = None
    has_incomplete_cost: int
    created_at: datetime
    items: list[OrderCostSnapshotItemResponse] = Field(default_factory=list)
