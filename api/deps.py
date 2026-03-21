from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from services.auth import decode_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")

    token = auth_header[7:]
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    user = db.query(User).filter(User.id == payload["user_id"], User.is_active == True).first()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    return user


def require_permission(perm_key: str):
    def dependency(current_user: User = Depends(get_current_user)):
        if current_user.is_admin:
            return current_user
        if perm_key not in (current_user.permissions or []):
            raise HTTPException(status_code=403, detail=f"无 {perm_key} 权限")
        return current_user

    return Depends(dependency)
