from sqlalchemy import Column, Numeric, String

from database import Base


class Part(Base):
    __tablename__ = "part"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    image = Column(String, nullable=True)
    category = Column(String, nullable=True)
    color = Column(String, nullable=True)
    unit = Column(String, nullable=True)
    unit_cost = Column(Numeric(10, 2), nullable=True)
    plating_process = Column(String, nullable=True)
