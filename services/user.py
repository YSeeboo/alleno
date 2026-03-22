from __future__ import annotations

from sqlalchemy.orm import Session

from models.user import User
from services.auth import hash_password


def create_user(db: Session, data: dict, *, calling_user: User | None = None) -> User:
    existing = db.query(User).filter(User.username == data["username"]).first()
    if existing:
        raise ValueError(f"用户名 {data['username']} 已存在")

    is_admin = data.get("is_admin", False)
    if is_admin and (calling_user is None or not calling_user.is_admin):
        raise ValueError("只有管理员才能创建管理员用户")

    user = User(
        username=data["username"],
        password_hash=hash_password(data["password"]),
        owner=data["owner"],
        permissions=data.get("permissions", []),
        is_admin=is_admin,
    )
    db.add(user)
    db.flush()
    return user


def list_users(db: Session) -> list[User]:
    return db.query(User).filter(User.is_active == True).all()


def get_user(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


def update_user(db: Session, user_id: int, data: dict, *, calling_user: User | None = None) -> User:
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if user is None:
        raise ValueError("用户不存在")

    # Only admins can modify admin users
    if user.is_admin and (calling_user is None or not calling_user.is_admin):
        raise ValueError("只有管理员才能修改管理员账户")

    # Protect admin users: cannot change their permissions or is_admin status (even by themselves)
    if user.is_admin:
        data.pop("permissions", None)
        data.pop("is_admin", None)

    # Only admins can grant is_admin to others
    if "is_admin" in data and data["is_admin"] and (calling_user is None or not calling_user.is_admin):
        raise ValueError("只有管理员才能授予管理员权限")

    password = data.pop("password", None)
    if password:
        user.password_hash = hash_password(password)

    for key, value in data.items():
        if value is not None:
            setattr(user, key, value)

    db.flush()
    return user


def delete_user(db: Session, user_id: int) -> None:
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if user is None:
        raise ValueError("用户不存在")
    if user.is_admin:
        raise ValueError("不能删除管理员用户")

    user.is_active = False
    db.flush()
