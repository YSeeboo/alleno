from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class StockRequest(BaseModel):
    item_type: str
    item_id: str
    qty: float
    reason: str
    note: Optional[str] = None


class StockResponse(BaseModel):
    item_type: str
    item_id: str
    current: float


class InventoryOverviewItem(BaseModel):
    item_type: str
    item_id: str
    name: str
    image: Optional[str] = None
    is_composite: Optional[bool] = None
    category: Optional[str] = None
    current: float
    updated_at: Optional[datetime] = None


class LogEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_type: str
    item_id: str
    change_qty: float
    reason: str
    note: Optional[str] = None
    created_at: datetime


class PaginatedLogResponse(BaseModel):
    total: int
    items: list[LogEntryResponse]
