from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------- 收回弹窗请求 ----------

class ReceiptItemIn(BaseModel):
    item_id: str = Field(min_length=1)
    item_type: Literal["part", "jewelry"]
    qty: float = Field(gt=0)

    @field_validator("item_id")
    @classmethod
    def item_id_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("item_id 不能为空白字符串")
        return v.strip()


class VendorReceiptCreate(BaseModel):
    vendor_name: str = Field(min_length=1)
    order_type: Literal["plating", "handcraft"]
    order_id: str = Field(min_length=1)
    items: list[ReceiptItemIn] = Field(min_length=1)

    @field_validator("vendor_name")
    @classmethod
    def vendor_name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("vendor_name 不能为空白字符串")
        return v.strip()

    @field_validator("order_id")
    @classmethod
    def order_id_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("order_id 不能为空白字符串")
        return v.strip()


# ---------- 看板卡片 ----------

class VendorCard(BaseModel):
    vendor_name: str
    order_type: str    # "plating" | "handcraft"
    part_count: int    # 配件种类数量
    created_at: datetime


class KanbanRow(BaseModel):
    status: str        # "pending_dispatch" | "pending_return" | "returned"
    vendors: list[VendorCard]
    total: int


class KanbanResponse(BaseModel):
    pending_dispatch: KanbanRow
    pending_return: KanbanRow
    returned: KanbanRow


# ---------- 厂家详情 ----------

class VendorItemSummary(BaseModel):
    item_id: str
    item_type: str           # "part" | "jewelry"
    item_name: str | None = None
    image: str | None = None
    plating_method: str | None
    dispatched_qty: float
    received_qty: float


class VendorOrderSummary(BaseModel):
    order_id: str
    order_type: str
    status: str
    created_at: datetime


class VendorDetailResponse(BaseModel):
    vendor_name: str
    order_type: str
    items: list[VendorItemSummary]
    orders: list[VendorOrderSummary]


# ---------- 收回弹窗 - 订单下拉 ----------

class VendorOrderOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: str
    status: str
    created_at: datetime


# ---------- 收回弹窗 - 订单明细（带剩余量提示）----------

class OrderItemHint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: str
    item_type: str         # "part" | "jewelry"
    item_name: str | None  # 可能查不到
    dispatched_qty: float
    received_qty: float    # 该订单已收回量
    remaining_qty: float   # dispatched_qty - received_qty


class OrderItemsForReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: str
    order_type: str
    items: list[OrderItemHint]


# ---------- 手动状态变更 ----------

class OrderStatusChangeRequest(BaseModel):
    order_id: str = Field(min_length=1)
    order_type: Literal["plating", "handcraft"]
    new_status: Literal["pending", "processing", "completed"]

    @field_validator("order_id")
    @classmethod
    def order_id_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("order_id 不能为空白字符串")
        return v.strip()
