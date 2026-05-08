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
    note: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]


class RestockSourceItem(BaseModel):
    request_id: int
    handcraft_order_id: Optional[str]
    supplier_name: str
    created_at: datetime


class RestockSummaryItem(BaseModel):
    part_id: str
    part_name: str
    part_image: Optional[str] = None
    current_stock: float
    source_count: int
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
    note: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
