from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String

from database import Base
from time_utils import now_beijing


class Part(Base):
    __tablename__ = "part"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    image = Column(String, nullable=True)
    category = Column(String, nullable=True)
    color = Column(String, nullable=True)
    unit = Column(String, nullable=True)
    unit_cost = Column(Numeric(18, 7), nullable=True)
    purchase_cost = Column(Numeric(18, 7), nullable=True)
    bead_cost = Column(Numeric(18, 7), nullable=True)
    plating_cost = Column(Numeric(18, 7), nullable=True)
    plating_process = Column(String, nullable=True)
    assembly_cost = Column(Numeric(18, 7), nullable=True)
    spec = Column(String, nullable=True)
    parent_part_id = Column(String, ForeignKey("part.id"), nullable=True)
    is_composite = Column(Boolean, nullable=False, server_default="false")


class PartCostLog(Base):
    __tablename__ = "part_cost_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    field = Column(String, nullable=False)
    cost_before = Column(Numeric(18, 7), nullable=True)
    cost_after = Column(Numeric(18, 7), nullable=True)
    unit_cost_before = Column(Numeric(18, 7), nullable=True)
    unit_cost_after = Column(Numeric(18, 7), nullable=True)
    source_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
