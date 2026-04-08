from sqlalchemy import Column, String, Numeric, ForeignKey

from database import Base


class PartBom(Base):
    __tablename__ = "part_bom"

    id = Column(String, primary_key=True)
    parent_part_id = Column(String, ForeignKey("part.id"), nullable=False, index=True)
    child_part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty_per_unit = Column(Numeric(10, 4), nullable=False)
