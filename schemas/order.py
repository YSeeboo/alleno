from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderItemCreate(BaseModel):
    jewelry_id: Optional[str] = None
    part_id: Optional[str] = None
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    remarks: Optional[str] = None

    @model_validator(mode="after")
    def _xor(self):
        if (self.jewelry_id is None) == (self.part_id is None):
            raise ValueError("jewelry_id 和 part_id 必须且只能填一个")
        return self


class OrderCreate(BaseModel):
    customer_name: str
    items: List[OrderItemCreate]
    created_at: Optional[date] = None


class StatusUpdate(BaseModel):
    status: str


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: str
    jewelry_id: Optional[str] = None
    part_id: Optional[str] = None
    quantity: int
    unit_price: float
    remarks: Optional[str] = None
    customer_code: str | None = None
    # Enriched (populated by service layer at response time)
    part_name: Optional[str] = None
    part_image: Optional[str] = None
    part_unit: Optional[str] = None


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_name: str
    status: str
    total_amount: Optional[float] = None
    packaging_cost: Optional[float] = None
    barcode_text: Optional[str] = None
    barcode_image: Optional[str] = None
    mark_text: Optional[str] = None
    mark_image: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime


class OrderItemUpdate(BaseModel):
    customer_code: str | None = None
    quantity: Optional[int] = Field(None, gt=0)
    unit_price: Optional[float] = Field(None, ge=0)


class BatchCustomerCodeRequest(BaseModel):
    item_ids: list[int] = Field(..., min_length=1)
    prefix: str = Field(..., min_length=1)
    start_number: int = Field(..., ge=0)
    padding: int = Field(2, ge=1, le=6)


class BatchCustomerCodeResponse(BaseModel):
    updated_count: int


class ExtraInfoUpdate(BaseModel):
    customer_name: Optional[str] = None
    barcode_text: Optional[str] = None
    barcode_image: Optional[str] = None
    mark_text: Optional[str] = None
    mark_image: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[date] = None


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
    part_is_composite: Optional[bool] = None
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
    """订单列表页的备货进度概要"""
    order_id: str
    total: int
    completed: int


# --- Batch schemas ---

class TodoBatchItemInput(BaseModel):
    jewelry_id: str
    quantity: int = Field(..., gt=0, strict=True)


class TodoBatchCreateRequest(BaseModel):
    items: list[TodoBatchItemInput] = Field(..., min_length=1)


class TodoBatchJewelryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    jewelry_id: str
    jewelry_name: str
    jewelry_image: str | None = None
    quantity: int


class TodoBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_id: str
    handcraft_order_id: str | None = None
    supplier_name: str | None = None
    created_at: datetime
    jewelries: list[TodoBatchJewelryResponse] = []
    items: list[OrderTodoItemResponse] = []


class TodoBatchListResponse(BaseModel):
    batches: list[TodoBatchResponse]


class LinkSupplierRequest(BaseModel):
    supplier_name: str


class LinkSupplierResponse(BaseModel):
    handcraft_order_id: str


class JewelryStatusResponse(BaseModel):
    jewelry_id: str
    jewelry_name: str
    jewelry_image: str | None = None
    quantity: int
    status: str


class JewelryForBatchResponse(BaseModel):
    jewelry_id: str
    jewelry_name: str
    jewelry_image: str | None = None
    order_quantity: int
    allocated_quantity: int
    remaining_quantity: int
    selectable: bool
    disabled_reason: str | None = None


class SourceJewelryItem(BaseModel):
    jewelry_id: str
    jewelry_name: str = ""
    qty_per_unit: float
    order_qty: int
    subtotal: float


class PartsSummaryItemResponse(BaseModel):
    part_id: str
    part_name: str
    part_image: str | None = None
    part_is_composite: bool = False
    total_qty: float
    raw_total_qty: float
    current_stock: float
    reserved_qty: float
    global_demand: float
    remaining_qty: float
    # Pre-computed from RAW floats (before ceiling). True iff the global
    # BOM demand across all active orders fits in the available part stock
    # for this order. Callers must NOT reconstruct this from current_stock /
    # reserved_qty / global_demand — those are ceiled independently and can
    # disagree with the raw comparison around fractional meter quantities.
    globally_sufficient: bool
    source_jewelries: list[SourceJewelryItem] = []


# --- Picking Simulation (配货模拟) ---


class PickingVariant(BaseModel):
    """One (qty_per_unit, units_count) row under a part."""
    qty_per_unit: float
    units_count: int
    subtotal: float
    picked: bool


class PickingPartRow(BaseModel):
    """One part with its variants. `is_composite_child=True` means this part
    appears — at least partly — because of a composite parent in some
    jewelry's BOM."""
    part_id: str
    part_name: str
    part_image: Optional[str] = None
    current_stock: float
    is_composite_child: bool
    variants: List[PickingVariant]
    total_required: float


class PickingProgress(BaseModel):
    total: int    # total number of variant rows
    picked: int   # number of variant rows currently marked picked


class PickingSimulationResponse(BaseModel):
    order_id: str
    customer_name: str
    rows: List[PickingPartRow]
    progress: PickingProgress


class PickingMarkRequest(BaseModel):
    part_id: str
    qty_per_unit: float


class PickingPdfRequest(BaseModel):
    include_picked: bool = False
