from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    username: str
    password: str
    owner: str
    permissions: list[str] = []
    is_admin: bool = False


class UserUpdate(BaseModel):
    password: Optional[str] = None
    owner: Optional[str] = None
    permissions: Optional[list[str]] = None
    is_admin: Optional[bool] = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    owner: str
    permissions: list[str]
    is_admin: bool
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: UserResponse
