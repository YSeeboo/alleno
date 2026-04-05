from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ConfirmLossRequest(BaseModel):
    loss_qty: float
    deduct_amount: Optional[float] = None
    reason: Optional[str] = None
    note: Optional[str] = None


class ConfirmLossHandcraftRequest(ConfirmLossRequest):
    item_type: str  # "part" or "jewelry"


class BatchConfirmLossPlatingItem(BaseModel):
    plating_order_item_id: int
    loss_qty: float
    deduct_amount: Optional[float] = None
    reason: Optional[str] = None


class BatchConfirmLossPlatingRequest(BaseModel):
    items: list[BatchConfirmLossPlatingItem]


class BatchConfirmLossHandcraftItem(BaseModel):
    item_id: int
    item_type: str  # "part" or "jewelry"
    loss_qty: float
    deduct_amount: Optional[float] = None
    reason: Optional[str] = None


class BatchConfirmLossHandcraftRequest(BaseModel):
    items: list[BatchConfirmLossHandcraftItem]


class BatchConfirmLossResponse(BaseModel):
    confirmed_count: int


class ProductionLossResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_type: str
    order_id: str
    item_id: int
    item_type: str
    part_id: Optional[str] = None
    jewelry_id: Optional[str] = None
    loss_qty: float
    deduct_amount: Optional[float] = None
    reason: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime
