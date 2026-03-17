from typing import Optional
from pydantic import BaseModel, ConfigDict


class PartCreate(BaseModel):
    name: str
    category: str
    image: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    unit_cost: Optional[float] = None
    plating_process: Optional[str] = None


class PartUpdate(BaseModel):
    name: Optional[str] = None
    image: Optional[str] = None
    category: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    unit_cost: Optional[float] = None
    plating_process: Optional[str] = None


class PartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    image: Optional[str] = None
    category: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    unit_cost: Optional[float] = None
    plating_process: Optional[str] = None
