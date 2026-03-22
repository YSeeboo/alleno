from sqlalchemy import Column, Numeric, String

from database import Base


class Jewelry(Base):
    __tablename__ = "jewelry"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    image = Column(String, nullable=True)
    category = Column(String, nullable=True)
    color = Column(String, nullable=True)
    unit = Column(String, nullable=True)
    retail_price = Column(Numeric(10, 3), nullable=True)
    wholesale_price = Column(Numeric(10, 3), nullable=True)
    status = Column(String, nullable=False, default="active")
