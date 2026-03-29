from typing import Optional
from pydantic import BaseModel, ConfigDict


class JewelryCreate(BaseModel):
    name: str
    category: str
    image: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    retail_price: Optional[float] = None
    wholesale_price: Optional[float] = None
    handcraft_cost: Optional[float] = None
    status: Optional[str] = "active"


class JewelryUpdate(BaseModel):
    name: Optional[str] = None
    image: Optional[str] = None
    category: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    retail_price: Optional[float] = None
    wholesale_price: Optional[float] = None
    handcraft_cost: Optional[float] = None


class StatusUpdate(BaseModel):
    status: str


class JewelryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    image: Optional[str] = None
    category: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    retail_price: Optional[float] = None
    wholesale_price: Optional[float] = None
    handcraft_cost: Optional[float] = None
    status: str
