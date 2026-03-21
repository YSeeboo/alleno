from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from schemas.user import LoginRequest, LoginResponse, UserResponse
from services.auth import authenticate, create_token
from api.deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def api_login(body: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate(db, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="账号/密码错误")
    token = create_token(user.id, user.username, user.is_admin)
    return LoginResponse(token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
def api_me(current_user: User = Depends(get_current_user)):
    return current_user
