from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class OrderItemCreate(BaseModel):
    jewelry_id: str
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
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
    packaging_cost: Optional[float] = None
    created_at: datetime


# --- TodoList ---

class OrderTodoItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: str
    part_id: str
    required_qty: float
    # Enriched fields (populated by service)
    part_name: Optional[str] = None
    part_image: Optional[str] = None
    stock_qty: Optional[float] = None
    gap: Optional[float] = None
    is_complete: Optional[bool] = None
    linked_production: Optional[list] = None


# --- Link ---

class LinkCreateRequest(BaseModel):
    """单选关联：一个生产项关联一个 TodoList 行"""
    order_todo_item_id: Optional[int] = None
    order_id: Optional[str] = None
    plating_order_item_id: Optional[int] = None
    handcraft_part_item_id: Optional[int] = None
    handcraft_jewelry_item_id: Optional[int] = None
    purchase_order_item_id: Optional[int] = None


class BatchLinkRequest(BaseModel):
    """批量关联：多个配件项按 part_id 自动匹配 TodoList 行"""
    order_id: str
    plating_order_item_ids: list[int] = Field(default_factory=list)
    handcraft_part_item_ids: list[int] = Field(default_factory=list)
    purchase_order_item_ids: list[int] = Field(default_factory=list)


class BatchLinkResponse(BaseModel):
    linked: int
    skipped: list[str] = Field(default_factory=list)


class LinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_todo_item_id: Optional[int] = None
    order_id: Optional[str] = None
    plating_order_item_id: Optional[int] = None
    handcraft_part_item_id: Optional[int] = None
    handcraft_jewelry_item_id: Optional[int] = None
    purchase_order_item_id: Optional[int] = None


class OrderProgressResponse(BaseModel):
    """订单列表页的生产进度概要"""
    order_id: str
    total: int
    completed: int
