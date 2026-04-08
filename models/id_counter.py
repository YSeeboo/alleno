from sqlalchemy import Column, String, Integer
from database import Base


class IdCounter(Base):
    __tablename__ = "id_counter"

    prefix = Column(String, primary_key=True)
    last_number = Column(Integer, nullable=False, default=0)
