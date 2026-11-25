from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BomSet(BaseModel):
    jewelry_id: str
    part_id: str
    qty_per_unit: float


class BomQty(BaseModel):
    qty_per_unit: float


class BomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    jewelry_id: str
    part_id: str
    qty_per_unit: float


class BomCopyJewelry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    unit: str | None
    status: str


class BomCopySource(BomCopyJewelry):
    part_count: int


class BomCopySources(BaseModel):
    items: list[BomCopySource]
    has_more: bool


class BomCopyPreview(BaseModel):
    source: BomCopyJewelry
    target_unit: str | None
    rows: list[BomResponse]


class BomCopyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_id: str = Field(min_length=1)
    qty_per_unit: Decimal = Field(gt=0, max_digits=10, decimal_places=4)


class BomCopyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    source_unit: str | None
    target_unit: str | None
    unit_confirmed: bool = False
    items: list[BomCopyItem] = Field(min_length=1)

    @field_validator("items")
    @classmethod
    def unique_parts(cls, items):
        if len({item.part_id for item in items}) != len(items):
            raise ValueError("待添加配件编号不能重复")
        return items


class BomCopyResult(BaseModel):
    added_part_ids: list[str]
    skipped_part_ids: list[str]
