from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from schemas.user import UserCreate, UserResponse, UserUpdate
from services.user import create_user, delete_user, get_user, list_users, update_user
from api._errors import service_errors
from api.deps import get_current_user, require_permission

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/", response_model=List[UserResponse], dependencies=[require_permission("users")])
def api_list_users(db: Session = Depends(get_db)):
    return list_users(db)


@router.post("/", response_model=UserResponse, status_code=201, dependencies=[require_permission("users")])
def api_create_user(body: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    with service_errors():
        user = create_user(db, body.model_dump(), calling_user=current_user)
    return user


@router.put("/{user_id}", response_model=UserResponse, dependencies=[require_permission("users")])
def api_update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    with service_errors():
        user = update_user(db, user_id, body.model_dump(exclude_unset=True), calling_user=current_user)
    return user


@router.delete("/{user_id}", status_code=204, dependencies=[require_permission("users")])
def api_delete_user(user_id: int, db: Session = Depends(get_db)):
    with service_errors():
        delete_user(db, user_id)
