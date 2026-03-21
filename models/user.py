from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String

from database import Base
from time_utils import now_beijing


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    owner = Column(String, nullable=False)
    permissions = Column(JSON, default=[])
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=False, default=now_beijing)
