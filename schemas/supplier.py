from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


SUPPLIER_TYPES = {"plating", "handcraft", "parts", "customer"}


class SupplierCreate(BaseModel):
    name: str
    type: str

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("商家名称不能为空")
        return v

    @field_validator("type")
    @classmethod
    def type_valid(cls, v: str) -> str:
        if v not in SUPPLIER_TYPES:
            raise ValueError(f"type 必须是 {', '.join(sorted(SUPPLIER_TYPES))} 之一")
        return v


class SupplierUpdate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("商家名称不能为空")
        return v


class SupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    created_at: Optional[datetime] = None
