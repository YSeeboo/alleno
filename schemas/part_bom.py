from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PartBomSet(BaseModel):
    child_part_id: str
    qty_per_unit: float = Field(gt=0)


class PartBomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_part_id: str
    child_part_id: str
    qty_per_unit: float
    child_part_name: Optional[str] = None
    child_part_image: Optional[str] = None
    child_is_composite: Optional[bool] = None
