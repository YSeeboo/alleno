from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from database import Base
from time_utils import now_beijing


class JewelryTemplate(Base):
    __tablename__ = "jewelry_template"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    image = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing)

    items = relationship("JewelryTemplateItem", backref="template",
                         lazy="select", order_by="JewelryTemplateItem.id",
                         cascade="all, delete-orphan")


class JewelryTemplateItem(Base):
    __tablename__ = "jewelry_template_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("jewelry_template.id"), nullable=False)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty_per_unit = Column(Numeric(10, 4), nullable=False)
