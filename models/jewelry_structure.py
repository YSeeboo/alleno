from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base
from time_utils import now_beijing


class JewelryStructure(Base):
    __tablename__ = "jewelry_structure"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    note = Column(String, nullable=False, default="")
    category = Column(String, nullable=False)
    unit = Column(String, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    # Stable slot keys intentionally survive renames. Deleted keys remain in
    # schemes until explicitly repaired, rather than cascading away silently.
    slots = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=now_beijing)
    schemes = relationship("JewelryStructureScheme", cascade="all, delete-orphan",
                           order_by="JewelryStructureScheme.id")


class JewelryStructureScheme(Base):
    __tablename__ = "jewelry_structure_scheme"

    id = Column(Integer, primary_key=True)
    structure_id = Column(Integer, ForeignKey("jewelry_structure.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    overrides = Column(JSON, nullable=False)


class JewelryStructureBatch(Base):
    __tablename__ = "jewelry_structure_batch"
    __table_args__ = (UniqueConstraint("user_id", "request_key", name="uq_structure_batch_request"),)

    id = Column(Integer, primary_key=True)
    # Historical provenance is deliberately not a live FK to jewelry, structure
    # or user: deleting those must not mutate the saved creation result.
    user_id = Column(Integer, nullable=False)
    request_key = Column(String(80), nullable=False)
    payload_digest = Column(String(64), nullable=False)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=now_beijing)
