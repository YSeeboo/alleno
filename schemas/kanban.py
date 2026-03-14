from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
    items: list[ReceiptItemIn] = Field(min_length=1)

    @field_validator("vendor_name")
    @classmethod
    def vendor_name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("vendor_name 不能为空白字符串")
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
