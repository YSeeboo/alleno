from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator
from schemas.jewelry_options import JewelryCategory, JewelryUnit

Qty = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=4)]
Price = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=7)]
Key = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")]
Name = Annotated[str, Field(min_length=1, max_length=120)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Slot(Input):
    key: Key
    name: Name
    part_id: str | None = None
    qty: Qty = Decimal(1)
    selectable: bool = False


class Override(Input):
    part_id: str | None = None
    qty: Qty | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set or ("qty" in self.model_fields_set and self.qty is None):
            raise ValueError("覆盖设置不能为空，用量不能为 null")
        return self


class StructureWrite(Input):
    name: Name
    note: str = Field(default="", max_length=2000)
    category: JewelryCategory
    unit: JewelryUnit
    slots: list[Slot] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_keys(self):
        if len({s.key for s in self.slots}) != len(self.slots):
            raise ValueError("组成位置标识不能重复")
        return self


class StructureUpdate(StructureWrite):
    revision: int = Field(ge=1)


class SchemeWrite(Input):
    name: Name
    structure_revision: int = Field(ge=1)
    overrides: dict[Key, Override] = Field(default_factory=dict, max_length=100)


class BatchRow(Input):
    key: Key
    name: Name
    scheme_id: int | None = Field(default=None, ge=1)
    selections: dict[Key, str] = Field(default_factory=dict, max_length=100)
    overrides: dict[Key, Override] = Field(default_factory=dict, max_length=100)
    removed_keys: list[Key] = Field(default_factory=list, max_length=100)
    extras: list[Slot] = Field(default_factory=list, max_length=100)
    color: str | None = Field(default=None, max_length=120)
    image: str | None = Field(default=None, max_length=2000)
    retail_price: Price | None = None
    wholesale_price: Price | None = None
    handcraft_cost: Price | None = None


class BatchInput(Input):
    structure_id: int = Field(ge=1)
    structure_revision: int = Field(ge=1)
    draft: StructureWrite | None = None
    default_scheme_id: int | None = Field(default=None, ge=1)
    rows: list[BatchRow] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_rows(self):
        if len({r.key for r in self.rows}) != len(self.rows):
            raise ValueError("饰品行标识不能重复")
        return self


class BatchConfirm(Input):
    request_key: Key = Field(min_length=12)
    preview_token: str = Field(min_length=1, max_length=4000)
    batch: BatchInput
