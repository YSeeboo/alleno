from sqlalchemy import Column, ForeignKey, Numeric, String

from database import Base


class Bom(Base):
    __tablename__ = "bom"

    id = Column(String, primary_key=True)
    jewelry_id = Column(String, ForeignKey("jewelry.id"), nullable=False)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty_per_unit = Column(Numeric(10, 4), nullable=False)
