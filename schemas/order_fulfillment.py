from decimal import Decimal
from pydantic import BaseModel, Field


class FulfillmentActivation(BaseModel):
    confirmed_no_prior_shipments: bool


class ReservationUpdate(BaseModel):
    quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4, allow_inf_nan=False)
    expected_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4, allow_inf_nan=False)


class ShipmentLine(BaseModel):
    order_item_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4, allow_inf_nan=False)


class ShipmentCreate(BaseModel):
    order_id: str = Field(min_length=1)
    request_key: str = Field(min_length=16, max_length=100)
    lines: list[ShipmentLine] = Field(min_length=1, max_length=500)
    tracking: str = Field(default="", max_length=2000)
    note: str = Field(default="", max_length=5000)


class ShipmentConfirm(BaseModel):
    actual_goods_checked: bool
