from datetime import date as date_type
from typing import Literal, Optional, List
from pydantic import BaseModel, ConfigDict


class ReceiptInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    receipt_id: str
    receipt_item_id: int
    receipt_date: date_type


class DispatchedItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plating_order_item_id: int
    plating_order_id: str
    supplier_name: str
    part_id: Optional[str] = None
    part_name: Optional[str] = None
    part_image: Optional[str] = None
    plating_method: Optional[str] = None
    qty: float
    unit: Optional[str] = None
    weight: Optional[float] = None
    weight_unit: Optional[str] = None
    note: Optional[str] = None
    dispatch_date: date_type
    days_out: Optional[int] = None       # None when is_completed
    is_completed: bool
    receive_part_id: Optional[str] = None
    receive_part_name: Optional[str] = None
    receive_part_image: Optional[str] = None


class ReceivedItem(DispatchedItem):
    actual_received_qty: float
    unreceived_qty: float
    loss_total_qty: float
    loss_state: Literal["none", "pending", "confirmed"]
    receipts: List[ReceiptInfo]
    latest_receipt_id: Optional[str] = None


class DispatchedListResponse(BaseModel):
    items: List[DispatchedItem]
    total: int


class ReceivedListResponse(BaseModel):
    items: List[ReceivedItem]
    total: int
