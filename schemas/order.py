from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class OrderItemCreate(BaseModel):
    jewelry_id: str
    quantity: int
    unit_price: float
    remarks: Optional[str] = None


class OrderCreate(BaseModel):
    customer_name: str
    items: List[OrderItemCreate]


class StatusUpdate(BaseModel):
    status: str


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: str
    jewelry_id: str
    quantity: int
    unit_price: float
    remarks: Optional[str] = None


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_name: str
    status: str
    total_amount: Optional[float] = None
    created_at: datetime
