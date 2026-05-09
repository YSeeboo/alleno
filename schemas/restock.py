from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class RestockRequestCreate(BaseModel):
    part_id: str = Field(min_length=1)
    handcraft_order_id: Optional[str] = None
    source: Literal["picking", "manual"]
    note: Optional[str] = None


class RestockRequestPatch(BaseModel):
    status: Literal["done"]


class RestockRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    part_id: str
    handcraft_order_id: Optional[str]
    source: str
    status: str
    shortfall_qty: Optional[float] = None
    note: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]


class RestockShortfallUpdate(BaseModel):
    # null clears the value; a positive number sets it. We accept any
    # non-negative float (user might write 0 to mean "no need" without
    # deleting the row).
    shortfall_qty: Optional[float] = Field(None, ge=0)


class RestockSourceItem(BaseModel):
    request_id: int
    handcraft_order_id: Optional[str]
    supplier_name: str
    created_at: datetime
    qty: Optional[float] = None


class RestockSummaryItem(BaseModel):
    part_id: str
    part_name: str
    part_image: Optional[str] = None
    current_stock: float
    source_count: int
    total_qty: Optional[float] = None
    sources: List[RestockSourceItem]


class RestockMarkPartDoneRequest(BaseModel):
    part_id: str = Field(min_length=1)


class RestockMarkPartDoneResponse(BaseModel):
    updated: int


class RestockHistoryItem(BaseModel):
    id: int
    part_id: str
    part_name: str
    handcraft_order_id: Optional[str]
    supplier_name: Optional[str]
    source: str
    qty: Optional[float] = None
    shortfall_qty: Optional[float] = None
    note: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
