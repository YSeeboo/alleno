from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint

from database import Base
from time_utils import now_beijing


class Supplier(Base):
    __tablename__ = "supplier"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # plating / handcraft / parts / customer
    created_at = Column(DateTime, default=now_beijing)

    __table_args__ = (UniqueConstraint("name", "type"),)
