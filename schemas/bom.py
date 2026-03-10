from pydantic import BaseModel, ConfigDict


class BomSet(BaseModel):
    jewelry_id: str
    part_id: str
    qty_per_unit: float


class BomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    jewelry_id: str
    part_id: str
    qty_per_unit: float
